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

## 真机与云端验证（2026-11-03 15:16-15:26）

| 项 | 结果 |
|---|---|
| Bark 真机连通 | `--test-push` 成功，iPhone 收到「✅ 全球情报推送测试」 |
| DeepSeek Key | `chat/completions` 返回 200（实际模型 `deepseek-flash`） |
| 本地真实推送 | 15:20 发出 2 条消息 / 6 个事件，全部 200 |
| GitHub 仓库 | `zhengrongzhan9-cpu/global-intel`（public，152 文件 2.5MB） |
| Actions hourly | run `41595827704` success：534 条采集 → 343 事件 → 31 条 AI → 2 条推送 / 6 事件 |
| Actions morning | run `41596118748` success：690 条采集 → 549 相关 → 14 条 AI → 3 条推送 / 10 事件 |
| 数据缓存 | Restore/Save data 均 success，去重台账跨运行保留 |
| Secrets | `BARK_URL`、`AI_API_KEY` 已写入，日志中均以 `***` 脱敏 |

## 尚未验证

| 项 | 阻塞原因 |
|---|---|
| World Monitor 实时数据 | 免费账户为交互式 OAuth；需 `wm_` Key 或 Pro |
| DSH 加载 MCP 后的工具调用 | 需重启 DSH 并设置 `WM_KEY` |
| 20:30 定时日报 | 需等到当晚 20:20 KL 的 cron 触发（代码路径已用 `mode=evening` 验证） |

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