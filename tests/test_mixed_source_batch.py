"""Regression: a substantial heuristic fallback must not poison a good sibling."""
from unittest.mock import patch

import pytest

from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import RAW_REL, make_cfg, write_raw
from tests.test_source_receipt_acceptance import (
    FAILED_MARKER, FAILED_RAW_REL, RoutingSourceProvider, apply_saved_plan,
    build_init_plan, save_plan, source_pages, source_stage,
)


def make_mixed_vault(root):
    cfg = make_cfg(root)
    cfg["initialize"] = {"seed_stage": False}
    write_raw(root)
    # Unlike the earlier sibling fixture, these long prose sentences survive
    # heuristic extraction, reproducing the real-world blocked fallback page.
    (root / FAILED_RAW_REL).write_text(
        f"# {FAILED_MARKER}。\n\n"
        "这段材料描述一个尚未核实的采访案例，参与者提出需要继续整理相关证据。"
        "项目目前只保存讨论纪要，材料中的计划不能当作已经完成的行动和结果。\n",
        encoding="utf-8",
    )
    return cfg


def test_substantial_failed_source_is_diagnostic_only_and_good_sibling_applies(tmp_path):
    cfg = make_mixed_vault(tmp_path)
    originals = {p: p.read_bytes() for p in (tmp_path / "raw").glob("*.md")}
    provider = RoutingSourceProvider()
    plan = build_init_plan(cfg, "b12-mixed", provider)
    pages = source_pages(plan)
    assert len(pages) == 1
    assert pages[0]["sources"] == [RAW_REL]
    outcomes = {o["rel"]: o for o in source_stage(plan)["input_outcomes"]}
    failed = outcomes[FAILED_RAW_REL]
    assert failed["analysis_mode"] == "heuristic-fallback"
    assert failed["outcome"] == "blocked" and failed["complete"] is False
    assert failed["targets"] == failed["required_targets"] == []
    assert "non_llm_source" in failed["reason"]
    assert plan["plan_quality"]["blocked_placeholder_pages"] == []
    _, code = apply_saved_plan(cfg, plan)
    assert code == 0
    queue = steward.load_queue(steward.review_queue_path(cfg))
    page_rows = [q for q in queue if q.get("scope") == "page"]
    assert len(page_rows) == 1 and page_rows[0]["status"] == "applied"
    saved = tmp_path / pages[0]["rel_path"]
    saved_before = saved.read_bytes()
    calls_before = len(provider.calls)
    repeat = build_init_plan(cfg, "b12-mixed-repeat", provider)
    assert len(provider.calls) - calls_before == 1
    assert FAILED_MARKER in provider.calls[-1]["text"]
    assert source_pages(repeat) == []
    assert saved.read_bytes() == saved_before
    for path, before in originals.items():
        assert path.read_bytes() == before


def test_no_llm_plan_has_diagnostics_but_no_unwritable_source_review_pages(tmp_path):
    cfg = make_mixed_vault(tmp_path)
    with patch("core.llm.call_chat_completion", side_effect=AssertionError("offline")) as provider:
        plan = steward.build_initialization_plan(
            cfg, plan_run_id="b12-offline", stamp=steward.stamp(),
            executor_plan_fn=steward.mvp_executor_plan,
            page_requires_manual_review=steward.page_requires_manual_review,
            duplicate_page_targets=steward.duplicate_page_targets,
            page_has_blocked_placeholder=lambda p: steward.page_has_blocked_placeholder(p, cfg),
            planned_raw_coverage=steward.planned_raw_coverage,
            batch_size=3, use_llm=False,
        )
    assert not provider.called
    assert source_pages(plan) == []
    outcomes = source_stage(plan)["input_outcomes"]
    assert len(outcomes) == 2
    assert all(o["outcome"] == "blocked" and not o["complete"] for o in outcomes)
    save_plan(cfg, plan)
    assert not any(q.get("scope") == "page" for q in steward.load_queue(steward.review_queue_path(cfg)))


@pytest.mark.parametrize("mode", ["heuristic", "heuristic-fallback"])
def test_old_non_llm_plans_remain_blocked_even_when_reviewed(tmp_path, mode):
    cfg = make_cfg(tmp_path)
    page = {"skill": "topic-research-compile", "analysis_mode": mode,
            "rel_path": "wiki/sources/old.md", "content": "旧的降级候选"}
    with pytest.raises(SystemExit, match="mock 或弱占位"):
        steward.preflight_apply_pages(cfg, tmp_path, [page], allow_reviewed=True)
    assert not (tmp_path / "wiki/sources/old.md").exists()
