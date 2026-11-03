from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit, urlunsplit

import requests

log = logging.getLogger("intel.bark")


class Bark:
    def __init__(self, url: str, group: str = "GlobalIntel"):
        self.group = group
        self.server = "https://api.day.app"
        self.key = ""
        text = (url or "").strip()
        if not text:
            return
        if "://" not in text:
            self.key = text.strip("/")
            return
        parts = urlsplit(text)
        self.server = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        self.key = parts.path.strip("/")
        if self.key.endswith(".json"):
            self.key = self.key[: -len(".json")]

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def send(self, title: str, body: str, level: str = "active") -> bool:
        if not self.configured:
            log.warning("Bark 未配置，跳过推送")
            return False
        endpoint = f"{self.server}/{self.key}"
        payload = {
            "title": title,
            "body": body,
            "group": self.group,
            "level": level,
        }
        try:
            resp = requests.post(endpoint, json=payload, timeout=25)
            data = resp.json() if resp.content else {}
            if resp.status_code == 200 and int(data.get("code", 200)) == 200:
                log.info("Bark 推送成功：%s（%s 字节）", title, len(body.encode("utf-8")))
                return True
            log.error("Bark 推送失败：HTTP %s %s", resp.status_code, resp.text[:200])
        except Exception as exc:  # noqa: BLE001
            log.error("Bark 推送异常：%s", exc)
        return False