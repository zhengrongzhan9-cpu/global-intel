from __future__ import annotations

import difflib
import html
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TZ_NAME = "Asia/Kuala_Lumpur"


def tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(TZ_NAME)
    except Exception:
        return timezone(timedelta(hours=8))


def now_local() -> datetime:
    return datetime.now(tz())


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def norm_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title or "").lower()
    text = re.sub(r"^\s*(breaking|update|exclusive|live|just in)\s*[:：]\s*", "", text)
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text[:300]


def canon_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except Exception:
        return url.lower()
    if not parts.netloc:
        return url.lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(("utm_", "spm", "from", "ref", "share", "fbclid"))
    ]
    return urlunsplit(
        (parts.scheme.lower() or "https", host, parts.path.rstrip("/"), urlencode(sorted(query)), "")
    )


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) < len(b):
        a, b = b, a
    if len(b) < len(a) * 0.55:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def parse_dt(value):
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def to_local(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz())
    return dt.astimezone(tz())


def extract_json(text):
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
        try:
            from json_repair import repair_json

            fixed = repair_json(candidate, return_objects=True)
            if isinstance(fixed, (dict, list)):
                return fixed
        except Exception:
            pass
    return None


def human_delta(dt, ref=None) -> str:
    if dt is None:
        return ""
    ref = ref or now_local()
    minutes = int((ref - dt).total_seconds() // 60)
    if minutes < 1:
        return "刚刚"
    if minutes < 60:
        return f"{minutes}分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}小时前"
    return f"{hours // 24}天前"


def parse_utc(value):
    """RSS 的 published_at 为 UTC 且常无时区后缀，按 UTC 解释后转本地时区。"""
    dt = parse_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return to_local(dt)
