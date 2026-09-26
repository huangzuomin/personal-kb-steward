# -*- coding: utf-8 -*-
"""B2 source receipt save-boundary regressions."""
from __future__ import annotations

import json
import hashlib

from core.pipeline_history import lookup_generation_receipt
from core.typed_card_updates import GENERATED_START
from tests.test_card_pipeline_integration import make_cfg, write_raw
from tests.test_source_receipt_acceptance import (
    SourceProvider,
    apply_saved_plan,
    build_init_plan,
    source_pages,
    source_stage,
    source_answer,
)
from scripts import personal_kb_steward as steward


RAW_REL = "raw/doc.md"


def _saved_receipt(plan_path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    receipts = plan["generation_receipts"]["stages"]
    source = [item for item in receipts if item.get("stage") == "source_compile"]
    assert len(source) == 1
    return plan, source[0]


def test_noop_snapshot_survives_outside_edit_and_repeat_has_zero_calls(tmp_path):
    cfg = make_cfg(tmp_path)
    write_raw(tmp_path)
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "pipeline-history-noop-a", provider)
    target = tmp_path / str(source_pages(first)[0]["rel_path"])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0

    target.write_bytes(target.read_bytes() + b"\nManual outside note.\n")
    second = build_init_plan(cfg, "pipeline-history-noop-b", provider)
    outcome = source_stage(second)["input_outcomes"][0]
    assert outcome["updater_disposition"] == "noop"
    assert outcome["updater_noop_targets"] == [str(target.relative_to(tmp_path)).replace("\\", "/")]
    assert outcome["updater_target_snapshots"]

    plan_path = steward.write_execution_plan(cfg, second)
    _, receipt = _saved_receipt(plan_path)
    saved_outcome = receipt["input_outcomes"][0]
    assert saved_outcome["updater_target_snapshots"]
    assert receipt["target_catalog"][saved_outcome["required_targets"][0]]["verification"] == "updater_snapshot"

    before = len(provider.calls)
    repeated = build_init_plan(cfg, "pipeline-history-noop-c", provider)
    assert len(provider.calls) - before == 0
    assert source_stage(repeated)["receipt_decision"] == "unchanged_inputs"


def test_noop_snapshot_changed_before_save_is_blocked_and_retryable(tmp_path):
    cfg = make_cfg(tmp_path)
    write_raw(tmp_path)
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "pipeline-history-race-a", provider)
    target = tmp_path / str(source_pages(first)[0]["rel_path"])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0

    target.write_bytes(target.read_bytes() + b"\nManual outside note.\n")
    second = build_init_plan(cfg, "pipeline-history-race-b", provider)
    before_save = source_stage(second)
    outcome = before_save["input_outcomes"][0]
    assert outcome["updater_disposition"] == "noop"
    changed = target.read_bytes().replace(
        GENERATED_START.encode("utf-8"),
        (GENERATED_START + "\nManual INSIDE edit after noop decision.\n").encode("utf-8"),
        1,
    )
    target.write_bytes(changed)

    plan_path = steward.write_execution_plan(cfg, second)
    _, receipt = _saved_receipt(plan_path)
    saved_outcome = receipt["input_outcomes"][0]
    assert receipt["generation_state"] == "blocked"
    assert saved_outcome["complete"] is False
    assert saved_outcome["outcome"] == "blocked"
    assert saved_outcome["receipt_binding_disposition"] == "blocked"
    assert "changed between updater decision and save" in str(saved_outcome["reason"])
    assert target.read_bytes() == changed

    before = len(provider.calls)
    repeated = build_init_plan(cfg, "pipeline-history-race-c", provider)
    assert len(provider.calls) - before >= 1
    assert source_stage(repeated).get("receipt_decision") != "unchanged_inputs"


def test_corrupt_schema_version_bool_is_retryable(tmp_path):
    cfg = make_cfg(tmp_path)
    write_raw(tmp_path)
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "pipeline-history-corrupt-a", provider)
    plan_path, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    saved = json.loads(plan_path.read_text(encoding="utf-8"))
    saved["generation_receipts"]["schema_version"] = True
    plan_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    raw_sha256 = hashlib.sha256((tmp_path / RAW_REL).read_bytes()).hexdigest()
    decision = lookup_generation_receipt(
        cfg,
        "source_compile",
        source_rel=RAW_REL,
        source_sha256=raw_sha256,
        use_llm=True,
    )
    assert decision is not None
    assert decision["decision"] == "retryable"
    assert decision["reason"] == "saved generation receipt schema is corrupt"
