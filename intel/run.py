from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .bark import Bark
from .cluster import build_clusters, cluster_urls, merge_clusters
from .config import load
from .crawl import run_crawler
from .llm import LLM, fallback_brief
from .relevance import is_relevant
from .render import digest_messages, hourly_messages, render_text
from .store import Ledger, Store
from .util import now_local, tz
from .wm import WorldMonitor

log = logging.getLogger("intel")


def setup_logging(data_dir: str):
    Path(data_dir, "logs").mkdir(parents=True, exist_ok=True)
    stamp = now_local().strftime("%Y%m%d-%H%M%S")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)
    file_handler = logging.FileHandler(Path(data_dir, "logs", f"run-{stamp}.log"), encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def resolve_mode(requested: str, now: datetime, ledger: Ledger, day: str) -> str:
    if requested != "auto":
        return requested
    if 8 <= now.hour < 11 and not ledger.digest_sent(day, "morning"):
        return "morning"
    if 20 <= now.hour < 23 and not ledger.digest_sent(day, "evening"):
        return "evening"
    return "hourly"


def window_start(mode: str, now: datetime, hours: float | None = None) -> datetime:
    if hours:
        return now - timedelta(hours=hours)
    if mode == "morning":
        return now - timedelta(hours=26)
    if mode == "evening":
        return datetime(now.year, now.month, now.day, tzinfo=tz())
    return now - timedelta(minutes=80)


def final_score(cluster, brief) -> float:
    rule = cluster.rule_score
    if brief.get("_fallback"):
        return round(rule / 7 * 10, 1)
    try:
        importance = float(brief.get("importance", 0))
    except Exception:
        importance = 0.0
    return round(0.25 * (rule / 7 * 10) + 0.75 * importance, 1)


def build_parser():
    parser = argparse.ArgumentParser(prog="intel.run", description="全球情报分析推送")
    parser.add_argument("--mode", default="auto", choices=["auto", "hourly", "morning", "evening"])
    parser.add_argument("--no-crawl", action="store_true", help="跳过 TrendRadar 采集")
    parser.add_argument("--dry-run", action="store_true", help="只渲染到 data/outbox，不推送")
    parser.add_argument("--test-push", action="store_true", help="发送一条 Bark 测试消息")
    parser.add_argument("--hours", type=float, default=None, help="自定义回看窗口（小时）")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load()
    setup_logging(cfg.data_dir)
    now = now_local()
    day = now.strftime("%Y-%m-%d")
    log.info("=== intel 启动 %s KL mode=%s ===", now.strftime("%Y-%m-%d %H:%M:%S"), args.mode)

    if args.test_push:
        bark = Bark(cfg.bark_url, cfg.bark_group)
        if not bark.configured:
            log.error("BARK_URL 未配置，无法测试")
            return 2
        body = (
            "推送链路测试成功\n"
            f"时间：{now.strftime('%Y-%m-%d %H:%M:%S')} KL\n"
            "时区：Asia/Kuala_Lumpur\n"
            f"主机：{Path.cwd()}"
        )
        ok = bark.send("✅ 全球情报推送测试", body, "timeSensitive")
        return 0 if ok else 1

    if not args.no_crawl:
        ok, tail = run_crawler(cfg.repo_root, cfg.crawl_timeout, cfg.crawl_retries)
        if tail:
            log.info("采集日志尾部：\n%s", tail)
        if not ok:
            log.error("采集最终失败，将使用既有数据继续")

    ledger = Ledger(str(Path(cfg.data_dir, "state.db")))
    mode = resolve_mode(args.mode, now, ledger, day)
    log.info("运行模式：%s", mode)

    if mode in ("morning", "evening") and ledger.digest_sent(day, mode):
        log.info("今日 %s 已发送，跳过", mode)
        return 0

    since = window_start(mode, now, args.hours)
    raw_items = Store(cfg.output_dir).items_since(since, since - timedelta(hours=12))
    items = [item for item in raw_items if is_relevant(item)]
    log.info(
        "读取新增 %s 条，相关性过滤后 %s 条（since %s）",
        len(raw_items),
        len(items),
        since.strftime("%m-%d %H:%M"),
    )
    if not items:
        log.info("窗口内无相关新增，结束")
        return 0

    clusters = build_clusters(items)
    if mode == "hourly":
        fresh = [c for c in clusters if not ledger.is_pushed(c.key, cluster_urls(c))]
    else:
        # 早晚报是当日全景汇总，允许包含已在小时推送中出现过的事件
        fresh = list(clusters)
    fresh.sort(key=lambda c: c.rule_score, reverse=True)
    candidates = fresh[: cfg.max_candidates]
    log.info("聚合为 %s 个事件，待分析 %s 个", len(clusters), len(candidates))
    if not candidates:
        log.info("没有未推送过的事件，结束")
        return 0

    max_calls = cfg.llm_max_calls if mode == "hourly" else cfg.llm_max_calls_digest
    llm = LLM(cfg.llm_key, cfg.llm_base, cfg.llm_model, cfg.llm_timeout, max_calls)
    if not llm.enabled:
        log.warning("未配置 AI_API_KEY，使用规则模式（仅推送评分 >= %.1f 的事件）", cfg.priority_score)

    need = [c for c in candidates if not ledger.cached_brief(c.key)]
    if need and llm.enabled:
        fresh_briefs, groups = llm.analyze(need)
    else:
        fresh_briefs, groups = {}, []
    log.info("AI 新分析 %s 条，语义合并 %s 组", len({id(v) for v in fresh_briefs.values()}), len(groups))

    by_key = {c.key: c for c in candidates}
    events = []
    covered = set()
    for group in groups:
        members = [by_key[key] for key in group if key in by_key]
        if not members:
            continue
        merged = merge_clusters(members) if len(members) > 1 else members[0]
        brief = None
        for member in members:
            brief = fresh_briefs.get(member.key) or ledger.cached_brief(member.key)
            if brief:
                break
        brief = brief or fallback_brief(merged)
        score = final_score(merged, brief)
        events.append([merged, brief, score])
        covered.update(member.key for member in members)
        for member in members:
            ledger.put_brief(member.key, member.title, brief, score)
        ledger.put_brief(merged.key, merged.title, brief, score)

    for cluster in candidates:
        if cluster.key in covered:
            continue
        brief = ledger.cached_brief(cluster.key) or fallback_brief(cluster)
        score = final_score(cluster, brief)
        events.append([cluster, brief, score])
        ledger.put_brief(cluster.key, cluster.title, brief, score)

    events.sort(key=lambda entry: -entry[2])

    headlines = []
    if mode == "hourly":
        priority = [e for e in events if e[2] >= cfg.priority_score]
        normal = [e for e in events if cfg.min_score <= e[2] < cfg.priority_score]
        selected = priority[: cfg.max_briefs + 2] + normal[: cfg.max_briefs]
        headlines = [
            {"title": e[0].title, "source_name": (e[0].sources or ["未知"])[0]}
            for e in events
            if 4.5 <= e[2] < cfg.min_score
        ][: cfg.max_headlines]
    else:
        selected = [e for e in events if e[2] >= cfg.digest_min_score][: cfg.digest_max]

    stats = {
        "new": len(raw_items),
        "relevant": len(items),
        "clusters": len(clusters),
        "events": len(events),
    }
    if not selected and not headlines:
        log.info("无达到阈值的事件，本次不推送")
        return 0

    overview = ""
    wm_note = ""
    if mode in ("morning", "evening"):
        if llm.enabled and selected:
            overview = llm.overview([e[0] for e in selected])
        if cfg.wm_key:
            wm = WorldMonitor(
                cfg.wm_key, str(Path(cfg.data_dir, "wm_budget.json")), cfg.wm_daily_budget
            )
            wm_note = wm.briefing(max_calls=4 if mode == "morning" else 1)
            if wm_note:
                log.info("World Monitor 增强已获取")

    if mode == "hourly":
        messages = hourly_messages(selected, headlines, stats)
    else:
        messages = digest_messages(mode, selected, overview, wm_note, stats)

    bark = Bark(cfg.bark_url, cfg.bark_group)
    if args.dry_run or not bark.configured:
        stamp = now.strftime("%Y%m%d-%H%M%S")
        outbox = Path(cfg.data_dir, "outbox")
        outbox.mkdir(parents=True, exist_ok=True)
        target = outbox / f"{stamp}-{mode}.md"
        target.write_text(render_text(selected, stats), encoding="utf-8")
        for title, body in messages:
            log.info("预览消息「%s」%s 字节\n%s", title, len(body.encode("utf-8")), body)
        log.info("dry-run 输出：%s", target)
        if not bark.configured:
            log.warning("BARK_URL 未配置，未真实推送")
        return 0

    level = "passive" if (now.hour >= 23 or now.hour < 7) else "active"
    ok_all = True
    for title, body in messages:
        ok_all = bark.send(title, body, level) and ok_all

    if not ok_all:
        log.error("存在推送失败，不写入台账，下次重试")
        return 1

    for cluster, brief, score in selected:
        ledger.mark_pushed(cluster.key, cluster_urls(cluster), [cluster.title], score, mode, day)
    if mode in ("morning", "evening"):
        ledger.mark_digest(day, mode)
    ledger.meta_set("last_success", now.strftime("%Y-%m-%d %H:%M:%S"))
    log.info("推送完成：%s 条消息，%s 个事件", len(messages), len(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())