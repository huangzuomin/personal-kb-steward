# -*- coding: utf-8 -*-
"""B2-derived positive-growth acceptance over public production seams.

The first wave has one valid case source, so concept and case pages are
produced from exact evidence already present in that source.  The follow-up
and counterexample waves add evidence through the real source-card boundary;
the same concept/case identities must update in place, and the final result
must match an all-at-once three-source control vault.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from core.vault import parse_frontmatter
from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import ROUND_SOURCES, build_cfg, prepare_vault
from tests import public_round_support
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


CASE_WAVES = (
    "project_case_01",
    "project_case_01_followup",
    "project_case_01_counterexample",
)


def _write_fixture(vault: Path, fixture_id: str) -> Path:
    fixture = public_round_support.load_fixture(fixture_id)
    path = vault / fixture["rel"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fixture["text"].encode("utf-8"))
    return path


def _make_vault(vault: Path, fixture_ids: tuple[str, ...]) -> None:
    prepare_vault(vault)
    for path in (vault / "raw").glob("*.md"):
        path.unlink()
    for path in (vault / "quicknote").glob("*.md"):
        path.unlink()
    for fixture_id in fixture_ids:
        _write_fixture(vault, fixture_id)


def _document_rels(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        return []
    return sorted({
        str(document.get("path"))
        for document in payload["documents"]
        if isinstance(document, dict) and isinstance(document.get("path"), str)
    })


def _filter_judgments(entry: dict[str, Any], allowed: set[str]) -> set[str]:
    retained: list[dict[str, Any]] = []
    statements: set[str] = set()
    for judgment in entry.get("judgments") or []:
        if not isinstance(judgment, dict):
            continue
        evidence = [
            item for item in judgment.get("evidence") or []
            if isinstance(item, dict) and item.get("source") in allowed
        ]
        if not evidence:
            continue
        copy = dict(judgment)
        copy["evidence"] = evidence
        retained.append(copy)
        if isinstance(copy.get("statement"), str):
            statements.add(copy["statement"])
    entry["judgments"] = retained
    return statements


def _positive_concept_response(payload: dict[str, Any]) -> str:
    allowed = set(_document_rels(payload))
    data = json.loads(public_round_support.concept_response(payload))
    for entry in data.get("concepts") or []:
        if not isinstance(entry, dict):
            continue
        statements = _filter_judgments(entry, allowed)
        entry["source_defined_boundary"] = [
            item for item in entry.get("source_defined_boundary") or []
            if isinstance(item, dict) and item.get("evidence_claim") in statements
        ]
        entry["suggested_interpretation"] = [
            item for item in entry.get("suggested_interpretation") or []
            if isinstance(item, dict) and item.get("supporting_claim") in statements
        ]
        # The canonical full-round response puts the source-defined boundary
        # in the counterexample.  A one/two-source wave may not have that
        # document yet, so bind the boundary to an exact fact statement that
        # is actually present in this wave; do not invent a paraphrase.
        if not entry["source_defined_boundary"]:
            definition = entry.get("definition_claim")
            fact_statements = [
                judgment.get("statement")
                for judgment in entry.get("judgments") or []
                if isinstance(judgment, dict)
                and judgment.get("kind") == "fact"
                and judgment.get("statement") != definition
            ]
            if fact_statements:
                entry["source_defined_boundary"] = [{
                    "evidence_claim": fact_statements[0],
                }]
    data["provenance_map"] = [
        item for item in data.get("provenance_map") or []
        if isinstance(item, dict) and item.get("rel") in allowed
    ]
    return json.dumps(data, ensure_ascii=False)


def _positive_case_response(payload: dict[str, Any]) -> str:
    allowed = set(_document_rels(payload))
    data = json.loads(public_round_support.case_response(payload))
    for entry in data.get("cases") or []:
        if not isinstance(entry, dict):
            continue
        statements = _filter_judgments(entry, allowed)
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        result["figures"] = [
            item for item in result.get("figures") or []
            if isinstance(item, dict) and item.get("claim") in statements
        ]
        entry["result"] = result
        entry["applicability"] = dict(entry.get("applicability") or {})
        entry["applicability"]["conditions"] = [
            item for item in entry["applicability"].get("conditions") or []
            if isinstance(item, dict) and item.get("claim") in statements
        ]
    data["provenance_map"] = [
        item for item in data.get("provenance_map") or []
        if isinstance(item, dict) and item.get("rel") in allowed
    ]
    return json.dumps(data, ensure_ascii=False)


class PositiveGrowthProvider(PublicProvider):
    """Canonical public responses filtered to the documents actually supplied."""

    def __init__(self) -> None:
        super().__init__()
        self.partial_topic_calls: list[list[str]] = []

    def __call__(self, *args: Any) -> str:
        payload = args[-1] if args and isinstance(args[-1], dict) else None
        system_prompt = args[-2] if len(args) >= 2 else ""
        if isinstance(payload, dict):
            task = payload.get("task")
            if task == "concept_extraction":
                response = _positive_concept_response(payload)
                self.log.record("concept:case_family", system_prompt, payload, response)
                return response
            if task == "case_extraction":
                response = _positive_case_response(payload)
                self.log.record("case:case_family", system_prompt, payload, response)
                return response
            if task == "question_led_topic_synthesis" and len(_document_rels(payload)) < 3:
                rels = _document_rels(payload)
                self.partial_topic_calls.append(rels)
                response = json.dumps({
                    "topic_viable": False,
                    "reason": f"当前仅提供 {len(rels)} 个来源，主题范围尚不足，暂不生成主题卡。",
                }, ensure_ascii=False)
                self.log.record("topic:case_family", system_prompt, payload, response)
                return response
        return super().__call__(*args)


def _page_identity(snapshot: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for rel, value in snapshot.items():
        kind = next((prefix.rstrip("/").split("/")[-1] for prefix in DERIVED_PREFIXES
                     if rel.startswith(prefix)), None)
        if kind:
            result[kind] = {
                "rel": rel,
                "object_id": value.get("object_id"),
                "revision": int(value["revision"]),
                "sha256": value["sha256"],
            }
    return result


def _normalized_derived(vault: Path) -> list[dict[str, Any]]:
    """Normalize semantic identity, claims/evidence, and source hashes."""
    rows: list[dict[str, Any]] = []
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
                evidence: list[dict[str, Any]] = []
                for item in claim.get("evidence") or []:
                    if not isinstance(item, dict):
                        continue
                    row = {
                        "source": item.get("source"),
                        "source_sha256": item.get("source_sha256"),
                        "quote": item.get("quote"),
                        "relation": item.get("relation"),
                    }
                    evidence.append(row)
                    evidence_rows.add(tuple(str(row[key]) for key in (
                        "source", "source_sha256", "quote", "relation")))
                claim_rows.append({
                    "statement": claim.get("statement"),
                    "kind": claim.get("kind"),
                    "confidence": claim.get("confidence"),
                    "evidence": sorted(evidence, key=lambda item: (
                        str(item.get("source")), str(item.get("quote")))),
                })
            origin = meta.get("origin") if isinstance(meta.get("origin"), dict) else {}
            source_hashes = meta.get("source_hashes") if isinstance(meta.get("source_hashes"), dict) else {}
            rows.append({
                "type": meta.get("type"),
                "title": meta.get("title"),
                "question": origin.get("research_question"),
                "sources": sorted(meta.get("sources") or []),
                "source_hashes": dict(sorted(source_hashes.items())),
                "claims": sorted(claim_rows, key=lambda item: (
                    str(item.get("statement")), str(item.get("kind")))),
                "evidence": [
                    {"source": source, "source_sha256": source_sha,
                     "quote": quote, "relation": relation}
                    for source, source_sha, quote, relation in sorted(evidence_rows)
                ],
            })
    return sorted(rows, key=lambda item: (str(item.get("type")), str(item.get("title"))))


def _derived_outcomes(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outcomes: dict[str, dict[str, Any]] = {}
    for action in plan.get("actions", []):
        if not isinstance(action, dict) or action.get("stage") not in DERIVED_STAGES:
            continue
        for outcome in action.get("typed_update_outcomes") or []:
            if isinstance(outcome, dict) and outcome.get("chosen_target"):
                outcomes[str(action["stage"])] = outcome
    return outcomes


def _normal_rel(value: Any) -> str:
    return str(value).replace("\\", "/")


def _assert_unique_derived_objects(snapshot: dict[str, dict[str, Any]]) -> None:
    object_ids: list[str] = []
    for rel, value in snapshot.items():
        if not any(rel.startswith(prefix) for prefix in DERIVED_PREFIXES):
            continue
        object_id = value.get("object_id")
        assert isinstance(object_id, str) and object_id
        object_ids.append(object_id)
    assert len(object_ids) == len(set(object_ids))


def _assert_derived_transition(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, list[str]]:
    """Check every actual derived create/update/noop at the apply boundary."""
    _assert_unique_derived_objects(after)
    assert set(before).issubset(after)
    updates: list[str] = []
    noops: list[str] = []
    creates: list[str] = []
    for stage, outcome in _derived_outcomes(plan).items():
        del stage
        target = _normal_rel(outcome.get("chosen_target"))
        operation = outcome.get("outcome")
        if operation == "create":
            assert target not in before
            assert target in after
            creates.append(target)
            continue
        if operation == "update":
            assert target in before and target in after
            previous = before[target]
            current = after[target]
            assert current["object_id"] == previous["object_id"]
            assert int(current["revision"]) == int(previous["revision"]) + 1
            assert current["sha256"] != previous["sha256"]
            updates.append(target)
            continue
        if operation == "noop":
            assert target in before and target in after
            previous = before[target]
            current = after[target]
            assert current["object_id"] == previous["object_id"]
            assert current["revision"] == previous["revision"]
            assert current["sha256"] == previous["sha256"]
            noops.append(target)
            continue
        assert operation in {"blocked", "zero", None}, (target, operation)

    expected_updates = set(updates)
    expected_noops = set(noops)
    for rel, previous in before.items():
        current = after[rel]
        assert current["object_id"] == previous["object_id"]
        if rel not in expected_updates:
            assert current["revision"] == previous["revision"], rel
            assert current["sha256"] == previous["sha256"], rel
    assert expected_updates.isdisjoint(expected_noops)
    return {"updates": updates, "noops": noops, "creates": creates}


def _assert_same_existing_ids(
    expected: dict[str, dict[str, Any]], snapshot: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    current = _page_identity(snapshot)
    for kind, value in expected.items():
        assert current[kind]["object_id"] == value["object_id"]
    return current


def _assert_revision_accounting(
    baseline: dict[str, dict[str, Any]],
    snapshot: dict[str, dict[str, Any]],
    applied_updates: dict[str, int],
) -> None:
    for rel, value in baseline.items():
        assert rel in snapshot
        assert int(snapshot[rel]["revision"]) == (
            int(value["revision"]) + applied_updates.get(rel, 0)
        )


def _apply_derived_plan(
    cfg: dict[str, Any], vault: Path, plan: dict[str, Any],
    applied_updates: dict[str, int],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    before = typed_card_snapshot(vault)
    apply_saved_plan(cfg, plan)
    after = typed_card_snapshot(vault)
    transition = _assert_derived_transition(before, after, plan)
    for target in transition["updates"]:
        applied_updates[target] = applied_updates.get(target, 0) + 1
    return before, after, transition


def _summary(plan: dict[str, Any]) -> dict[str, Any]:
    stages = {}
    for stage, action in stage_map(plan).items():
        stages[stage] = {
            key: action.get(key)
            for key in ("state", "reason", "reason_detail", "provider_calls",
                        "eligible_sources", "planned_items", "typed_update_outcomes",
                        "receipt_decision")
            if key in action
        }
    return {
        "run_id": plan.get("run_id"),
        "derived_pages": [str(page.get("rel_path") or page.get("target"))
                          for page in plan_pages(plan)],
        "stages": stages,
    }


def _assert_exact_raw(vault: Path) -> None:
    for fixture_id in CASE_WAVES:
        fixture = public_round_support.load_fixture(fixture_id)
        path = vault / fixture["rel"]
        if path.exists():
            assert path.read_bytes() == fixture["text"].encode("utf-8")


@pytest.fixture
def growth_vault(tmp_path: Path):
    vault = tmp_path / "growth"
    _make_vault(vault, (CASE_WAVES[0],))
    cfg = build_cfg(vault)
    yield vault, cfg
    _assert_exact_raw(vault)


def test_positive_concept_case_growth_preserves_identity_and_matches_control(
    growth_vault, tmp_path: Path,
):
    vault, cfg = growth_vault
    provider = PositiveGrowthProvider()
    evidence: dict[str, Any] = {
        "scope": "public synthetic case family; actual init/finalize/save/review/apply seams",
        "waves": {},
        "control": {},
        "baseline": "production integration is concurrent/in-flight during this BEFORE run",
    }
    applied_updates: dict[str, int] = {}
    try:
        # Wave 1: one real source produces positive concept/case pages from A.
        intake1 = build_intake_plan(cfg, provider, "b2-derived-growth-1-intake")
        assert intake1["planned_pages"]
        _, intake1_after, intake1_transition = _apply_derived_plan(
            cfg, vault, intake1, applied_updates,
        )
        final1 = build_finalize_plan(cfg, provider, "b2-derived-growth-1-finalize")
        assert len(plan_pages(final1)) == 2
        assert stage_map(final1)["concept_generation"]["state"] == "full"
        assert stage_map(final1)["case_generation"]["state"] == "full"
        assert stage_map(final1)["topic_generation"]["state"] == "zero"
        assert len(_derived_outcomes(final1)) == 2
        _, first, final1_transition = _apply_derived_plan(
            cfg, vault, final1, applied_updates,
        )
        first_ids = _page_identity(first)
        assert set(first_ids) == {"concepts", "cases"}
        evidence["waves"]["wave1"] = {
            "intake": _summary(intake1),
            "intake_transition": intake1_transition,
            "finalize": _summary(final1),
            "finalize_transition": final1_transition,
            "snapshot": first_ids,
        }

        # Wave 2: adding B changes the related context.  The real intake plan
        # may therefore evaluate and update the existing derived cards before
        # the later finalize plan; both plans go through normal review/apply.
        _write_fixture(vault, CASE_WAVES[1])
        intake2 = build_intake_plan(cfg, provider, "b2-derived-growth-2-intake")
        _, intake2_after, intake2_transition = _apply_derived_plan(
            cfg, vault, intake2, applied_updates,
        )
        intake2_ids = _assert_same_existing_ids(first_ids, intake2_after)
        final2 = build_finalize_plan(cfg, provider, "b2-derived-growth-2-finalize")
        _, second, final2_transition = _apply_derived_plan(
            cfg, vault, final2, applied_updates,
        )
        second_ids = _assert_same_existing_ids(first_ids, second)
        assert set(second_ids) == {"concepts", "cases"}
        _assert_revision_accounting(first, second, applied_updates)
        evidence["waves"]["wave2"] = {
            "intake": _summary(intake2),
            "intake_transition": intake2_transition,
            "intake_snapshot": intake2_ids,
            "finalize": _summary(final2),
            "finalize_transition": final2_transition,
            "snapshot": second_ids,
        }

        # Wave 3: C makes the topic eligible.  As with B, intake and finalize
        # may split the actual updates; account for each applied transition.
        _write_fixture(vault, CASE_WAVES[2])
        intake3 = build_intake_plan(cfg, provider, "b2-derived-growth-3-intake")
        _, intake3_after, intake3_transition = _apply_derived_plan(
            cfg, vault, intake3, applied_updates,
        )
        intake3_ids = _assert_same_existing_ids(first_ids, intake3_after)
        final3 = build_finalize_plan(cfg, provider, "b2-derived-growth-3-finalize")
        _, wave_final, final3_transition = _apply_derived_plan(
            cfg, vault, final3, applied_updates,
        )
        wave_ids = _assert_same_existing_ids(first_ids, wave_final)
        assert set(wave_ids) == {"concepts", "cases", "topics"}
        _assert_revision_accounting(first, wave_final, applied_updates)
        evidence["waves"]["wave3"] = {
            "intake": _summary(intake3),
            "intake_transition": intake3_transition,
            "intake_snapshot": intake3_ids,
            "finalize": _summary(final3),
            "finalize_transition": final3_transition,
            "snapshot": wave_ids,
        }

        # Control: all three valid sources are present before the first typed
        # finalize.  The final normalized semantic/evidence set must match.
        control_vault = tmp_path / "all-at-once"
        _make_vault(control_vault, CASE_WAVES)
        control_cfg = build_cfg(control_vault)
        control_provider = PositiveGrowthProvider()
        control_intake = build_intake_plan(control_cfg, control_provider, "b2-derived-growth-control-intake")
        assert control_intake["planned_pages"]
        apply_saved_plan(control_cfg, control_intake)
        control_final = build_finalize_plan(control_cfg, control_provider, "b2-derived-growth-control-finalize")
        assert len(plan_pages(control_final)) == 3
        apply_saved_plan(control_cfg, control_final)
        control_snapshot = typed_card_snapshot(control_vault)
        assert len(control_snapshot) == 3
        assert _normalized_derived(vault) == _normalized_derived(control_vault)
        evidence["control"] = {
            "intake": _summary(control_intake),
            "finalize": _summary(control_final),
            "normalized_match": True,
            "snapshot": _page_identity(control_snapshot),
        }

        # With no input/context change after the complete three-source result,
        # an immediate normal finalize repeat must not call providers or write
        # another derived page.  Keep this as an observable user-facing gate.
        repeat_before = typed_card_snapshot(vault)
        counts_before = provider.counts()
        repeat = build_finalize_plan(cfg, provider, "b2-derived-growth-repeat")
        counts_after = provider.counts()
        repeat_after = typed_card_snapshot(vault)
        evidence["repeat"] = {
            "plan": _summary(repeat),
            "provider_counts_before": counts_before,
            "provider_counts_after": counts_after,
            "snapshot_equal": repeat_before == repeat_after,
        }
        assert counts_after == counts_before
        assert plan_pages(repeat) == []
        assert repeat_after == repeat_before
        _assert_derived_transition(repeat_before, repeat_after, repeat)
        for action in stage_map(repeat).values():
            assert action.get("provider_calls", 0) == 0
            if "receipt_decision" in action:
                assert action["receipt_decision"] == "unchanged_inputs"
    except Exception as exc:
        evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        evidence["provider_counts"] = provider.counts()
        evidence["partial_topic_calls"] = provider.partial_topic_calls
        evidence["raw_hashes"] = {
            rel: hashlib.sha256((vault / rel).read_bytes()).hexdigest()
            for rel in (ROUND_SOURCES[fixture_id] for fixture_id in CASE_WAVES)
            if (vault / rel).exists()
        }
        evidence_path = tmp_path / "positive-growth-evidence.json"
        evidence["evidence_path"] = str(evidence_path)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
