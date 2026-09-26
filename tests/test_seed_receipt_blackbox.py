# -*- coding: utf-8 -*-
"""B2-seed receipt acceptance through the real init/review/apply path.

The fixture uses public synthetic quicknote/inbox files and the actual atomic
seed executor/updater.  Only the model provider is replaced; concept/case
providers are separate counters so derived discovery calls cannot be confused
with seed calls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import make_cfg, card_state_of


INPUTS = {
    "quicknote/seed-a.md": (
        "# 合成快速观察\n\n"
        "先记录一个小假设，再核对一次结果。\n"
    ),
    "inbox/seed-b.md": (
        "# 合成收件观察\n\n"
        "把下一步行动写成一个可检查的小实验。\n"
    ),
}


class SeedProvider:
    """Provider sentinel for the actual ``atomic_seed`` model call."""

    def __init__(self, *, zero: bool = False):
        self.zero = zero
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        if self.zero:
            return json.dumps({"thoughts": []}, ensure_ascii=False)
        thoughts = []
        for unit in payload.get("units", []):
            unit_id = int(unit["id"])
            thoughts.append({
                "title": f"合成种子观察-{unit_id}",
                "kind": "assertion",
                "statement": f"第{unit_id}个输入可沉淀为一个待复核的小念头。",
                "unit_ids": [unit_id],
                "growth_directions": [{
                    "action": "记录一次实际结果并回看假设。",
                    "basis": "需要用一次小实验核对这个念头。",
                }],
                "negative_scope": ["暂不外推到其他场景。"],
            })
        return json.dumps({"thoughts": thoughts}, ensure_ascii=False)


class DerivedZeroProvider:
    """Separate concept/case counter; valid zero is returned if called."""

    def __init__(self, kind: str):
        self.kind = kind
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        if self.kind == "concept":
            return json.dumps({"concept_found": False, "reason": "seed blackbox zero"},
                              ensure_ascii=False)
        return json.dumps({"case_found": False, "reason": "seed blackbox zero"},
                          ensure_ascii=False)


@pytest.fixture
def seed_vault(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    before: dict[str, bytes] = {}
    for rel, text in INPUTS.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        before[rel] = target.read_bytes()
    yield tmp_path, cfg
    for rel, expected in before.items():
        assert (tmp_path / rel).read_bytes() == expected


def build_init_plan(
    cfg: dict,
    run_id: str,
    provider: SeedProvider,
    *,
    include_all: bool = False,
):
    concept = DerivedZeroProvider("concept")
    case = DerivedZeroProvider("case")
    # ``skills/mindseed-grow/executor.py`` imports the provider at load time;
    # patch the public core seam before the real executor is loaded.
    with patch("core.llm.call_chat_completion", provider):
        plan = steward.build_initialization_plan(
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
            discover_providers={"concept": concept, "case": case},
        )
    # Keep derived-call accounting next to the plan without changing the
    # production result shape.
    plan["_blackbox_derived_calls"] = {
        "concept": len(concept.calls),
        "case": len(case.calls),
    }
    return plan


def save_plan(cfg: dict, plan: dict) -> Path:
    path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    return path


def apply_saved_plan(cfg: dict, plan: dict) -> Path:
    path = save_plan(cfg, plan)
    queue_path = steward.review_queue_path(cfg)
    queue = steward.load_queue(queue_path)
    run_items = [item for item in queue if item.get("run_id") == plan["run_id"]]
    assert run_items, "seed proposal must be represented in the review queue"
    for item in run_items:
        assert steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="approve",
                id=item["id"],
                reason="B2 seed synthetic acceptance",
            ),
        ) == 0
    assert steward.command_review(
        cfg,
        SimpleNamespace(review_command="apply-approved", run_id=plan["run_id"]),
    ) == 0
    return path


def seed_stage(plan: dict) -> dict:
    return next(action for action in plan["actions"]
                if action.get("stage") == "seed_cluster")


def seed_pages(plan: dict) -> list[dict]:
    return [
        page for page in plan.get("planned_pages", [])
        if str(page.get("rel_path") or page.get("target") or "").startswith("wiki/seeds/")
    ]


def seed_cards(root: Path) -> list[Path]:
    directory = root / "wiki" / "seeds"
    return sorted(path for path in directory.glob("*.md")
                  if path.name != "README.md") if directory.exists() else []


def plan_text(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, sort_keys=True)


def assert_derived_calls_are_separate(plan: dict) -> None:
    derived = plan.get("_blackbox_derived_calls") or {}
    assert derived == {"concept": 0, "case": 0}


def test_seed_pending_repeat_has_zero_calls_and_old_plan_ref(seed_vault):
    root, cfg = seed_vault
    provider = SeedProvider()

    first = build_init_plan(cfg, "b2-seed-pending-a", provider, include_all=False)
    assert provider.calls, "first plan must exercise the real atomic provider seam"
    assert seed_pages(first)
    first_path = save_plan(cfg, first)
    first_bytes = first_path.read_bytes()
    first_calls = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-seed-pending-b", provider, include_all=False)
    stage = seed_stage(repeat)
    assert len(provider.calls) == first_calls
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "pending_review"
    assert seed_pages(repeat) == []
    assert first_path.read_bytes() == first_bytes
    assert first_path.name in plan_text(repeat) or "b2-seed-pending-a" in plan_text(repeat)
    assert_derived_calls_are_separate(repeat)


def test_seed_applied_repeat_preserves_all_ids_revisions_and_bytes(seed_vault):
    root, cfg = seed_vault
    provider = SeedProvider()

    first = build_init_plan(cfg, "b2-seed-applied-a", provider, include_all=False)
    pages = seed_pages(first)
    assert pages
    first_path = apply_saved_plan(cfg, first)
    assert first_path.exists()
    cards_before = {
        path.relative_to(root).as_posix(): {
            "bytes": path.read_bytes(),
            "object_id": card_state_of(path).get("object_id"),
            "revision": int(card_state_of(path).get("revision")),
            "thought_id": card_state_of(path).get("seed_state", {}).get("thought_id"),
        }
        for path in seed_cards(root)
    }
    assert cards_before
    calls_before = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-seed-applied-b", provider, include_all=False)
    stage = seed_stage(repeat)
    assert len(provider.calls) == calls_before
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "unchanged_inputs"
    assert seed_pages(repeat) == []
    cards_after = {
        path.relative_to(root).as_posix(): {
            "bytes": path.read_bytes(),
            "object_id": card_state_of(path).get("object_id"),
            "revision": int(card_state_of(path).get("revision")),
            "thought_id": card_state_of(path).get("seed_state", {}).get("thought_id"),
        }
        for path in seed_cards(root)
    }
    assert cards_after == cards_before
    assert_derived_calls_are_separate(repeat)


def test_seed_rejected_repeat_has_zero_calls_and_no_resubmit(seed_vault):
    root, cfg = seed_vault
    provider = SeedProvider()

    first = build_init_plan(cfg, "b2-seed-rejected-a", provider, include_all=False)
    first_path = save_plan(cfg, first)
    queue_path = steward.review_queue_path(cfg)
    queue = steward.load_queue(queue_path)
    run_items = [item for item in queue if item.get("run_id") == first["run_id"]]
    assert run_items
    for item in run_items:
        assert steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="reject",
                id=item["id"],
                reason="B2 seed synthetic rejection",
            ),
        ) == 0
    calls_before = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-seed-rejected-b", provider, include_all=False)
    stage = seed_stage(repeat)
    assert len(provider.calls) == calls_before
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "review_rejected"
    assert seed_pages(repeat) == []
    assert not seed_cards(root)
    assert first_path.exists()
    assert any(item.get("status") == "rejected" for item in steward.load_queue(queue_path)
               if item.get("run_id") == first["run_id"])


def test_seed_explicit_valid_zero_has_zero_repeat_calls_and_no_fake_card(seed_vault):
    root, cfg = seed_vault
    provider = SeedProvider(zero=True)

    first = build_init_plan(cfg, "b2-seed-zero-a", provider, include_all=False)
    first_stage = seed_stage(first)
    outcomes = first_stage.get("input_outcomes") or []
    assert len(outcomes) == len(INPUTS)
    assert all(item.get("outcome") == "zero" and item.get("complete") is True
               for item in outcomes), outcomes
    assert all(item.get("required_targets") == [] for item in outcomes)
    assert seed_pages(first) == []
    assert not seed_cards(root)
    first_path = save_plan(cfg, first)
    calls_before = len(provider.calls)

    repeat = build_init_plan(cfg, "b2-seed-zero-b", provider, include_all=False)
    stage = seed_stage(repeat)
    assert len(provider.calls) == calls_before
    assert stage.get("provider_calls", 0) == 0
    assert stage.get("receipt_decision") == "zero_output"
    assert seed_pages(repeat) == []
    assert not seed_cards(root)
    assert first_path.exists()
    assert_derived_calls_are_separate(repeat)


@pytest.mark.parametrize("apply_first", [False, True], ids=["pending", "applied"])
def test_seed_model_change_invalidates_pending_or_applied_receipt(apply_first, seed_vault):
    root, cfg = seed_vault
    cfg["llm"]["model"] = "synthetic-seed-model-v1"
    provider = SeedProvider()

    first = build_init_plan(cfg, "b2-seed-model-a", provider, include_all=False)
    assert provider.calls
    if apply_first:
        apply_saved_plan(cfg, first)
    else:
        save_plan(cfg, first)
    calls_before = len(provider.calls)

    cfg["llm"]["model"] = "synthetic-seed-model-v2"
    repeat = build_init_plan(cfg, "b2-seed-model-b", provider, include_all=False)
    stage = seed_stage(repeat)
    assert len(provider.calls) == calls_before + 1
    assert stage.get("provider_calls", 0) == 1
    assert stage.get("receipt_decision") not in {
        "pending_review", "unchanged_inputs", "review_rejected", "zero_output",
    }
    assert stage.get("input_outcomes")
    assert_derived_calls_are_separate(repeat)
