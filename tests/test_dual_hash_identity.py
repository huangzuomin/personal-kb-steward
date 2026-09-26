# -*- coding: utf-8 -*-
"""GP002 Phase 3B：dual hash identity（byte integrity ≠ processing identity）。

六 Case 矩阵 + review_rejected 保护。全部走真实流程（真实回执、真实 review/apply）。
已知真实 hash 常数（Sample A 生产数据，固定期望值）：
  CRLF bytes → 0694396f…   LF bytes → aa92b5f1…
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import build_cfg, prepare_vault
from tests.test_derived_receipt_blackbox import (
    PublicProvider,
    build_intake_plan,
)
from core.content_identity import NO_MATCH, content_identity_sha256, match_content_identity

DRIFT_RAW = "raw/research_summary_uncited_01.md"   # 受控漂移样本
OTHER_RAW = "raw/project_case_01.md"               # 未被改写的对照样本


def _crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def _write_raw(root: Path, rel: str, text: str, *, eol: str = "lf", bom: bool = False) -> bytes:
    body = _crlf(text) if eol == "crlf" else text
    raw = body.encode("utf-8")
    if bom:
        raw = b"\xef\xbb\xbf" + raw
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return raw


def _sha(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def _review_and_apply(cfg, plan, *, reject_rel_prefix: str | None = None):
    """真实 review：默认全批准；给出 reject_rel_prefix 时拒绝该来源页并 subset 应用。"""
    steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        if item.get("run_id") != plan["run_id"]:
            continue
        target = str(item.get("target") or "")
        command = "reject" if (reject_rel_prefix and target.startswith(reject_rel_prefix)) else "approve"
        assert steward.command_review(cfg, SimpleNamespace(
            review_command=command, id=item["id"], reason="dual-hash fixture")) == 0
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id=plan["run_id"])) == 0


def _source_page_rel(plan, raw_rel=DRIFT_RAW, prefix=("wiki/sources/", "_kb-steward/sources/")):
    """来源卡页 = 文件名内嵌 raw stem 的那张（source-<stem>-<hash>.md）。"""
    stem = Path(raw_rel).stem
    return next(
        page["rel_path"] for page in plan.get("planned_pages", [])
        if any(str(page.get("rel_path", "")).startswith(p) for p in prefix)
        and stem in str(page.get("rel_path", "")))


@pytest.fixture
def built_vault(tmp_path: Path):
    """CRLF 形态的受控 raw → 真实 intake plan 已构建未审核（各测试自行处置）。"""
    root = tmp_path / "vault"
    prepare_vault(root)
    cfg = build_cfg(root)
    text = (root / DRIFT_RAW).read_text(encoding="utf-8")
    _write_raw(root, DRIFT_RAW, text, eol="crlf")
    plan = build_intake_plan(cfg, PublicProvider(), "dual-hash-intake")
    assert plan["planned_pages"]
    return root, cfg, text, plan


def _selection_group(cfg, rel):
    from core.pipeline_history import select_generation_inputs
    from core.vault import build_index

    index = build_index(cfg)
    selection = select_generation_inputs(index, cfg, "topic-research-compile", use_llm=True)
    for group in ("generate", "pending", "rejected", "unchanged", "retryable"):
        for item in selection.get(group, []):
            candidate_rel = item["note"].rel if isinstance(item, dict) else item.rel
            if candidate_rel == rel:
                return group
    return "absent"


def _lookup_decision(cfg, rel):
    from core.pipeline_history import lookup_generation_receipt, _stage_name
    from core.vault import build_index

    index = build_index(cfg)
    note = index.by_rel[rel]
    decision = lookup_generation_receipt(
        cfg, _stage_name("topic-research-compile"),
        source_rel=rel, source_sha256=note.sha256,
        source_bytes=note.path.read_bytes(), use_llm=True)
    return (decision or {}).get("decision")


# ---------------------------------------------------------------------------
# Case 1｜LF → LF（BYTE_MATCH，现状刻画）
# ---------------------------------------------------------------------------
def test_case1_unchanged_byte_match(built_vault):
    root, cfg, _text, plan = built_vault
    _review_and_apply(cfg, plan)
    assert _selection_group(cfg, OTHER_RAW) == "unchanged", (
        "对照样本未漂移：回执应命中 unchanged")


# ---------------------------------------------------------------------------
# Case 2｜CRLF → LF（REPRESENTATION_DRIFT，核心 RED）
# ---------------------------------------------------------------------------
def test_case2_crlf_to_lf_is_representation_drift(built_vault):
    root, cfg, text, plan = built_vault
    _review_and_apply(cfg, plan)
    _write_raw(root, DRIFT_RAW, text, eol="lf")   # 唯一变化：CRLF → LF
    assert _selection_group(cfg, DRIFT_RAW) == "unchanged", (
        "表示漂移不得触发重新生成（应为 unchanged，而非 generate）")


# ---------------------------------------------------------------------------
# Case 3｜BOM+LF（REPRESENTATION_DRIFT）
# ---------------------------------------------------------------------------
def test_case3_bom_to_no_bom_is_representation_drift(built_vault):
    root, cfg, text, plan = built_vault
    _review_and_apply(cfg, plan)
    _write_raw(root, DRIFT_RAW, text, eol="lf", bom=True)
    assert _selection_group(cfg, DRIFT_RAW) == "unchanged", "BOM 漂移不得触发重新生成"


# ---------------------------------------------------------------------------
# Case 4｜真实正文修改 → CHANGED / generate
# ---------------------------------------------------------------------------
def test_case4_real_content_change_generates(built_vault):
    root, cfg, text, plan = built_vault
    _review_and_apply(cfg, plan)
    _write_raw(root, DRIFT_RAW, text + "\n新增一句真正不同的正文内容。\n")
    assert _selection_group(cfg, DRIFT_RAW) == "generate", "真实内容变化必须重新进入 generate"


# ---------------------------------------------------------------------------
# Case 5｜identity same + contract mismatch → RETRYABLE
# ---------------------------------------------------------------------------
def test_case5_contract_mismatch_stays_retryable(built_vault):
    root, cfg, text, plan = built_vault
    _review_and_apply(cfg, plan)
    _write_raw(root, DRIFT_RAW, text, eol="lf")
    from core.pipeline_history import (
        _stage_name, _contract_snapshot, lookup_generation_receipt)
    from core.vault import build_index

    index = build_index(cfg)
    note = index.by_rel[DRIFT_RAW]
    real_snapshot = _contract_snapshot
    module = __import__("core.pipeline_history", fromlist=["_contract_snapshot"])

    def altered(cfg_, stage, source_rel, source_sha256, use_llm, skill=None):
        snap = real_snapshot(cfg_, stage, source_rel, source_sha256, use_llm, skill=skill)
        return {"semantic": {"kind": "poison"}, **{
            k: v for k, v in (snap or {}).items() if k != "semantic"}}

    original = getattr(module, "_contract_snapshot")
    setattr(module, "_contract_snapshot", altered)
    try:
        decision = lookup_generation_receipt(
            cfg, _stage_name("topic-research-compile"),
            source_rel=DRIFT_RAW, source_sha256=note.sha256,
            source_bytes=note.path.read_bytes(), use_llm=True)
    finally:
        setattr(module, "_contract_snapshot", original)
    assert (decision or {}).get("decision") == "retryable", decision


# ---------------------------------------------------------------------------
# Case 6｜Provenance 分离：processing identity same，byte provenance stale
# ---------------------------------------------------------------------------
def test_case6_provenance_stays_byte_sensitive(built_vault):
    root, cfg, text, plan = built_vault
    _review_and_apply(cfg, plan)
    source_card_rel = _source_page_rel(plan)
    _write_raw(root, DRIFT_RAW, text, eol="lf")

    from core.card_pipeline import collect_eligible_sources
    from core.state import is_processed, load_processed_index
    from core.vault import build_index

    index = build_index(cfg)
    note = index.by_rel[DRIFT_RAW]
    # processing identity：漂移后的 raw 仍视为已处理
    assert is_processed(load_processed_index(cfg), note, "topic-research-compile"), (
        "表示漂移后 processing identity 必须保持 unchanged")
    # provenance：来源卡声明的 CRLF byte hash 与当前 LF bytes 不符 → 不得进入池
    pool = {row["rel"] for row in collect_eligible_sources(index, cfg)["notes"]}
    assert source_card_rel not in pool, (
        "byte provenance stale 的来源卡不得被静默重绑进池")


# ---------------------------------------------------------------------------
# §十三｜review_rejected + representation drift → 仍 review_rejected
# ---------------------------------------------------------------------------
def test_review_rejected_survives_representation_drift(built_vault):
    root, cfg, text, plan = built_vault
    source_card_rel = _source_page_rel(plan)
    # 真实 GP-001 路径：拒绝重复来源卡页 → subset apply → 回执记为 review_rejected
    _review_and_apply(cfg, plan, reject_rel_prefix=source_card_rel)
    assert _lookup_decision(cfg, DRIFT_RAW) == "review_rejected"

    # 表示漂移后：拒绝决策必须存续（不得退回 generate）
    _write_raw(root, DRIFT_RAW, text, eol="lf")
    assert _lookup_decision(cfg, DRIFT_RAW) == "review_rejected", (
        "review_rejected 不得因表示漂移退回 generate（Sample A 复发防线）")


def test_distinct_invalid_utf8_bytes_do_not_share_content_identity():
    old_bytes = b"source\xff\n"
    changed_bytes = b"source\xfe\n"
    old_identity = content_identity_sha256(old_bytes)

    assert old_identity != content_identity_sha256(changed_bytes)
    match = match_content_identity(
        _sha(old_bytes), old_identity, changed_bytes)
    assert match["kind"] == NO_MATCH
