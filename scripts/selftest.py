from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel.bark import Bark
from intel.cluster import build_clusters, merge_clusters
from intel.llm import clean_brief, fallback_brief
from intel.render import hourly_messages
from intel.util import canon_url, norm_title, similarity


def make_item(title, source="BBC World", sid="bbc-world", kind="rss", url="", summary=""):
    return {
        "uid": title[:8],
        "kind": kind,
        "title": title,
        "source_id": sid,
        "source_name": source,
        "rank": 1,
        "url": url or f"https://example.com/{abs(hash(title))}",
        "summary": summary,
        "published_at": None,
        "crawl_at": None,
    }


def test_url():
    assert canon_url("https://www.reuters.com/x/?utm_source=a") == "https://reuters.com/x"
    assert canon_url("http://Example.com/a/#frag") == "http://example.com/a"


def test_title():
    assert norm_title("Breaking: Hello, WORLD!") == "helloworld"


def test_cluster():
    items = [
        make_item("Israel strikes Gaza school, dozens reported killed"),
        make_item("Israel strikes Gaza school, dozens reported killed", source="Al Jazeera", sid="aljazeera"),
        make_item("Oil prices fall after Iran signals talks"),
    ]
    clusters = build_clusters(items)
    assert len(clusters) == 2, len(clusters)
    merged = merge_clusters([clusters[0]])
    assert len(merged.sources) == 2, merged.sources


def test_brief():
    cluster = build_clusters([make_item("Fed cuts rates by 25bp")])[0]
    raw = {
        "ids": [1],
        "title_zh": "美联储降息25个基点",
        "summary": "美联储宣布降息25个基点。" * 20,
        "background": "（判断）通胀回落为降息提供空间。",
        "impact": {"countries": ["美国"], "sectors": ["银行"], "markets": ["美股", "美债"]},
        "unverified": "暂无未证实信息",
        "credibility": "high",
        "importance": 9,
        "category": "宏观政策",
    }
    brief = clean_brief(raw, cluster)
    assert brief["importance"] == 9
    assert brief["credibility"] == "高"
    assert len(brief["summary"]) <= 110
    assert brief["category"] == "宏观政策"


def test_fallback():
    cluster = build_clusters([make_item("Some headline about tariffs")])[0]
    brief = fallback_brief(cluster)
    assert brief["_fallback"] is True


def test_render():
    cluster = build_clusters([make_item("标题" * 30)])[0]
    brief = fallback_brief(cluster)
    messages = hourly_messages([[cluster, brief, 9.0]], [], {"new": 1})
    assert messages
    for _, body in messages:
        assert len(body.encode("utf-8")) <= 3600, len(body.encode("utf-8"))


def test_bark_parse():
    assert Bark("https://api.day.app/abc123").key == "abc123"
    assert Bark("abc123").server == "https://api.day.app"
    assert Bark("https://bark.example.com/xyz/").key == "xyz"


def main():
    tests = [test_url, test_title, test_cluster, test_brief, test_fallback, test_render, test_bark_parse]
    for test in tests:
        test()
        print(f"OK {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()