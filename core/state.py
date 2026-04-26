from __future__ import annotations

from typing import Any

from .config import processed_index_path, read_json, state_path, write_json
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
    write_json(state_path(cfg), state)


def changed_notes(index: VaultIndex, state: dict[str, Any]) -> list[Note]:
    seen = state.get("files", {})
    return [note for note in index.notes if seen.get(note.rel, {}).get("sha256") != note.sha256]


def load_processed_index(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        return {"version": 1, "processed": {}}
    return read_json(processed_index_path(cfg), {"version": 1, "processed": {}})


def save_processed_index(data: dict[str, Any], cfg: dict[str, Any], timestamp: str) -> None:
    data["version"] = 1
    data["updated_at"] = timestamp
    write_json(processed_index_path(cfg), data)


def processed_record(data: dict[str, Any], note: Note, skill: str) -> dict[str, Any] | None:
    return data.get("processed", {}).get(note.rel, {}).get("skills", {}).get(skill)


def is_processed(data: dict[str, Any], note: Note, skill: str) -> bool:
    record = processed_record(data, note, skill)
    return bool(record and record.get("sha256") == note.sha256)


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
            file_record["skills"][skill] = {
                "sha256": note.sha256,
                "processed_at": timestamp,
                "outputs": outputs,
                "operation_status": "created" if outputs else "skipped",
            }
    save_processed_index(data, cfg, timestamp)
