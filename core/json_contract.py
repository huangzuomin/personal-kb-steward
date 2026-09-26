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

# Contract metadata (not content): when the model omits these, the candidate
# is still fully grounded and traceable, so discarding it would throw away real
# work over a missing label. Default to the MOST conservative value instead.
# Content-bearing keys are never invented — see apply_contract_defaults.
CONTRACT_DEFAULT_KEYS = {
    "confidence": "low",
    "review_required": True,
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


def apply_contract_defaults(data: dict[str, Any]) -> list[str]:
    """Fill contract-metadata keys the model omitted. Returns human-readable
    notes so the degradation is visible in the saved plan instead of silent.

    Only keys in CONTRACT_DEFAULT_KEYS are filled; content-bearing keys
    (title/summary/sources/...) are never invented, and an item missing those
    is still reported as an issue by validate_contract.

    Defaulting confidence forces review_required=True: a low-confidence page
    must never reach the vault without review (see validator.validate_skill_items).
    """
    notes: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return notes
    for idx, item in enumerate(data.get("items", [])):
        if not isinstance(item, dict):
            continue
        filled: list[str] = []
        for key, default in CONTRACT_DEFAULT_KEYS.items():
            value = item.get(key)
            blank = value is None or (isinstance(value, str) and not value.strip())
            if blank:
                item[key] = default
                filled.append(key)
        if not filled:
            continue
        if item.get("confidence") == "low":
            item["review_required"] = True
        notes.append(
            f"items[{idx}] 未返回 {'、'.join(filled)}，"
            f"按最低置信度处理并强制人工复核"
        )
    return notes


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
