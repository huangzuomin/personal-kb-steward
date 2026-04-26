"""Jinja2-based Markdown page renderer for all Skill outputs."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    _JINJA2_AVAILABLE = True
except ImportError:
    _JINJA2_AVAILABLE = False

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _make_env() -> "Environment":
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    env.filters["lower"] = lambda v: str(v).lower()
    return env


def render_template(template_name: str, context: dict[str, Any]) -> str:
    """
    Render a Jinja2 template from core/templates/<template_name>.
    Falls back to a plain YAML+body dump if Jinja2 is not available.
    """
    ctx = {
        "today": dt.date.today().isoformat(),
        "title": context.get("title", ""),
        "type": context.get("type", ""),
        "status": context.get("status", "manual_review"),
        "stage": context.get("stage", "needs_context"),
        "sources": context.get("sources", []),
        "related": context.get("related", []),
        "tags": context.get("tags", []),
        "confidence": context.get("confidence", "low"),
        "review_required": str(bool(context.get("review_required", True))).lower(),
        **context,
    }
    if not _JINJA2_AVAILABLE:
        # minimal fallback: just frontmatter + body
        fm_lines = [
            "---",
            f"title: {json.dumps(ctx['title'], ensure_ascii=False)}",
            f"type: {ctx['type']}",
            f"status: {ctx['status']}",
            f"stage: {ctx['stage']}",
            f"created: {ctx['today']}",
            f"updated: {ctx['today']}",
            f"sources: {json.dumps(ctx['sources'], ensure_ascii=False)}",
            f"related: {json.dumps(ctx['related'], ensure_ascii=False)}",
            f"tags: {json.dumps(ctx['tags'], ensure_ascii=False)}",
            f"confidence: {ctx['confidence']}",
            f"review_required: {ctx['review_required']}",
            "---",
            "",
            f"# {ctx['title']}",
            "",
            ctx.get("summary", ""),
        ]
        return "\n".join(fm_lines)
    env = _make_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(**ctx)
