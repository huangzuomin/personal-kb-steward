"""Focused public/synthetic checks for the read-only B3b evidence reader."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from core.plan_output_evidence import subset_evidence_hash, verified_plan_outputs
from core.vault import build_index


ROOT = Path(__file__).resolve().parents[1]


def _cfg(tmp_path: Path) -> dict:
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    vault = tmp_path / "vault"
    vault.mkdir()
    cfg["knowledge_base"] = str(vault)
    cfg["state_file"] = str(vault / ".state.json")
    cfg["safety"]["plans_dir"] = str(vault / ".openclaw" / "plans")
    cfg["safety"]["runs_dir"] = str(vault / ".openclaw" / "runs")
    cfg["safety"]["processed_index"] = str(vault / ".openclaw" / "processed-index.json")
    cfg["safety"]["manual_review_queue"] = str(vault / ".openclaw" / "manual-review" / "queue.jsonl")
    cfg["safety"]["backup_dir"] = str(vault / ".openclaw" / "backups")
    cfg["safety"]["operation_log"] = str(vault / ".openclaw" / "operation-log.jsonl")
    (vault / ".openclaw" / "plans").mkdir(parents=True)
    (vault / ".openclaw" / "runs" / "attempts").mkdir(parents=True)
    (vault / "wiki" / "sources").mkdir(parents=True)
    return cfg


def _identity(n: int) -> str:
    return f"kb:00000000-0000-4000-8000-{n:012d}"


def _page(target: str, n: int, *, revision: int = 1) -> dict:
    object_id = _identity(n)
    content = (
        "---\n"
        f"title: Evidence {n}\n"
        "type: source-note\n"
        f"object_id: {object_id}\n"
        f"revision: {revision}\n"
        "---\n"
        f"# Evidence {n}\n\nBound output {n}.\n"
    )
    return {
        "rel_path": target,
        "operation": "create",
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "object_id": object_id,
        "revision": revision,
    }


def _plan(cfg: dict, *pages: dict, run_id: str = "parent-run") -> tuple[Path, dict, str]:
    data = {"run_id": run_id, "planned_pages": list(pages), "task": "public evidence"}
    path = Path(cfg["safety"]["plans_dir"]) / f"{run_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, data, hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog(*pages: dict) -> dict:
    return {
        page["rel_path"]: {
            "canonical_path": page["rel_path"],
            "content_sha256": page["content_sha256"],
            "object_id": page["object_id"],
            "revision": page["revision"],
        }
        for page in pages
    }


def _write_output(cfg: dict, page: dict) -> None:
    root = Path(cfg["knowledge_base"])
    target = root / page["rel_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(page["content"].encode("utf-8"))


def _created(page: dict) -> dict:
    return {
        "rel_path": page["rel_path"],
        "expected_sha256": page["content_sha256"],
        "sha256": page["content_sha256"],
        "content_verified": True,
        "object_id": page["object_id"],
        "revision": page["revision"],
        "operation": page["operation"],
    }


def _ordinary_manifest(cfg: dict, plan_path: Path, plan_hash: str, pages: list[dict], *, run_id: str = "parent-run", status: str = "applied") -> dict:
    manifest = {
        "run_id": run_id,
        "status": status,
        "plan_path": str(plan_path),
        "plan_sha256": plan_hash,
        "created": [_created(page) for page in pages],
    }
    if status == "applied":
        manifest["reconcile"] = {"ok": True, "missing": [], "hash_mismatch": []}
    else:
        manifest["write_started"] = True
        manifest["reconcile"] = {"ok": False, "missing": [], "hash_mismatch": ["incomplete sibling"]}
    return manifest


def _save_manifest(cfg: dict, name: str, manifest: dict, *, attempt_run: str | None = None) -> Path:
    runs = Path(cfg["safety"]["runs_dir"])
    parent = Path("attempts") / (attempt_run or manifest.get("run_id", "event")) if attempt_run else Path(".")
    path = runs / parent / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _reader(cfg: dict, plan_path: Path, plan_hash: str, pages: list[dict]) -> dict:
    return verified_plan_outputs(build_index(cfg), cfg, plan_path, plan_hash, _catalog(*pages))


def test_ordinary_applied_manifest_rechecks_current_bytes_and_identity(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    manifest_path = _save_manifest(cfg, "parent-run", _ordinary_manifest(cfg, plan_path, plan_hash, [page]))

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert result["conflicts"] == []
    assert result["manifest_paths"] == [str(manifest_path)]
    fact = result["verified"][page["rel_path"]]
    assert fact["content_sha256"] == page["content_sha256"]
    assert fact["object_id"] == page["object_id"]
    assert fact["revision"] == page["revision"]
    assert fact["manifest_path"] == str(manifest_path)
    assert fact["run_id"] == "parent-run"


def test_two_linked_subset_successes_union_by_exact_parent_and_subset_hash(tmp_path: Path):
    cfg = _cfg(tmp_path)
    first, second = _page("wiki/sources/a.md", 1), _page("wiki/sources/b.md", 2)
    plan_path, _plan_data, plan_hash = _plan(cfg, first, second)
    _write_output(cfg, first)
    _write_output(cfg, second)
    for ordinal, page in enumerate((first, second), 1):
        selected = _catalog(page)
        manifest = {
            "run_id": f"subset-{ordinal}",
            "parent_run_id": "parent-run",
            "parent_plan_path": str(plan_path),
            "parent_plan_sha256": plan_hash,
            "subset_hash": subset_evidence_hash("parent-run", plan_hash, selected),
            "selected_targets": selected,
            "status": "applied",
            "reconcile": {"ok": True},
            "created": [_created(page)],
        }
        _save_manifest(cfg, f"subset-{ordinal}", manifest)

    result = _reader(cfg, plan_path, plan_hash, [first, second])

    assert result["conflicts"] == []
    assert set(result["verified"]) == {first["rel_path"], second["rel_path"]}
    assert set(result["verified"][first["rel_path"]]["run_ids"]) == {"subset-1"}
    assert set(result["verified"][second["rel_path"]]["run_ids"]) == {"subset-2"}


@pytest.mark.parametrize("reconcile", [None, {"ok": False}, {"ok": True}])
def test_applied_subset_requires_real_reconcile_before_verified_output(tmp_path: Path, reconcile: dict | None):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    selected = _catalog(page)
    manifest = {
        "run_id": "subset-1",
        "parent_run_id": "parent-run",
        "parent_plan_path": str(plan_path),
        "parent_plan_sha256": plan_hash,
        "subset_hash": subset_evidence_hash("parent-run", plan_hash, selected),
        "selected_targets": selected,
        "status": "applied",
        "created": [_created(page)],
    }
    if reconcile is not None:
        manifest["reconcile"] = reconcile
    _save_manifest(cfg, "subset-1", manifest)

    result = _reader(cfg, plan_path, plan_hash, [page])

    if reconcile == {"ok": True}:
        assert set(result["verified"]) == {page["rel_path"]}
        assert result["conflicts"] == []
    else:
        assert result["verified"] == {}
        assert any(item["code"] == "applied_reconcile_missing" for item in result["conflicts"])


def test_failed_batch_keeps_individually_verified_write_separate_from_success(tmp_path: Path):
    cfg = _cfg(tmp_path)
    first, second = _page("wiki/sources/a.md", 1), _page("wiki/sources/b.md", 2)
    plan_path, _plan_data, plan_hash = _plan(cfg, first, second)
    _write_output(cfg, first)
    manifest = _ordinary_manifest(cfg, plan_path, plan_hash, [first], status="failed")
    path = _save_manifest(cfg, "parent-run", manifest)

    result = _reader(cfg, plan_path, plan_hash, [first, second])

    assert result["verified"] == {}
    assert set(result["observed_failed"]) == {first["rel_path"]}
    assert result["observed_failed"][first["rel_path"]]["manifest_path"] == str(path)
    assert result["conflicts"] == []


def test_late_failed_event_does_not_replace_prior_applied_fact(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    applied = _ordinary_manifest(cfg, plan_path, plan_hash, [page])
    _save_manifest(cfg, "parent-run", applied)
    late = _ordinary_manifest(cfg, plan_path, plan_hash, [page], status="failed")
    late["event_id"] = "late-failure"
    _save_manifest(cfg, "late.json", late, attempt_run="parent-run")

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert page["rel_path"] in result["verified"]
    assert page["rel_path"] in result["observed_failed"]
    assert result["conflicts"] == []
    assert len(result["verified"][page["rel_path"]]["evidence"]) == 1


def test_unrelated_run_is_ignored_and_current_or_queue_only_proof_is_not_enough(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    other_plan = copy.deepcopy(_ordinary_manifest(cfg, plan_path, "0" * 64, [page]))
    other_plan["run_id"] = "other-run"
    other_plan["plan_path"] = str(Path(cfg["knowledge_base"]) / ".openclaw" / "plans" / "other.json")
    _save_manifest(cfg, "other-run", other_plan)
    _write_output(cfg, page)
    empty = _ordinary_manifest(cfg, plan_path, plan_hash, [], status="applied")
    _save_manifest(cfg, "parent-run", empty)

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert result["verified"] == {}
    assert str(Path(cfg["safety"]["runs_dir"]) / "other-run.json") not in result["manifest_paths"]
    assert any(item["code"] == "manifest_target_missing" for item in result["conflicts"])


def test_missing_current_file_and_queue_only_row_never_establish_output(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    queue = Path(cfg["safety"]["manual_review_queue"])
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(json.dumps({"run_id": "parent-run", "target": page["rel_path"], "status": "approved"}) + "\n", encoding="utf-8")
    result = _reader(cfg, plan_path, plan_hash, [page])
    assert result["verified"] == {}
    assert result["observed_failed"] == {}
    assert result["manifest_paths"] == []


def test_stale_current_edit_and_hash_or_run_forgery_fail_closed(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    forged = _ordinary_manifest(cfg, plan_path, plan_hash, [page])
    forged["run_id"] = "forged-run"
    forged["plan_sha256"] = "f" * 64
    _save_manifest(cfg, "forged", forged)
    (Path(cfg["knowledge_base"]) / page["rel_path"]).write_text(page["content"] + "stale edit\n", encoding="utf-8")
    valid = _ordinary_manifest(cfg, plan_path, plan_hash, [page])
    _save_manifest(cfg, "parent-run", valid)

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert result["verified"] == {}
    codes = {item["code"] for item in result["conflicts"]}
    assert "manifest_plan_hash_mismatch" in codes or "manifest_run_mismatch" in codes
    assert "current_target_unverified" in codes


def test_conflicting_matching_records_are_visible_without_latest_wins(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    _save_manifest(cfg, "parent-run", _ordinary_manifest(cfg, plan_path, plan_hash, [page]))
    conflicting = _ordinary_manifest(cfg, plan_path, plan_hash, [page])
    conflicting["created"][0]["object_id"] = _identity(9)
    _save_manifest(cfg, "conflicting", conflicting)

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert page["rel_path"] in result["verified"]
    assert any(item["code"] == "manifest_item_identity_mismatch" for item in result["conflicts"])


def test_forged_subset_membership_hash_and_bool_revision_are_conflicts(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    _write_output(cfg, page)
    selected = _catalog(page)
    selected[page["rel_path"]]["revision"] = True
    subset = {
        "run_id": "subset-1",
        "parent_run_id": "parent-run",
        "parent_plan_path": str(plan_path),
        "parent_plan_sha256": plan_hash,
        "subset_hash": "0" * 64,
        "selected_targets": selected,
        "status": "applied",
        "reconcile": {"ok": True},
        "created": [_created(page)],
    }
    _save_manifest(cfg, "subset-1", subset)

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert result["verified"] == {}
    codes = {item["code"] for item in result["conflicts"]}
    assert "target_catalog_identity_invalid" not in codes
    assert "subset_target_tuple_mismatch" in codes


def test_out_of_root_manifest_target_is_never_opened(tmp_path: Path):
    cfg = _cfg(tmp_path)
    page = _page("wiki/sources/a.md", 1)
    plan_path, _plan_data, plan_hash = _plan(cfg, page)
    outside = tmp_path / "outside.md"
    outside.write_text("must remain untouched", encoding="utf-8")
    forged = _ordinary_manifest(cfg, plan_path, plan_hash, [page])
    forged["created"][0]["rel_path"] = "../outside.md"
    _save_manifest(cfg, "parent-run", forged)

    result = _reader(cfg, plan_path, plan_hash, [page])

    assert result["verified"] == {}
    assert outside.read_text(encoding="utf-8") == "must remain untouched"
    assert any(item["code"] == "manifest_item_target_invalid" for item in result["conflicts"])


def test_subset_hash_is_order_independent_but_parent_bound():
    catalog = {
        "wiki/b.md": {"canonical_path": "wiki/b.md", "content_sha256": "b" * 64, "object_id": _identity(2), "revision": 1},
        "wiki/a.md": {"canonical_path": "wiki/a.md", "content_sha256": "a" * 64, "object_id": _identity(1), "revision": 1},
    }
    reverse = {key: catalog[key] for key in reversed(list(catalog))}
    assert subset_evidence_hash("parent", "c" * 64, catalog) == subset_evidence_hash("parent", "c" * 64, reverse)
    assert subset_evidence_hash("parent", "c" * 64, catalog) != subset_evidence_hash("other", "c" * 64, catalog)
