from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

from .vault import Note


def today() -> str:
    return dt.datetime.now().date().isoformat()


def note_summary(note: Note, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", note.body).strip()
    if not text:
        return note.title
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def frontmatter(
    title: str,
    type_: str,
    status: str,
    source: list[str],
    related: list[str] | None = None,
    tags: list[str] | None = None,
    confidence: str = "medium",
    review_required: bool | None = None,
    stage: str | None = None,
) -> str:
    if review_required is None:
        review_required = status in {"manual_review", "conflict"} or stage in {"insufficient", "weak", "unsupported", "needs_context"}
    return "\n".join([
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {type_}",
        f"status: {status}",
        f"stage: {stage or status}",
        f"created: {today()}",
        f"updated: {today()}",
        f"sources: {json.dumps(source, ensure_ascii=False)}",
        f"related: {json.dumps(related or [], ensure_ascii=False)}",
        f"tags: {json.dumps(tags or [], ensure_ascii=False)}",
        f"confidence: {confidence}",
        f"review_required: {str(review_required).lower()}",
        "---",
        "",
    ])


def slug(text: str, fallback: str = "page") -> str:
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if ascii_part:
        return ascii_part[:80]
    return f"{fallback}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:10]}"


def bullet(items: list[str], empty: str) -> str:
    return "".join(f"- {item}\n" for item in items) if items else f"- {empty}\n"
