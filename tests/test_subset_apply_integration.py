"""Focused B3 writer integration checks on the public producer fixture.

The fixture uses the real synthetic producer, plan binding, review queue, and
existing apply writer.  Only the provider seam is offline-mocked.  These
tests exercise the authority boundaries around that path; they do not create
ready-made output pages or call a second writer.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.review_queue import save_queue
from scripts import personal_kb_steward as steward
from tests.test_subset_apply_blackbox import (
    _expected_snapshot,
    _prepare_real_two_output_plan,
    _queue_for,
    _review,
    _target_snapshots,
)


def _apply(cfg: dict, provider: object, run_id: str) -> int:
    return _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    )


def _approve(cfg: dict, provider: object, item_id: str) -> int:
    return _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="approve", id=item_id, reason="B3 integration fixture"
        ),
    )


def _reject(cfg: dict, provider: object, item_id: str) -> int:
    return _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="reject", id=item_id, reason="B3 integration rejection"
        ),
    )


def test_saved_page_contract_does_not_fallback_to_approved_aggregate(tmp_path: Path):
    run_id = "b3-integration-no-legacy-fallback"
    cfg, plan, plan_path, plan_bytes, originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    assert plan.get("review_contract") == "page-scoped-v1"
    aggregate = {
        "id": "aggregate-only",
        "run_id": run_id,
        "entry": plan["entry"],
        "task": plan["task"],
        "type": "planned_pages_require_review",
        "status": "approved",
    }
    save_queue(steward.review_queue_path(cfg), [aggregate])

    assert _apply(cfg, provider, run_id) == 1
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert _queue_for(cfg, run_id) == [aggregate]
    assert plan_path.read_bytes() == plan_bytes
    assert {rel: (tmp_path / rel).read_bytes() for rel in originals} == originals


def test_writer_rechecks_parent_hash_before_first_byte(tmp_path: Path):
    run_id = "b3-integration-parent-boundary"
    cfg, plan, plan_path, plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    first = _queue_for(cfg, run_id)[0]
    assert _approve(cfg, provider, first["id"]) == 0

    original_validate = steward.validate_object_writes

    def mutate_parent(index, pages, *, schema_version=None):
        result = original_validate(index, pages, schema_version=schema_version)
        plan_path.write_bytes(plan_bytes + b"\n")
        return result

    with patch.object(steward, "validate_object_writes", side_effect=mutate_parent), patch.object(
        steward, "safe_write_text", wraps=steward.safe_write_text
    ) as write:
        assert _apply(cfg, provider, run_id) == 1
        assert write.call_count == 0

    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert _queue_for(cfg, run_id)[0]["status"] == "approved"
    plan_path.write_bytes(plan_bytes)


def test_writer_rechecks_queue_snapshot_before_first_byte(tmp_path: Path):
    run_id = "b3-integration-queue-boundary"
    cfg, plan, plan_path, plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    first = _queue_for(cfg, run_id)[0]
    assert _approve(cfg, provider, first["id"]) == 0
    queue_path = steward.review_queue_path(cfg)
    original_validate = steward.validate_object_writes

    def mutate_queue(index, pages, *, schema_version=None):
        result = original_validate(index, pages, schema_version=schema_version)
        rows = steward.load_queue(queue_path)
        rows[0]["reason"] = "changed after subset authorization"
        save_queue(queue_path, rows)
        return result

    with patch.object(steward, "validate_object_writes", side_effect=mutate_queue), patch.object(
        steward, "safe_write_text", wraps=steward.safe_write_text
    ) as write:
        assert _apply(cfg, provider, run_id) == 1
        assert write.call_count == 0

    changed = _queue_for(cfg, run_id)[0]
    assert changed["status"] == "approved"
    assert changed["reason"] == "changed after subset authorization"
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert plan_path.read_bytes() == plan_bytes


def test_writer_rejects_malformed_queue_before_first_byte(tmp_path: Path):
    run_id = "b3-integration-malformed-queue"
    cfg, plan, _plan_path, _plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    first = _queue_for(cfg, run_id)[0]
    assert _approve(cfg, provider, first["id"]) == 0
    queue_path = steward.review_queue_path(cfg)
    original_validate = steward.validate_object_writes

    def corrupt_queue(index, pages, *, schema_version=None):
        result = original_validate(index, pages, schema_version=schema_version)
        with queue_path.open("a", encoding="utf-8") as stream:
            stream.write("{malformed queue row\n")
        return result

    with patch.object(steward, "validate_object_writes", side_effect=corrupt_queue), patch.object(
        steward, "safe_write_text", wraps=steward.safe_write_text
    ) as write:
        assert _apply(cfg, provider, run_id) == 1
        assert write.call_count == 0

    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert _queue_for(cfg, run_id)[0]["status"] == "approved"


def test_outer_subset_precheck_preserves_malformed_queue_bytes(tmp_path: Path):
    run_id = "b3-integration-outer-malformed-queue"
    cfg, plan, _plan_path, _plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    first = _queue_for(cfg, run_id)[0]
    assert _approve(cfg, provider, first["id"]) == 0
    queue_path = steward.review_queue_path(cfg)
    broken = queue_path.read_bytes() + (
        b'{"run_id":"legacy-without-id","type":"old_review","status":"pending"}\n'
        b'{malformed queue row\n'
    )
    queue_path.write_bytes(broken)

    assert _apply(cfg, provider, run_id) == 1
    assert queue_path.read_bytes() == broken
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])


def test_forged_page_hash_cannot_authorize_existing_producer_output(tmp_path: Path):
    run_id = "b3-integration-forged-authority"
    cfg, plan, _plan_path, _plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    queue_path = steward.review_queue_path(cfg)
    rows = _queue_for(cfg, run_id)
    rows[0]["status"] = "approved"
    rows[0]["content_sha256"] = "0" * 64
    save_queue(queue_path, rows)

    assert _apply(cfg, provider, run_id) == 1
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert _queue_for(cfg, run_id)[0]["status"] == "approved"


def test_non_page_pending_blocker_stops_subset_without_writing(tmp_path: Path):
    run_id = "b3-integration-non-page-blocker"
    cfg, plan, _plan_path, _plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    queue_path = steward.review_queue_path(cfg)
    rows = _queue_for(cfg, run_id)
    rows[0]["status"] = "approved"
    rows.append(
        {
            "id": "seed-blocker",
            "run_id": run_id,
            "entry": plan["entry"],
            "task": plan["task"],
            "type": "seed_quality_issues",
            "status": "pending",
        }
    )
    save_queue(queue_path, rows)

    assert _apply(cfg, provider, run_id) == 1
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    statuses = {item["id"]: item["status"] for item in _queue_for(cfg, run_id)}
    assert statuses[rows[0]["id"]] == "approved"
    assert statuses["seed-blocker"] == "pending"


def test_all_rejected_subset_is_terminal_rejected_without_manifest(tmp_path: Path):
    run_id = "b3-integration-all-rejected"
    cfg, plan, _plan_path, _plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    rows = _queue_for(cfg, run_id)
    for row in rows:
        assert _reject(cfg, provider, row["id"]) == 0

    assert _apply(cfg, provider, run_id) == 0
    assert all((tmp_path / page["rel_path"]).exists() is False for page in plan["planned_pages"])
    assert all(item["status"] == "rejected" for item in _queue_for(cfg, run_id))
    assert not list(Path(cfg["safety"]["runs_dir"]).glob(f"{run_id}*.json"))


def test_partial_write_keeps_failed_manifest_and_marks_only_observed_target(tmp_path: Path):
    run_id = "b3-integration-partial-write"
    cfg, plan, plan_path, plan_bytes, _originals, _log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    rows = _queue_for(cfg, run_id)
    for row in rows:
        assert _approve(cfg, provider, row["id"]) == 0
    original_write = steward.safe_write_text
    calls: list[str] = []

    def fail_second(cfg_arg, target, content, **kwargs):
        calls.append(Path(target).relative_to(tmp_path).as_posix())
        if len(calls) == 2:
            raise OSError("synthetic second page write failure")
        return original_write(cfg_arg, target, content, **kwargs)

    with patch.object(steward, "safe_write_text", side_effect=fail_second):
        assert _apply(cfg, provider, run_id) == 1

    targets = [page["rel_path"] for page in plan["planned_pages"]]
    observed = _target_snapshots(tmp_path, targets)
    assert observed[targets[0]] == _expected_snapshot(plan, targets[0])
    assert observed[targets[1]] is None
    statuses = {item["target"]: item["status"] for item in _queue_for(cfg, run_id)}
    assert statuses == {targets[0]: "applied", targets[1]: "approved"}
    assert plan_path.read_bytes() == plan_bytes

    failed_paths = sorted(Path(cfg["safety"]["runs_dir"]).glob(f"{run_id}.subset-*.json"))
    assert len(failed_paths) == 1
    failed_path = failed_paths[0]
    failed = json.loads(failed_path.read_text(encoding="utf-8"))
    assert failed["status"] == "failed"
    assert failed["run_id"] == failed_path.stem
    assert failed["run_id"].startswith(f"{run_id}.subset-")
    assert failed["parent_run_id"] == run_id
    assert failed["parent_plan_path"] == str(plan_path)
    assert failed["parent_plan_sha256"]
    assert failed["plan_sha256"] == failed["parent_plan_sha256"]
    assert failed["subset_hash"]
    assert set(failed["selected_targets"]) == set(targets)
    assert failed["created"][0]["rel_path"] == targets[0]
    assert failed["created"][0]["content_verified"] is True
    assert len(calls) == 2

    # The failed selection remains protected; a later explicit apply can only
    # authorize the exact approved remainder after re-reading observed_failed.
    assert _apply(cfg, provider, run_id) == 0
    resumed = _target_snapshots(tmp_path, targets)
    assert resumed[targets[0]] == _expected_snapshot(plan, targets[0])
    assert resumed[targets[1]] == _expected_snapshot(plan, targets[1])
    assert {item["target"]: item["status"] for item in _queue_for(cfg, run_id)} == {
        targets[0]: "applied",
        targets[1]: "applied",
    }
