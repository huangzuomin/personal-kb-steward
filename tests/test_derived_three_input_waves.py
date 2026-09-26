# -*- coding: utf-8 -*-
"""B2-derived three-input-wave acceptance over public production seams.

The scenario uses only the marked synthetic fixtures and the real
initializer/finalizer, saved-plan, review, and apply boundaries.  The provider
is deterministic and public: it returns an explicit zero for an incomplete
case family, reuses the canonical three-source responses once all three
inputs are present, and lets the real source executor reject the damaged
fixture before a model call.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.vault import parse_frontmatter
from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import (
    ROUND_SOURCES,
    build_cfg,
    prepare_vault,
)
from tests import public_round_support
from tests.test_derived_receipt_blackbox import (
    DERIVED_PREFIXES,
    DERIVED_STAGES,
    PublicProvider,
    apply_saved_plan,
    build_finalize_plan,
    build_intake_plan,
    plan_pages,
    save_plan,
    stage_map,
    typed_card_snapshot,
)


CASE_WAVE_FIXTURES = (
    "project_case_01",
    "project_case_01_followup",
    "project_case_01_counterexample",
)
BAD_FIXTURE = "neg_damaged"


def _write_exact_fixture(vault: Path, fixture_id: str) -> Path:
    fix = public_round_support.load_fixture(fixture_id)
    rel = fix["rel"]
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fix["text"].encode("utf-8"))
    return path


def _make_selective_vault(vault: Path, fixture_ids: tuple[str, ...]) -> None:
    """Create a fresh marked vault containing exact public fixture bytes."""
    prepare_vault(vault)
    for path in (vault / "raw").glob("*.md"):
        path.unlink()
    for path in (vault / "quicknote").glob("*.md"):
        path.unlink()
    for fixture_id in fixture_ids:
        _write_exact_fixture(vault, fixture_id)


def _document_paths(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return []
    return sorted({
        str(item.get("path"))
        for item in documents
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    })


class WaveProvider(PublicProvider):
    """Fixed public provider with truthful partial-wave responses."""

    def __init__(self) -> None:
        super().__init__()
        self.partial_waves: list[dict[str, Any]] = []
        self.bad_payload_attempts = 0

    def __call__(self, *args: Any) -> str:
        payload = args[-1] if args and isinstance(args[-1], dict) else None
        system_prompt = args[-2] if len(args) >= 2 else ""
        if isinstance(payload, dict):
            task = payload.get("task")
            if task in {
                "concept_extraction",
                "case_extraction",
                "question_led_topic_synthesis",
            }:
                rels = _document_paths(payload)
                if len(rels) < len(CASE_WAVE_FIXTURES):
                    self.partial_waves.append({"task": task, "documents": rels})
                    stage = {
                        "concept_extraction": "concept:case_family",
                        "case_extraction": "case:case_family",
                        "question_led_topic_synthesis": "topic:case_family",
                    }[task]
                    key = {
                        "concept_extraction": "concept_found",
                        "case_extraction": "case_found",
                        "question_led_topic_synthesis": "topic_viable",
                    }[task]
                    response = json.dumps({
                        key: False,
                        "reason": f"当前仅有 {len(rels)} 个相关来源，范围不足，暂不形成派生卡。",
                    }, ensure_ascii=False)
                    self.log.record(stage, system_prompt, payload, response)
                    return response

            # The actual source executor checks the damaged marker before
            # calling the provider.  Keep this guard as a diagnostic if a
            # future source seam ever passes the payload through.
            if isinstance(payload.get("text"), str) and "\ufffd" in payload["text"]:
                self.bad_payload_attempts += 1
                self.log.record("source:neg_damaged", system_prompt, payload, "")
                raise RuntimeError("synthetic damaged source must be rejected")
        return super().__call__(*args)


def _source_input_outcomes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for action in plan.get("actions", []):
        if not isinstance(action, dict) or action.get("stage") != "source_compile":
            continue
        values = action.get("input_outcomes")
        if isinstance(values, list):
            outcomes.extend(item for item in values if isinstance(item, dict))
    return outcomes


def _source_outcome(plan: dict[str, Any], rel: str) -> dict[str, Any]:
    matches = [item for item in _source_input_outcomes(plan) if item.get("rel") == rel]
    assert len(matches) == 1, (rel, _source_input_outcomes(plan), plan.get("actions"))
    return matches[0]


def _derived_normalized(vault: Path) -> list[dict[str, Any]]:
    """Keep semantic identity, claims, evidence, and source hashes only."""
    normalized: list[dict[str, Any]] = []
    for prefix in DERIVED_PREFIXES:
        directory = vault / Path(prefix)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            meta, _ = parse_frontmatter(path.read_bytes().decode("utf-8"))
            state = meta.get("card_state") if isinstance(meta.get("card_state"), dict) else {}
            claims = state.get("claims") if isinstance(state.get("claims"), list) else []
            claim_rows: list[dict[str, Any]] = []
            evidence_rows: set[tuple[str, str, str, str]] = set()
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                evidence = claim.get("evidence") if isinstance(claim.get("evidence"), list) else []
                evidence_norm: list[dict[str, Any]] = []
                for item in evidence:
                    if not isinstance(item, dict):
                        continue
                    row = {
                        "source": item.get("source"),
                        "source_sha256": item.get("source_sha256"),
                        "quote": item.get("quote"),
                        "relation": item.get("relation"),
                    }
                    evidence_norm.append(row)
                    evidence_rows.add((
                        str(row["source"]), str(row["source_sha256"]),
                        str(row["quote"]), str(row["relation"]),
                    ))
                claim_rows.append({
                    "statement": claim.get("statement"),
                    "kind": claim.get("kind"),
                    "confidence": claim.get("confidence"),
                    "evidence": sorted(evidence_norm, key=lambda item: (
                        str(item.get("source")), str(item.get("quote")),
                    )),
                })
            origin = meta.get("origin") if isinstance(meta.get("origin"), dict) else {}
            source_hashes = meta.get("source_hashes")
            if not isinstance(source_hashes, dict):
                source_hashes = {}
            normalized.append({
                "type": meta.get("type"),
                "title": meta.get("title"),
                "question": origin.get("research_question"),
                "sources": sorted(meta.get("sources") or []),
                "source_hashes": dict(sorted(source_hashes.items())),
                "claims": sorted(claim_rows, key=lambda item: (
                    str(item.get("statement")), str(item.get("kind")),
                )),
                "evidence": [
                    {"source": source, "source_sha256": source_sha,
                     "quote": quote, "relation": relation}
                    for source, source_sha, quote, relation in sorted(evidence_rows)
                ],
            })
    return sorted(normalized, key=lambda item: (str(item.get("type")), str(item.get("title"))))


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    stages: dict[str, dict[str, Any]] = {}
    for action in plan.get("actions", []):
        if not isinstance(action, dict):
            continue
        stage = action.get("stage")
        if stage not in {"source_compile", *DERIVED_STAGES}:
            continue
        stages[str(stage)] = {
            key: action.get(key)
            for key in (
                "state", "outcome", "reason", "reason_detail", "provider_calls",
                "eligible_sources", "planned_items", "input_outcomes",
                "receipt_decision", "receipt_ref", "typed_update_outcomes",
            )
            if key in action
        }
    return {
        "run_id": plan.get("run_id"),
        "planned_pages": [
            str(page.get("rel_path") or page.get("target"))
            for page in plan_pages(plan)
        ],
        "stages": stages,
        "source_input_outcomes": _source_input_outcomes(plan),
    }


def _approve_and_try_apply(cfg: dict[str, Any], plan: dict[str, Any]) -> int:
    """Review a saved plan and preserve the real apply result."""
    save_plan(cfg, plan)
    queue_path = steward.review_queue_path(cfg)
    for item in steward.load_queue(queue_path):
        if item.get("run_id") != plan.get("run_id"):
            continue
        assert steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="approve",
                id=item["id"],
                reason="B2 three-wave synthetic fixture approval",
            ),
        ) == 0
    return steward.command_review(
        cfg,
        SimpleNamespace(review_command="apply-approved", run_id=plan.get("run_id")),
    )


def _assert_raw_fixture_bytes(vault: Path, fixture_ids: tuple[str, ...]) -> None:
    for fixture_id in fixture_ids:
        rel = public_round_support.load_fixture(fixture_id)["rel"]
        path = vault / rel
        if path.exists():
            assert path.read_bytes() == public_round_support.load_fixture(fixture_id)["text"].encode("utf-8")


@pytest.fixture
def wave_vault(tmp_path: Path):
    vault = tmp_path / "waves"
    _make_selective_vault(vault, (CASE_WAVE_FIXTURES[0],))
    cfg = build_cfg(vault)
    yield vault, cfg
    _assert_raw_fixture_bytes(vault, CASE_WAVE_FIXTURES)


def test_three_input_waves_match_all_at_once_and_repeat(wave_vault, tmp_path: Path):
    vault, cfg = wave_vault
    provider = WaveProvider()
    evidence: dict[str, Any] = {
        "scope": "public synthetic fixture; actual production seams, provider mocked only",
        "waves": {},
        "counts": {},
    }
    try:
        # Wave 1: one eligible case source.  The real source page is applied;
        # each derived stage records an explicit zero and no topic page exists.
        wave1_intake = build_intake_plan(cfg, provider, "b2-derived-waves-1-intake")
        assert wave1_intake["planned_pages"]
        apply_saved_plan(cfg, wave1_intake)
        wave1_finalize = build_finalize_plan(cfg, provider, "b2-derived-waves-1-finalize")
        assert plan_pages(wave1_finalize) == []
        assert set(stage_map(wave1_finalize)) == DERIVED_STAGES
        assert all(stage_map(wave1_finalize)[kind]["state"] == "zero"
                   for kind in DERIVED_STAGES)
        save_plan(cfg, wave1_finalize)
        evidence["waves"]["wave1"] = {
            "intake": _plan_summary(wave1_intake),
            "finalize": _plan_summary(wave1_finalize),
        }

        # Wave 2: add the exact follow-up source and repeat the real seams.
        _write_exact_fixture(vault, CASE_WAVE_FIXTURES[1])
        wave2_intake = build_intake_plan(cfg, provider, "b2-derived-waves-2-intake")
        assert wave2_intake["planned_pages"]
        apply_saved_plan(cfg, wave2_intake)
        wave2_finalize = build_finalize_plan(cfg, provider, "b2-derived-waves-2-finalize")
        assert plan_pages(wave2_finalize) == []
        assert set(stage_map(wave2_finalize)) == DERIVED_STAGES
        assert all(stage_map(wave2_finalize)[kind]["state"] == "zero"
                   for kind in DERIVED_STAGES)
        save_plan(cfg, wave2_finalize)
        evidence["waves"]["wave2"] = {
            "intake": _plan_summary(wave2_intake),
            "finalize": _plan_summary(wave2_finalize),
        }

        # Wave 3: add the valid counterexample beside a damaged public input.
        # Save/review/apply is attempted against the mixed plan.  If the
        # current run-level gate rejects the sibling batch, retain that exact
        # result and continue through a new valid-input plan below.
        _write_exact_fixture(vault, CASE_WAVE_FIXTURES[2])
        bad_path = _write_exact_fixture(vault, BAD_FIXTURE)
        wave3_bad = build_intake_plan(cfg, provider, "b2-derived-waves-3-bad")
        counter_rel = ROUND_SOURCES[CASE_WAVE_FIXTURES[2]]
        bad_rel = public_round_support.load_fixture(BAD_FIXTURE)["rel"]
        counter_outcome = _source_outcome(wave3_bad, counter_rel)
        bad_outcome = _source_outcome(wave3_bad, bad_rel)
        assert counter_outcome.get("complete") is True
        assert counter_outcome.get("outcome") == "ok"
        assert bad_outcome.get("outcome") in {"blocked", "error"}
        assert bad_outcome.get("complete") is False
        bad_apply_rc = _approve_and_try_apply(cfg, wave3_bad)
        evidence["waves"]["wave3_bad_input"] = {
            "plan": _plan_summary(wave3_bad),
            "apply_rc": bad_apply_rc,
            "bad_rel": bad_rel,
            "bad_outcome": bad_outcome,
            "counterexample_outcome": counter_outcome,
        }

        # The damaged fixture is synthetic test input only.  Isolate it after
        # its failed source attempt, then continue using the normal plan path.
        bad_path.unlink()
        wave3_continue = build_intake_plan(cfg, provider, "b2-derived-waves-3-continue")
        if wave3_continue["planned_pages"]:
            apply_saved_plan(cfg, wave3_continue)
        else:
            save_plan(cfg, wave3_continue)
        assert (vault / ROUND_SOURCES[CASE_WAVE_FIXTURES[2]]).exists()
        evidence["waves"]["wave3_continue"] = _plan_summary(wave3_continue)

        wave_final = build_finalize_plan(cfg, provider, "b2-derived-waves-final")
        if plan_pages(wave_final):
            assert len(plan_pages(wave_final)) == 3
            apply_saved_plan(cfg, wave_final)
        wave_snapshot = typed_card_snapshot(vault)
        assert len(wave_snapshot) == 3
        wave_normalized = _derived_normalized(vault)
        assert len(wave_normalized) == 3
        evidence["waves"]["finalize"] = _plan_summary(wave_final)
        evidence["waves"]["final_snapshot"] = {
            rel: {
                "sha256": value["sha256"],
                "object_id": value["object_id"],
                "revision": value["revision"],
            }
            for rel, value in wave_snapshot.items()
        }

        # Control: all three valid inputs are available before the first
        # finalize.  The exact same public provider must yield the same
        # normalized semantic result, while object IDs and timestamps may vary.
        control_vault = tmp_path / "all-at-once"
        _make_selective_vault(control_vault, CASE_WAVE_FIXTURES)
        control_cfg = build_cfg(control_vault)
        control_provider = WaveProvider()
        control_intake = build_intake_plan(control_cfg, control_provider, "b2-derived-control-intake")
        assert control_intake["planned_pages"]
        apply_saved_plan(control_cfg, control_intake)
        control_finalize = build_finalize_plan(control_cfg, control_provider, "b2-derived-control-finalize")
        assert len(plan_pages(control_finalize)) == 3
        apply_saved_plan(control_cfg, control_finalize)
        control_snapshot = typed_card_snapshot(control_vault)
        assert len(control_snapshot) == 3
        control_normalized = _derived_normalized(control_vault)
        assert wave_normalized == control_normalized
        _assert_raw_fixture_bytes(control_vault, CASE_WAVE_FIXTURES)
        evidence["control"] = {
            "intake": _plan_summary(control_intake),
            "finalize": _plan_summary(control_finalize),
            "normalized_match": wave_normalized == control_normalized,
            "final_snapshot": {
                rel: {
                    "sha256": value["sha256"],
                    "object_id": value["object_id"],
                    "revision": value["revision"],
                }
                for rel, value in control_snapshot.items()
            },
        }

        # Same-vault repeat is the final acceptance check.  Preserve exact
        # bytes/identity and require all three derived provider counts to stay
        # unchanged.  A failure here is retained as product evidence: it is
        # not converted into a weaker semantic assertion.
        counts_before_repeat = provider.counts()
        repeat = build_finalize_plan(cfg, provider, "b2-derived-waves-final-repeat")
        repeat_snapshot = typed_card_snapshot(vault)
        repeat_stages = stage_map(repeat)
        evidence["counts"] = {
            "before_repeat": counts_before_repeat,
            "after_repeat": provider.counts(),
        }
        evidence["repeat"] = _plan_summary(repeat)
        evidence["repeat"]["snapshot_equal"] = repeat_snapshot == wave_snapshot
        evidence["repeat"]["snapshot"] = {
            rel: {
                "sha256": value["sha256"],
                "object_id": value["object_id"],
                "revision": value["revision"],
            }
            for rel, value in repeat_snapshot.items()
        }
        repeat_violations: list[str] = []
        if plan_pages(repeat):
            repeat_violations.append(f"planned_pages={len(plan_pages(repeat))}")
        if repeat_snapshot != wave_snapshot:
            repeat_violations.append("typed_snapshot_changed")
        if set(repeat_stages) != DERIVED_STAGES:
            repeat_violations.append(f"stages={sorted(repeat_stages)}")
        for kind, stage in repeat_stages.items():
            if stage.get("provider_calls") != 0:
                repeat_violations.append(
                    f"{kind}.provider_calls={stage.get('provider_calls')}"
                )
            if stage.get("receipt_decision") != "unchanged_inputs":
                repeat_violations.append(
                    f"{kind}.receipt_decision={stage.get('receipt_decision')!r}"
                )
        if provider.counts() != counts_before_repeat:
            repeat_violations.append(
                f"counts {counts_before_repeat} -> {provider.counts()}"
            )
        evidence["repeat"]["violations"] = repeat_violations
        assert not repeat_violations, json.dumps(repeat_violations, ensure_ascii=False)
    except Exception as exc:
        evidence["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        raise
    finally:
        evidence["provider_counts"] = provider.counts()
        evidence["partial_waves"] = provider.partial_waves
        evidence["raw_hashes"] = {
            rel: hashlib.sha256((vault / rel).read_bytes()).hexdigest()
            for rel in (ROUND_SOURCES[fid] for fid in CASE_WAVE_FIXTURES)
            if (vault / rel).exists()
        }
        # Per-run evidence belongs under pytest's isolated temp tree.  The
        # checked-in BEFORE report is historical evidence and must not be
        # overwritten by later reruns or a broader test command.
        evidence_path = tmp_path / "three-waves-evidence.json"
        evidence["evidence_path"] = str(evidence_path)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
