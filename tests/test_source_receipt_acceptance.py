# -*- coding: utf-8 -*-
"""B2 source receipt acceptance through the public init/review/apply path.

These tests use the public synthetic raw fixture and the real source executor.
Only the source provider is replaced; typed discovery providers return valid
zero results so their calls cannot be mistaken for source-provider calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.typed_card_updates import GENERATED_START
from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import (
    RAW_REL,
    card_state_of,
    make_cfg,
    source_answer,
    write_raw,
)


FAILED_RAW_REL = "raw/failed.md"
FAILED_MARKER = "故意失败来源"


class SourceProvider:
    """Small provider sentinel; calls here mean source executor calls only."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        return self.response


class RoutingSourceProvider:
    """Return the valid fixture for one raw and fail the sibling raw."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        if FAILED_MARKER in str(payload.get("text") or ""):
            raise RuntimeError("synthetic source provider failure")
        return source_answer()


class FailingSourceProvider:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        raise RuntimeError("synthetic retry failure")


def concept_zero_provider(cfg, system_prompt, payload):
    del cfg, system_prompt, payload
    return json.dumps(
        {"concept_found": False, "reason": "合成验收不生成概念卡"},
        ensure_ascii=False,
    )


def case_zero_provider(cfg, system_prompt, payload):
    del cfg, system_prompt, payload
    return json.dumps(
        {"case_found": False, "reason": "合成验收不生成案例卡"},
        ensure_ascii=False,
    )


def zero_source_answer() -> str:
    return json.dumps(
        {
            "chunk_viable": False,
            "reason": "合成资料已完整读取，但没有可独立沉淀的信息。",
            "key_statements": [],
            "topics": [],
        },
        ensure_ascii=False,
    )


def write_failed_raw(root: Path) -> Path:
    target = root / FAILED_RAW_REL
    target.write_text(
        f"# 合成失败来源\n\n{FAILED_MARKER}：本输入用于验证 sibling 隔离。\n",
        encoding="utf-8",
    )
    return target


def fake_source_contract(version: str) -> dict[str, str]:
    return {
        "generator_version": version,
        "prompt_sha256": f"prompt-{version}",
        "schema_sha256": f"schema-{version}",
        "implementation_files": {"synthetic": version},
    }


@pytest.fixture
def source_vault(tmp_path):
    cfg = make_cfg(tmp_path)
    write_raw(tmp_path)
    raw_before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "raw").glob("*.md")
    }
    yield tmp_path, cfg
    raw_after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / "raw").glob("*.md")
    }
    for rel, before in raw_before.items():
        assert raw_after.get(rel) == before


def build_init_plan(cfg, run_id: str, provider: SourceProvider, *, include_all=False):
    """Build through the production initializer, with only source mocked."""
    with patch("core.llm.call_chat_completion", provider):
        return steward.build_initialization_plan(
            cfg,
            plan_run_id=run_id,
            stamp=steward.stamp(),
            executor_plan_fn=steward.mvp_executor_plan,
            page_requires_manual_review=steward.page_requires_manual_review,
            duplicate_page_targets=steward.duplicate_page_targets,
            page_has_blocked_placeholder=lambda page: steward.page_has_blocked_placeholder(page, cfg),
            planned_raw_coverage=steward.planned_raw_coverage,
            batch_size=6,
            use_llm=True,
            include_all=include_all,
            discover_providers={
                "concept": concept_zero_provider,
                "case": case_zero_provider,
            },
        )


def save_plan(cfg, plan):
    path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    return path


def apply_saved_plan(cfg, plan):
    """Use the normal saved-plan -> review approve -> apply-approved path."""
    path = save_plan(cfg, plan)
    run_id = plan["run_id"]
    queue_path = steward.review_queue_path(cfg)
    queued = steward.load_queue(queue_path)
    for item in queued:
        if item.get("run_id") == run_id:
            assert steward.command_review(
                cfg,
                SimpleNamespace(
                    review_command="approve",
                    id=item["id"],
                    reason="B2 synthetic acceptance",
                ),
            ) == 0
    result = steward.command_review(
        cfg,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    )
    return path, result


def source_stage(plan):
    return next(action for action in plan["actions"] if action.get("stage") == "source_compile")


def source_pages(plan):
    return [
        page
        for page in plan.get("planned_pages", [])
        if str(page.get("rel_path") or page.get("target") or "").startswith("wiki/sources/")
    ]


def source_cards(root: Path):
    directory = root / "wiki" / "sources"
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md") if directory.exists() else []


def plan_text(plan) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True)


def test_pending_same_source_is_cached_without_call_and_keeps_old_plan(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-pending-a", provider, include_all=False)
    assert provider.calls, "the first source plan must exercise the real provider seam"
    first_path = save_plan(cfg, first)
    first_bytes = first_path.read_bytes()
    first_calls = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-source-pending-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == first_calls, "pending source input must not call source provider again"
    assert source_pages(repeat) == []
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "pending_review"
    assert first_path.exists()
    assert first_path.read_bytes() == first_bytes
    assert "b2-source-pending-a" in plan_text(repeat) or first_path.name in plan_text(repeat)


def test_applied_same_source_keeps_identity_revision_and_bytes(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-applied-a", provider, include_all=False)
    pages = source_pages(first)
    assert pages
    target = root / str(pages[0]["rel_path"])
    raw_before = (root / RAW_REL).read_bytes()
    first_path, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    assert first_path.exists()
    before_card = target.read_bytes()
    before_meta = card_state_of(target)
    before_calls = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-source-applied-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == before_calls
    assert source_pages(repeat) == []
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "unchanged_inputs"
    assert target.read_bytes() == before_card
    after_meta = card_state_of(target)
    assert after_meta["object_id"] == before_meta["object_id"]
    assert int(after_meta["revision"]) == int(before_meta["revision"])
    assert (root / RAW_REL).read_bytes() == raw_before


def test_rejected_same_source_is_cached_without_reproposal(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-rejected-a", provider, include_all=False)
    first_path = save_plan(cfg, first)
    first_calls = len(provider.calls)
    queue_path = steward.review_queue_path(cfg)
    queued = steward.load_queue(queue_path)
    run_items = [item for item in queued if item.get("run_id") == first["run_id"]]
    assert run_items, "source proposal must be represented in the review queue"
    for item in run_items:
        assert steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="reject",
                id=item["id"],
                reason="B2 synthetic rejection",
            ),
        ) == 0

    repeat = build_init_plan(cfg, "b2-source-rejected-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == first_calls
    assert source_pages(repeat) == []
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "review_rejected"
    assert first_path.exists()
    assert source_cards(root) == []
    assert any(
        item.get("run_id") == first["run_id"] and item.get("status") == "rejected"
        for item in steward.load_queue(queue_path)
    )


def test_explicit_valid_zero_is_cached_without_card_or_source_call(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(zero_source_answer())

    first = build_init_plan(cfg, "b2-source-zero-a", provider, include_all=False)
    first_path = save_plan(cfg, first)
    first_stage = source_stage(first)
    first_outcomes = first_stage.get("input_outcomes") or []
    assert first_outcomes and first_outcomes[0].get("outcome") == "zero"
    assert source_pages(first) == []
    assert source_cards(root) == []
    first_calls = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-source-zero-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == first_calls
    assert source_pages(repeat) == []
    assert source_cards(root) == []
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") in {"zero_output", "pending_review"}
    assert first_path.exists()


def test_manual_source_card_edit_invalidates_applied_cache_without_overwrite(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-manual-a", provider, include_all=False)
    pages = source_pages(first)
    assert pages
    target = root / str(pages[0]["rel_path"])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    original_card = target.read_bytes()
    original_meta = card_state_of(target)
    before_calls = len(provider.calls)

    original_text = original_card.decode("utf-8")
    assert GENERATED_START in original_text
    edited_text = original_text.replace(
        GENERATED_START,
        GENERATED_START + "\n手工改动（生成区）：阻止静默覆盖。",
        1,
    )
    target.write_bytes(edited_text.encode("utf-8"))
    edited_card = target.read_bytes()

    repeat = build_init_plan(cfg, "b2-source-manual-b", provider, include_all=False)
    stage = source_stage(repeat)
    outcomes = stage.get("input_outcomes") or []
    source_call_delta = len(provider.calls) - before_calls

    assert target.read_bytes() == edited_card
    assert target.read_bytes() != original_card
    assert source_pages(repeat) == []
    assert stage.get("processed", 0) == 0
    assert source_call_delta == 1
    assert outcomes
    outcome = outcomes[0]
    assert outcome.get("outcome") == "blocked", outcomes
    assert outcome.get("updater_disposition") == "blocked", outcomes
    assert "托管区块摘要" in str(outcome.get("reason") or "")
    after_meta = card_state_of(target)
    assert after_meta["object_id"] == original_meta["object_id"]
    assert int(after_meta["revision"]) == int(original_meta["revision"])


@pytest.mark.parametrize("apply_first", [False, True], ids=["pending", "applied"])
def test_source_model_change_invalidates_saved_receipt(source_vault, apply_first):
    root, cfg = source_vault
    cfg["llm"]["model"] = "synthetic-model-v1"
    provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-model-a", provider, include_all=False)
    assert provider.calls
    if apply_first:
        _, apply_result = apply_saved_plan(cfg, first)
        assert apply_result == 0
    else:
        save_plan(cfg, first)
    first_calls = len(provider.calls)

    cfg["llm"]["model"] = "synthetic-model-v2"
    repeat = build_init_plan(cfg, "b2-source-model-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == first_calls + 1
    assert stage.get("provider_calls", 1) == 1
    assert stage.get("receipt_decision") not in {
        "pending_review", "unchanged_inputs", "review_rejected", "zero_output",
    }


def test_source_generator_contract_drift_invalidates_applied_receipt(source_vault):
    root, cfg = source_vault
    provider = SourceProvider(source_answer())

    with patch(
        "core.pipeline_history.source_generator_contract",
        return_value=fake_source_contract("contract-v1"),
    ):
        first = build_init_plan(cfg, "b2-source-contract-a", provider, include_all=False)
    pages = source_pages(first)
    assert pages
    target = root / str(pages[0]["rel_path"])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    before_card = target.read_bytes()
    first_calls = len(provider.calls)

    with patch(
        "core.pipeline_history.source_generator_contract",
        return_value=fake_source_contract("contract-v2"),
    ):
        repeat = build_init_plan(cfg, "b2-source-contract-b", provider, include_all=False)
    stage = source_stage(repeat)

    assert len(provider.calls) == first_calls + 1
    assert stage.get("provider_calls", 1) == 1
    assert source_pages(repeat) == []
    assert target.read_bytes() == before_card


def test_failed_source_sibling_retries_without_reprocessing_applied_sibling(source_vault):
    root, cfg = source_vault
    failed_raw = write_failed_raw(root)
    failed_raw_before = failed_raw.read_bytes()
    provider = RoutingSourceProvider()

    first = build_init_plan(cfg, "b2-source-sibling-a", provider, include_all=False)
    first_stage = source_stage(first)
    first_outcomes = {item["rel"]: item for item in first_stage.get("input_outcomes", [])}
    assert first_outcomes[RAW_REL]["outcome"] == "ok"
    assert first_outcomes[FAILED_RAW_REL]["outcome"] in {"error", "blocked", "partial"}
    assert first_outcomes[FAILED_RAW_REL]["complete"] is False
    pages = source_pages(first)
    assert len(pages) == 1
    assert RAW_REL in pages[0].get("sources", [])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    calls_before_repeat = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-source-sibling-b", provider, include_all=False)
    stage = source_stage(repeat)
    repeat_calls = provider.calls[calls_before_repeat:]
    repeat_outcomes = {item["rel"]: item for item in stage.get("input_outcomes", [])}

    assert len(repeat_calls) == 1
    assert FAILED_MARKER in str(repeat_calls[0].get("text") or "")
    assert FAILED_RAW_REL in repeat_outcomes
    assert RAW_REL not in repeat_outcomes
    assert source_pages(repeat) == []
    assert failed_raw.read_bytes() == failed_raw_before


def test_failed_retry_then_restored_source_converges_to_verified_receipt(source_vault):
    root, cfg = source_vault
    good_provider = SourceProvider(source_answer())

    first = build_init_plan(cfg, "b2-source-converge-a", good_provider, include_all=False)
    pages = source_pages(first)
    assert pages
    target = root / str(pages[0]["rel_path"])
    _, apply_result = apply_saved_plan(cfg, first)
    assert apply_result == 0
    original_card = target.read_bytes()

    original_text = original_card.decode("utf-8")
    edited_text = original_text.replace(
        GENERATED_START,
        GENERATED_START + "\n失败重试编辑（生成区）。",
        1,
    )
    target.write_text(edited_text, encoding="utf-8", newline="")

    failed_provider = FailingSourceProvider()
    failed_plan = build_init_plan(cfg, "b2-source-converge-b", failed_provider, include_all=False)
    failed_stage = source_stage(failed_plan)
    failed_outcomes = failed_stage.get("input_outcomes") or []
    assert failed_provider.calls
    assert failed_outcomes
    assert failed_outcomes[0].get("outcome") in {"error", "blocked", "partial"}
    assert failed_outcomes[0].get("complete") is False
    assert source_pages(failed_plan) == []
    failed_path = save_plan(cfg, failed_plan)
    assert failed_path.exists()
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        if item.get("run_id") == failed_plan["run_id"]:
            assert steward.command_review(
                cfg,
                SimpleNamespace(
                    review_command="reject",
                    id=item["id"],
                    reason="B2 synthetic failed retry",
                ),
            ) == 0

    target.write_bytes(original_card)
    recovery_provider = SourceProvider(source_answer())
    recovery = build_init_plan(cfg, "b2-source-converge-c", recovery_provider, include_all=False)
    recovery_stage = source_stage(recovery)

    assert recovery_provider.calls == []
    assert source_pages(recovery) == []
    assert recovery_stage.get("provider_calls", 0) == 0
    assert recovery_stage.get("receipt_decision") == "unchanged_inputs"
    assert target.read_bytes() == original_card
