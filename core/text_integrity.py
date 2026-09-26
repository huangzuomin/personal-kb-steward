"""T10 hard gate: Unicode replacement character (U+FFFD) marks damaged text.

A U+FFFD anywhere in a source string means the original bytes were undecodable
somewhere and were silently substituted; the text is NOT trustworthy evidence.
We reject such inputs before any provider invocation and reject model responses
containing U+FFFD before parsing/accepting. No repair, no character removal, no
hash normalization, no meaning reconstruction — and no fuzzy mojibake heuristics:
ordinary '?', valid CJK/emoji, BOM/CRLF all stay valid. This check is independent
of (and does not alter) secret-scanning policy.
"""
from __future__ import annotations

from typing import Any

REPLACEMENT = "�"

NOTE_TEXT_FIELDS = ("source_text", "body", "title")


def contains_replacement(value: Any) -> bool:
    """True if any string reachable in value contains U+FFFD."""
    if isinstance(value, str):
        return REPLACEMENT in value
    if isinstance(value, dict):
        return any(contains_replacement(k) or contains_replacement(v)
                   for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_replacement(item) for item in value)
    return False


def damaged_reasons(note: dict[str, Any], rel: str,
                    fields: tuple[str, ...] = NOTE_TEXT_FIELDS) -> list[str]:
    """Per-input reasons for a damaged note; empty list means clean."""
    reasons: list[str] = []
    if not isinstance(note, dict):
        return reasons
    for field in fields:
        value = note.get(field)
        if isinstance(value, str) and REPLACEMENT in value:
            reasons.append(
                f"{rel}: {field} 包含 Unicode 替换字符 U+FFFD，原文已在解码时损坏；"
                "按损坏来源拒绝，不做修复或含义重建（damaged_source）")
    return reasons


def damaged_unit_reasons(units: list[Any], snapshots: dict | None) -> list[str]:
    """Scan supplied units and their snapshots for U+FFFD (atomic supplied path)."""
    reasons: list[str] = []
    for i, unit in enumerate(units):
        if contains_replacement(unit):
            reasons.append(f"信息单元 {i} 包含 U+FFFD 损坏字符，拒绝纳入（damaged_source）")
    for source, snap in (snapshots or {}).items():
        if isinstance(snap, dict) and contains_replacement(snap.get("source_text")):
            reasons.append(f"快照 {source!r} 包含 U+FFFD 损坏字符，拒绝使用（damaged_source）")
    return reasons


def assert_clean_response(raw: Any, where: str) -> None:
    """Raise ValueError when a model response contains U+FFFD.

    The raw response remains available to the evaluation recorder; diagnostics
    here deliberately do NOT echo the corrupted text.
    """
    if isinstance(raw, str) and REPLACEMENT in raw:
        raise ValueError(
            f"{where}: 模型响应包含 Unicode 替换字符 U+FFFD，按编码损坏响应拒绝；"
            "不解析、不接受为合法零或完整产出")


def assert_clean_data(data: Any, where: str) -> None:
    """Raise ValueError when PARSED model data carries U+FFFD (JSON \\uFFFD
    escapes hide the character from the raw string but the accepted text is
    equally damaged)."""
    if contains_replacement(data):
        raise ValueError(
            f"{where}: 模型输出解析后包含 Unicode 替换字符 U+FFFD，按编码损坏响应拒绝；"
            "不作为合法零或完整产出")
