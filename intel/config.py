from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS = {
    "output_dir": "output",
    "data_dir": "data",
    "bark_group": "GlobalIntel",
    "push": {
        "min_score": 5.0,
        "priority_score": 7.5,
        "max_briefs": 5,
        "max_headlines": 6,
        "max_candidates": 60,
        "digest_min_score": 4.0,
        "digest_max": 10,
    },
    "llm": {
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "timeout": 120,
        "max_calls": 4,
        "max_calls_digest": 8,
    },
    "wm": {"daily_budget": 5},
    "crawl": {"timeout": 900, "retries": 2},
}


@dataclass
class Settings:
    output_dir: str = "output"
    data_dir: str = "data"
    bark_url: str = ""
    bark_group: str = "GlobalIntel"
    llm_key: str = ""
    llm_base: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_timeout: int = 120
    llm_max_calls: int = 4
    llm_max_calls_digest: int = 8
    min_score: float = 6.0
    priority_score: float = 8.0
    max_briefs: int = 5
    max_headlines: int = 6
    max_candidates: int = 60
    digest_min_score: float = 5.0
    digest_max: int = 10
    wm_key: str = ""
    wm_daily_budget: int = 5
    crawl_timeout: int = 900
    crawl_retries: int = 2
    repo_root: Path = field(default_factory=lambda: Path("."))


def _merge(base: dict, extra: dict):
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def load(repo_root: str | None = None) -> Settings:
    root = Path(repo_root or os.environ.get("INTEL_ROOT", ".")).resolve()
    cfg = {key: (value.copy() if isinstance(value, dict) else value) for key, value in DEFAULTS.items()}
    path = root / "config" / "intel.yaml"
    if path.exists():
        try:
            _merge(cfg, yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except Exception as exc:  # noqa: BLE001
            print(f"[config] intel.yaml 解析失败，使用默认值：{exc}")

    push = cfg["push"]
    llm = cfg["llm"]
    wm = cfg["wm"]
    crawl = cfg["crawl"]

    return Settings(
        output_dir=str(root / cfg.get("output_dir", "output")),
        data_dir=str(root / cfg.get("data_dir", "data")),
        bark_url=os.environ.get("BARK_URL", "").strip(),
        bark_group=os.environ.get("BARK_GROUP", cfg.get("bark_group", "GlobalIntel")),
        llm_key=os.environ.get("AI_API_KEY", "").strip(),
        llm_base=os.environ.get("AI_API_BASE", llm.get("api_base", "")).strip(),
        llm_model=os.environ.get("AI_MODEL", llm.get("model", "deepseek-chat")).strip(),
        llm_timeout=int(os.environ.get("AI_TIMEOUT", llm.get("timeout", 120))),
        llm_max_calls=int(llm.get("max_calls", 4)),
        llm_max_calls_digest=int(llm.get("max_calls_digest", 8)),
        min_score=float(os.environ.get("PUSH_MIN_SCORE", push.get("min_score", 6.0))),
        priority_score=float(os.environ.get("PUSH_PRIORITY_SCORE", push.get("priority_score", 8.0))),
        max_briefs=int(push.get("max_briefs", 5)),
        max_headlines=int(push.get("max_headlines", 6)),
        max_candidates=int(push.get("max_candidates", 60)),
        digest_min_score=float(push.get("digest_min_score", 5.0)),
        digest_max=int(push.get("digest_max", 10)),
        wm_key=os.environ.get("WM_KEY", "").strip(),
        wm_daily_budget=int(os.environ.get("WM_DAILY_BUDGET", wm.get("daily_budget", 5))),
        crawl_timeout=int(crawl.get("timeout", 900)),
        crawl_retries=int(crawl.get("retries", 2)),
        repo_root=root,
    )