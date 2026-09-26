# -*- coding: utf-8 -*-
"""Focused B2-derived receipt and cohort lifecycle checks.

The vault and provider data in this module are public synthetic fixtures.  The
tests use the real generator, saved-plan and page writer seams; the small
apply helper marks the approved queue rows after invoking the existing plan
writer directly because the concurrent B3 subset dispatcher is not wired into
the normal review command in this checkpoint.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.card_pipeline import discover_cards
from core.derived_index import rebuild
from core.pipeline_history import source_generator_contract
from core.retrieval import Retriever, retrieval_prefixes
from core.typed_card_updates import GENERATED_START
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests import public_round_support
from tests.test_derived_receipt_blackbox import (
    DERIVED_STAGES,
    PublicProvider,
    build_finalize_plan,
    build_intake_plan,
    intake_card_paths,
    plan_pages,
    save_plan,
    stage_map,
    typed_card_snapshot,
)
from tests.test_derived_receipt_edges import TaggedTopicProvider
from scripts.evaluate_public_baseline import build_cfg, prepare_vault


class OverrideProvider(PublicProvider):
    """Public provider with one deliberately bounded response variation."""

    def __init__(self, mode: str = "normal") -> None:
        super().__init__()
        self.mode = mode

    def __call__(self, *args):
        payload = args[-1] if args and isinstance(args[-1], dict) else {}
        response = super().__call__(*args)
        task = payload.get("task")
        if self.mode == "zero":
            if task == "concept_extraction":
                return json.dumps({"concept_found": False, "reason": "fixture zero"}, ensure_ascii=False)
            if task == "case_extraction":
                return json.dumps({"case_found": False, "reason": "fixture zero"}, ensure_ascii=False)
            if task == "question_led_topic_synthesis":
                return json.dumps({"topic_viable": False, "reason": "fixture zero"}, ensure_ascii=False)
        if self.mode == "malformed":
            return "this is not a JSON model response"
        if self.mode == "partial" and task == "question_led_topic_synthesis":
            data = json.loads(response)
            first_rel = str(payload.get("documents", [{}])[0].get("path") or "")
            data["source_map"] = [item for item in data.get("source_map", [])
                                   if item.get("rel") == first_rel]
            data["judgments"] = [item for item in data.get("judgments", [])
                                  if all(e.get("source") == first_rel
                                         for e in item.get("evidence", []))]
            data["tensions"] = []
            data["evidence_gaps"] = []
            data["next_actions"] = []
            return json.dumps(data, ensure_ascii=False)
        return response


class ExtraConceptProvider(PublicProvider):
    """Create one additional valid concept target for cohort history tests."""

    def __call__(self, *args):
        payload = args[-1] if args and isinstance(args[-1], dict) else {}
        response = super().__call__(*args)
        if payload.get("task") != "concept_extraction":
            return response
        data = json.loads(response)
        extra = copy.deepcopy(data["concepts"][0])
        extra["name"] = "历史额外概念候选"
        data["concepts"].append(extra)
        return json.dumps(data, ensure_ascii=False)


class ExtraCaseProvider(PublicProvider):
    """Create one additional valid case target in the newer cohort plan."""

    def __call__(self, *args):
        payload = args[-1] if args and isinstance(args[-1], dict) else {}
        response = super().__call__(*args)
        if payload.get("task") != "case_extraction":
            return response
        data = json.loads(response)
        extra = copy.deepcopy(data["cases"][0])
        extra["title"] = "历史第二案例候选"
        extra_claim = {
            "statement": "历史第二案例候选的独立复核判断（合成、未核实）",
            "kind": "fact",
            "confidence": "low",
            "evidence": [{
                "source": public_round_support.CASE_FAMILY[0],
                "quote": public_round_support.Q["case_rate"],
                "relation": "supports",
            }],
        }
        extra["judgments"].append(extra_claim)
        extra["result"]["figures"].append({"claim": extra_claim["statement"]})
        data["cases"].append(extra)
        return json.dumps(data, ensure_ascii=False)


@pytest.fixture
def derived_vault(tmp_path: Path):
    root = tmp_path / "vault"
    prepare_vault(root)
    cfg = build_cfg(root)
    protected = {
        rel: (root / rel).read_bytes()
        for rel in [*public_round_support.ROUND_SOURCES.values(),
                    public_round_support.ROUND_DIALOGUE[1]]
    }
    yield root, cfg, protected
    for rel, expected in protected.items():
        assert (root / rel).read_bytes() == expected, rel


def _apply_approved_plan(cfg: dict, plan: dict) -> Path:
    """Apply a saved approved plan and preserve its queue receipt status."""
    path = save_plan(cfg, plan)
    queue_path = steward.review_queue_path(cfg)
    for item in steward.load_queue(queue_path):
        if item.get("run_id") != plan["run_id"] or item.get("status") != "pending":
            continue
        assert steward.command_review(
            cfg,
            SimpleNamespace(review_command="approve", id=item["id"], reason="B2 derived fixture"),
        ) == 0
    # B3's page-subset dispatcher is intentionally still a separate checkpoint;
    # this calls the existing full-plan writer while keeping the receipt queue
    # state truthful for the B2 selector.
    assert steward.command_apply_plan(
        cfg, str(path), allow_reviewed=True, expected_run_id=plan["run_id"]
    ) == 0
    items = steward.load_queue(queue_path)
    for item in items:
        if item.get("run_id") == plan["run_id"] and item.get("status") == "approved":
            item["status"] = "applied"
    from core.review_queue import save_queue
    save_queue(queue_path, items)
    return path


def _reject_saved_plan(cfg: dict, plan: dict) -> Path:
    path = save_plan(cfg, plan)
    queue_path = steward.review_queue_path(cfg)
    for item in steward.load_queue(queue_path):
        if item.get("run_id") != plan["run_id"]:
            continue
        if item.get("status") == "pending":
            assert steward.command_review(
                cfg,
                SimpleNamespace(review_command="reject", id=item["id"], reason="B2 retry fixture"),
            ) == 0
    return path


def _prepare_intake(root: Path, cfg: dict, provider: PublicProvider) -> None:
    _apply_approved_plan(cfg, build_intake_plan(cfg, provider, "derived-intake"))


def test_source_contract_includes_inherited_frontmatter_template():
    root = Path(__file__).resolve().parents[1]
    template = root / "core" / "templates" / "base_frontmatter.j2"
    contract = source_generator_contract()
    inventory = contract["implementation_files"]
    expected = hashlib.sha256(template.read_bytes()).hexdigest()
    assert "core/templates/base_frontmatter.j2" in inventory
    assert inventory["core/templates/base_frontmatter.j2"] == expected
    assert "base_frontmatter.j2" in (root / "core" / "templates" / "source_note.j2").read_text(encoding="utf-8")


def _external_topic_plan(cfg: dict, provider: PublicProvider, run_id: str) -> dict:
    """Build one real topic-only plan to change retrieval context."""
    typed = dict(cfg)
    question = cfg["card_pipeline"]["topic_questions"][0]
    typed["card_pipeline"] = {
        **cfg["card_pipeline"],
        "topic_questions": [f"{question}（外部上下文历史探针）"],
    }
    index = build_index(typed)
    discovery = discover_cards(
        index, typed, run_id=run_id, use_llm=True, kinds=("topic",),
        providers={"topic": provider},
    )
    actions = [
        {"operation": "pipeline_stage", "entry": "finalize_kb",
         "skill": "kb-finalize", "risk": "medium", **stage}
        for stage in discovery["stages"].values()
    ]
    return {
        "run_id": run_id,
        "created_at": steward.stamp(),
        "mode": "dry-run",
        "task": "external topic context fixture",
        "entry": "finalize_kb",
        "primary_skill": "kb-finalize",
        "knowledge_base": str(index.root),
        "actions": actions,
        "planned_pages": discovery["planned_pages"],
        "_generation_receipt_drafts": discovery["generation_receipt_drafts"],
        "manual_review": ([{"type": "finalize_review", "risk": "medium",
                             "reason": "external context fixture"}]
                           if discovery["planned_pages"] else []),
    }


def test_valid_zero_receipt_repeats_without_provider_calls(derived_vault):
    root, cfg, _protected = derived_vault
    intake_provider = PublicProvider()
    _prepare_intake(root, cfg, intake_provider)

    provider = OverrideProvider("zero")
    first = build_finalize_plan(cfg, provider, "derived-zero-a")
    assert not plan_pages(first)
    assert set(stage_map(first)) == DERIVED_STAGES
    assert all(stage.get("state") == "zero" for stage in stage_map(first).values())
    first_path = save_plan(cfg, first)
    before = provider.counts()

    repeat = build_finalize_plan(cfg, provider, "derived-zero-b")
    assert provider.counts() == before
    assert not plan_pages(repeat)
    assert all(stage.get("receipt_decision") == "zero_output"
               for stage in stage_map(repeat).values())
    saved = json.loads(first_path.read_text(encoding="utf-8"))
    assert {item["generation_state"] for item in saved["generation_receipts"]["stages"]} == {"zero"}


def test_rejected_derived_receipt_repeats_without_provider_calls(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())
    provider = PublicProvider()
    first = build_finalize_plan(cfg, provider, "derived-rejected-a")
    assert plan_pages(first)
    _reject_saved_plan(cfg, first)
    before = provider.counts()

    repeat = build_finalize_plan(cfg, provider, "derived-rejected-b")
    assert provider.counts() == before
    assert not plan_pages(repeat)
    assert all(stage.get("receipt_decision") == "review_rejected"
               for stage in stage_map(repeat).values())


@pytest.mark.parametrize("mode,expected_state", [("malformed", "error"), ("partial", "stub")])
def test_incomplete_derived_receipts_are_retryable_not_cached_success(
    derived_vault, mode, expected_state
):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())
    provider = OverrideProvider(mode)
    first = build_finalize_plan(cfg, provider, f"derived-{mode}-a")
    selected = stage_map(first)
    assert selected
    if mode == "malformed":
        assert all(stage.get("state") == expected_state for stage in selected.values())
    else:
        assert selected["topic_generation"].get("state") == expected_state
    _reject_saved_plan(cfg, first)
    before = provider.counts()

    repeat = build_finalize_plan(cfg, provider, f"derived-{mode}-b")
    after = provider.counts()
    if mode == "malformed":
        assert all(after[kind] > before[kind] for kind in ("concept", "case", "topic"))
    else:
        # The partial topic outcome is retryable even though the unrelated
        # successful concept/case siblings remain correctly rejected by the
        # run-level review decision.
        assert after["topic"] > before["topic"]
        assert stage_map(repeat)["topic_generation"].get("receipt_decision") is None
    assert not any(stage.get("receipt_decision") in {
        "unchanged_inputs", "zero_output", "review_rejected"
    } for name, stage in stage_map(repeat).items()
        if mode == "malformed" or name == "topic_generation")


def test_manual_generated_region_edit_is_blocked_and_not_cached(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())
    provider = PublicProvider()
    first = build_finalize_plan(cfg, provider, "derived-manual-a")
    _apply_approved_plan(cfg, first)
    before = typed_card_snapshot(root)
    target_rel = next(rel for rel in before if rel.startswith("wiki/concepts/"))
    target = root / target_rel
    edited = target.read_bytes().replace(
        GENERATED_START.encode("utf-8"),
        (GENERATED_START + "\n人工生成区修改：保留并阻止静默覆盖。").encode("utf-8"),
        1,
    )
    target.write_bytes(edited)
    calls_before = provider.counts()

    retry = build_finalize_plan(cfg, provider, "derived-manual-b")
    calls_after = provider.counts()
    assert any(calls_after[kind] > calls_before[kind] for kind in ("concept", "case", "topic"))
    concept = stage_map(retry)["concept_generation"]
    assert concept.get("state") == "blocked"
    assert concept.get("reason") == "updater_blocked"
    blocked = concept.get("typed_update_outcomes") or []
    assert blocked and blocked[0].get("outcome") == "blocked"
    assert target.read_bytes() == edited

    path = save_plan(cfg, retry)
    saved = json.loads(path.read_text(encoding="utf-8"))
    concept_receipt = next(item for item in saved["generation_receipts"]["stages"]
                           if item.get("stage") == "concept_generation")
    assert concept_receipt.get("generation_state") == "blocked"
    assert concept_receipt["input_outcomes"][0]["complete"] is False


def test_sqlite_scoped_exclusion_happens_before_limit_for_seed_context(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())
    seeds = intake_card_paths(root, "seeds")
    assert seeds
    seed_rel = seeds[0].relative_to(root).as_posix()
    high_hits: set[str] = set()
    for i in range(50):
        rel = f"wiki/concepts/cohort-hit-{i}.md"
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\n"
            f"title: cohort hit {i}\n"
            "type: concept-page\nstatus: growing\nstage: candidate\n"
            "sources: []\nreview_required: true\n---\n"
            + ("写作目标 高命中 own cohort context。\n" * 3),
            encoding="utf-8",
        )
        high_hits.add(rel)
    rebuild(cfg)
    selection = Retriever(cfg, build_index(cfg)).select(
        "写作目标", limit=1, prefixes=retrieval_prefixes(cfg),
        exclude_paths=high_hits,
    )
    assert [note.rel for note in selection.notes] == [seed_rel]
    assert not (high_hits & {note.rel for note in selection.notes})
    assert selection.report.get("engine") == "sqlite+live-delta"


def test_effective_environment_model_change_invalidates_derived_receipt(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())
    provider = PublicProvider()
    with patch.dict(os.environ, {"OPENAI_MODEL": "synthetic-derived-model-a", "LLM_MODEL": ""}):
        first = build_finalize_plan(cfg, provider, "derived-env-a")
        assert plan_pages(first)
        save_plan(cfg, first)
        before = provider.counts()
    with patch.dict(os.environ, {"OPENAI_MODEL": "synthetic-derived-model-b", "LLM_MODEL": ""}):
        changed = build_finalize_plan(cfg, provider, "derived-env-b")
    after = provider.counts()
    assert all(after[kind] > before[kind] for kind in ("concept", "case", "topic"))
    assert all(stage.get("provider_calls", 0) == 1 for stage in stage_map(changed).values())


def test_history_cohort_is_scoped_to_one_newest_verified_plan(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())

    # Plan A writes an extra concept output.  A separate topic-only plan then
    # changes the live retrieval context without changing the derived base
    # closure.  Plan B has the same base closure but a distinct extra case
    # output, making the two verified plans observably different cohorts.
    plan_a = build_finalize_plan(cfg, ExtraConceptProvider(), "derived-cohort-a")
    extra_concept = next(
        page["rel_path"] for page in plan_pages(plan_a)
        if page["rel_path"].startswith("wiki/concepts/")
        and "历史额外概念候选" in page["rel_path"]
    )
    _apply_approved_plan(cfg, plan_a)

    external = _external_topic_plan(cfg, TaggedTopicProvider(), "derived-cohort-external")
    assert plan_pages(external)
    _apply_approved_plan(cfg, external)

    plan_b = build_finalize_plan(cfg, ExtraCaseProvider(), "derived-cohort-b")
    assert any(page["rel_path"].startswith("wiki/cases/")
               and "历史第二案例候选" in page["rel_path"]
               for page in plan_pages(plan_b))
    _apply_approved_plan(cfg, plan_b)

    repeat = build_finalize_plan(cfg, PublicProvider(), "derived-cohort-repeat")
    concept = stage_map(repeat)["concept_generation"]
    excluded = set(concept.get("retrieval", {}).get("excluded_paths") or [])
    related = set(concept.get("related_candidates") or [])
    # The newer Plan B is the only candidate peer cohort.  Plan A's extra
    # output remains a real related card and is not silently swallowed by a
    # union of every historical plan with the same pre-context.
    assert extra_concept not in excluded
    assert extra_concept in related


def test_initializer_and_finalizer_share_derived_receipt_identity(derived_vault):
    root, cfg, _protected = derived_vault
    _prepare_intake(root, cfg, PublicProvider())

    init_provider = PublicProvider()
    init = build_intake_plan(cfg, init_provider, "derived-entry-init")
    assert len(plan_pages(init)) == 3
    assert init_provider.counts()["concept"] == 1
    assert init_provider.counts()["case"] == 1
    assert init_provider.counts()["topic"] == 1
    _apply_approved_plan(cfg, init)

    final_provider = PublicProvider()
    repeat = build_finalize_plan(cfg, final_provider, "derived-entry-finalize")
    assert plan_pages(repeat) == []
    assert final_provider.counts()["concept"] == 0
    assert final_provider.counts()["case"] == 0
    assert final_provider.counts()["topic"] == 0
    assert all(stage.get("receipt_decision") == "unchanged_inputs"
               for stage in stage_map(repeat).values())
