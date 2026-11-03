from __future__ import annotations

# 热榜来源混杂社会/娱乐新闻：强词命中 1 个即保留；弱词需命中 2 个。
STRONG_CN = (
    "美联储", "FOMC", "降息", "加息", "通胀", "CPI", "国债", "收益率", "A股", "港股",
    "美股", "原油", "布伦特", "关税", "制裁", "出口管制", "稀土", "半导体", "芯片",
    "英伟达", "台积电", "光刻机", "以色列", "伊朗", "俄罗斯", "乌克兰", "北约",
    "军演", "演习", "大选", "政变", "空袭", "导弹", "停火", "断交", "降准",
    "地方债", "证监会", "楼市", "房地产", "比特币", "加密货币", "黄金", "白银",
    "美联储", "非农", "北向资金", "债务违约", "熔断", "暴跌", "暴涨",
)

WEAK_CN = (
    "美国", "中国", "欧盟", "日本", "韩国", "台湾", "朝鲜", "沙特", "土耳其",
    "印度", "德国", "法国", "英国", "战争", "冲突", "能源", "电力", "煤炭",
    "央行", "财政", "GDP", "PMI", "就业", "失业", "供应链", "航运", "港口",
    "汇率", "外汇", "美元", "人民币", "股市", "债市", "油价",
)

STRONG_EN = (
    "fomc", "rate cut", "rate hike", "inflation", "treasury", "tariff", "sanction",
    "export control", "semiconductor", "chip", "nvidia", "tsmc", "opec", "brent",
    "airstrike", "missile", "ceasefire", "coup", "nato", "israel", "iran",
    "russia", "ukraine", "pboc", "yuan", "bitcoin", "crypto", "gold price",
)

WEAK_EN = (
    "fed", "stocks", "bond", "dollar", "gold", "oil", "china", "japan", "korea",
    "taiwan", "saudi", "turkey", "india", "germany", "election", "war",
    "conflict", "energy", "supply chain", "shipping", "recession",
)


def is_relevant(item) -> bool:
    """RSS 源已人工筛选，全部保留；热榜只保留财经/地缘相关条目。"""
    if item.get("kind") == "rss":
        return True
    text = (item.get("title") or "").lower()
    if any(term.lower() in text for term in STRONG_CN):
        return True
    if any(term in text for term in STRONG_EN):
        return True
    weak = sum(1 for term in WEAK_CN if term.lower() in text)
    weak += sum(1 for term in WEAK_EN if term in text)
    return weak >= 2