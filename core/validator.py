from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def _link_target(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2].strip()
    text = text.split("|", 1)[0].split("#", 1)[0].strip().replace("\\", "/")
    return text


def _known_link_index(known: set[str] | list[dict[str, Any]]) -> tuple[set[str], dict[str, set[str]]]:
    if isinstance(known, set):
        documents = [{"path": path, "title": ""} for path in known]
    else:
        documents = known

    paths: set[str] = set()
    aliases: dict[str, set[str]] = {}
    for doc in documents:
        path = str(doc.get("path") or "").replace("\\", "/").strip()
        if not path:
            continue
        paths.add(path)
        p = PurePosixPath(path)
        candidates = {
            path,
            path.removesuffix(".md"),
            p.name,
            p.stem,
            str(doc.get("title") or "").strip(),
        }
        for alias in {item for item in candidates if item}:
            aliases.setdefault(alias, set()).add(path)
            aliases.setdefault(alias.casefold(), set()).add(path)
    return paths, aliases


def resolve_known_link(value: Any, known: set[str] | list[dict[str, Any]]) -> str | None:
    target = _link_target(value)
    if not target:
        return None
    paths, aliases = _known_link_index(known)
    if target in paths:
        return target
    matches = aliases.get(target) or aliases.get(target.casefold()) or set()
    return next(iter(matches)) if len(matches) == 1 else None


def canonicalize_related_links(data: dict[str, Any], known: set[str] | list[dict[str, Any]]) -> None:
    """Normalize uniquely-resolved Obsidian links to canonical provided source paths."""
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        normalized: list[str] = []
        for link in item.get("related", []):
            resolved = resolve_known_link(link, known)
            normalized.append(resolved or str(link))
        item["related"] = normalized


def validate_skill_items(data: dict[str, Any], known: set[str] | list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    paths, _ = _known_link_index(known)
    for idx, item in enumerate(data.get("items", [])):
        for source in item.get("sources", []):
            if source in {"raw", "raw/", "wiki", "wiki/"} or str(source).endswith("/"):
                issues.append(f"items[{idx}] source too broad: {source}")
            if source not in paths:
                issues.append(f"items[{idx}] source not provided: {source}")
        if item.get("confidence") == "low" and not item.get("review_required"):
            issues.append(f"items[{idx}] low confidence must require review.")

        pending = {_link_target(link) for link in item.get("pending_links", [])}
        for link in item.get("related", []):
            target = _link_target(link)
            if resolve_known_link(link, known) is None and target not in pending:
                issues.append(f"items[{idx}] related link is not known or pending: {link}")
    return issues
