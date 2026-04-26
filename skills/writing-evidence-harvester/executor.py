from __future__ import annotations

from renderer import render


def execute(context: dict) -> dict:
    """
    writing-evidence-harvester executor.
    输入：query（选题）+ notes（来源笔记列表）
    输出：evidence-pack 页面，结构化拆分事实/案例/数据/时间线/反方/缺口
    """
    query = context.get("query", "")
    notes = context.get("notes", [])
    evidence_items = context.get("evidence_items", [])
    timeline = context.get("timeline", [])
    sources = [n["rel"] for n in notes]

    facts = [i for i in evidence_items if i.get("kind") in ("事实线索", "事实")]
    cases = [i for i in evidence_items if i.get("kind") == "案例"]
    enough = len(evidence_items) >= 5 and len(sources) >= 2

    item = {
        "title": f"证据包：{query[:60] or '未命名主题'}",
        "type": "evidence-pack",
        "status": "compiled" if enough else "manual_review",
        "stage": "compiled" if enough else "insufficient",
        "sources": sources,
        "related": [],
        "tags": ["证据包"],
        "confidence": "medium" if enough else "low",
        "review_required": not enough,
        # 模板字段
        "topic_scope": query or "请在此说明选题边界。",
        "facts": [{"source": f["source"], "text": f["text"]} for f in facts[:10]],
        "cases": [{"source": c["source"], "text": c["text"]} for c in cases[:8]],
        "data_points": [],
        "people_orgs": [],
        "timeline": timeline[:20],
        "counter_views": [],
        "quotable": [],
        "evidence_strength": "medium" if enough else "insufficient — 来源不足，请补充后再进入写作环节。",
        "source_limits": ["所有证据需回到原文确认上下文后方可引用。"],
        "gaps": [] if enough else ["来源数量不足", "缺少反方观点", "缺少可直接引用段落"],
        "manual_review": [] if enough else ["来源不足，需要人工确认再进入 material-pack。"],
    }

    content = render(item)
    return {
        "skill": "writing-evidence-harvester",
        "pages": [{
            "rel_dir_key": "evidence_dir",
            "filename": f"evidence-pack.md",
            "content": content,
            "sources": sources,
            "item": item,
        }],
        "processed": len(notes),
        "inputs": sources,
        "issues": [] if enough else ["证据不足，生成 manual_review evidence-pack。"],
        "items": [item],
    }
