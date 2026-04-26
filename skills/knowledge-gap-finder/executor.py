from __future__ import annotations

from renderer import render


_GAP_TYPES = [
    ("缺案例", "来源中未找到具体案例，写作时论据会空洞。", "high", "寻找具体的机构、项目或事件案例。", "case-story-bank-builder"),
    ("缺时间线", "事件发展脉络不清，难以说明因果关系。", "medium", "梳理关键事件节点和日期。", "writing-evidence-harvester"),
    ("缺反方", "只有支持方来源，论点单薄，易被质疑。", "high", "主动寻找反例或持不同立场的来源。", "claim-evidence-checker"),
    ("缺数据", "缺少可量化证据，主张缺乏说服力。", "medium", "查找统计数字、调研报告或公开数据。", "writing-evidence-harvester"),
    ("缺一手来源", "现有来源均为二手引用，可信度存疑。", "medium", "寻找官方文件、当事人访谈或原始报告。", "writing-evidence-harvester"),
    ("缺可引用段落", "没有能直接引用的具体原文，引述会过于概括。", "low", "回到原文，找到可直接引用的段落。", "writing-evidence-harvester"),
]


def execute(context: dict) -> dict:
    """
    knowledge-gap-finder executor.
    输入：query（主题）+ notes（来源笔记）+ evidence_items
    输出：gap-report，明确指出缺什么、风险是什么、建议如何补
    """
    query = context.get("query", "")
    notes = context.get("notes", [])
    evidence_items = context.get("evidence_items", [])
    sources = [n["rel"] for n in notes]

    has_cases = any(i.get("kind") == "案例" for i in evidence_items)
    has_timeline = bool(context.get("timeline"))
    has_data = any("%" in i.get("text", "") or "万" in i.get("text", "") or "亿" in i.get("text", "") for i in evidence_items)

    gap_items = []
    for gap_type, desc, priority, path, skill in _GAP_TYPES:
        if gap_type == "缺案例" and has_cases:
            continue
        if gap_type == "缺时间线" and has_timeline:
            continue
        if gap_type == "缺数据" and has_data:
            continue
        if gap_type == "缺一手来源" and len(sources) >= 3:
            continue
        gap_items.append({
            "type": gap_type,
            "description": desc,
            "priority": priority,
            "risk": f"如果不补充「{gap_type}」，写出的内容将缺乏说服力或被质疑。",
            "suggested_path": path,
            "next_skill": skill,
        })

    # 始终补充反方和可引用段落（几乎永远缺）
    if not any(g["type"] == "缺反方" for g in gap_items):
        gap_items.append({
            "type": "缺可引用段落",
            "description": "找到具体可引用的段落，避免过于概括。",
            "priority": "low",
            "risk": "引述过于概括，读者无法验证。",
            "suggested_path": "回到原文，标记关键段落。",
            "next_skill": "writing-evidence-harvester",
        })

    enough_sources = len(sources) >= 2
    item = {
        "title": f"知识缺口报告：{query[:60] or '未命名主题'}",
        "type": "gap-report",
        "status": "growing" if enough_sources else "manual_review",
        "stage": "open",
        "sources": sources,
        "related": [],
        "tags": ["知识缺口"],
        "confidence": "medium" if enough_sources else "low",
        "review_required": not enough_sources,
        # 模板字段
        "current_topic": query or "请补充选题描述。",
        "gap_items": gap_items,
        "manual_review": [] if enough_sources else ["来源不足，缺口分析可能不完整，需要人工确认。"],
    }

    content = render(item)
    return {
        "skill": "knowledge-gap-finder",
        "pages": [{
            "rel_dir_key": "gaps_dir",
            "filename": "gap-report.md",
            "content": content,
            "sources": sources,
            "item": item,
        }],
        "processed": len(gap_items),
        "inputs": sources,
        "issues": [],
        "items": [item],
    }
