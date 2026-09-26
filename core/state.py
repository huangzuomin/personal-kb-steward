from __future__ import annotations

import json
from typing import Any

from .config import processed_index_path, read_json, state_path
from .content_identity import match_content_identity
from .safety import safe_write_text
from .vault import Note, VaultIndex


def load_state(cfg: dict[str, Any]) -> dict[str, Any]:
    return read_json(state_path(cfg), {})


def save_state(cfg: dict[str, Any], index: VaultIndex, operations: list[dict[str, Any]], timestamp: str) -> None:
    state = load_state(cfg)
    state["agent"] = cfg["agent"]
    state["last_run"] = timestamp
    state["knowledge_base"] = str(index.root)
    state["files"] = {
        note.rel: {
            "sha256": note.sha256,
            "mtime": note.mtime,
            "size": note.size,
            "title": note.title,
        }
        for note in index.notes
    }
    state.setdefault("history", [])
    state["history"].append({"time": timestamp, "operations": operations})
    state["history"] = state["history"][-30:]
    safe_write_text(
        cfg,
        state_path(cfg),
        json.dumps(state, ensure_ascii=False, indent=2),
        run_id=str(cfg.get("_run_id") or timestamp),
        operation="write_state",
        reason="Persist runtime state; previous state is backed up first.",
    )


def changed_notes(index: VaultIndex, state: dict[str, Any]) -> list[Note]:
    seen = state.get("files", {})
    return [note for note in index.notes if seen.get(note.rel, {}).get("sha256") != note.sha256]


def load_processed_index(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        return {"version": 1, "processed": {}}
    data = read_json(processed_index_path(cfg), {"version": 1, "processed": {}})
    if not isinstance(data, dict):
        return {"version": 1, "processed": {}, "_schema_error": "processed-index root is not an object"}
    if "processed" not in data:
        message = "processed-index schema mismatch: expected key 'processed'"
        if "records" in data:
            message += "; found legacy/external key 'records'"
        return {"version": 1, "processed": {}, "_schema_error": message, "_raw_keys": sorted(data.keys())}
    if not isinstance(data.get("processed"), dict):
        return {"version": 1, "processed": {}, "_schema_error": "processed-index key 'processed' is not an object"}
    return data


def save_processed_index(data: dict[str, Any], cfg: dict[str, Any], timestamp: str) -> None:
    data["version"] = 1
    data["updated_at"] = timestamp
    safe_write_text(
        cfg,
        processed_index_path(cfg),
        json.dumps(data, ensure_ascii=False, indent=2),
        run_id=str(cfg.get("_run_id") or timestamp),
        operation="write_processed_index",
        reason="Persist processed index; previous index is backed up first.",
    )


def processed_record(data: dict[str, Any], note: Note, skill: str) -> dict[str, Any] | None:
    return data.get("processed", {}).get(note.rel, {}).get("skills", {}).get(skill)


def is_processed(data: dict[str, Any], note: Note, skill: str) -> bool:
    record = processed_record(data, note, skill)
    if not (record and record.get("operation_status") in {"created", "skipped"}):
        return False
    if record.get("sha256") == note.sha256:
        return True
    # GP002: byte hash 不同时，用 content identity 兜底（CRLF/LF/BOM 表示漂移
    # 属同一内容）；漂移判定需要当前字节，仅在 byte/identity 双未命中时读取。
    recorded_identity = record.get("content_identity_sha256")
    note_identity = getattr(note, "content_identity_sha256", "") or ""
    if recorded_identity and note_identity and recorded_identity == note_identity:
        return True
    try:
        raw = note.path.read_bytes()
    except OSError:
        return False
    kind = match_content_identity(
        record.get("sha256"), recorded_identity, raw)["kind"]
    return kind in {"BYTE_MATCH", "IDENTITY_MATCH", "REPRESENTATION_DRIFT"}


def unprocessed_notes(data: dict[str, Any], notes: list[Note], skill: str) -> list[Note]:
    return [note for note in notes if not is_processed(data, note, skill)]


def update_processed_index(index: VaultIndex, cfg: dict[str, Any], operations: list[dict[str, Any]], timestamp: str) -> None:
    data = load_processed_index(cfg)
    processed = data.setdefault("processed", {})
    for op in operations:
        skill = op.get("skill")
        if not skill:
            continue
        outputs = op.get("created", [])
        source_outputs = op.get("source_outputs", {})
        has_review_gate = bool(op.get("manual_reviews")) or bool(op.get("review_required")) or str(op.get("confidence", "")).lower() == "low"
        has_issues = bool(op.get("issues"))
        for rel in op.get("inputs", []):
            note = index.by_rel.get(rel)
            if not note:
                continue
            file_record = processed.setdefault(rel, {
                "title": note.title,
                "current_sha256": note.sha256,
                "skills": {},
            })
            file_record["title"] = note.title
            file_record["current_sha256"] = note.sha256
            # GP002: content identity 与 byte hash 并列写 forward（byte 语义不变）。
            note_identity = getattr(note, "content_identity_sha256", "") or ""
            if note_identity:
                file_record["content_identity_sha256"] = note_identity
            rel_outputs = source_outputs.get(rel, outputs)
            # Status is decided per source, not per operation: one operation can
            # carry several sources whose outcomes differ (a written page next to
            # a deliberately rejected one).  Reporting the whole operation's
            # status for every source would label a declined source "created"
            # with no outputs.
            if has_review_gate or has_issues:
                operation_status = "needs_review"
            elif rel_outputs:
                operation_status = "created"
            else:
                operation_status = "skipped"
            skill_record = {
                "sha256": note.sha256,
                "processed_at": timestamp,
                "outputs": rel_outputs,
                "operation_status": operation_status,
            }
            if note_identity:
                skill_record["content_identity_sha256"] = note_identity
            file_record["skills"][skill] = skill_record
    save_processed_index(data, cfg, timestamp)
