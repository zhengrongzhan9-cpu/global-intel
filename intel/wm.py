from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import requests

log = logging.getLogger("intel.wm")

ENDPOINT = "https://worldmonitor.app/mcp"


class WorldMonitor:
    """World Monitor MCP 客户端（需要 API Key；免费账户额度为 5 次/天）。"""

    def __init__(self, api_key: str, budget_file: str = "data/wm_budget.json", daily_budget: int = 5):
        self.api_key = (api_key or "").strip()
        self.budget_file = Path(budget_file)
        self.daily_budget = int(daily_budget)
        self.session_id = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _budget(self):
        today = datetime.now().strftime("%Y-%m-%d")
        data = {}
        if self.budget_file.exists():
            try:
                data = json.loads(self.budget_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if data.get("date") != today:
            data = {"date": today, "used": 0}
        return data

    def _consume(self, n: int = 1) -> bool:
        data = self._budget()
        if data["used"] + n > self.daily_budget:
            log.warning("World Monitor 今日额度已用完（%s/%s）", data["used"], self.daily_budget)
            return False
        data["used"] += n
        self.budget_file.parent.mkdir(parents=True, exist_ok=True)
        self.budget_file.write_text(json.dumps(data), encoding="utf-8")
        return True

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "global-intel/0.1",
            "X-WorldMonitor-Key": self.api_key,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _parse(self, response):
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except Exception:
                        continue
            return None
        try:
            return response.json()
        except Exception:
            return None

    def _initialize(self):
        if self.session_id:
            return
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "global-intel", "version": "0.1"},
            },
        }
        resp = requests.post(ENDPOINT, headers=self._headers(), json=payload, timeout=40)
        self.session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if resp.status_code >= 400:
            log.warning("WM initialize 失败：%s %s", resp.status_code, resp.text[:200])

    def call(self, tool: str, args: dict | None = None):
        if not self.enabled:
            return None
        if not self._consume():
            return None
        try:
            self._initialize()
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args or {}},
            }
            resp = requests.post(ENDPOINT, headers=self._headers(), json=payload, timeout=45)
            data = self._parse(resp) or {}
            if "error" in data:
                log.warning("WM %s 调用失败：%s", tool, str(data["error"])[:200])
                return None
            content = (data.get("result") or {}).get("content") or []
            for block in content:
                if block.get("type") == "text":
                    try:
                        return json.loads(block.get("text") or "")
                    except Exception:
                        return block.get("text")
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("WM %s 异常：%s", tool, exc)
            return None

    def briefing(self, max_calls: int = 4) -> str:
        if not self.enabled:
            return ""
        notes = []
        brief = self.call("get_world_brief")
        if isinstance(brief, dict):
            text = brief.get("brief") or brief.get("summary") or brief.get("text")
            if isinstance(text, str) and text.strip():
                notes.append("全球态势：" + text.strip()[:260])
        hotspots = self.call("get_hotspot_escalation")
        if isinstance(hotspots, dict):
            items = hotspots.get("hotspots") or hotspots.get("items") or []
            names = []
            for item in items[:4]:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("region") or item.get("country")
                    score = item.get("score") or item.get("escalation")
                    if name:
                        names.append(f"{name}{(' ' + str(score)) if score is not None else ''}")
            if names:
                notes.append("升级热点：" + "、".join(names))
        choke = self.call("get_chokepoint_status")
        if isinstance(choke, dict):
            items = choke.get("chokepoints") or choke.get("items") or []
            alerts = []
            for item in items[:4]:
                if isinstance(item, dict) and (item.get("status") or "").lower() not in ("", "normal", "open"):
                    alerts.append(str(item.get("name") or item.get("chokepoint") or ""))
            if alerts:
                notes.append("航运要道异常：" + "、".join([a for a in alerts if a]))
        alerts = self.call("get_alert_digest")
        if isinstance(alerts, dict):
            items = alerts.get("alerts") or alerts.get("items") or []
            titles = [str(i.get("title")) for i in items[:3] if isinstance(i, dict) and i.get("title")]
            if titles:
                notes.append("阈值告警：" + "；".join(titles)[:200])
        return "\n".join(notes[:max_calls])