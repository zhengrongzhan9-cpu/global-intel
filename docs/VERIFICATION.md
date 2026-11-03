# 验证记录

验证时间：2026-11-03（Asia/Kuala_Lumpur / Asia/Shanghai 同一 UTC+8）

## 已实际验证

| 项 | 方法 | 结果 |
|---|---|---|
| 依赖安装 | `uv sync --frozen --no-dev`（Python 3.12.14） | 通过，`import trendradar/litellm/feedparser/boto3` 成功 |
| 真实采集 | 8 个热榜 + 29 个 RSS | 28 源成功、1 源 403（mining.com）；RSS 共 749 条 |
| 数据落库 | SQLite `output/news`、`output/rss` | 含 title/url/published_at/summary，字段完整 |
| 相关性过滤 | 热榜社会新闻 | 275 条 → 135 条，娱乐/民生类被剔除 |
| 字面聚类 | URL + 标题相似度 | 135 条 → 130 个事件（同一标题多平台可合并） |
| 推送链路 | 本地 mock Bark（HTTP 200） | 2 条消息，3318 / 1660 字节，均成功 |
| 台账防重 | 连续两次运行 | 已推送 24 条标题全部唯一，无重复 |
| 早晚报 | `--mode evening` | 1 条消息，含当日已推送事件，正常渲染 |
| 单元自测 | `scripts/selftest.py` | 7 项全部通过 |
| World Monitor MCP | `tools/list` | HTTP 200，返回 100 个工具 |
| World Monitor 鉴权 | 无 Key `tools/call` | HTTP 401，提示 OAuth 或 `X-WorldMonitor-Key` |
| World Monitor 免密工具 | `get_sources` | HTTP 200，847 个信源 |
| DSH MCP 能力 | 官方文档 + 内置 SDK | 支持 `streamable-http` + 自定义 headers，已生成 overlay |
| RSS 可达性 | 29 个源逐个请求 | 28 个返回 RSS/Atom |

## 尚未验证（需要你的输入）

| 项 | 阻塞原因 |
|---|---|
| iPhone 真实 Bark 推送 | 缺 `BARK_URL` |
| GitHub Actions 端到端 | 缺仓库与 PAT |
| LLM 五段式简报 | 缺 `AI_API_KEY`（代码路径与 JSON 校验已单测） |
| World Monitor 实时数据 | 免费账户为交互式 OAuth；需 `wm_` Key 或 Pro |
| DSH 加载 MCP 后的工具调用 | 需重启 DSH 并设置 `WM_KEY` |

## 已验证的免费额度事实

- World Monitor 免费账户：**5 次/天**缓存型 MCP 调用；Pro $39.99/月（50 次/天）；API $99.99/月（1000 次/天）。
- GitHub Actions：公开仓库免费不限分钟；私有仓库 2000 分钟/月，按每小时一次约需 2500–4000 分钟，不够。
- Bark：免费。
- DeepSeek：按 24 次/天、每次约 1.5 万 tokens 估算，约 $3–6/月。

## 平台限制

1. GitHub cron 延迟 5–15 分钟，早晚报可能略晚于 08:30 / 20:30。
2. Actions 每次运行环境全新，必须靠 cache 恢复 `output/` 与 `data/`；cache 被驱逐会丢失去重历史（概率低）。
3. newsnow 公共 API 为第三方免费服务，偶发不可用；RSS 独立不受影响。
4. World Monitor 免费面板数据刷新 5–15 分钟，且无历史回溯。