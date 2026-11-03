from __future__ import annotations

import json
import logging

import requests

from .cluster import merge_clusters
from .util import extract_json, now_local

log = logging.getLogger("intel.llm")

CATEGORIES = ("地缘政治", "全球市场", "宏观政策", "贸易供应链", "中国经济", "科技能源", "综合")
CREDIBILITY = {"高": "高", "中": "中", "低": "低", "high": "高", "medium": "中", "low": "低"}

SYSTEM_PROMPT = (
    "你是一名全球金融、政治与地缘战略情报分析师，服务对象是关注全球市场与中国资产的专业读者。"
    "你只输出严格合法的 JSON，不输出 Markdown、解释或前后缀。"
)

ANALYZE_PROMPT = """今天是 {date}（Asia/Kuala_Lumpur）。以下是 {count} 条候选事件，已按字面相似度去重，但仍可能有同一事件的不同措辞。

{events}

任务分两步：
A. 语义去重：如果多条描述同一事件（同一主体+同一动作），把它们的 id 合并成一条；不同事件不要合并。
B. 对每条（合并后的）事件输出中文情报简报。

硬性要求：
1. 事实与判断分离：summary 只写可核实的已发生事实；推断、预判、因果解释只能写在 background，并以「（判断）」标注。
2. 未证实的军事行动、伤亡数字、袭击归属、领导人动向，必须放进 unverified，不得写成既定事实。
3. 政治表述保持中立，不评价制度、不评价领导人、不使用情绪化形容词。
4. summary 不超过 100 个汉字；background 不超过 140 个汉字；unverified 不超过 80 个汉字；没有未证实信息就写「暂无未证实信息」。
5. 影响面要具体：国家用通用名（如 美国、中国、伊朗），行业用通用名（如 能源、半导体、航运），市场用（如 美股、A股、黄金、原油、美债）。
6. title_zh 不超过 40 个汉字，英文专有名词可保留。
7. importance 为 0-10 的整数：10=开战/政权更迭/央行紧急行动；8-9=重大制裁、断供、市场熔断；6-7=重要政策或财报；5 以下=一般动态。

只输出如下 JSON：
{{"events":[{{"ids":[1,5],"title_zh":"","summary":"","background":"","impact":{{"countries":[],"sectors":[],"markets":[]}},"unverified":"","credibility":"高|中|低","importance":0,"category":"地缘政治|全球市场|宏观政策|贸易供应链|中国经济|科技能源|综合"}}]}}"""

OVERVIEW_PROMPT = """今天是 {date}。以下是过去 24 小时全球情报中评分最高的标题：

{titles}

请用中文写 3 条「今日主线」，每条不超过 40 个汉字，只写事实性概括与市场含义，不预测点位、不编造数据。输出 JSON：{{"lines":["","",""]}}"""


class LLM:
    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: int = 120,
        max_calls: int = 3,
    ):
        self.api_key = api_key or ""
        self.api_base = (api_base or "https://api.deepseek.com/v1").rstrip("/")
        self.model = model or "deepseek-chat"
        self.timeout = timeout
        self.max_calls = max_calls
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _chat(self, messages, max_tokens=3200):
        if self.calls >= self.max_calls:
            log.warning("LLM 调用次数已达上限 %s，跳过", self.max_calls)
            return ""
        self.calls += 1
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(2):
            try:
                resp = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )
                if resp.status_code == 400 and "response_format" in payload:
                    payload.pop("response_format", None)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                log.warning("LLM 请求失败（第 %s 次）：%s", attempt + 1, exc)
        return ""

    def analyze(self, clusters):
        """返回 (briefs_by_key, groups_of_keys)。"""
        briefs = {}
        groups = []
        pending = list(clusters)
        batch_size = 8
        for start in range(0, len(pending), batch_size):
            if not self.enabled or self.calls >= self.max_calls:
                break
            batch = pending[start : start + batch_size]
            lines = []
            for idx, cluster in enumerate(batch, 1):
                when = cluster.latest_pub or cluster.last_at
                lines.append(
                    json.dumps(
                        {
                            "id": idx,
                            "sources": cluster.sources[:4],
                            "time": when.strftime("%m-%d %H:%M") if when else "",
                            "title": cluster.title,
                            "summary": cluster.summary[:160],
                        },
                        ensure_ascii=False,
                    )
                )
            prompt = ANALYZE_PROMPT.format(
                date=now_local().strftime("%Y-%m-%d"),
                count=len(batch),
                events="\n".join(lines),
            )
            content = self._chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            data = extract_json(content)
            if not data or not isinstance(data.get("events"), list):
                log.warning("LLM 返回无法解析，改用规则简报")
                continue
            for raw in data["events"]:
                ids = raw.get("ids")
                if not isinstance(ids, list):
                    ids = [raw.get("id")]
                members = []
                for value in ids:
                    try:
                        idx = int(value)
                    except Exception:
                        continue
                    if 1 <= idx <= len(batch):
                        members.append(batch[idx - 1])
                if not members:
                    continue
                unique = []
                for member in members:
                    if member not in unique:
                        unique.append(member)
                merged = merge_clusters(unique) if len(unique) > 1 else unique[0]
                brief = clean_brief(raw, merged)
                briefs[merged.key] = brief
                for member in unique:
                    briefs[member.key] = brief
                groups.append([member.key for member in unique])
        return briefs, groups

    def overview(self, clusters) -> str:
        if not self.enabled or not clusters:
            return ""
        titles = "\n".join(
            f"{i}. [{c.sources[0] if c.sources else ''}] {c.title}"
            for i, c in enumerate(clusters[:8], 1)
        )
        content = self._chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": OVERVIEW_PROMPT.format(
                        date=now_local().strftime("%Y-%m-%d"), titles=titles
                    ),
                },
            ],
            max_tokens=600,
        )
        data = extract_json(content) or {}
        lines = [str(x).strip() for x in data.get("lines", []) if str(x).strip()]
        return "\n".join(f"· {line}" for line in lines[:3])


def _clip(value, limit: int) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def clean_brief(raw: dict, cluster) -> dict:
    impact = raw.get("impact") or {}
    if not isinstance(impact, dict):
        impact = {}

    def as_list(key):
        values = impact.get(key) or []
        if isinstance(values, str):
            values = [values]
        return [_clip(v, 12) for v in values if str(v).strip()][:4]

    try:
        importance = float(raw.get("importance", 0))
    except Exception:
        importance = 0.0

    category = str(raw.get("category") or "综合").strip()
    if category not in CATEGORIES:
        category = "综合"

    credibility = CREDIBILITY.get(str(raw.get("credibility", "")).strip().lower(), "中")

    return {
        "title_zh": _clip(raw.get("title_zh") or cluster.title, 60),
        "summary": _clip(raw.get("summary"), 110),
        "background": _clip(raw.get("background"), 160),
        "impact": {
            "countries": as_list("countries"),
            "sectors": as_list("sectors"),
            "markets": as_list("markets"),
        },
        "unverified": _clip(raw.get("unverified") or "暂无未证实信息", 90),
        "credibility": credibility,
        "importance": max(0.0, min(10.0, importance)),
        "category": category,
    }


def fallback_brief(cluster) -> dict:
    body = cluster.summary or cluster.title
    return {
        "_fallback": True,
        "title_zh": _clip(cluster.title, 60),
        "summary": _clip(body, 100),
        "background": "规则模式生成，未调用 AI 交叉验证。",
        "impact": {"countries": [], "sectors": [], "markets": []},
        "unverified": "未经 AI 核实，请以原文为准",
        "credibility": "低",
        "importance": round(cluster.rule_score / 7 * 10, 1),
        "category": "综合",
    }