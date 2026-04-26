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
    if "items" not in data or not isinstance(data["items"], list):
        issues.append("LLM JSON must contain an items list.")
        return issues
    for idx, item in enumerate(data["items"]):
        if not isinstance(item, dict):
            issues.append(f"items[{idx}] must be an object.")
            continue
        missing = sorted(REQUIRED_ITEM_KEYS - set(item))
        if missing:
            issues.append(f"items[{idx}] missing keys: {', '.join(missing)}")
        if not isinstance(item.get("sources", []), list):
            issues.append(f"items[{idx}].sources must be a list.")
        if item.get("source"):
            issues.append(f"items[{idx}] uses legacy source; use sources.")
    return issues
