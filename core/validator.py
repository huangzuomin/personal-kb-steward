from __future__ import annotations

from typing import Any


def validate_skill_items(data: dict[str, Any], allowed_sources: set[str]) -> list[str]:
    issues: list[str] = []
    for idx, item in enumerate(data.get("items", [])):
        for source in item.get("sources", []):
            if source in {"raw", "raw/", "wiki", "wiki/"} or str(source).endswith("/"):
                issues.append(f"items[{idx}] source too broad: {source}")
            if source not in allowed_sources:
                issues.append(f"items[{idx}] source not provided: {source}")
        if item.get("confidence") == "low" and not item.get("review_required"):
            issues.append(f"items[{idx}] low confidence must require review.")
        for link in item.get("related", []):
            if link not in allowed_sources and link not in item.get("pending_links", []):
                issues.append(f"items[{idx}] related link is not known or pending: {link}")
    return issues
