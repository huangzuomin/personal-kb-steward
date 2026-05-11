from __future__ import annotations

from renderer import render


def infer_official_evidence_level(source_type: str, text: str) -> str:
    haystack = f"{source_type} {text}"
    if any(key in haystack for key in ("法律", "法规", "国家标准", "正式批示", "会议决定")):
        return "E5"
    if any(key in haystack for key in ("正式文件", "官方通报", "正式报表", "规范性文件")):
        return "E4"
    if any(key in haystack for key in ("内部台账", "会议纪要", "调研记录", "工作总结")):
        return "E3"
    if any(key in haystack for key in ("主流媒体", "研究报告", "公开论文", "第三方报告")):
        return "E2"
    if any(key in haystack for key in ("截图", "网传", "网络评论", "未核实", "线索")):
        return "E1"
    return "E0" if not source_type else "E3"


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
    source_type = context.get("source_type") or (evidence_items[0].get("source_type", "") if evidence_items else "")
    all_text = " ".join(str(i.get("text", "")) for i in evidence_items)
    evidence_level = context.get("evidence_level") or infer_official_evidence_level(source_type, all_text)

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
        "evidence_level": evidence_level,
        "source_type": source_type or "未标注来源类型",
        "verification_status": context.get("verification_status") or ("待人工复核" if not enough else "初步整理"),
        "can_support": context.get("can_support") or (["内部工作情况", "问题描述"] if evidence_level in ("E3", "E4", "E5") else ["背景补充", "线索观察"]),
        "cannot_support": context.get("cannot_support") or (["对外正式定性"] if evidence_level in ("E2", "E1", "E0") else ["未经授权的责任认定"]),
        "usage_note": context.get("usage_note") or "供机关材料系统消费前，仍需按具体文种和使用场景复核。",
        "publicity_risk": context.get("publicity_risk") or "未判断公开属性。",
        "secrecy_risk": context.get("secrecy_risk") or "未判断保密风险。",
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
