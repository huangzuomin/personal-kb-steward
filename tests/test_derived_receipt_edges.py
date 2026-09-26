# -*- coding: utf-8 -*-
"""Bounded B2-derived receipt edge checks over public production seams.

These cases intentionally use the real public initializer/finalizer, saved-plan
and review/apply seams.  Only the fixed public provider is replaced.  The
three-input-wave comparison is documented in the companion BEFORE report; it
is kept separate from this edge checkpoint until the partial-input fixture can
be made truthful without manufacturing ready cards.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import (
    ROUND_DIALOGUE,
    ROUND_SOURCES,
    build_cfg,
    prepare_vault,
)
from tests.test_derived_receipt_blackbox import (
    DERIVED_PREFIXES,
    DERIVED_STAGES,
    PublicProvider,
    apply_saved_plan,
    build_finalize_plan,
    build_intake_plan,
    plan_pages,
    stage_map,
    typed_card_snapshot,
)


class TaggedTopicProvider(PublicProvider):
    """Public provider with an optional valid topic-title variation.

    The underlying response remains the public fixed response.  The title
    variation makes one genuinely separate derived target through the actual
    topic generator, so the external-card case does not hand-write a ready
    page or bypass the plan/apply boundary.
    """

    def __init__(self) -> None:
        super().__init__()
        self.topic_suffix = ""

    def __call__(self, *args):
        payload = args[-1] if args and isinstance(args[-1], dict) else None
        response = super().__call__(*args)
        if self.topic_suffix and isinstance(payload, dict) and payload.get("task") == "question_led_topic_synthesis":
            data = json.loads(response)
            data["title"] = f"{data['title']}{self.topic_suffix}"
            return json.dumps(data, ensure_ascii=False)
        return response


@pytest.fixture
def edge_vault(tmp_path: Path):
    """Fresh public synthetic vault; original input bytes are protected."""
    vault = tmp_path / "vault"
    prepare_vault(vault)
    cfg = build_cfg(vault)
    input_rels = [*ROUND_SOURCES.values(), ROUND_DIALOGUE[1]]
    original_bytes = {rel: (vault / rel).read_bytes() for rel in input_rels}
    yield vault, cfg, original_bytes
    for rel, expected in original_bytes.items():
        assert (vault / rel).read_bytes() == expected, rel


def _derived_counts(provider: PublicProvider) -> dict[str, int]:
    counts = provider.counts()
    return {kind: counts[kind] for kind in ("concept", "case", "topic")}


def _saved_receipt_stages(path: Path) -> dict[str, dict]:
    saved = json.loads(path.read_text(encoding="utf-8"))
    receipts = saved.get("generation_receipts")
    assert isinstance(receipts, dict), "saved finalize plan must persist generation_receipts"
    stages = receipts.get("stages")
    assert isinstance(stages, list), "generation_receipts.stages must be a list"
    selected = {
        str(stage.get("stage")): stage
        for stage in stages
        if isinstance(stage, dict) and stage.get("stage") in DERIVED_STAGES
    }
    assert set(selected) == DERIVED_STAGES
    return selected


def _assert_re_evaluated(plan: dict, before: dict[str, int], provider: PublicProvider) -> None:
    after = _derived_counts(provider)
    assert all(after[kind] > before[kind] for kind in before), (before, after)
    stages = stage_map(plan)
    assert set(stages) == DERIVED_STAGES
    assert all(int(stages[kind].get("provider_calls", 0)) > 0 for kind in DERIVED_STAGES)
    for stage in stages.values():
        if "receipt_decision" in stage:
            assert stage["receipt_decision"] not in {"unchanged_inputs", "pending_review"}


def _paths_seen_as_related(plan: dict) -> set[str]:
    paths: set[str] = set()
    for stage in stage_map(plan).values():
        paths.update(str(value) for value in stage.get("related_candidates", []) if value)
        retrieval = stage.get("retrieval")
        if isinstance(retrieval, dict):
            for hit in retrieval.get("hits", []):
                if isinstance(hit, dict) and hit.get("path"):
                    paths.add(str(hit["path"]))
    return paths


def test_changed_model_invalidates_pending_derived_receipt(edge_vault):
    vault, cfg, original_bytes = edge_vault
    provider = PublicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-edge-model-intake")
    apply_saved_plan(cfg, intake)
    first = build_finalize_plan(cfg, provider, "b2-derived-edge-model-first")
    assert len(plan_pages(first)) == 3
    first_path = steward.write_execution_plan(cfg, first)
    steward.write_manual_review_queue(cfg, first)
    _saved_receipt_stages(first_path)
    before = _derived_counts(provider)

    cfg["llm"]["model"] = "public-derived-contract-drift-v2"
    changed = build_finalize_plan(cfg, provider, "b2-derived-edge-model-changed")
    _assert_re_evaluated(changed, before, provider)
    assert len(plan_pages(changed)) == 3
    assert {rel: (vault / rel).read_bytes() for rel in original_bytes} == original_bytes


def test_changed_question_invalidates_applied_derived_receipt(edge_vault):
    vault, cfg, original_bytes = edge_vault
    provider = PublicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-edge-question-intake")
    apply_saved_plan(cfg, intake)
    first = build_finalize_plan(cfg, provider, "b2-derived-edge-question-first")
    assert len(plan_pages(first)) == 3
    apply_saved_plan(cfg, first)
    typed_before = typed_card_snapshot(vault)
    before = _derived_counts(provider)

    question = cfg["card_pipeline"]["topic_questions"][0]
    cfg["card_pipeline"]["topic_questions"] = [f"{question}（第二版研究问题）"]
    changed = build_finalize_plan(cfg, provider, "b2-derived-edge-question-changed")
    _assert_re_evaluated(changed, before, provider)
    assert typed_card_snapshot(vault) == typed_before
    assert {rel: (vault / rel).read_bytes() for rel in original_bytes} == original_bytes


def test_self_cohort_is_ignored(edge_vault):
    vault, cfg, original_bytes = edge_vault
    provider = TaggedTopicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-edge-cohort-intake")
    apply_saved_plan(cfg, intake)
    first = build_finalize_plan(cfg, provider, "b2-derived-edge-cohort-first")
    assert len(plan_pages(first)) == 3
    apply_saved_plan(cfg, first)
    typed_before = typed_card_snapshot(vault)
    before_self = _derived_counts(provider)

    same = build_finalize_plan(cfg, provider, "b2-derived-edge-cohort-self-repeat")
    assert _derived_counts(provider) == before_self
    assert plan_pages(same) == []
    assert typed_card_snapshot(vault) == typed_before


def test_external_derived_card_invalidates_restored_cohort(edge_vault):
    vault, cfg, original_bytes = edge_vault
    provider = TaggedTopicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-edge-external-intake")
    apply_saved_plan(cfg, intake)
    first = build_finalize_plan(cfg, provider, "b2-derived-edge-external-first")
    assert len(plan_pages(first)) == 3
    apply_saved_plan(cfg, first)

    original_question = cfg["card_pipeline"]["topic_questions"][0]
    cfg["card_pipeline"]["topic_questions"] = [f"{original_question}（外部相关卡实验）"]
    provider.topic_suffix = "（外部相关卡）"
    external = build_finalize_plan(cfg, provider, "b2-derived-edge-external-card")
    external_pages = [
        page for page in plan_pages(external)
        if "外部相关卡" in json.dumps(page, ensure_ascii=False)
    ]
    assert external_pages, "external derived card must be generated by the real topic provider seam"
    external_rel = str(external_pages[0].get("rel_path") or external_pages[0].get("target"))
    apply_saved_plan(cfg, external)

    cfg["card_pipeline"]["topic_questions"] = [original_question]
    provider.topic_suffix = ""
    before_restored = _derived_counts(provider)
    restored = build_finalize_plan(cfg, provider, "b2-derived-edge-external-restored")
    _assert_re_evaluated(restored, before_restored, provider)
    assert external_rel in _paths_seen_as_related(restored)
    assert external_rel.startswith(DERIVED_PREFIXES)
    assert {rel: (vault / rel).read_bytes() for rel in original_bytes} == original_bytes


def test_derived_receipt_closure_keeps_source_inputs_and_upstream_cards(edge_vault):
    vault, cfg, original_bytes = edge_vault
    provider = PublicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-edge-closure-intake")
    apply_saved_plan(cfg, intake)
    first = build_finalize_plan(cfg, provider, "b2-derived-edge-closure-first")
    assert len(plan_pages(first)) == 3
    path = steward.write_execution_plan(cfg, first)
    steward.write_manual_review_queue(cfg, first)
    stages = _saved_receipt_stages(path)

    source_rels = set(ROUND_SOURCES.values())
    for stage in stages.values():
        closure = stage.get("input_closure")
        assert isinstance(closure, dict)
        originals = closure.get("originals")
        assert isinstance(originals, list) and originals
        original_paths = {str(item.get("rel")) for item in originals if isinstance(item, dict)}
        assert original_paths <= source_rels
        assert original_paths
        for key in ("upstream_cards", "retrieval_context"):
            entries = closure.get(key, [])
            assert isinstance(entries, list)
            assert not any(
                str(item.get("rel") or "").startswith(DERIVED_PREFIXES)
                for item in entries if isinstance(item, dict)
            )
    assert {rel: (vault / rel).read_bytes() for rel in original_bytes} == original_bytes
