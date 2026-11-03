from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("intel.crawl")


def run_crawler(root: Path, timeout: int = 900, retries: int = 2):
    """调用 TrendRadar 采集，返回 (成功, 日志尾部)。"""
    root = Path(root).resolve()
    env = os.environ.copy()
    env["CONFIG_PATH"] = str(root / "config" / "config.yaml")
    env["PYTHONIOENCODING"] = "utf-8"
    vendor = str(root / "vendor" / "TrendRadar")
    env["PYTHONPATH"] = vendor + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    last = ""
    for attempt in range(retries + 1):
        log.info("TrendRadar 采集开始（第 %s 次）", attempt + 1)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "trendradar"],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            last = f"采集超时（>{timeout}s）"
            log.warning(last)
            continue
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = "\n".join(out.strip().splitlines()[-25:])
        if proc.returncode == 0:
            log.info("TrendRadar 采集完成")
            return True, tail
        last = tail
        log.warning("TrendRadar 采集失败（exit=%s）", proc.returncode)
        time.sleep(15 * (attempt + 1))
    return False, last