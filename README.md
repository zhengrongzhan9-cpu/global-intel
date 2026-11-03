# 全球金融 / 政治 / 地缘战略情报系统

基于 [TrendRadar](https://github.com/sansan0/TrendRadar) 的采集与去重能力，加上自建的 AI 分析层，
每小时扫描全球公开信源，只把**重要且尚未通知**的信息推送到 iPhone（Bark）。

时区统一 `Asia/Kuala_Lumpur`（UTC+8）。

## 架构

```
GitHub Actions（每小时 :07 + 08:20 / 20:20 KL）
        │
        ├─ TrendRadar 采集：8 个中国热榜 + 29 个国际 RSS
        │      └─ SQLite（标题/链接/时间/摘要）
        │
        ├─ intel 分析层
        │      ├─ 相关性过滤（热榜里的社会新闻先剔除）
        │      ├─ 字面聚类 + LLM 语义去重
        │      ├─ 五段式中文简报（标题/摘要/背景/影响/存疑）
        │      ├─ 重要性评分（规则 40% + 模型 60%）
        │      └─ 推送台账（SQLite，防重复）
        │
        └─ Bark 推送（≤3.4KB 自动分批）
               ├─ 每小时：≥8 分立即推，6-8 分合并推
               ├─ 08:30：全球晨报（过去 24h Top 10）
               └─ 20:30：当日汇总
```

## 目录

| 路径 | 作用 |
|---|---|
| `vendor/TrendRadar/` | 上游代码，固定 v6.11.0，只做采集 |
| `config/config.yaml` | 采集配置（时区、平台、RSS、关闭内置推送） |
| `config/frequency_words.txt` | 六大类关键词（地缘/市场/宏观/贸易/中国/科技） |
| `config/intel.yaml` | 评分阈值、条数上限、模型参数 |
| `intel/` | 分析层：过滤、聚类、LLM、渲染、Bark、台账 |
| `.github/workflows/intel.yml` | 定时任务 |
| `dsh/worldmonitor.cordis.yml` | DSH 的 World Monitor MCP 接入配置 |

## 部署

1. 推送本仓库到 GitHub（**公开仓库**，Actions 分钟数才免费）。
2. 在 `Settings → Secrets and variables → Actions` 添加：

| Secret | 必填 | 说明 |
|---|---|---|
| `BARK_URL` | 是 | `https://api.day.app/你的DeviceKey` |
| `AI_API_KEY` | 强烈建议 | DeepSeek 等 OpenAI 兼容 Key |
| `AI_API_BASE` | 否 | 默认 `https://api.deepseek.com/v1` |
| `AI_MODEL` | 否 | 默认 `deepseek-chat` |
| `WM_KEY` | 否 | World Monitor 的 `wm_` Key（免费额度 5 次/天） |

3. `Actions → Global Intel → Run workflow`，`mode` 选 `hourly` 做一次手动验证。

## 定时表

| KL 时间 | 动作 | UTC cron |
|---|---|---|
| 每小时 :07（08/20 点除外） | 增量扫描 + 重要事件推送 | `7 1-11,13-23 * * *` |
| 08:20 触发 | 08:30 前发出全球晨报 | `20 0 * * *` |
| 20:20 触发 | 20:30 前发出当日汇总 | `20 12 * * *` |

GitHub Actions 的实际启动通常延迟 5–15 分钟，这是平台特性，无法消除。

## 评分

综合分 = 0.4 × 规则分 + 0.6 × 模型分：

- 规则分：多源印证（2 源 +1.5 / 3 源 +2.5）、Tier-1 来源 +1.5、战争/制裁/导弹等强信号最多 +2、暴跌/熔断 +1、央行利率动作 +0.5。
- 模型分：0–10，10 = 开战/政权更迭/央行紧急行动。

阈值：`push.min_score`（默认 6）、`push.priority_score`（默认 8），可在 `config/intel.yaml` 调整。

## 去重

1. URL 规范化（去 `utm_*`、锚点、尾斜杠）。
2. 标题归一化后字面聚类（英文 token Jaccard + 中文 bigram Jaccard，阈值 0.62）。
3. 交给模型做语义合并（同一主体 + 同一动作合并为一条）。
4. 推送台账按 URL 与事件指纹双重判重，已推送的不再进入候选。

## 成本

| 项 | 方案 | 月成本 |
|---|---|---|
| GitHub Actions | 公开仓库 | $0 |
| DeepSeek | 约 24 次 × 1.5 万 tokens | ≈ $3–6 |
| World Monitor | 免费账户 5 次/天 | $0 |
| Bark | 免费 | $0 |

## 本地运行

```powershell
# 首次：安装依赖
pip install -r requirements.txt
pip install -e vendor/TrendRadar --no-deps

# 预览（不推送）
$env:BARK_URL="https://api.day.app/你的Key"
python -m intel.run --mode hourly --dry-run

# 真实推送
python -m intel.run --mode hourly

# 连通性测试
python -m intel.run --test-push
```

本地数据在 `output/`（采集）与 `data/`（台账、日志、预览），均已被 `.gitignore` 排除。

## 已知限制

- **World Monitor 免费账户**：MCP 每天仅 5 次调用，只够晨报增强；其免费 OAuth 是交互式登录，无法在 Actions 里自动续期。要每小时调用需 Pro（$39.99/月）。
- **RSS 可达性**：本机实测 28/29 可用；`mining.com` 返回 403，已保留但不会致命。部分站点（Reuters 旧域名、IMF、ACLED）不可用，已用替代源。
- **Actions 延迟**：整点扫描实际在 :07–:22 之间启动；早晚报可能晚于 08:30/20:30 几分钟。
- **无 AI Key 时**为规则模式，只推送 ≥8 分事件，简报不带中文翻译与背景。
- **GPL-3.0**：`vendor/TrendRadar` 为 GPL-3.0，本仓库整体按 GPL-3.0 分发，保留上游版权声明。

## 故障排查

| 现象 | 排查 |
|---|---|
| 没有推送 | 看 Actions 日志里 `读取新增/聚合/无达到阈值`；确认 `BARK_URL` |
| 重复推送 | 检查 `data/state.db` 是否被缓存恢复；Actions cache 是否命中 `intel-data-` |
| 热榜 0 条 | newsnow 公共 API 偶发不可用，属上游问题；RSS 不受影响 |
| 简报是英文 | `AI_API_KEY` 未配置或额度不足，走了规则回退 |

## 声明

公开信息聚合，仅供研究参考，不构成投资建议。政治信息保持中立呈现。