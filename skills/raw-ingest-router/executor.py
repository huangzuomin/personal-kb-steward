from __future__ import annotations

import json
from typing import Any

from core.llm import call_chat_completion

def execute(context: dict[str, Any]) -> dict[str, Any]:
    notes = context.get("notes", [])
    cfg = context.get("config", {})
    use_llm = context.get("use_llm", True)

    routing_map = {
        "seed": [],
        "work_memory": [],
        "research_report": [],
        "unclear": [],
    }
    issues = []
    processed = 0

    if not notes:
        return {"routing_map": routing_map, "issues": issues, "processed": 0, "created": []}

    if not use_llm:
        # Mock logic
        for note in notes:
            routing_map["unclear"].append(note)
        return {
            "skill": "raw-ingest-router",
            "routing_map": routing_map,
            "issues": issues,
            "processed": len(notes),
            "created": [],
        }

    system_prompt = """你是一个自动分类器。请阅读用户提供的笔记内容，将其归类为以下之一：
- `seed`: 短片段、摘录、灵感、碎碎念。
- `work_memory`: 会议纪要、项目复盘、周报、待办事项。
- `research_report`: 行业报告、学术论文、长篇调研、案例分析。
- `unclear`: 混合内容或无法确定。

返回 JSON 格式：{"category": "<分类名称>"}
"""
    for note in notes:
        text = f"Title: {note.get('title', '')}\n\n{note.get('body', '')[:3000]}"
        try:
            resp = call_chat_completion(cfg, system_prompt, {"text": text})
            data = json.loads(resp)
            category = data.get("category", "unclear")
            if category in routing_map:
                routing_map[category].append(note)
            else:
                routing_map["unclear"].append(note)
            processed += 1
        except Exception as e:
            issues.append(f"分类失败 {note.get('rel')}: {e}")
            routing_map["unclear"].append(note)

    return {
        "skill": "raw-ingest-router",
        "routing_map": routing_map,
        "issues": issues,
        "processed": processed,
        "created": [],
    }
