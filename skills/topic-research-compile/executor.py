from __future__ import annotations

import json
from typing import Any

from core.llm import call_chat_completion
from renderer import render


def execute(context: dict[str, Any]) -> dict[str, Any]:
    notes = context.get("notes", [])
    cfg = context.get("config", {})
    use_llm = context.get("use_llm", True)

    created = []
    issues = []
    processed = 0

    if not notes:
        return {"skill": "topic-research-compile", "created": [], "issues": issues, "processed": 0}

    system_prompt = """你是一个专业的行业研究员。请阅读这篇长文调研报告/文章，提取以下信息：
1. 提炼出 1-3 个核心的“概念”或“论点”作为拟定专题（Topic）的名称。
2. 撰写一段关于这篇来源文档的结构化摘要（Source Note Content）。
3. 针对提取的每一个 Topic，写一段简短的研究边界或核心关注点（Topic Stub Content）。

返回 JSON 格式：
{
  "source_summary": "...",
  "topics": [
    {
      "topic_title": "...",
      "topic_stub_content": "..."
    }
  ]
}
"""

    for note in notes:
        if not use_llm:
            # Mock behavior
            pages = render({
                "source_rel": note.get("rel"),
                "source_title": note.get("title"),
                "source_summary": "Mock summary for dry-run.",
                "topics": [{"title": f"Topic from {note.get('title')}", "content": "Mock stub content"}]
            })
            created.extend(pages)
            processed += 1
            continue

        text = f"Title: {note.get('title', '')}\n\n{note.get('body', '')[:4000]}"
        try:
            resp = call_chat_completion(cfg, system_prompt, {"text": text})
            data = json.loads(resp)
            
            pages = render({
                "source_rel": note.get("rel"),
                "source_title": note.get("title"),
                "source_summary": data.get("source_summary", ""),
                "topics": [
                    {"title": t.get("topic_title", ""), "content": t.get("topic_stub_content", "")}
                    for t in data.get("topics", [])
                ]
            })
            created.extend(pages)
            processed += 1
        except Exception as e:
            issues.append(f"提炼报告失败 {note.get('rel')}: {e}")

    return {
        "skill": "topic-research-compile",
        "created": created,
        "issues": issues,
        "processed": processed,
    }
