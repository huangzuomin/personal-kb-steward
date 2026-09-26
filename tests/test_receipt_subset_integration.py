"""Joint B2/B3 read-side checks for page-scoped subset receipts.

The parent plan and page manifests are public synthetic records, while the
queue and output evidence are read through the production seams.  These tests
exercise the history selector's per-input view without changing the frozen
B3 writer or inventing a second output ledger.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.page_review_scope import page_review_records
from core.pipeline_history import _binding_digest, _decision_for_match
from core.plan_output_evidence import subset_evidence_hash
from core.review_queue import save_queue
from tests.test_plan_output_evidence import (
    _cfg,
    _created,
    _page,
    _save_manifest,
    _write_output,
)


def _save_parent(cfg: dict, *pages: dict, run_id: str) -> tuple[Path, dict]:
    for page in pages:
        page.setdefault("canonical_path", page["rel_path"])
        page.setdefault("target", page["rel_path"])
    plan = {
        "run_id": run_id,
        "review_contract": "page-scoped-v1",
        "planned_pages": list(pages),
        "task": "B2/B3 subset receipt integration",
    }
    path = Path(cfg["safety"]["plans_dir"]) / f"{run_id}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, plan


def _catalog(*pages: dict) -> dict[str, dict]:
    return {
        page["rel_path"]: {
            "canonical_path": page["rel_path"],
            "operation": page["operation"],
            "content_sha256": page["content_sha256"],
            "object_id": page["object_id"],
            "revision": page["revision"],
        }
        for page in pages
    }


def _receipt(pages: list[dict], inputs: list[tuple[str, str]]) -> dict:
    catalog = _catalog(*pages)
    outcomes = [
        {
            "rel": rel,
            "source_sha256": sha,
            "outcome": "ok",
            "complete": True,
            "required_targets": [page["rel_path"]],
        }
        for page, (rel, sha) in zip(pages, inputs)
    ]
    return {
        "receipt_id": "receipt-joint-subsets",
        "fingerprint_sha256": hashlib.sha256(b"joint-subsets").hexdigest(),
        "generation_state": "ok",
        "input_closure": {"originals": []},
        "input_outcomes": outcomes,
        "target_catalog": catalog,
        "binding_sha256": _binding_digest(catalog),
    }


def _queue_for(plan: dict, cfg: dict, states: dict[str, str]) -> None:
    records = page_review_records(plan)
    queue_path = cfg["safety"]["manual_review_queue"]
    existing = []
    if Path(queue_path).exists():
        existing = [
            json.loads(line)
            for line in Path(queue_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    existing = [item for item in existing if item.get("run_id") != plan["run_id"]]
    output = []
    for record in records:
        record = dict(record)
        record["id"] = f"review-{record['target'].replace('/', '-')}"
        record["status"] = states.get(record["target"], "pending")
        record["run_id"] = plan["run_id"]
        record["entry"] = "init_kb"
        record["task"] = plan["task"]
        record["risk"] = "medium"
        output.append(record)
    # The queue helper owns the JSONL encoding and preserves strict rows.
    save_queue(Path(queue_path), existing + output)


def _subset_manifest(cfg: dict, plan_path: Path, plan: dict, page: dict,
                     *, name: str, status: str = "applied") -> Path:
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    selected = _catalog(page)
    data = {
        "run_id": name,
        "parent_run_id": plan["run_id"],
        "parent_plan_path": str(plan_path),
        "parent_plan_sha256": plan_hash,
        "subset_hash": subset_evidence_hash(plan["run_id"], plan_hash, selected),
        "selected_targets": selected,
        "status": status,
        "created": [_created(page)],
    }
    if status == "applied":
        data["reconcile"] = {"ok": True}
    else:
        data["write_started"] = True
        data["reconcile"] = {"ok": False, "missing": [page["rel_path"]]}
    return _save_manifest(cfg, name, data)


def _match(plan_path: Path, plan: dict, receipt: dict) -> dict:
    return {"plan_path": plan_path, "plan": plan, "receipt": receipt}


def test_per_input_subset_union_ignores_pending_sibling_then_closes(tmp_path: Path):
    cfg = _cfg(tmp_path)
    first = _page("wiki/sources/joint-a.md", 1)
    second = _page("wiki/sources/joint-b.md", 2)
    plan_path, plan = _save_parent(cfg, first, second, run_id="joint-per-input")
    receipt = _receipt(
        [first, second],
        [("raw/a.md", "a" * 64), ("raw/b.md", "b" * 64)],
    )

    _write_output(cfg, first)
    _queue_for(plan, cfg, {first["rel_path"]: "applied", second["rel_path"]: "pending"})
    _subset_manifest(cfg, plan_path, plan, first, name="joint-subset-a")

    first_decision = _decision_for_match(
        cfg, _match(plan_path, plan, receipt), source_rel="raw/a.md"
    )
    second_decision = _decision_for_match(
        cfg, _match(plan_path, plan, receipt), source_rel="raw/b.md"
    )
    assert first_decision["decision"] == "unchanged_inputs", first_decision
    assert second_decision["decision"] == "pending_review"
    assert first_decision["output_evidence"]["verified"]
    assert second_decision["required_targets"] == [second["rel_path"]]

    # Complete the independent sibling in a second protected subset.  The
    # selector must union both manifests under the exact parent hash instead
    # of taking the lexically latest subset as the whole truth.
    _write_output(cfg, second)
    _queue_for(plan, cfg, {
        first["rel_path"]: "applied", second["rel_path"]: "applied",
    })
    _subset_manifest(cfg, plan_path, plan, second, name="joint-subset-b")

    closed = _decision_for_match(
        cfg, _match(plan_path, plan, receipt), source_rel="raw/b.md"
    )
    assert closed["decision"] == "unchanged_inputs"
    assert set(closed["output_evidence"]["verified"]) == {
        first["rel_path"], second["rel_path"],
    }


def test_failed_observed_write_and_later_subset_are_unionable_without_success_claim(
    tmp_path: Path,
):
    cfg = _cfg(tmp_path)
    first = _page("wiki/sources/joint-failed-a.md", 3)
    second = _page("wiki/sources/joint-failed-b.md", 4)
    plan_path, plan = _save_parent(cfg, first, second, run_id="joint-failed-subset")
    receipt = _receipt(
        [first, second],
        [("raw/c.md", "c" * 64), ("raw/d.md", "d" * 64)],
    )

    _write_output(cfg, first)
    _queue_for(plan, cfg, {first["rel_path"]: "applied", second["rel_path"]: "pending"})
    failed_path = _subset_manifest(
        cfg, plan_path, plan, first, name="joint-failed-attempt", status="failed"
    )
    first_decision = _decision_for_match(
        cfg, _match(plan_path, plan, receipt), source_rel="raw/c.md"
    )
    assert first_decision["decision"] == "unchanged_inputs", first_decision
    assert first_decision["output_evidence"]["verified"] == {}
    assert first_decision["output_evidence"]["observed_failed"][first["rel_path"]]
    assert failed_path.exists()

    _write_output(cfg, second)
    _queue_for(plan, cfg, {
        first["rel_path"]: "applied", second["rel_path"]: "applied",
    })
    _subset_manifest(cfg, plan_path, plan, second, name="joint-remainder")
    closed = _decision_for_match(
        cfg, _match(plan_path, plan, receipt), source_rel="raw/d.md"
    )
    assert closed["decision"] == "unchanged_inputs"
    evidence = closed["output_evidence"]
    assert first["rel_path"] in evidence["observed_failed"]
    assert second["rel_path"] in evidence["verified"]
