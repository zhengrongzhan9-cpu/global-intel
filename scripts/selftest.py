from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intel.bark import Bark
from intel.cluster import build_clusters, merge_clusters
from intel.llm import _events_payload, clean_brief, fallback_brief
from intel.render import digest_messages, hourly_messages
from intel.run import _duplicate_selected, _is_major_update
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



def test_major_update():
    class C:
        key = "k"
        urls = {"https://a"}

    prev = {"key": "k", "urls": {"https://a"}, "score": 5.0}
    assert _is_major_update(C(), 4.0, prev) is False
    assert _is_major_update(C(), 6.2, prev) is True

    class C2:
        key = "k2"
        urls = {"https://a", "https://b"}

    assert _is_major_update(C2(), 5.0, prev) is True


def test_intra_digest_dedup():
    class C:
        def __init__(self, key, url, norm):
            self.key, self.urls, self.norm = key, {url}, norm

    first = C("a", "https://a", "iranstrikesqeshm")
    second = C("b", "https://b", "iranstrikesqeshmisland")
    brief = {"title_zh": "美媒称美军打击伊朗格什姆岛"}
    selected = [[first, brief, 8.0]]
    assert _duplicate_selected(second, brief, selected) is True
    other = C("c", "https://c", "europecoldstoragecyberattack")
    assert _duplicate_selected(other, {"title_zh": "欧洲冷柜网络攻击"}, selected) is False


def test_digest_message():
    class C:
        key = "k"
        title = "标题"
        sources = ["BBC World"]
        urls = {"https://x"}
        latest_pub = None
        last_at = None
        items = []

    brief = {"title_zh": "测试标题", "summary": "一句摘要。"}
    messages = digest_messages("morning", [[C(), brief, 8.0]], "", "", {"new": 1}, "https://example.com/d.html")
    assert messages and "https://example.com/d.html" in messages[0][1]
    assert len(messages[0][1].encode("utf-8")) < 3400



def test_bark_payload():
    """Bark 的 markdown 字段会覆盖 body，必须确保不再发送该字段。"""
    import intel.bark as bark_mod

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b'{"code":200}'
        text = '{"code":200}'

        def json(self):
            return {"code": 200}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    original = bark_mod.requests.post
    bark_mod.requests.post = fake_post
    try:
        ok = Bark("https://api.day.app/abc123").send(
            "测试标题", "完整中文正文\n第二行链接 https://example.com", "active"
        )
    finally:
        bark_mod.requests.post = original

    assert ok is True
    payload = captured["json"]
    assert "markdown" not in payload, payload
    assert payload["body"] == "完整中文正文\n第二行链接 https://example.com"
    assert payload["title"] == "测试标题"
    assert payload["group"] == "GlobalIntel"



def test_events_payload():
    assert _events_payload({"events": [1]}) == {"events": [1]}
    assert _events_payload([{"id": 1}]) == {"events": [{"id": 1}]}
    assert _events_payload(None) is None
    assert _events_payload({"foo": 1}) is None


def main():
    tests = [test_url, test_title, test_cluster, test_brief, test_fallback, test_render, test_bark_parse,
             test_major_update, test_intra_digest_dedup, test_digest_message, test_bark_payload, test_events_payload]
    for test in tests:
        test()
        print(f"OK {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()