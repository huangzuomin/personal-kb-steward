from __future__ import annotations

from renderer import render


def execute(context: dict) -> dict:
    task = {
        "topic": context.get("topic") or context.get("query") or "",
        "requested_doc_type": context.get("requested_doc_type", ""),
        "reader_role": context.get("reader_role", ""),
        "purpose": context.get("purpose", ""),
        "deadline": context.get("deadline", ""),
    }
    material_pack = context.get("material_pack", {}) or {}
    evidence_pack = context.get("evidence_pack", {}) or {}
    source_refs = context.get("source_refs") or material_pack.get("sources") or evidence_pack.get("sources") or []
    known_gaps = context.get("known_gaps") or material_pack.get("gaps") or evidence_pack.get("gaps") or []
    risk_notes = context.get("risk_notes") or material_pack.get("risks") or material_pack.get("risks_and_gaps") or []

    item = {
        "title": f"机关材料交接包：{task['topic'][:60] or '未命名任务'}",
        "type": "official-material-handoff",
        "task": task,
        "material_pack_ref": context.get("material_pack_ref", "material-pack.md"),
        "evidence_pack_ref": context.get("evidence_pack_ref", "evidence-pack.md"),
        "source_refs": source_refs,
        "known_gaps": known_gaps,
        "risk_notes": risk_notes,
        "recommended_next_step": context.get("recommended_next_step") or "交由 official-material-workflow 生成 TaskBrief、草稿和 ReviewReport。",
    }

    content = render(item)
    return {
        "skill": "official-material-handoff",
        "pages": [{
            "rel_dir_key": "reports_dir",
            "filename": "official-material-handoff.md",
            "content": content,
            "sources": source_refs,
            "item": item,
        }],
        "processed": len(source_refs),
        "inputs": source_refs,
        "issues": [],
        "items": [item],
    }
