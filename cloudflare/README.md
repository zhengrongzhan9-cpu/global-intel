# Cloudflare Workers 定时触发

用 Cloudflare Cron Triggers 调 GitHub `workflow_dispatch`，绕开 GitHub 新仓库 schedule 不触发的问题。

## 时间表（UTC，与 KL 差 8 小时）

| UTC cron | 吉隆坡时间 | mode |
|---|---|---|
| `7 1-11,13-23 * * *` | 每小时 :07（避开 08/20 点） | hourly |
| `20 0 * * *` | 08:20 | morning |
| `20 12 * * *` | 20:20 | evening |

## 权限与密钥

- Cloudflare API Token：模板 **Edit Cloudflare Workers**（只需 Workers Scripts: Edit）。
- GitHub **Fine-grained PAT**：仅选 `global-intel` 仓库，权限 `Actions: Read and write` + `Metadata: Read-only`，有效期建议 90 天。
- 两个密钥都只存在 Cloudflare Secret：`GITHUB_TOKEN`、`TRIGGER_KEY`。
- `TRIGGER_KEY` 仅用于受保护的 `/trigger` 验证入口。

## 部署

```powershell
$env:CF_API_TOKEN="..."
$env:CF_ACCOUNT_ID="..."
$env:GITHUB_TOKEN="github_pat_..."
python cloudflare\deploy.py
```

## 验证

1. `GET /health` 返回 crons。
2. `GET /trigger?mode=hourly` 带 `X-Trigger-Key`，应返回 204 并出现一次 GitHub workflow_dispatch。
3. 检查 GitHub run 成功、Bark 正文正常、Pages 链接正常。
4. 全部通过后再移除 `.github/workflows/intel.yml` 里的 `schedule`，避免重复触发。

## 本地测试

```powershell
node cloudflare\test\worker.test.mjs
```