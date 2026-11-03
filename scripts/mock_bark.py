"""本地 Bark 模拟服务，仅用于验证推送链路。"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LOG = Path("data/mock-bark.log")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"path": self.path, "payload": payload}, ensure_ascii=False) + "\n")
        body = json.dumps({"code": 200, "message": "success"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"mock bark listening on {port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()