# -*- coding: utf-8 -*-
"""B2-derived immediate-repeat checks over the public production seams.

The fixture is created by the public baseline runner, then the real
initializer/finalizer, saved-plan boundary, review queue, and apply writer are
used.  Only the model provider is replaced with the fixed public synthetic
provider.  These are execution checks for receipt behavior; applying pages in
the marked fixture vault is not semantic production acceptance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.vault import parse_frontmatter
from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import (
    ROUND_DIALOGUE,
    ROUND_SOURCES,
    build_cfg,
    prepare_vault,
)
from tests import public_round_support


DERIVED_PREFIXES = ("wiki/concepts/", "wiki/cases/", "wiki/topics/")
DERIVED_STAGES = {
    "concept_generation",
    "case_generation",
    "topic_generation",
}


class PublicProvider:
    """Fixed public provider with independently inspectable stage counts."""

    def __init__(self) -> None:
        self.log = public_round_support.CallLog()
        self._provider = public_round_support.make_offline_provider(self.log)

    def __call__(self, *args):
        return self._provider(*args)

    def count(self, prefix: str) -> int:
        return self.log.stage_count(prefix)

    def counts(self) -> dict[str, int]:
        return {
            "source": self.count("source:"),
            "seed": self.count("seed:"),
            "concept": self.count("concept:"),
            "case": self.count("case:"),
            "topic": self.count("topic:"),
        }


@pytest.fixture
def public_vault(tmp_path: Path):
    """Fresh public synthetic vault with exact original input bytes."""
    vault = tmp_path / "vault"
    prepare_vault(vault)
    cfg = build_cfg(vault)
    input_rels = [*ROUND_SOURCES.values(), ROUND_DIALOGUE[1]]
    original_bytes = {rel: (vault / rel).read_bytes() for rel in input_rels}
    yield vault, cfg, original_bytes
    for rel, expected in original_bytes.items():
        assert (vault / rel).read_bytes() == expected, rel


def build_intake_plan(cfg: dict, provider: PublicProvider, run_id: str) -> dict:
    """Build the real source+seed intake plan with the public provider seam."""
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
            include_all=True,
            discover_providers={
                "concept": provider,
                "case": provider,
                "topic": provider,
            },
        )


def build_finalize_plan(cfg: dict, provider: PublicProvider, run_id: str) -> dict:
    """Build a typed finalize plan through the actual three generator seams."""
    return steward.make_finalize_plan(
        cfg,
        plan_run_id=run_id,
        stamp=steward.stamp(),
        use_llm=True,
        providers={"concept": provider, "case": provider, "topic": provider},
    )


def save_plan(cfg: dict, plan: dict) -> Path:
    path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    return path


def apply_saved_plan(cfg: dict, plan: dict) -> Path:
    """Use the normal saved-plan -> review approve -> apply-approved path."""
    path = save_plan(cfg, plan)
    queue_path = steward.review_queue_path(cfg)
    for item in steward.load_queue(queue_path):
        if item.get("run_id") != plan["run_id"]:
            continue
        assert steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="approve",
                id=item["id"],
                reason="B2 derived synthetic fixture approval",
            ),
        ) == 0
    assert steward.command_review(
        cfg,
        SimpleNamespace(review_command="apply-approved", run_id=plan["run_id"]),
    ) == 0
    return path


def plan_pages(plan: dict) -> list[dict]:
    return [
        page
        for page in plan.get("planned_pages", [])
        if str(page.get("rel_path") or page.get("target") or "").replace("\\", "/").startswith(DERIVED_PREFIXES)
    ]


def stage_map(plan: dict) -> dict[str, dict]:
    return {
        str(action.get("stage")): action
        for action in plan.get("actions", [])
        if action.get("stage") in DERIVED_STAGES
    }


def intake_card_paths(vault: Path, dirname: str) -> list[Path]:
    directory = vault / "wiki" / dirname
    return sorted(path for path in directory.glob("*.md") if path.name != "README.md")


def typed_card_snapshot(vault: Path) -> dict[str, dict]:
    snapshot: dict[str, dict] = {}
    for prefix in DERIVED_PREFIXES:
        directory = vault / Path(prefix)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            raw = path.read_bytes()
            meta, _ = parse_frontmatter(raw.decode("utf-8"))
            snapshot[path.relative_to(vault).as_posix()] = {
                "bytes": raw,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "object_id": meta.get("object_id"),
                "revision": meta.get("revision"),
            }
    return snapshot


def assert_intake_counts(vault: Path, provider: PublicProvider) -> None:
    assert provider.counts() == {
        "source": 4,
        "seed": 1,
        "concept": 0,
        "case": 0,
        "topic": 0,
    }
    assert len(intake_card_paths(vault, "sources")) == 4
    assert len(intake_card_paths(vault, "seeds")) == 2


def assert_originals_unchanged(vault: Path, original_bytes: dict[str, bytes]) -> None:
    assert {
        rel: (vault / rel).read_bytes() for rel in original_bytes
    } == original_bytes


def test_derived_pending_repeat_has_zero_calls_no_pages_and_old_plan_ref(public_vault):
    vault, cfg, original_bytes = public_vault
    provider = PublicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-pending-intake")
    apply_saved_plan(cfg, intake)
    assert_intake_counts(vault, provider)

    first = build_finalize_plan(cfg, provider, "b2-derived-pending-a")
    assert len(plan_pages(first)) == 3
    assert provider.counts() == {
        "source": 4,
        "seed": 1,
        "concept": 1,
        "case": 1,
        "topic": 1,
    }
    first_path = save_plan(cfg, first)
    first_bytes = first_path.read_bytes()
    counts_before_repeat = provider.counts()

    repeat = build_finalize_plan(cfg, provider, "b2-derived-pending-b")
    repeat_stages = stage_map(repeat)
    assert provider.counts() == counts_before_repeat
    assert plan_pages(repeat) == []
    assert set(repeat_stages) == DERIVED_STAGES
    assert all(stage.get("provider_calls") == 0 for stage in repeat_stages.values())
    assert all(stage.get("receipt_decision") == "pending_review"
               for stage in repeat_stages.values())
    repeat_text = json.dumps(repeat, ensure_ascii=False, sort_keys=True)
    assert first_path.name in repeat_text or first["run_id"] in repeat_text
    assert first_path.read_bytes() == first_bytes
    assert_originals_unchanged(vault, original_bytes)


def test_derived_applied_repeat_has_zero_calls_and_preserves_typed_cards(public_vault):
    vault, cfg, original_bytes = public_vault
    provider = PublicProvider()

    intake = build_intake_plan(cfg, provider, "b2-derived-applied-intake")
    apply_saved_plan(cfg, intake)
    assert_intake_counts(vault, provider)

    first = build_finalize_plan(cfg, provider, "b2-derived-applied-a")
    assert len(plan_pages(first)) == 3
    first_path = apply_saved_plan(cfg, first)
    assert first_path.exists()
    typed_before = typed_card_snapshot(vault)
    assert len(typed_before) == 3
    counts_before_repeat = provider.counts()

    repeat = build_finalize_plan(cfg, provider, "b2-derived-applied-b")
    repeat_stages = stage_map(repeat)
    assert provider.counts() == counts_before_repeat
    assert plan_pages(repeat) == []
    assert set(repeat_stages) == DERIVED_STAGES
    assert all(stage.get("provider_calls") == 0 for stage in repeat_stages.values())
    assert all(stage.get("receipt_decision") == "unchanged_inputs"
               for stage in repeat_stages.values())
    assert typed_card_snapshot(vault) == typed_before
    assert_originals_unchanged(vault, original_bytes)
