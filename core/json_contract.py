from __future__ import annotations

import json
import re
from typing import Any


REQUIRED_ITEM_KEYS = {
    "title",
    "type",
    "status",
    "stage",
    "sources",
    "summary",
    "confidence",
    "review_required",
}


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def validate_contract(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(data, dict) or "items" not in data or not isinstance(data["items"], list):
        issues.append("LLM JSON must contain an items list.")
        return issues
    for idx, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            issues.append(f"items[{idx}] must be an object.")
            continue
        missing = sorted(REQUIRED_ITEM_KEYS - set(item))
        if missing:
            issues.append(f"items[{idx}] missing keys: {', '.join(missing)}")
        for key in ("sources", "related", "pending_links", "manual_review"):
            if key in item and (not isinstance(item[key], list) or not all(isinstance(v, str) for v in item[key])):
                issues.append(f"items[{idx}].{key} must be an array of strings.")
        for key in ("title", "type", "status", "stage", "summary", "confidence"):
            if key in item and not isinstance(item[key], str):
                issues.append(f"items[{idx}].{key} must be a string.")
        if "review_required" in item and type(item["review_required"]) is not bool:
            issues.append(f"items[{idx}].review_required must be a boolean.")
        if item.get("type") == "topic-card":
            for key in ("why_now", "signals", "angles", "risks", "gaps"):
                if key in item and (not isinstance(item[key], list) or not all(isinstance(v, str) for v in item[key])):
                    issues.append(f"items[{idx}].{key} must be an array of strings.")
            for key in ("one_sentence_topic", "tension", "score"):
                if key in item and not isinstance(item[key], str):
                    issues.append(f"items[{idx}].{key} must be a string.")
        if item.get("source"):
            issues.append(f"items[{idx}] uses legacy source; use sources.")
    return issues
