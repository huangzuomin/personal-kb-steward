"""Configured, vault-relative knowledge locations. No process-global binding."""
from __future__ import annotations
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

DEFAULT_KNOWLEDGE_DIRS = {
    "seed_dir": "wiki/seeds", "topics_dir": "wiki/topics", "sources_dir": "wiki/sources",
    "work_memory_dir": "wiki/work-memory", "evidence_dir": "wiki/evidence",
    "gaps_dir": "wiki/gaps", "claims_dir": "wiki/claim-checks",
    "concepts_dir": "wiki/concepts", "cases_dir": "wiki/cases",
    "materials_dir": "wiki/material-packs", "reviews_dir": "wiki/project-reviews",
}
INTERNAL_DIRS = frozenset({".git", ".kb", ".openclaw", ".obsidian", ".workbuddy-ai"})
INPUT_DIRS = frozenset({"raw", "quicknote", "inbox"})


def relative_dir(value: str) -> str:
    """Accept either separator, never silently turn absolute/traversal paths into relative ones."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("write directory must be a nonempty relative path")
    text = value.strip().replace("\\", "/").rstrip("/")
    path = PurePosixPath(text)
    if (path.is_absolute() or PureWindowsPath(text).drive or ".." in path.parts
            or not path.parts or path.as_posix() != text or any(c in text for c in "\x00\r\n")):
        raise ValueError(f"Unsafe vault-relative directory: {value}")
    return text


def knowledge_dirs(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    write = (cfg or {}).get("write", {})
    dirs = {key: relative_dir(write.get(key, fallback)) for key, fallback in DEFAULT_KNOWLEDGE_DIRS.items()}
    for path in dirs.values():
        if set(PurePosixPath(path).parts) & INTERNAL_DIRS or PurePosixPath(path).parts[0] in INPUT_DIRS:
            raise ValueError(f"Knowledge output overlaps raw/internal data: {path}")
    return dirs


def knowledge_prefixes(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(path + "/" for path in knowledge_dirs(cfg).values()))


def scan_dirs(cfg: dict[str, Any]) -> list[str]:
    """Scan explicitly configured outputs as well as inputs, never their broader parent."""
    return list(dict.fromkeys([*cfg["scan"]["include_dirs"], *knowledge_dirs(cfg).values()]))


def excluded_note(cfg: dict[str, Any], path) -> bool:
    names = {name.casefold() for name in cfg["scan"].get("exclude_files", [])}
    return path.name.casefold() in names or path.stem.casefold() in names


def validate_options(cfg: dict[str, Any]) -> list[str]:
    errors = []
    try:
        knowledge_dirs(cfg)
        from .output_paths import auxiliary_layout
        auxiliary_layout(cfg)
        for key, value in cfg.get("write", {}).items():
            if key.endswith("_dir"):
                relative_dir(value)
    except (ValueError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    minimum = cfg.get("quality_gate", {}).get("min_sources_for_seed", 2)
    if type(minimum) is not int or minimum < 1:
        errors.append("quality_gate.min_sources_for_seed must be a positive integer")
    title = cfg.get("write", {}).get("index_title", "个人知识库")
    if not isinstance(title, str) or not title.strip() or any(c in title for c in "\r\n"):
        errors.append("write.index_title must be nonempty single-line text")
    scan = cfg.get("scan", {})
    for key in ("max_total_source_chars", "max_source_chars"):
        value = scan.get(key, 0)
        if type(value) is not int or value < 0:
            errors.append(f"scan.{key} must be a nonnegative integer")
    value = scan.get("exclude_files", [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        errors.append("scan.exclude_files must be a list of nonempty filenames/stems")
    compat = cfg.get("link_resolution", {})
    if not isinstance(compat, dict) or type(compat.get("obsidian_compat", False)) is not bool:
        errors.append("link_resolution.obsidian_compat must be boolean")
    for key in ("candidate_promotion", "heuristic_topics"):
        rules = cfg.get(key, [])
        if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
            errors.append(f"{key} must be a list of rules")
            continue
        for rule in rules:
            markers = rule.get("match_any", [])
            if not isinstance(markers, list) or not all(isinstance(v, str) and v for v in markers):
                errors.append(f"{key}.match_any must be a list of nonempty strings")
            for number in ("min_sources", "max_sources"):
                if number in rule and (type(rule[number]) is not int or rule[number] < 1):
                    errors.append(f"{key}.{number} must be a positive integer")
            if key == "candidate_promotion":
                expected = {"topic": "topics_dir", "concept": "concepts_dir", "case": "cases_dir", "material-pack": "materials_dir"}
                if not rule.get("title") or expected.get(rule.get("kind")) != rule.get("rel_dir_key"):
                    errors.append("candidate_promotion requires a title and matching kind/rel_dir_key")
                body = rule.get("body", [])
                if not isinstance(body, list) or not all(isinstance(line, str) for line in body):
                    errors.append("candidate_promotion.body must be a list of lines")
    if not isinstance(cfg.get("finalize_aggregation", {}), dict):
        errors.append("finalize_aggregation must be an object")
    return errors
