import re
from typing import Any

from core.jinja_renderer import render_markdown


def slug(text: str, fallback: str = "topic") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text).strip()
    cleaned = re.sub(r"[，。；;、\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", cleaned).strip("-").lower()
    return (cleaned or ascii_part or fallback)[:72]


def short_hash(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def render(data: dict[str, Any]) -> list[dict[str, Any]]:
    source_rel = data.get("source_rel", "")
    source_name = source_rel.split("/")[-1].replace(".md", "")
    source_target = f"wiki/sources/source-{slug(source_name, 'source')}-{short_hash(source_rel)}.md"
    topic_specs = [
        {**topic, "title": topic.get("title", f"Topic-{idx}")}
        for idx, topic in enumerate(data.get("topics", []))
    ]

    source_content = render_markdown("source_note.j2", {
        "title": f"Source: {data.get('source_title', source_name)}",
        "type": "source-note",
        "status": "growing",
        "stage": "compiled",
        "source_rel": source_rel,
        "sources": [source_rel],
        "tags": ["source"],
        "confidence": "high",
        "review_required": False,
        "origin": {"source_paths": [source_rel], "operation": "topic-research-compile"},
        "summary": data.get("source_summary", ""),
        "topics": topic_specs,
        "key_facts": data.get("key_facts", []),
        "quality_flags": data.get("quality_flags", []),
        "analysis_mode": data.get("analysis_mode", "unknown"),
    })
    return [{
        "skill": "topic-research-compile",
        "target": source_target,
        "sources": [source_rel],
        "content": source_content,
        "analysis_mode": data.get("analysis_mode", "unknown"),
        "review_required": False,
        "confidence": "high",
    }]
