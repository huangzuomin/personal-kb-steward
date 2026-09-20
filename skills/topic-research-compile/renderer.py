import re
from typing import Any

from core.layout import relative_dir
from core.jinja_renderer import render_markdown
from core.content_safety import assert_safe_content


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
    assert_safe_content(data)
    mode = str(data.get("analysis_mode") or "unknown")
    flags = data.get("quality_flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ValueError("quality_flags must be an array of strings")
    facts = data.get("key_facts", [])
    if not isinstance(facts, list) or not all(isinstance(fact, str) for fact in facts):
        raise ValueError("key_facts must be an array of strings")
    summary = data.get("source_summary", "")
    if not isinstance(summary, str):
        raise ValueError("source_summary must be a string")
    flags = list(flags)
    if not summary.strip() or not facts:
        flags.append("摘要或关键事实不足，需要人工复核。")
    review = mode != "llm" or bool(flags)
    confidence = "low" if review else "medium"
    source_rel = data.get("source_rel", "")
    source_name = source_rel.split("/")[-1].replace(".md", "")
    sources_dir = relative_dir(data.get("sources_dir") or "wiki/sources")
    source_target = f"{sources_dir}/source-{slug(source_name, 'source')}-{short_hash(source_rel)}.md"
    topic_specs = [
        {**topic, "title": topic.get("title", f"Topic-{idx}")}
        for idx, topic in enumerate(data.get("topics", []))
    ]

    source_content = render_markdown("source_note.j2", {
        "title": f"Source: {data.get('source_title', source_name)}",
        "type": "source-note",
        "status": "manual_review" if review else "growing",
        "stage": "needs_context" if review else "compiled",
        "source_rel": source_rel,
        "sources": [source_rel],
        "tags": ["source"],
        "confidence": confidence,
        "review_required": review,
        "origin": {"source_paths": [source_rel], "operation": "topic-research-compile"},
        "summary": summary,
        "topics": topic_specs,
        "key_facts": facts,
        "quality_flags": flags,
        "analysis_mode": mode,
    })
    return [{
        "skill": "topic-research-compile",
        "target": source_target,
        "sources": [source_rel],
        "content": source_content,
        "quality_flags": flags,
        "analysis_mode": mode,
        "review_required": review,
        "confidence": confidence,
    }]
