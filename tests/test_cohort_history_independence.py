# -*- coding: utf-8 -*-
"""GP001 Phase 6：cohort 的历史位置无关性（RECEIPT_FINGERPRINT_ACCIDENTAL_COUPLING 修复）。

核心断言（§三 核心测试）：当前 index/disk 中真实存在、可验证的 sibling derived
outputs（concept/case）不因"topic 回执记录在哪个 plan 里"而改变 cohort。

History A：topic explicit-zero 回执与 concept/case ok 回执在同一个 finalize plan。
History B：把同一个 topic explicit-zero 回执单独放进一个"不完整尝试"plan
（batch-scoped intake 的收窄形态：concept/case 回执缺席）并使其成为最新的
topic-bearing plan。两种历史的当前知识状态完全相同 ⇒ cohort 必须相同。

安全防线（§八/§九，非 RED）：
- explicit-zero 回执不得伪造 sibling 路径；
- 漂移/删除的 sibling 不得进入 cohort（现有 fail-closed 语义容忍）。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from core.pipeline_history import derived_cohort_paths
from core.vault import build_index
from scripts import personal_kb_steward as steward
from scripts.evaluate_public_baseline import build_cfg, prepare_vault
from tests.test_derived_receipt_blackbox import (
    PublicProvider,
    apply_saved_plan,
    build_finalize_plan,
    save_plan,
)


class ZeroTopicProvider(PublicProvider):
    """concept/case 正常产出、topic 恒为 explicit-zero 的 fixture provider。"""

    def __call__(self, *args):
        payload = args[-1] if args and isinstance(args[-1], dict) else {}
        response = super().__call__(*args)
        if payload.get("task") == "question_led_topic_synthesis":
            return json.dumps(
                {"topic_viable": False, "reason": "fixture zero"}, ensure_ascii=False)
        return response


@pytest.fixture
def cohort_vault(tmp_path: Path):
    root = tmp_path / "vault"
    prepare_vault(root)
    return root, build_cfg(root)


def _apply_intake(root, cfg):
    from tests.test_derived_receipt_blackbox import build_intake_plan

    plan = build_intake_plan(cfg, PublicProvider(), "cohort-history-intake")
    apply_saved_plan(cfg, plan)
    return plan


def _typed_rels(plan, prefix):
    return sorted(
        page["rel_path"] for page in plan.get("planned_pages", [])
        if str(page.get("rel_path", "")).startswith(prefix))


def _topic_closure_base(plan):
    for st in (plan.get("generation_receipts") or {}).get("stages") or []:
        if st.get("stage") == "topic_generation":
            return st.get("input_closure")
    raise AssertionError("plan 没有 topic 回执")


def _call_cohort(cfg, index, closure_base):
    return derived_cohort_paths(
        cfg, skill="kb-finalize", stage="topic_generation",
        input_closure=copy.deepcopy(closure_base), index=index)


def test_cohort_is_history_location_independent(cohort_vault):
    root, cfg = cohort_vault
    _apply_intake(root, cfg)
    final_zero = build_finalize_plan(cfg, ZeroTopicProvider(), "cohort-history-a-final")
    apply_saved_plan(cfg, final_zero)
    concept_rel = _typed_rels(final_zero, "wiki/concepts/")[0]
    case_rel = _typed_rels(final_zero, "wiki/cases/")[0]
    index = build_index(cfg)
    closure = _topic_closure_base(final_zero)

    # History A：topic explicit-zero 回执与 concept/case ok 回执同 plan
    cohort_a = _call_cohort(cfg, index, closure)
    assert cohort_a == {concept_rel, case_rel}, cohort_a

    # History B：同一个 topic explicit-zero 回执单独放进最新的"不完整尝试"plan
    #（无 concept/case 回执——batch-scoped intake 收窄后的真实形态）。
    # 当前知识状态不变 ⇒ cohort 不得变化。
    topic_only = copy.deepcopy(final_zero)
    topic_only["run_id"] = "cohort-history-b-topic-only"
    stages = (topic_only.get("generation_receipts") or {}).get("stages") or []
    topic_only["generation_receipts"]["stages"] = [
        st for st in stages if st.get("stage") == "topic_generation"]
    assert topic_only["generation_receipts"]["stages"], "fixture 需要 topic 回执"
    assert topic_only["generation_receipts"]["stages"][0].get("generation_state") == "zero"
    save_plan(cfg, topic_only)

    cohort_b = _call_cohort(cfg, build_index(cfg), closure)
    assert cohort_b == {concept_rel, case_rel}, (
        f"cohort 依赖了 topic 回执所在 plan（history-location coupling）："
        f"History A={cohort_a} History B={cohort_b}")


def test_explicit_zero_history_yields_no_ghost_siblings(cohort_vault):
    root, cfg = cohort_vault
    _apply_intake(root, cfg)
    final_zero = build_finalize_plan(cfg, ZeroTopicProvider(), "cohort-zero-final")
    apply_saved_plan(cfg, final_zero)
    topic_rel_candidates = _typed_rels(final_zero, "wiki/topics/")
    index = build_index(cfg)
    closure = _topic_closure_base(final_zero)

    cohort = _call_cohort(cfg, index, closure)
    # explicit-zero 回执自身不得伪造任何路径：cohort 只能含真实存在的 concept/case 兄弟，
    # 不得包含 zero 回执自己的（不存在的）topic 产出路径。
    for rel in topic_rel_candidates:
        assert rel not in cohort, rel
    from core.layout import knowledge_dirs
    dirs = knowledge_dirs(cfg)
    assert all(rel.startswith((dirs["concepts_dir"] + "/", dirs["cases_dir"] + "/"))
               for rel in cohort), cohort


def test_deleted_or_drifted_sibling_never_enters_cohort(cohort_vault):
    root, cfg = cohort_vault
    _apply_intake(root, cfg)
    final_zero = build_finalize_plan(cfg, ZeroTopicProvider(), "cohort-stale-final")
    apply_saved_plan(cfg, final_zero)
    concept_rel = _typed_rels(final_zero, "wiki/concepts/")[0]
    case_rel = _typed_rels(final_zero, "wiki/cases/")[0]
    closure = _topic_closure_base(final_zero)

    # 字节漂移：case 卡被篡改 ⇒ 漂移的 sibling 不得进入 cohort
    case_path = root / case_rel
    case_path.write_bytes(case_path.read_bytes() + "\n被篡改。\n".encode("utf-8"))
    cohort_drifted = _call_cohort(cfg, build_index(cfg), closure)
    assert case_rel not in cohort_drifted, cohort_drifted

    # 删除：concept 卡被删除 ⇒ 不得进入 cohort
    (root / concept_rel).unlink()
    cohort_deleted = _call_cohort(cfg, build_index(cfg), closure)
    assert concept_rel not in cohort_deleted, cohort_deleted
