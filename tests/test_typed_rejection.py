# -*- coding: utf-8 -*-
"""GP002 Phase 5：typed rejection（duplicate 跨 contract 存续；quality/other 保持 Model C）。

枚举：duplicate / quality / policy / other（缺省=other，兼容历史）。
拒绝原因自由文本继续保留为审计字段；typed 字段是唯一可计算语义。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import build_cfg, prepare_vault
from tests.test_derived_receipt_blackbox import build_intake_plan, PublicProvider
from tests.test_dual_hash_identity import (
    DRIFT_RAW,
    OTHER_RAW,
    _lookup_decision,
    _selection_group,
    _write_raw,
)


def _queue_item(cfg, run_id, target_prefix):
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        if item.get("run_id") == run_id and str(item.get("target") or "").startswith(target_prefix):
            return item
    raise AssertionError(f"queue item not found: {target_prefix}")


def _reject(cfg, item, rejection_type=None, reason="typed rejection fixture"):
    kwargs = {"review_command": "reject", "id": item["id"], "reason": reason}
    if rejection_type is not None:
        kwargs["rejection_type"] = rejection_type
    assert steward.command_review(cfg, SimpleNamespace(**kwargs)) == 0


def _apply(cfg, plan):
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id=plan["run_id"])) == 0


@pytest.fixture
def rejected_vault(tmp_path: Path):
    """CRLF raw → intake plan → 拒绝 DRIFT_RAW 的来源卡（typed）→ subset apply。

    返回 (root, cfg, text, plan, rejection_type)。
    """
    root = tmp_path / "vault"
    prepare_vault(root)
    cfg = build_cfg(root)
    text = (root / DRIFT_RAW).read_text(encoding="utf-8")
    _write_raw(root, DRIFT_RAW, text, eol="crlf")
    plan = build_intake_plan(cfg, PublicProvider(), "typed-reject-intake")
    steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    return root, cfg, text, plan


def _reject_drift_card(cfg, plan, rejection_type):
    from pathlib import Path as _P
    card = next(p["rel_path"] for p in plan["planned_pages"]
                if str(p.get("rel_path", "")).startswith("wiki/sources/")
                and _P(DRIFT_RAW).stem in str(p.get("rel_path", "")))
    card_item = _queue_item(cfg, plan["run_id"], card)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        if item.get("run_id") != plan["run_id"]:
            continue
        if item.get("id") == card_item["id"]:
            _reject(cfg, item, rejection_type=rejection_type)
            continue
        assert steward.command_review(cfg, SimpleNamespace(
            review_command="approve", id=item["id"], reason="fixture approve")) == 0
    _apply(cfg, plan)
    return card


# ---------------------------------------------------------------------------
# 一｜CLI / Queue schema
# ---------------------------------------------------------------------------
def test_reject_cli_records_typed_reason(rejected_vault):
    root, cfg, _text, plan = rejected_vault
    card = next(p["rel_path"] for p in plan["planned_pages"]
                if str(p.get("rel_path", "")).startswith("wiki/sources/"))
    item = _queue_item(cfg, plan["run_id"], card)
    _reject(cfg, item, rejection_type="duplicate", reason="duplicate card already exists")
    saved = _queue_item(cfg, plan["run_id"], card)
    assert saved["status"] == "rejected"
    assert saved["rejection_type"] == "duplicate"
    assert saved["resolution_reason"] == "duplicate card already exists"


def test_reject_cli_parser_accepts_rejection_type(tmp_path: Path):
    import json as _json

    from core import config as config_module

    root = tmp_path / "vault"
    prepare_vault(root)
    cfg = build_cfg(root)
    _write_raw(root, DRIFT_RAW, "# 合成文档\n\n回顾触发器必须绑定到已经存在的卡片上。\n")
    plan = build_intake_plan(cfg, PublicProvider(), "typed-cli-plan")
    steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    first = steward.load_queue(steward.review_queue_path(cfg))[0]
    # argv 级测试：--rejection-type 必须被 parser 接受并落库。
    # 实现前 argparse exit 2；实现后经 CONFIG_PATH 重定向写入隔离队列。
    (root / "config.json").write_text(_json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    original_config_path = config_module.CONFIG_PATH
    config_module.CONFIG_PATH = root / "config.json"
    try:
        # 实现前：argparse exit 2（RED 已记录）；实现后：正常执行并落库。
        assert steward.main(["review", "reject", first["id"],
                             "--reason", "typed", "--rejection-type", "duplicate"]) == 0
    finally:
        config_module.CONFIG_PATH = original_config_path
    saved = steward.load_queue(steward.review_queue_path(cfg))
    saved_item = next(i for i in saved if i["id"] == first["id"])
    assert saved_item["status"] == "rejected"
    assert saved_item["rejection_type"] == "duplicate"


def test_reject_cli_quality_type(rejected_vault):
    root, cfg, _text, plan = rejected_vault
    card = next(p["rel_path"] for p in plan["planned_pages"]
                if str(p.get("rel_path", "")).startswith("wiki/sources/"))
    item = _queue_item(cfg, plan["run_id"], card)
    _reject(cfg, item, rejection_type="quality", reason="quality below bar")
    saved = _queue_item(cfg, plan["run_id"], card)
    assert saved["rejection_type"] == "quality"
    assert saved["resolution_reason"] == "quality below bar"


def test_legacy_queue_item_without_type_reads_as_other(rejected_vault):
    root, cfg, _text, plan = rejected_vault
    card = next(p["rel_path"] for p in plan["planned_pages"]
                if str(p.get("rel_path", "")).startswith("wiki/sources/"))
    item = _queue_item(cfg, plan["run_id"], card)
    _reject(cfg, item, rejection_type="other", reason="old rejection")
    # 模拟历史形态：手工移除新字段（不批量迁移历史数据）
    queue_path = steward.review_queue_path(cfg)
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line]
    for row in rows:
        if row.get("id") == item["id"]:
            row.pop("rejection_type", None)
    queue_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    # 历史形态必须可读、不报 schema error，且字段保持缺席
    from core.review_runs import load_checked_queue
    loaded = load_checked_queue(queue_path)
    legacy = next(i for i in loaded if i["id"] == item["id"])
    assert legacy["status"] == "rejected"
    assert "rejection_type" not in legacy


# ---------------------------------------------------------------------------
# 二｜决策矩阵（Case A–F）
# ---------------------------------------------------------------------------
def test_case_a_duplicate_same_contract_review_rejected(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "duplicate")
    assert _lookup_decision(cfg, DRIFT_RAW) == "review_rejected"


def test_case_b_duplicate_new_contract_still_review_rejected(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "duplicate")
    _write_raw(root, DRIFT_RAW, text, eol="lf")   # 表示漂移：identity same
    from core.pipeline_history import _contract_snapshot
    module = __import__("core.pipeline_history", fromlist=["_contract_snapshot"])
    original = module._contract_snapshot

    def new_contract(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=None):
        snap = original(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=skill)
        return {"semantic": {"kind": "upgraded-algorithm"}, **{
            k: v for k, v in (snap or {}).items() if k != "semantic"}}

    setattr(module, "_contract_snapshot", new_contract)
    try:
        decision = _lookup_decision(cfg, DRIFT_RAW)
    finally:
        setattr(module, "_contract_snapshot", original)
    assert decision == "review_rejected", (
        f"duplicate reject 必须跨 contract 存续（实测：{decision}）")


def test_case_c_quality_same_contract_review_rejected(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "quality")
    assert _lookup_decision(cfg, DRIFT_RAW) == "review_rejected"


def test_case_d_quality_new_contract_retryable(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "quality")
    _write_raw(root, DRIFT_RAW, text, eol="lf")
    from core.pipeline_history import _contract_snapshot
    module = __import__("core.pipeline_history", fromlist=["_contract_snapshot"])
    original = module._contract_snapshot

    def new_contract(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=None):
        snap = original(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=skill)
        return {"semantic": {"kind": "upgraded-algorithm"}, **{
            k: v for k, v in (snap or {}).items() if k != "semantic"}}

    setattr(module, "_contract_snapshot", new_contract)
    try:
        decision = _lookup_decision(cfg, DRIFT_RAW)
    finally:
        setattr(module, "_contract_snapshot", original)
    assert decision == "retryable", (
        f"quality reject 在新 contract 下应允许重试（实测：{decision}）")


def test_case_e_other_new_contract_retryable(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "other")
    _write_raw(root, DRIFT_RAW, text, eol="lf")
    from core.pipeline_history import _contract_snapshot
    module = __import__("core.pipeline_history", fromlist=["_contract_snapshot"])
    original = module._contract_snapshot

    def new_contract(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=None):
        snap = original(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=skill)
        return {"semantic": {"kind": "upgraded-algorithm"}, **{
            k: v for k, v in (snap or {}).items() if k != "semantic"}}

    setattr(module, "_contract_snapshot", new_contract)
    try:
        decision = _lookup_decision(cfg, DRIFT_RAW)
    finally:
        setattr(module, "_contract_snapshot", original)
    assert decision == "retryable", "other（历史兼容）必须保持 contract-scoped"


def test_case_f_duplicate_content_changed_generates(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "duplicate")
    _write_raw(root, DRIFT_RAW, text + "\n新增一句真正不同的正文内容。\n")
    assert _selection_group(cfg, DRIFT_RAW) == "generate", (
        "content identity 真实变化必须解除 duplicate reject")


# ---------------------------------------------------------------------------
# 三｜Skill / Target scope：duplicate reject 不影响其他来源与其他技能
# ---------------------------------------------------------------------------
def test_duplicate_reject_does_not_leak_to_other_inputs(rejected_vault):
    root, cfg, text, plan = rejected_vault
    _reject_drift_card(cfg, plan, "duplicate")
    # 同 contract：其他输入不受 duplicate reject 影响（保持 unchanged）
    assert _selection_group(cfg, OTHER_RAW) == "unchanged", (
        "duplicate reject 不得影响同 contract 下其他输入")
    # 新 contract：其他输入因 contract 走 retryable，而非被 duplicate 拒绝波及
    _write_raw(root, DRIFT_RAW, text, eol="lf")
    from core.pipeline_history import _contract_snapshot
    module = __import__("core.pipeline_history", fromlist=["_contract_snapshot"])
    original = module._contract_snapshot

    def new_contract(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=None):
        snap = original(cfg_, stage, source_rel_, source_sha256_, use_llm, skill=skill)
        return {"semantic": {"kind": "upgraded-algorithm"}, **{
            k: v for k, v in (snap or {}).items() if k != "semantic"}}

    setattr(module, "_contract_snapshot", new_contract)
    try:
        assert _selection_group(cfg, OTHER_RAW) != "rejected", (
            "duplicate reject 不得以 rejected 形式泄漏到其他输入")
    finally:
        setattr(module, "_contract_snapshot", original)
