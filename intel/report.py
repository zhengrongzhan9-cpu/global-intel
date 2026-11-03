from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

CSS = """
:root{--bg:#0f1419;--card:#171e26;--line:#24303c;--text:#e6edf3;--muted:#9aa7b4;--accent:#4ea1ff;--hot:#ff6b6b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 60px}
header{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:20px}
h1{font-size:22px;margin:0 0 6px}
.meta{color:var(--muted);font-size:13px}
.overview{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:18px 0}
.overview h2{font-size:15px;margin:0 0 8px;color:var(--accent)}
.overview div{font-size:14px;margin:4px 0}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0}
article.deep{border-color:#3b5b7a;box-shadow:0 0 0 1px rgba(78,161,255,.15)}
h2.title{font-size:17px;margin:0 0 8px;line-height:1.4}
.badge{display:inline-block;font-size:11px;padding:2px 7px;border-radius:6px;background:#22303d;color:var(--muted);margin-right:6px}
.badge.hot{background:#3a1f24;color:var(--hot)}
.badge.deep{background:#1d3550;color:var(--accent)}
.field{margin:8px 0;font-size:14.5px}
.field b{color:var(--muted);font-weight:600;margin-right:4px}
.src{font-size:12.5px;color:var(--muted);margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
.src a{color:var(--accent);text-decoration:none;word-break:break-all}
.deepbox{margin-top:12px;padding:12px 14px;background:#101a24;border-left:3px solid var(--accent);border-radius:6px;font-size:14.5px}
footer{margin-top:28px;color:var(--muted);font-size:12.5px;text-align:center}
ul.plain{margin:6px 0;padding-left:18px}
ul.plain li{margin:3px 0;font-size:14px}
"""


def _e(text) -> str:
    return html.escape(str(text or ""), quote=True)


def _fmt_time(cluster) -> str:
    when = cluster.latest_pub or cluster.last_at
    return when.strftime("%m-%d %H:%M") if when else ""


def _sources(cluster, limit: int = 6) -> str:
    seen = set()
    parts = []
    for item in cluster.items:
        sid = item.get("source_id") or item.get("source_name")
        if sid in seen:
            continue
        seen.add(sid)
        name = _e(item.get("source_name") or sid)
        url = item.get("url") or ""
        published = item.get("published_at")
        stamp = published.strftime("%m-%d %H:%M") if published else ""
        label = f"{name} · {stamp}" if stamp else name
        if url:
            parts.append(f'<a href="{_e(url)}" target="_blank" rel="noopener">{label}</a>')
        else:
            parts.append(label)
        if len(parts) >= limit:
            break
    return " ｜ ".join(parts)


def _impact(brief) -> str:
    impact = brief.get("impact") or {}
    parts = []
    for key, label in (("countries", "国家"), ("sectors", "行业"), ("markets", "市场")):
        values = impact.get(key) or []
        if values:
            parts.append(f"{label} {'/'.join(values)}")
    return "｜".join(parts)


def _article(cluster, brief, score, index, deep: bool) -> str:
    chips = [f'<span class="badge {"hot" if score >= 8 else ""}">{score:.1f}</span>']
    if brief.get("category"):
        chips.append(f'<span class="badge">{_e(brief["category"])}</span>')
    if deep:
        chips.append('<span class="badge deep">深度</span>')
    if brief.get("_update"):
        chips.append('<span class="badge hot">新进展</span>')

    blocks = [
        f'<article class="{"deep" if deep else ""}" id="e{index}">',
        f'<h2 class="title">{"".join(chips)} {_e(brief.get("title_zh") or cluster.title)}</h2>',
    ]
    if brief.get("summary"):
        blocks.append(f'<div class="field"><b>事实</b>{_e(brief["summary"])}</div>')
    if brief.get("background"):
        blocks.append(f'<div class="field"><b>背景</b>{_e(brief["background"])}</div>')
    interests = brief.get("interests") or []
    if interests:
        items = "".join(f"<li>{_e(v)}</li>" for v in interests)
        blocks.append(f'<div class="field"><b>国家与利益</b><ul class="plain">{items}</ul></div>')
    impact = _impact(brief)
    if impact:
        blocks.append(f'<div class="field"><b>影响</b>{_e(impact)}</div>')
    if brief.get("unverified"):
        blocks.append(
            f'<div class="field"><b>存疑</b>{_e(brief["unverified"])}（可信度{_e(brief.get("credibility", "中"))}）</div>'
        )
    if brief.get("deep_dive"):
        blocks.append(f'<div class="deepbox"><b>深度分析</b><br>{_e(brief["deep_dive"])}</div>')
    blocks.append(f'<div class="src">{_fmt_time(cluster)} KL ｜ {_sources(cluster)}</div>')
    blocks.append("</article>")
    return "\n".join(blocks)


def render_digest(kind: str, day: str, generated_at: str, entries, overview: str, wm_note: str, stats: dict) -> str:
    label = "全球晨报" if kind == "morning" else "当日汇总"
    title = f"{label} · {day}"
    blocks = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{_e(title)}</title><style>{CSS}</style></head><body><div class=\"wrap\">",
        "<header>",
        f"<h1>{_e(label)} · {_e(day)}</h1>",
        f'<div class="meta">生成于 {_e(generated_at)} KL ｜ 入选 {len(entries)} 件 ｜ 扫描 {stats.get("new", 0)} 条新增</div>',
        "</header>",
    ]
    if overview:
        lines = "".join(f"<div>{_e(line)}</div>" for line in overview.splitlines() if line.strip())
        blocks.append(f'<section class="overview"><h2>今日主线</h2>{lines}</section>')
    if wm_note:
        lines = "".join(f"<div>{_e(line)}</div>" for line in wm_note.splitlines() if line.strip())
        blocks.append(f'<section class="overview"><h2>World Monitor</h2>{lines}</section>')

    for index, (cluster, brief, score) in enumerate(entries, 1):
        blocks.append(_article(cluster, brief, score, index, deep=index <= 3 and bool(brief.get("deep_dive"))))

    blocks.append(
        '<footer>公开信息聚合，仅供研究参考，不构成投资建议。<br>'
        f'<a href="../index.html" style="color:#4ea1ff">全部简报</a></footer>'
    )
    blocks.append("</div></body></html>")
    return "\n".join(blocks)


def write_digest(repo_root: Path, day: str, kind: str, html_text: str) -> Path:
    folder = Path(repo_root) / "docs" / "digests"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day}-{kind}.html"
    path.write_text(html_text, encoding="utf-8")
    return path


def write_index(repo_root: Path) -> Path:
    folder = Path(repo_root) / "docs" / "digests"
    folder.mkdir(parents=True, exist_ok=True)
    files = sorted(folder.glob("*.html"), reverse=True)[:60]
    rows = []
    for path in files:
        name = path.stem
        parts = name.split("-")
        day = "-".join(parts[:3]) if len(parts) >= 4 else name
        kind = "晨报" if name.endswith("morning") else "晚报"
        rows.append(f'<li><a href="digests/{_e(path.name)}">{_e(day)} {kind}</a></li>')
    items = "\n".join(rows) or "<li>暂无简报</li>"
    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全球情报简报</title><style>{CSS}</style></head>
<body><div class="wrap"><header><h1>全球情报简报</h1>
<div class="meta">全球金融 · 政治 · 地缘战略</div></header>
<ul class="plain">{items}</ul>
<footer>公开信息聚合，不构成投资建议。</footer></div></body></html>"""
    path = Path(repo_root) / "docs" / "index.html"
    path.write_text(body, encoding="utf-8")
    return path