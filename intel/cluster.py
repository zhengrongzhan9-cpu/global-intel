from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from .util import canon_url, norm_title, similarity, strip_html, tz

TIER3 = {
    "ft-world",
    "nikkei-asia",
    "scmp-china",
    "bbc-world",
    "aljazeera",
    "fed-press",
    "boj",
    "crisisgroup",
    "eia",
}

SEVERITY = (
    "war",
    "airstrike",
    "air strike",
    "missile",
    "invasion",
    "nuclear",
    "coup",
    "sanction",
    "blockade",
    "战争",
    "空袭",
    "导弹",
    "入侵",
    "核武",
    "政变",
    "制裁",
    "封锁",
    "断交",
    "冲突升级",
    "停火破裂",
)

SHOCK = (
    "plunge",
    "crash",
    "slump",
    "default",
    "暴跌",
    "崩盘",
    "熔断",
    "违约",
    "闪崩",
    "暴涨",
    "飙升",
)

POLICY = ("fed", "fomc", "ecb", "boj", "pboc", "美联储", "央行", "货币政策")
RATE = ("rate cut", "rate hike", "降息", "加息", "降准", "利率决议")

MERGE_THRESHOLD = 0.55

COUNTRIES = {
    "iran", "iraq", "israel", "gaza", "russia", "ukraine", "china", "taiwan",
    "japan", "korea", "saudi", "turkey", "india", "germany", "france", "britain",
    "uk", "pakistan", "syria", "lebanon", "yemen", "egypt", "venezuela", "mexico",
}

ACTIONS = {
    "strike", "strikes", "struck", "attack", "attacks", "airstrike", "airstrikes",
    "invasion", "invade", "invades", "sanction", "sanctions", "war", "ceasefire",
    "missile", "missiles", "nuclear", "coup", "blockade", "tariff", "tariffs",
}


@dataclass
class Cluster:
    items: list = field(default_factory=list)
    urls: set = field(default_factory=set)
    title: str = ""
    norm: str = ""
    url: str = ""
    key: str = ""
    sources: list = field(default_factory=list)
    first_at: datetime | None = None
    last_at: datetime | None = None
    latest_pub: datetime | None = None
    rule_score: float = 0.0
    summary: str = ""


def _tokens(title: str):
    text = unicodedata.normalize("NFKC", title or "").lower().replace("\u2019", "'")
    out = set()
    for token in re.split(r"[^a-z0-9']+", text):
        token = token.strip("'")
        if token.endswith("'s"):
            token = token[:-2]
        if len(token) > 2:
            out.add(token)
    return out


def _grams(norm: str):
    if len(norm) < 2:
        return {norm}
    return {norm[i : i + 2] for i in range(len(norm) - 1)}


def _overlap(a, b) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sim(item, cluster) -> float:
    a, b = item["norm"], cluster.norm
    ratio = similarity(a, b)
    if ratio >= 0.72:
        return ratio
    shared = item["tokens"] & cluster.tokens
    if (shared & COUNTRIES) and (shared & ACTIONS):
        return max(ratio, 0.72)
    best = ratio
    best = max(best, _overlap(item["tokens"], cluster.tokens) * 0.95)
    best = max(best, _overlap(item["grams"], cluster.grams))
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 12 and short in long and len(short) >= len(long) * 0.55:
        best = max(best, 0.75)
    return best


def build_clusters(items, threshold: float = MERGE_THRESHOLD) -> list[Cluster]:
    prepared = []
    for item in items:
        title = (item.get("title") or "").strip()
        norm = norm_title(title)
        if len(norm) < 8:
            continue
        copy = dict(item)
        copy["norm"] = norm
        copy["curl"] = canon_url(item.get("url") or "")
        copy["tokens"] = _tokens(title)
        copy["grams"] = _grams(norm)
        prepared.append(copy)

    prepared.sort(key=lambda x: x.get("crawl_at") or datetime.min.replace(tzinfo=tz()))

    clusters: list[Cluster] = []
    for item in prepared:
        target = None
        for cluster in clusters:
            if item["curl"] and item["curl"] in cluster.urls:
                target = cluster
                break
            if _sim(item, cluster) >= threshold:
                target = cluster
                break
        if target is None:
            cluster = Cluster(items=[item], urls={item["curl"]} if item["curl"] else set())
            cluster.title = item["title"]
            cluster.norm = item["norm"]
            cluster.tokens = item["tokens"]
            cluster.grams = item["grams"]
            cluster.url = item.get("url") or ""
            clusters.append(cluster)
        else:
            target.items.append(item)
            if item["curl"]:
                target.urls.add(item["curl"])
            if len(item["title"]) > len(target.title):
                target.title = item["title"]
                target.norm = item["norm"]
                target.tokens = item["tokens"]
                target.grams = item["grams"]
                target.url = item.get("url") or target.url

    for cluster in clusters:
        _finalize(cluster)
    return clusters


def _finalize(cluster: Cluster):
    seen = set()
    sources = []
    for item in cluster.items:
        sid = item.get("source_id") or item.get("source_name") or "unknown"
        if sid not in seen:
            seen.add(sid)
            sources.append(item.get("source_name") or sid)
    cluster.sources = sources

    times = [i["crawl_at"] for i in cluster.items if i.get("crawl_at")]
    if times:
        cluster.first_at = min(times)
        cluster.last_at = max(times)
    pubs = [i["published_at"] for i in cluster.items if i.get("published_at")]
    cluster.latest_pub = max(pubs) if pubs else cluster.last_at

    cluster.summary = ""
    for item in cluster.items:
        if item.get("summary"):
            cluster.summary = strip_html(item["summary"])[:300]
            break

    cluster.key = hashlib.sha1(cluster.norm.encode("utf-8")).hexdigest()[:16]
    cluster.rule_score = score_rules(cluster)


def score_rules(cluster: Cluster) -> float:
    score = 0.0
    count = len(cluster.sources)
    if count >= 3:
        score += 2.5
    elif count == 2:
        score += 1.5

    tiers = []
    for item in cluster.items:
        sid = item.get("source_id") or ""
        if sid in TIER3:
            tiers.append(3)
        elif item.get("kind") == "hotlist":
            tiers.append(1)
        else:
            tiers.append(2)
    if tiers and max(tiers) >= 3:
        score += 1.5

    text = (cluster.title + " " + cluster.summary).lower()
    severity = sum(1 for word in SEVERITY if word in text)
    score += min(2.0, severity * 0.6)
    if any(word in text for word in SHOCK):
        score += 1.0
    if any(word in text for word in POLICY) and any(word in text for word in RATE):
        score += 0.5

    return round(min(7.0, score), 2)


def cluster_urls(cluster: Cluster):
    return [url for url in cluster.urls if url]

def merge_clusters(clusters) -> Cluster:
    """把多个字面聚类合并为一个事件（用于 LLM 语义去重）。"""
    items, urls, sources = [], set(), []
    for cluster in clusters:
        items.extend(cluster.items)
        urls |= set(cluster.urls)
        for name in cluster.sources:
            if name not in sources:
                sources.append(name)
    rep = max(items, key=lambda item: len(item.get("title") or ""))
    merged = Cluster(items=items, urls=urls)
    merged.title = rep.get("title") or ""
    merged.norm = rep.get("norm") or norm_title(merged.title)
    merged.url = rep.get("url") or ""
    merged.sources = sources
    times = [item["crawl_at"] for item in items if item.get("crawl_at")]
    if times:
        merged.first_at = min(times)
        merged.last_at = max(times)
    pubs = [item["published_at"] for item in items if item.get("published_at")]
    merged.latest_pub = max(pubs) if pubs else merged.last_at
    merged.summary = ""
    for item in items:
        if item.get("summary"):
            merged.summary = strip_html(item["summary"])[:300]
            break
    merged.key = hashlib.sha1(
        "|".join(sorted(cluster.key for cluster in clusters)).encode("utf-8")
    ).hexdigest()[:16]
    merged.rule_score = score_rules(merged)
    return merged

