# 配置说明

## 相对上游 TrendRadar v6.11.0 的改动

| 配置 | 上游默认 | 本项目 | 原因 |
|---|---|---|---|
| `app.timezone` | Asia/Shanghai | Asia/Kuala_Lumpur | 统一推送时区 |
| `schedule.enabled` | false | false | 调度交给 GitHub Actions，避免双重推送 |
| `notification.enabled` | true | **false** | 推送统一由 intel 层发出 |
| `report.mode` | current | incremental | 只处理新增 |
| `platforms.sources` | 11 个 | 8 个 | 保留财经/综合类，去掉娱乐向平台 |
| `rss.feeds` | 3 个 | 29 个 | 全球财经/地缘/能源/科技 |
| `rss.freshness_filter.max_age_days` | 1 | 2 | 覆盖周末与低更新源 |
| `storage.backend` | auto | local | Actions 用 cache 持久化，不需要 R2 |
| `storage.local.retention_days` | 0 | 7 | 控制 cache 体积 |
| `ai_analysis.enabled` | true | false | 不用 TrendRadar 的四段式分析 |
| `ai_translation.enabled` | true | false | 翻译由 intel 层统一做 |
| `advanced.crawler.request_interval` | 2000ms | 800ms | 8 个源，降低总耗时 |

## RSS 清单（29 个，实测 28 个可用）

| 类别 | 源 |
|---|---|
| 通讯社/综合 | Al Jazeera、BBC World、Guardian World、Euronews、DW、France24 未用 |
| 亚洲/中国 | SCMP China、Nikkei Asia、Straits Times Asia、Japan Times、Xinhua World |
| 金融/宏观 | FT World、CNBC World、CNBC Markets、MarketWatch、Investing Commodities、Investing Forex、Fed Press、Bank of Japan |
| 地缘/智库 | Crisis Group、Foreign Policy、Politico EU、UN News |
| 能源/大宗 | OilPrice、EIA、Mining.com（403，保留观察） |
| 科技/AI | TechCrunch、The Verge、Ars Technica、SemiAnalysis |

不可用并已放弃：Reuters 旧 RSS 域名（DNS 解析失败）、IMF（403）、ACLED（404）、CFR（404）、
World Bank（404）、OECD（403）、ECB（证书链不完整）、财新/第一财经（RSS 路径已下线）。

## 关键词分组

`config/frequency_words.txt` 分六组：地缘政治与军事、全球市场、宏观政策、贸易与供应链、
中国经济与市场、科技与能源。另含 `[GLOBAL_FILTER]` 过滤娱乐/广告。

注意：该文件主要影响 TrendRadar 的 HTML 报告；intel 层读取全部新增条目后自行过滤与评分，
所以关键词调整不会导致漏推送。

## intel 评分

```
规则分（0-7）
  +2.5  三个及以上独立来源
  +1.5  两个来源
  +1.5  含 Tier-1 来源（FT/Nikkei/SCMP/BBC/Al Jazeera/Fed/BoJ/Crisis Group/EIA）
  +0.6/项  强信号词（war/airstrike/missile/nuclear/sanction/战争/空袭/导弹/制裁…）最多 +2
  +1.0  市场冲击词（plunge/crash/default/暴跌/熔断/违约…）
  +0.5  央行 + 利率动作同时出现

综合分 = 0.25 × (规则分 / 7 × 10) + 0.75 × 模型 importance
```

无 AI Key 时：综合分 = 规则分 / 7 × 10，且只推送 ≥ `priority_score` 的事件。

## 去重参数

| 参数 | 值 | 位置 |
|---|---|---|
| 字面聚类阈值 | 0.55 | `intel/cluster.py: MERGE_THRESHOLD` |
| 英文 token 权重 | 0.95 | 同上 `_sim` |
| 中文 bigram Jaccard | 直接比较 | 同上 `_grams` |
| 国家+动作实体规则 | 0.72 | 同上 `_sim`（如 iran + strikes 直接合并） |
| 撇号归一化 | `iran's` = `iran` | 同上 `_tokens` |
| 语义合并 | LLM `ids` 数组 | `intel/llm.py: ANALYZE_PROMPT` |
| 简报缓存 | 20 小时 | `intel/store.py: cached_brief` |
| RSS 发布时间下限 | 窗口起点 -12h | `intel/run.py` |

## 台账结构（data/state.db）

| 表 | 用途 |
|---|---|
| `pushed` | 已推送事件指纹、分数、时间 |
| `digest_events` | 早晚报已报道事件（跨期去重依据） |
| `pushed_urls` | 已推送 URL（防同文不同标题） |
| `seen` | AI 简报缓存（省 token） |
| `digests` | 早晚报发送状态（每天各一次） |
| `meta` | 最近成功时间等 |

## 早晚报参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `push.digest_min_score` | 5.0 | 入选最低分，不凑数 |
| `push.digest_max` | 14 | 单期最多事件数 |
| `llm.max_calls_digest` | 10 | 8 批分析 + 今日主线 + 深度分析 |
| `report.public_base_url` | 空 | 留空则由 `GITHUB_REPOSITORY` 推导 Pages 地址 |

跨期去重规则：同一事件若 URL 集合未扩大、且评分未比上期提高 1.0 以上，则跳过；
因此“新的信源跟进”或“评分显著上升”会作为新进展再次报道。

## 调整建议