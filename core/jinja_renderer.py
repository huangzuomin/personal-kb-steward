"""Jinja2-based Markdown page renderer for all Skill outputs."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

_JINJA2_IMPORT_ERROR: ImportError | None = None

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    _JINJA2_AVAILABLE = True
except ImportError as exc:
    _JINJA2_AVAILABLE = False
    _JINJA2_IMPORT_ERROR = exc

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class RendererDependencyError(RuntimeError):
    """Do not silently discard fields when a required renderer is missing."""


def require_renderer() -> None:
    if not _JINJA2_AVAILABLE:
        raise RendererDependencyError(
            "Jinja2 不可用，已停止渲染；请使用当前 Python 执行 python -m pip install -r requirements.txt。"
        ) from _JINJA2_IMPORT_ERROR


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
    Missing dependencies fail closed; no summary-only substitute is produced.
    """
    require_renderer()
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
        "origin": context.get("origin", {"source_paths": context.get("sources", [])}),
        **context,
    }
    env = _make_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(**ctx)


def render_markdown(template_name: str, context: dict[str, Any]) -> str:
    return render_template(template_name, context)
