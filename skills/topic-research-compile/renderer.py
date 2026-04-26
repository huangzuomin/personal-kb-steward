import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from core.jinja_renderer import render_markdown


def slug(text: str) -> str:
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if ascii_part:
        return ascii_part[:72]
    return "topic-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def render(data: dict[str, Any]) -> list[dict[str, Any]]:
    pages = []
    rid = run_id()
    
    # 1. Render source note
    source_rel = data.get("source_rel", "")
    source_name = source_rel.split("/")[-1].replace(".md", "")
    source_target = f"wiki/sources/source-{slug(source_name)}.md"
    source_content = render_markdown("source_note.j2", {
        "title": f"Source: {data.get('source_title', source_name)}",
        "source_rel": source_rel,
        "summary": data.get("source_summary", ""),
        "topics": data.get("topics", [])
    })
    pages.append({
        "skill": "topic-research-compile",
        "target": source_target,
        "content": source_content,
        "manual_review": {
            "type": "new_source_note",
            "risk": "P2",
            "reason": "自动生成 Source Note，需确认摘要准确性。",
            "sources": [source_rel]
        }
    })

    # 2. Render topic pages
    for idx, topic in enumerate(data.get("topics", [])):
        topic_title = topic.get("title", f"Topic-{idx}")
        topic_target = f"wiki/topics/topic-{slug(topic_title)}-{rid}-{idx}.md"
        topic_content = render_markdown("topic_stub.j2", {
            "title": topic_title,
            "source_rel": source_rel,
            "source_target": source_target,
            "content": topic.get("content", ""),
        })
        pages.append({
            "skill": "topic-research-compile",
            "target": topic_target,
            "content": topic_content,
            "manual_review": {
                "type": "new_topic_stub",
                "risk": "P1",
                "reason": "自动从长文提炼出新 Topic 雏形，需人工确认边界与命名。",
                "sources": [source_rel]
            }
        })
        
    return pages
