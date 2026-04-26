from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_contract import extract_json, validate_contract
from .llm import LLMError, call_chat_completion, mock_skill_response
from .renderer import render_previews
from .skill_loader import build_system_prompt, load_skill
from .validator import validate_skill_items


def run_skill_runtime(
    root: Path,
    cfg: dict[str, Any],
    skill_name: str,
    task: str,
    documents: list[dict[str, str]],
    *,
    mock: bool = False,
) -> dict[str, Any]:
    spec = load_skill(root, skill_name)
    payload = {
        "task": task,
        "skill": skill_name,
        "output_contract": {
            "top_level": "items",
            "required_item_keys": [
                "title",
                "type",
                "status",
                "stage",
                "sources",
                "summary",
                "confidence",
                "review_required",
            ],
            "forbidden": ["source", "full_article", "draft_article"],
        },
        "documents": documents,
    }
    try:
        if mock:
            data = mock_skill_response(skill_name, task, documents)
            raw_text = json.dumps(data, ensure_ascii=False)
        else:
            raw_text = call_chat_completion(cfg, build_system_prompt(spec), payload)
            data = extract_json(raw_text)
    except (LLMError, json.JSONDecodeError, FileNotFoundError, KeyError) as exc:
        return {
            "enabled": True,
            "mock": mock,
            "skill": skill_name,
            "skill_path": str(spec.path) if "spec" in locals() else "",
            "ok": False,
            "issues": [str(exc)],
            "items": [],
            "previews": [],
        }

    allowed_sources = {doc["path"] for doc in documents}
    issues = validate_contract(data)
    issues.extend(validate_skill_items(data, allowed_sources))
    return {
        "enabled": True,
        "mock": mock,
        "skill": skill_name,
        "skill_path": str(spec.path),
        "ok": not issues,
        "issues": issues,
        "items": data.get("items", []),
        "previews": render_previews(data),
        "raw_chars": len(raw_text),
    }
