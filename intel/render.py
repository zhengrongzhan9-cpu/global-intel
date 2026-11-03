from __future__ import annotations

from .util import now_local

LIMIT = 3400


def _score_tag(score: float) -> str:
    if score >= 8:
        return "🔴"
    if score >= 6:
        return "🟠"
    return "⚪"


def _impact_line(impact: dict) -> str:
    parts = []
    for key, label in (("countries", "国家"), ("sectors", "行业"), ("markets", "市场")):
        values = impact.get(key) or []
        if values:
            parts.append(f"{label} {'/'.join(values)}")
    return "影响：" + "｜".join(parts) if parts else ""


def event_block(cluster, brief: dict, score: float) -> str:
    when = cluster.latest_pub or cluster.last_at
    clock = when.strftime("%m-%d %H:%M") if when else ""
    sources = " / ".join(cluster.sources[:3]) or "未知来源"
    lines = [f"{_score_tag(score)} {score:.1f}｜{brief.get('title_zh') or cluster.title}"]
    lines.append(f"{sources} · {clock}")
    if brief.get("summary"):
        lines.append(f"摘要：{brief['summary']}")
    if brief.get("background"):
        lines.append(f"背景：{brief['background']}")
    impact = _impact_line(brief.get("impact") or {})
    if impact:
        lines.append(impact)
    if brief.get("unverified"):
        lines.append(f"存疑：{brief['unverified']}（可信度{brief.get('credibility', '中')}）")
    if cluster.url:
        lines.append(cluster.url)
    return "\n".join(lines)


def _pack(title: str, blocks, footer: str = "", limit: int = LIMIT):
    messages = []
    body = []
    size = len(title.encode("utf-8")) + 64

    def flush():
        nonlocal body, size
        if not body:
            return
        text = "\n\n".join(body)
        if footer:
            text = text + "\n\n" + footer
        messages.append((title, text))
        body = []
        size = len(title.encode("utf-8")) + 64

    for block in blocks:
        length = len(block.encode("utf-8")) + 2
        if body and size + length > limit:
            flush()
        body.append(block)
        size += length
    flush() if body else None

    if not messages:
        messages.append((title, footer or "本次无新增重要信息。"))

    if len(messages) > 1:
        total = len(messages)
        messages = [
            (f"{title} ({i}/{total})", text) for i, (_, text) in enumerate(messages, 1)
        ]
    return messages


def hourly_messages(entries, headline_items, stats: dict):
    now = now_local()
    title = f"🌍 全球情报 · {now.strftime('%m-%d %H:%M')}"
    head = f"新增 {stats.get('new', 0)} 条，重要 {len(entries)} 条"
    blocks = [head]
    for cluster, brief, score in entries:
        blocks.append(event_block(cluster, brief, score))
    if headline_items:
        lines = ["📌 其他值得留意"]
        for item in headline_items:
            lines.append(f"· {item['title'][:80]}（{item['source_name']}）")
        blocks.append("\n".join(lines))
    footer = "回复「暂停」可停止推送 · 数据为公开来源，不构成投资建议"
    return _pack(title, blocks, footer)


def digest_messages(kind: str, entries, overview: str, wm_note: str, stats: dict):
    now = now_local()
    if kind == "morning":
        title = f"☀️ 全球晨报 · {now.strftime('%m-%d')}"
        head = f"过去 24 小时重点 {len(entries)} 条"
    else:
        title = f"🌙 当日汇总 · {now.strftime('%m-%d')}"
        head = f"今日重点 {len(entries)} 条"

    blocks = [head]
    if overview:
        blocks.append("🧭 今日主线\n" + overview)
    if wm_note:
        blocks.append("🛰 World Monitor\n" + wm_note)

    grouped = {}
    for cluster, brief, score in entries:
        grouped.setdefault(brief.get("category", "综合"), []).append((cluster, brief, score))

    order = ["地缘政治", "全球市场", "宏观政策", "贸易供应链", "中国经济", "科技能源", "综合"]
    for category in order:
        items = grouped.get(category)
        if not items:
            continue
        blocks.append(f"【{category}】")
        for cluster, brief, score in items:
            blocks.append(event_block(cluster, brief, score))

    footer = f"扫描 {stats.get('new', 0)} 条新增 · 公开信息，不构成投资建议"
    return _pack(title, blocks, footer)


def render_text(entries, stats: dict) -> str:
    """dry-run 时输出到文件的可读文本。"""
    parts = [f"# 全球情报预览 {now_local().strftime('%Y-%m-%d %H:%M')} KL", ""]
    parts.append(f"新增 {stats.get('new', 0)} 条，入选 {len(entries)} 条")
    for cluster, brief, score in entries:
        parts.append("")
        parts.append(event_block(cluster, brief, score))
    return "\n".join(parts)