"""Focused B2-seed receipt checks over the real plan/save/review/apply seam.

The provider is the only replaced boundary.  Pages are produced by the real
atomic seed executor and updater, so these checks cover receipt binding and
input selection rather than injecting ready-made cards.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.content_safety import SensitiveContentError
from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import make_cfg


class SeedProvider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        thoughts = []
        for unit in payload.get("units", []):
            source = str(unit.get("source") or "source").replace("/", "-")
            number = int(unit["id"])
            thoughts.append({
                "title": f"B2验收-{source}-{number}",
                "kind": "assertion",
                "statement": f"{source} 的第{number}个观察可沉淀为待复核的小念头。",
                "unit_ids": [number],
                "growth_directions": [{
                    "action": "记录一次结果并回看这个假设。",
                    "basis": "需要一次小实验核对这个念头。",
                }],
                "negative_scope": ["暂不外推到其他场景。"],
            })
        return json.dumps({"thoughts": thoughts}, ensure_ascii=False)


class DerivedZeroProvider:
    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt, payload
        return json.dumps({"concept_found": False, "reason": "B2 seed test"},
                          ensure_ascii=False)


class RaisingProvider:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        raise self.error


def make_seed_vault(root: Path, count: int) -> tuple[Path, dict]:
    cfg = make_cfg(root)
    for number in range(count):
        target = root / "quicknote" / f"seed-{number:02d}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"# B2 seed {number}\n\n记录第 {number} 个独立观察，准备一次小实验。\n",
            encoding="utf-8",
        )
    return root, cfg


def build_seed_plan(cfg: dict, run_id: str, provider: SeedProvider) -> dict:
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
            include_all=False,
            discover_providers={
                "concept": DerivedZeroProvider(),
                "case": DerivedZeroProvider(),
            },
        )


def save_plan(cfg: dict, plan: dict) -> Path:
    path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    return path


def apply_saved_plan(cfg: dict, plan: dict) -> Path:
    path = save_plan(cfg, plan)
    queue = steward.load_queue(steward.review_queue_path(cfg))
    items = [item for item in queue if item.get("run_id") == plan["run_id"]]
    assert items
    for item in items:
        assert steward.command_review(
            cfg,
            SimpleNamespace(review_command="approve", id=item["id"],
                             reason="B2 seed receipt acceptance"),
        ) == 0
    assert steward.command_review(
        cfg, SimpleNamespace(review_command="apply-approved", run_id=plan["run_id"])
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


def stage_inputs(stage: dict) -> list[str]:
    return [str(item.get("rel") or "") for item in stage.get("input_outcomes", [])]


def test_atomic_stage_reports_zero_provider_calls_for_empty_units(tmp_path: Path):
    root, cfg = make_seed_vault(tmp_path, 2)
    for path in (root / "quicknote").glob("*.md"):
        path.write_bytes(b"# Empty synthetic note\n")
    provider = SeedProvider()

    plan = build_seed_plan(cfg, "b2-seed-call-count-empty", provider)
    stage = seed_stage(plan)
    assert provider.calls == []
    assert stage["provider_calls"] == 0


@pytest.mark.parametrize(
    "error", [RuntimeError("synthetic model failure"),
               SensitiveContentError("synthetic provider safety failure")],
    ids=["ordinary-error", "sensitive-error"],
)
def test_atomic_stage_counts_provider_attempts_that_raise(tmp_path: Path, error: BaseException):
    root, cfg = make_seed_vault(tmp_path, 2)
    provider = RaisingProvider(error)

    plan = build_seed_plan(cfg, "b2-seed-call-count-error", provider)
    stage = seed_stage(plan)
    assert len(provider.calls) == 1
    assert stage["provider_calls"] == 1
    del root


def test_legacy_topic_stage_reports_observed_clustering_attempt(tmp_path: Path):
    root, cfg = make_seed_vault(tmp_path, 2)
    cfg["seed_generation"]["mode"] = "topic"
    provider = SeedProvider()

    plan = build_seed_plan(cfg, "b2-seed-call-count-topic", provider)
    stage = seed_stage(plan)
    assert len(provider.calls) == 1
    assert stage["provider_calls"] == 1
    del root


def test_seed_receipt_binds_contract_outcomes_and_targets(tmp_path: Path):
    root, cfg = make_seed_vault(tmp_path, 2)
    provider = SeedProvider()

    plan = build_seed_plan(cfg, "b2-seed-receipt-bind", provider)
    assert len(provider.calls) == 1
    assert seed_pages(plan)
    path = save_plan(cfg, plan)
    saved = json.loads(path.read_text(encoding="utf-8"))
    receipts = saved["generation_receipts"]
    assert receipts["schema_version"] == 1
    stage = next(item for item in receipts["stages"] if item["stage"] == "seed_cluster")
    contract = stage["input_closure"]["generator_contract"]
    inventory = contract["implementation_files"]
    assert "core/atomic_seed.py" in inventory
    assert "core/seed_updates.py" in inventory
    assert "skills/topic-research-compile/executor.py" not in inventory
    assert len(stage["input_outcomes"]) == 2
    assert all(item["complete"] is True for item in stage["input_outcomes"])
    assert all(item["required_targets"] for item in stage["input_outcomes"])
    assert all(
        target in stage["target_catalog"]
        for item in stage["input_outcomes"]
        for target in item["required_targets"]
    )
    assert all(item["source_sha256"] for item in stage["input_outcomes"])
    del root


def test_pending_seed_batch_does_not_starve_later_unseen_input(tmp_path: Path):
    root, cfg = make_seed_vault(tmp_path, 11)
    provider = SeedProvider()

    first = build_seed_plan(cfg, "b2-seed-batch-pending", provider)
    first_stage = seed_stage(first)
    assert stage_inputs(first_stage) == [f"quicknote/seed-{n:02d}.md" for n in range(10)]
    assert len(seed_pages(first)) >= 10
    save_plan(cfg, first)
    calls_before = len(provider.calls)

    continuation = build_seed_plan(cfg, "b2-seed-batch-continuation", provider)
    stage = seed_stage(continuation)
    assert len(provider.calls) == calls_before + 1
    assert stage["provider_calls"] == 1
    assert stage_inputs(stage) == ["quicknote/seed-10.md"]
    assert not any(path in stage_inputs(stage) for path in stage_inputs(first_stage))
    assert seed_pages(continuation)
    del root


def test_seed_successful_batch_is_not_regenerated_when_later_sibling_fails(tmp_path: Path):
    root, cfg = make_seed_vault(tmp_path, 11)
    provider = SeedProvider()

    first = build_seed_plan(cfg, "b2-seed-mixed-success", provider)
    apply_saved_plan(cfg, first)
    calls_after_success = len(provider.calls)

    failed_path = root / "quicknote" / "seed-10.md"
    failed_path.write_bytes("# B2 seed 10\n\n损坏字符：�\n".encode("utf-8"))
    failed = build_seed_plan(cfg, "b2-seed-mixed-failure", provider)
    failed_stage = seed_stage(failed)
    assert len(provider.calls) == calls_after_success
    assert stage_inputs(failed_stage) == ["quicknote/seed-10.md"]
    assert failed_stage["provider_calls"] == 0
    assert failed_stage["input_outcomes"][0]["complete"] is False
    assert failed_stage["input_outcomes"][0]["outcome"] == "blocked"
    assert seed_pages(failed) == []

    failed_path.write_text(
        "# B2 seed 10\n\n修复后的独立观察，准备一次小实验。\n",
        encoding="utf-8",
    )
    recovered = build_seed_plan(cfg, "b2-seed-mixed-retry", provider)
    recovered_stage = seed_stage(recovered)
    assert len(provider.calls) == calls_after_success + 1
    assert stage_inputs(recovered_stage) == ["quicknote/seed-10.md"]
    assert recovered_stage["provider_calls"] == 1
    assert all(item["complete"] is True for item in recovered_stage["input_outcomes"])
    assert seed_pages(recovered)
    apply_saved_plan(cfg, recovered)
