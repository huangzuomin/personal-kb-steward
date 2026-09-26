"""Separate plan/run identity from individual attempts; never erase recovery facts.

Canonical manifests remain the recovery entrypoint. Each terminal attempt also
has an independent immutable record. This is not a multi-file transaction or a
lock against simultaneous external writers.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import read_json, runs_dir, sha256_file, sha256_text
from .safety import append_operation_log, backup_root, operation_log_path, recovery_hint, user_next_step, _stamp


class RunRecordConflict(ValueError):
    """A run ID already has execution/recovery facts and cannot be reused."""


def _run_path(cfg: dict[str, Any], run_id: str) -> Path:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", run_id):
        raise RunRecordConflict("Invalid run_id; use a safe single path component")
    return runs_dir(cfg) / f"{run_id}.json"


def _protected(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        previous = read_json(path, {})
    except (OSError, ValueError):
        return True  # A corrupt existing audit record is not permission to replace it.
    return not isinstance(previous, dict) or (
        previous.get("status") != "failed" or bool(previous.get("created"))
        or bool(previous.get("write_started"))
    )


def assert_run_can_start(cfg: dict[str, Any], run_id: str) -> None:
    path = _run_path(cfg, run_id)
    if _protected(path):
        raise RunRecordConflict(f"Run {run_id} already has execution history; inspect {path} and generate a new plan")


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    """Per-file replace prevents truncated JSON; it is not a batch transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save_run_manifest(cfg: dict[str, Any], manifest: dict[str, Any]) -> Path:
    target = _run_path(cfg, manifest["run_id"])
    protected = _protected(target)
    attempt_id = str(cfg.get("_attempt_id") or uuid4())
    # A late reporting failure may produce a second terminal event for this attempt.
    event_id = str(uuid4())
    attempt_path = target.parent / "attempts" / manifest["run_id"] / f"{event_id}.json"
    record = {**manifest, "attempt_id": attempt_id, "event_id": event_id,
              "write_started": bool(cfg.get("_write_started")),
              "canonical_manifest": str(target), "preserved_existing_run": protected}
    _atomic_json(attempt_path, record)
    if protected:
        if manifest.get("status") != "failed":
            raise RunRecordConflict(f"Refusing to replace execution history: {target}")
        return attempt_path
    _atomic_json(target, record)
    return target


def record_failed_attempt(cfg: dict[str, Any], run_id: str, plan_path: Path | None,
                          root: Path | None, created: list[dict[str, Any]], exc: BaseException) -> None:
    try:
        _run_path(cfg, run_id)
    except RunRecordConflict:
        run_id = "invalid-" + hashlib.sha256(str(run_id).encode("utf-8")).hexdigest()[:16]
    cfg["_run_id"] = run_id
    failed = {"run_id": run_id, "failed_at": _stamp(), "plan_path": str(plan_path or ""),
              "knowledge_base": str(root or ""), "created": created,
              "backup_dir": str(backup_root(cfg) / run_id),
              "operation_log": str(operation_log_path(cfg)), "recovery_hint": recovery_hint(cfg, run_id),
              "next_step": user_next_step(exc), "status": "failed", "phase": cfg.get("_phase", "loading_plan"), "error": str(exc)}
    if plan_path is not None and plan_path.is_file():
        try:
            failed["plan_sha256"] = sha256_file(plan_path)
        except OSError:
            pass
    linkage = cfg.get("_subset_context")
    if isinstance(linkage, dict):
        for key in (
            "parent_run_id",
            "parent_plan_path",
            "parent_plan_sha256",
            "subset_hash",
            "selected_targets",
            "selected_review_ids",
            "queue_snapshot_sha256",
        ):
            if key in linkage:
                failed[key] = linkage[key]
    path = save_run_manifest(cfg, failed)
    # An unavailable operation log must not prevent persisting the failure facts.
    try:
        append_operation_log(cfg, {"operation": "apply_plan_failed", "run_id": run_id,
                                  "attempt_id": cfg.get("_attempt_id"), "error": str(exc),
                                  "manifest_path": str(path), "next_step": user_next_step(exc)})
    except OSError as log_error:
        print(f"Additional audit log error: {log_error}; failure facts are in {path}", file=sys.stderr)
    print(f"apply-plan 失败：{exc}\n下一步：{user_next_step(exc)}\n{recovery_hint(cfg, run_id)}\n失败 run manifest：{path}", file=sys.stderr)


def write_observed_page(cfg: dict[str, Any], page: dict[str, Any], target: Path,
                        created: list[dict[str, Any]], *, writer: Callable[..., dict[str, Any]],
                        identity: dict[str, Any]) -> None:
    """Record an actual mutation even if post-write logging raises.

    content_verified=false means the observed file did not match the proposal;
    the identity fields then describe the intended object, not a verified write.
    """
    before = sha256_file(target) if target.is_file() else None
    event = None
    try:
        event = writer(cfg, target, page["content"], run_id=cfg["_run_id"],
                       operation="apply_plan_update_page" if page.get("operation") == "update" else "apply_plan_create_page",
                       reason="Apply reviewed plan page; original raw/quicknote/inbox files are protected.")
    finally:
        after = sha256_file(target) if target.is_file() else None
        if event is not None or after != before:
            backup = backup_root(cfg) / cfg["_run_id"] / page["rel_path"]
            created.append({**identity, "rel_path": page["rel_path"], "sha256": after,
                            "expected_sha256": sha256_text(page["content"]),
                            "content_verified": after == sha256_text(page["content"]),
                            "backup_path": str(backup) if backup.is_file() else None,
                            "skill": page.get("skill"), "operation": page.get("operation", "create"),
                            "sources": page.get("sources", []),
                            "origin": page.get("origin") or {"source_paths": page.get("sources", [])}})
