from __future__ import annotations

import json
from typing import Any


def render_preview(item: dict[str, Any]) -> str:
    title = item.get("title", "Untitled")
    sources = item.get("sources", [])
    lines = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {item.get('type', 'unknown')}",
        f"status: {item.get('status', 'manual_review')}",
        f"stage: {item.get('stage', 'needs_context')}",
        f"sources: {json.dumps(sources, ensure_ascii=False)}",
        f"related: {json.dumps(item.get('related', []), ensure_ascii=False)}",
        f"confidence: {item.get('confidence', 'low')}",
        f"review_required: {str(bool(item.get('review_required', True))).lower()}",
        "---",
        "",
        f"# {title}",
        "",
        "## Summary",
        "",
        str(item.get("summary", "")),
        "",
        "## Sources",
        "",
    ]
    lines.extend(f"- {source}" for source in sources)
    lines.extend(["", "## Pending Links", ""])
    pending = item.get("pending_links", [])
    lines.extend(f"- {link}" for link in pending) if pending else lines.append("- None")
    lines.extend(["", "## Manual Review", ""])
    manual = item.get("manual_review", [])
    lines.extend(f"- {issue}" for issue in manual) if manual else lines.append("- None")
    return "\n".join(lines)


def render_previews(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"title": item.get("title"), "preview": render_preview(item)} for item in data.get("items", [])]
