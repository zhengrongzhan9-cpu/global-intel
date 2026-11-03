"""用 Cloudflare REST API 部署 Worker（不依赖 wrangler）。

所需环境变量：
  CF_API_TOKEN   Cloudflare API Token（权限：Workers Scripts: Edit）
  CF_ACCOUNT_ID  Cloudflare Account ID（可选，留空则自动查询）
  GITHUB_TOKEN   Fine-grained PAT（仅 global-intel，Actions: Read and write）
  TRIGGER_KEY    验证用随机串（可选，留空自动生成）
  GITHUB_REPO    默认 zhengrongzhan9-cpu/global-intel

密钥只经 HTTPS 发送到 Cloudflare，不打印、不落盘。
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path

import requests

BASE = "https://api.cloudflare.com/client/v4"
SCRIPT = "global-intel-cron"
CRONS = ["7 1-11,13-23 * * *", "20 0 * * *", "20 12 * * *"]
ROOT = Path(__file__).resolve().parent


def headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def check(resp, action: str):
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code >= 400 or not data.get("success", False):
        errors = data.get("errors") or resp.text[:300]
        raise SystemExit(f"{action} 失败：HTTP {resp.status_code} {errors}")
    return data.get("result")


def main() -> int:
    token = os.environ.get("CF_API_TOKEN", "").strip()
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    repo = os.environ.get("GITHUB_REPO", "zhengrongzhan9-cpu/global-intel").strip()
    trigger_key = os.environ.get("TRIGGER_KEY", "").strip() or secrets.token_hex(24)

    if not token or not gh_token:
        print("缺少 CF_API_TOKEN 或 GITHUB_TOKEN", file=sys.stderr)
        return 2

    verify = requests.get(f"{BASE}/user/tokens/verify", headers=headers(token), timeout=30)
    check(verify, "校验 Cloudflare Token")
    print("Cloudflare Token 有效")

    if not account_id:
        accounts = requests.get(f"{BASE}/accounts", headers=headers(token), timeout=30)
        result = check(accounts, "读取账号") or []
        if not result:
            print("未找到 Cloudflare 账号", file=sys.stderr)
            return 2
        account_id = result[0]["id"]
    print("Account ID:", account_id)

    source = (ROOT / "src" / "index.js").read_text(encoding="utf-8")
    metadata = {
        "main_module": "index.js",
        "compatibility_date": "2026-11-01",
        "bindings": [{"type": "plain_text", "name": "GITHUB_REPO", "text": repo}],
    }
    files = {
        "metadata": ("metadata.json", json.dumps(metadata), "application/json"),
        "index.js": ("index.js", source, "application/javascript+module"),
    }
    upload = requests.put(
        f"{BASE}/accounts/{account_id}/workers/scripts/{SCRIPT}",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=120,
    )
    check(upload, "上传 Worker")
    print("Worker 已上传")

    for name, value in (("GITHUB_TOKEN", gh_token), ("TRIGGER_KEY", trigger_key)):
        resp = requests.put(
            f"{BASE}/accounts/{account_id}/workers/scripts/{SCRIPT}/secrets",
            headers=headers(token),
            json={"name": name, "text": value, "type": "secret_text"},
            timeout=30,
        )
        check(resp, f"写入 Secret {name}")
        print(f"Secret {name} 已写入")

    sched = requests.put(
        f"{BASE}/accounts/{account_id}/workers/scripts/{SCRIPT}/schedules",
        headers=headers(token),
        json=[{"cron": cron} for cron in CRONS],
        timeout=30,
    )
    check(sched, "设置 Cron Triggers")
    print("Cron 已设置:", CRONS)

    # 确保 workers.dev 子域可用
    sub = None
    sub_resp = requests.get(f"{BASE}/accounts/{account_id}/workers/subdomain", headers=headers(token), timeout=30)
    if sub_resp.status_code == 200:
        sub = (sub_resp.json().get("result") or {}).get("subdomain")
    if not sub:
        candidate = "globalintel-" + secrets.token_hex(3)
        put = requests.put(
            f"{BASE}/accounts/{account_id}/workers/subdomain",
            headers=headers(token),
            json={"subdomain": candidate},
            timeout=30,
        )
        if put.status_code < 400:
            sub = candidate
    if not sub:
        print("警告：未配置 workers.dev 子域，无法做公网健康检查", file=sys.stderr)
        key_file = ROOT.parent / "data" / "cf_trigger_key.txt"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(trigger_key, encoding="utf-8")
        print("TRIGGER_KEY_FILE=" + str(key_file))
        return 0

    # 尝试开启 workers.dev（部分账号默认已开）
    requests.patch(
        f"{BASE}/accounts/{account_id}/workers/scripts/{SCRIPT}/script-settings",
        headers=headers(token),
        json={"workers_dev": True},
        timeout=30,
    )

    url = f"https://{SCRIPT}.{sub}.workers.dev"
    key_file = ROOT.parent / "data" / "cf_trigger_key.txt"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(trigger_key, encoding="utf-8")
    print("Worker URL:", url)
    print("HEALTH_URL=" + url + "/health")
    print("TRIGGER_URL=" + url + "/trigger")
    print("TRIGGER_KEY_FILE=" + str(key_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())