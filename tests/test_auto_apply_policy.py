# -*- coding: utf-8 -*-
"""GP002 Source Card Auto-Apply v0.1：policy 单元 + 历史 replay 固定 + 接线 + E2E。

历史 replay 常数来自 GP002 可行性回放（真实生产数据）：
  Help-Me-Edit（llm/full/flags=3）→ 人工 approve，质量有条件合格 ⇒ AUTO_APPLY
  10-of-the-Best / 79年前 / 9个有用（flags 20/14/10）→ 人工 approve 但事后 FAIL ⇒ QUARANTINE
  heuristic ×3 → 人工从未触碰 ⇒ AUTO_REJECT
  GP-001 重复提案 → 人工 reject ⇒ AUTO_REJECT
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.auto_apply_policy import (
    AUTO_APPLY, AUTO_REJECT, POLICY_VERSION, QUARANTINE,
    evaluate_auto_apply_policy,
)
from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import make_cfg, write_raw

SOURCE_TARGET_PREFIX = "wiki/sources/"


# ---------------------------------------------------------------------------
# 一｜provider 桩与 planned page 构造
# ---------------------------------------------------------------------------
def _stub_provider(*, source_flags: int = 0):
    """source 正常编译（可控 flags 数）+ typed 全 zero 的 provider 桩。"""
    flags_list = [f"合成质量标记 {i}" for i in range(source_flags)]
    payloads = []

    def provider(cfg, system_prompt, payload):
        payloads.append(payload)
        if isinstance(payload, dict):
            task = payload.get("task")
            if task == "concept_extraction":
                return json.dumps({"concept_found": False, "reason": "zero"},
                                  ensure_ascii=False)
            if task == "case_extraction":
                return json.dumps({"case_found": False, "reason": "zero"},
                                  ensure_ascii=False)
            if task == "question_led_topic_synthesis":
                return json.dumps({"topic_viable": False, "reason": "zero"},
                                  ensure_ascii=False)
        return json.dumps({
            "summary": "合成资料摘要",
            "key_statements": [{"text": "回顾触发器必须绑定到已经存在的卡片上。",
                                "quote": "回顾触发器必须绑定到已经存在的卡片上。",
                                "kind": "assertion"}],
            "topics": [{"title": "回顾触发器", "content": "围绕回顾触发器的研究框架"}],
            "limitations": ["合成限制：结论未经独立核实"],
            "quality_flags": flags_list,
        }, ensure_ascii=False)

    provider.payloads = payloads
    return provider


def build_intake_plan(cfg, run_id: str, *, source_flags: int = 0, use_llm: bool = True):
    """真实 init 流程（provider 桩：source 正常编译、typed zero）。"""
    prov = _stub_provider(source_flags=source_flags)
    with patch("core.llm.call_chat_completion", prov):
        return steward.build_initialization_plan(
            cfg, plan_run_id=run_id, stamp=steward.stamp(),
            executor_plan_fn=steward.mvp_executor_plan,
            page_requires_manual_review=steward.page_requires_manual_review,
            duplicate_page_targets=steward.duplicate_page_targets,
            page_has_blocked_placeholder=lambda page: steward.page_has_blocked_placeholder(page, cfg),
            planned_raw_coverage=steward.planned_raw_coverage,
            batch_size=6, use_llm=use_llm,
            discover_providers={"concept": prov, "case": prov})


def _source_page(*, mode="llm", coverage="full", flags=3,
                 target="wiki/sources/source-x-abc.md", type_="source-note",
                 with_state=True, review_required=True):
    flag_list = ", ".join(f'"flag {i}: 合成质量标记"' for i in range(flags))
    state = ('card_state: {"info_units": [{"statement": "s"}], "claims": []}\n'
             if with_state else "")
    content = (
        "---\n"
        'title: "Source: 合成来源"\n'
        f"type: {type_}\n"
        f"analysis_mode: {mode}\n"
        f"coverage: {coverage}\n"
        'sources: ["raw/合成来源.md"]\n'
        f"quality_flags: [{flag_list}]\n"
        f"{state}"
        "---\n正文\n")
    return {"rel_path": target, "target": target, "analysis_mode": mode,
            "review_required": review_required, "manual_review": [],
            "content": content, "content_sha256": "0" * 64,
            "object_id": "kb:test", "revision": 1}


def _queue_items(cfg):
    q = steward.review_queue_path(cfg)
    if not q.exists():
        return []
    return [json.loads(l) for l in q.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# 二｜policy 单元（Cases A–F + 历史 replay 固定）
# ---------------------------------------------------------------------------
def test_case_a_low_risk_source_auto_applies():
    d = evaluate_auto_apply_policy(_source_page(flags=3), target_exists=False)
    assert d["decision"] == AUTO_APPLY
    assert d["policy_version"] == POLICY_VERSION
    assert "quality_flags_within_v01_threshold" in d["reason_codes"]


def test_case_b_high_flags_quarantine():
    d = evaluate_auto_apply_policy(_source_page(flags=10), target_exists=False)
    assert d["decision"] == QUARANTINE
    assert any("quality_flags" in r for r in d["reason_codes"])


def test_case_c_heuristic_auto_reject():
    d = evaluate_auto_apply_policy(_source_page(mode="heuristic"), target_exists=False)
    assert d["decision"] == AUTO_REJECT
    assert "heuristic_no_write_eligibility" in d["reason_codes"]


def test_case_d_duplicate_target_auto_reject():
    d = evaluate_auto_apply_policy(_source_page(flags=3), target_exists=True)
    assert d["decision"] == AUTO_REJECT
    assert "duplicate_target" in d["reason_codes"]


def test_case_e_non_source_card_quarantine():
    d = evaluate_auto_apply_policy(_source_page(type_="case-story", flags=0),
                                   target_exists=False)
    assert d["decision"] == QUARANTINE
    assert "non_source_card_type" in d["reason_codes"]


def test_case_f_missing_fields_quarantine():
    d = evaluate_auto_apply_policy({"rel_path": "wiki/sources/x.md", "content": ""},
                                   target_exists=False)
    assert d["decision"] == QUARANTINE


# ---------------------------------------------------------------------------
# 三｜历史 replay 固定（真实生产数值，防边界悄悄扩大）
# ---------------------------------------------------------------------------
def test_historical_replay_help_me_edit_3_flags_auto_applies():
    d = evaluate_auto_apply_policy(_source_page(flags=3), target_exists=False)
    assert d["decision"] == AUTO_APPLY


@pytest.mark.parametrize("flags", [10, 14, 20])
def test_historical_replay_fail_cards_quarantine(flags):
    d = evaluate_auto_apply_policy(_source_page(flags=flags), target_exists=False)
    assert d["decision"] == QUARANTINE, (
        "历史上人工 approve 但事后判 FAIL 的三张卡（flags 10/14/20）必须 QUARANTINE——"
        "此断言防止 policy 阈值悄悄扩大自动放行边界")


def test_historical_replay_heuristic_pages_auto_reject():
    d = evaluate_auto_apply_policy(_source_page(mode="heuristic", flags=0),
                                   target_exists=False)
    assert d["decision"] == AUTO_REJECT


def test_historical_replay_duplicate_proposal_auto_reject():
    d = evaluate_auto_apply_policy(_source_page(flags=20), target_exists=True)
    assert d["decision"] == AUTO_REJECT


# ---------------------------------------------------------------------------
# 四｜接线：write_manual_review_queue 开关行为（真实 init 流程）
# ---------------------------------------------------------------------------
@pytest.fixture
def intake_vault(tmp_path: Path):
    """单篇短 raw → 真实 init 流程 → 1 张低风险来源卡审核项（flags≈0）。"""
    root = tmp_path / "vault"
    cfg = make_cfg(root)
    cfg["source_auto_apply"] = {"enabled": True}
    write_raw(root)
    plan = build_intake_plan(cfg, "auto-apply-intake")
    steward.write_execution_plan(cfg, plan)
    return root, cfg, plan


def test_wiring_auto_applies_clean_source_card(intake_vault):
    root, cfg, plan = intake_vault
    steward.write_manual_review_queue(cfg, plan)   # policy 在此触发
    items = _queue_items(cfg)
    source_saved = [x for x in items
                    if x.get("run_id") == plan["run_id"]
                    and x.get("type") == "planned_page_review"
                    and SOURCE_TARGET_PREFIX in str(x.get("target") or "")]
    assert source_saved, "fixture 应产生来源卡审核项"
    for saved in source_saved:
        assert saved["status"] == "approved", saved
        assert saved["resolved_by"] == f"system-policy:{POLICY_VERSION}"
        assert saved["auto_apply"]["policy_version"] == POLICY_VERSION
        assert "quality_flags_within_v01_threshold" in saved["auto_apply"]["reason_codes"]


def test_wiring_disabled_keeps_pending(intake_vault):
    root, cfg, plan = intake_vault
    cfg["source_auto_apply"] = {"enabled": False}
    source_targets = [str(p.get("rel_path") or p.get("target"))
                      for p in plan["planned_pages"]
                      if SOURCE_TARGET_PREFIX in str(p.get("rel_path") or p.get("target"))]
    steward.write_manual_review_queue(cfg, plan)
    items = _queue_items(cfg)
    for t in source_targets:
        saved = next(x for x in items if x.get("target") == t)
        assert saved["status"] == "pending", "开关关闭时不得自动批准"


# ---------------------------------------------------------------------------
# 五｜E2E：AUTO_APPLY → apply-approved → 真实落盘（零人工点击）
# ---------------------------------------------------------------------------
def test_e2e_auto_apply_writes_through_full_safety_chain(intake_vault):
    root, cfg, plan = intake_vault
    steward.write_manual_review_queue(cfg, plan)   # policy 在此触发
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id=plan["run_id"])) == 0
    applied = [p for p in plan["planned_pages"]
               if str(p.get("rel_path", "")).startswith(SOURCE_TARGET_PREFIX)]
    for p in applied:
        assert (root / p["rel_path"]).exists(), p["rel_path"]
    # QUARANTINE 页（若有）不得落盘
    for it in _queue_items(cfg):
        if it.get("run_id") == plan["run_id"] and it.get("status") == "pending":
            assert not (root / str(it.get("target") or "x")).exists()


def test_e2e_high_flags_source_quarantines_without_write(tmp_path: Path):
    root = tmp_path / "vault"
    cfg = make_cfg(root)
    cfg["source_auto_apply"] = {"enabled": True}
    write_raw(root)
    plan = build_intake_plan(cfg, "auto-quarantine-intake", source_flags=10)
    steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)   # flags=10 → QUARANTINE
    items = _queue_items(cfg)
    src = [x for x in items
           if x.get("run_id") == plan["run_id"]
           and x.get("type") == "planned_page_review"
           and SOURCE_TARGET_PREFIX in str(x.get("target") or "")]
    assert src and all(x["status"] == "pending" for x in src), src
    for p in plan["planned_pages"]:
        if SOURCE_TARGET_PREFIX in str(p.get("rel_path") or ""):
            assert not (root / p["rel_path"]).exists(), p["rel_path"]


def test_e2e_heuristic_source_auto_rejects_without_write(tmp_path: Path):
    """接线级 E2E：heuristic 来源页的手工计划 → AUTO_REJECT → 不落盘。

    （heuristic 编译对多数 fixture 文本会被 B10 安全门禁拦截在 plan 前，
    因此用手工计划直接测队列接线——决策语义与真实 heuristic 页完全一致。）
    """
    root = tmp_path / "vault"
    cfg = make_cfg(root)
    cfg["source_auto_apply"] = {"enabled": True}
    (root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
    page = _source_page(mode="heuristic", flags=0,
                        target="wiki/sources/source-heuristic-manual.md")
    plan = {"run_id": "auto-reject-heuristic", "entry": "init_kb",
            "task": "初始化知识库", "review_contract": "page-scoped-v1",
            "planned_pages": [dict(page, rel_path=page["target"],
                                   operation="create",
                                   content_sha256=str(int(page["content_sha256"], 16) % (16 ** 64)))],
            "manual_review": [{"type": "planned_pages_require_review",
                               "risk": "medium",
                               "reason": "页面需人工确认（fixture）",
                               "items": [page["target"]]}]}
    steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)   # heuristic → AUTO_REJECT
    items = _queue_items(cfg)
    rej = [it for it in items
           if it.get("run_id") == plan["run_id"] and it.get("status") == "rejected"]
    assert rej, "heuristic 来源卡应被 AUTO_REJECT"
    assert all(it.get("resolved_by") == f"system-policy:{POLICY_VERSION}" for it in rej)
    assert all("heuristic_no_write_eligibility" in (it.get("resolution_reason") or "")
               for it in rej)
    assert not (root / page["target"]).exists(), "AUTO_REJECT 不得落盘"
