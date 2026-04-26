from __future__ import annotations

from renderer import render


def execute(context: dict) -> dict:
    """
    writing-material-pack executor.
    输入：query（选题）+ notes + evidence_items + timeline
    输出：material-pack，包含可选写作角度和写作前检查清单
    """
    query = context.get("query", "")
    notes = context.get("notes", [])
    evidence_items = context.get("evidence_items", [])
    timeline = context.get("timeline", [])
    sources = [n["rel"] for n in notes]

    facts = [f"{i['kind']}：{i['text']}" for i in evidence_items if i.get("kind") in ("事实线索", "事实")]
    cases = [f"{i['kind']}：{i['text']}" for i in evidence_items if i.get("kind") == "案例"]
    has_counter = False  # 需要人工补充

    enough = len(evidence_items) >= 5 and cases

    writing_angles = []
    if evidence_items:
        writing_angles = [
            {
                "angle": "机制解释型",
                "core_claim": "解释\u300c" + query + "\u300d\u80cc\u540e\u7684\u8fd0\u4f5c\u903b\u8f91\u3002",
                "required_evidence": "事实 + 案例 + 时间线",
                "risk": "如果没有足够案例，会流于抽象。",
            },
            {
                "angle": "案例对比型",
                "core_claim": "\u7528\u5177\u4f53\u6848\u4f8b\u5bf9\u6bd4\u8bf4\u660e\u300c" + query + "\u300d\u7684\u5dee\u5f02\u3002",
                "required_evidence": "至少 2 个对比案例 + 反方观点",
                "risk": "缺少反方时，读者会质疑选择性引用。",
            },
        ]

    item = {
        "title": f"写作材料包：{query[:60] or '未命名选题'}",
        "type": "material-pack",
        "status": "compiled" if enough else "manual_review",
        "stage": "draft_ready" if enough else "insufficient",
        "sources": sources,
        "related": [],
        "tags": ["写作材料包"],
        "confidence": "medium" if enough else "low",
        "review_required": not enough,
        # 模板字段
        "topic_title": query or "请补充选题。",
        "core_tension": "需要人工提炼：这个选题的核心张力是什么？" if not enough else ("围绕\u300c" + query + "\u300d的核心张力：[待人工填写]"),
        "facts": facts[:10],
        "cases": cases[:8],
        "data_points": [],
        "timeline": timeline[:15],
        "people_orgs": [],
        "pro_views": [f"{i['text']}" for i in evidence_items[:3]],
        "counter_views": [],
        "risks_and_gaps": (
            ["缺少反方来源，写作前必须补充。"] if not has_counter else []
        ) + (
            ["证据条目不足，写作可信度存疑。"] if not enough else []
        ),
        "writing_angles": writing_angles,
        "dont_write": [
            "不要在没有具体案例支撑的情况下直接写结论段。",
            "不要把摘要当作直接引用。",
        ],
        "pre_write_checklist": [
            "确认核心论点有至少 2 个独立来源支撑。",
            "确认反方观点已纳入并标注。",
            "确认所有案例上下文已回到原文确认。",
            "确认 evidence-pack 已达到 compiled 状态。",
        ],
        "manual_review": [] if enough else [
            "证据不足，建议先运行 writing-evidence-harvester 补充证据。",
            "缺少反方来源，需要人工补充后再写。",
        ],
    }

    content = render(item)
    return {
        "skill": "writing-material-pack",
        "pages": [{
            "rel_dir_key": "materials_dir",
            "filename": "material-pack.md",
            "content": content,
            "sources": sources,
            "item": item,
        }],
        "processed": len(notes),
        "inputs": sources,
        "issues": [] if enough else ["证据不足，生成 manual_review material-pack。"],
        "items": [item],
    }
