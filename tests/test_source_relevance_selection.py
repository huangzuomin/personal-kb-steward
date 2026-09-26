# -*- coding: utf-8 -*-
"""GP001 Phase 4: case/concept 生成输入的相关性收窄（RELEVANCE_FILTER_MISSING）。

架构边界（见 iteration-artifacts GP001_SOURCE_RELEVANCE_FAILURE_BOUNDARY.md）：
- collect_eligible_sources 保持"宽候选池"生命周期语义 —— 本文件锁定该边界，
  不得把过滤错误地前移到池构造；
- 收窄只发生在 discover_cards 的 typed 生成输入组装（focus 相关性选择，
  复用 topic 分支既有检索语义与 topic_source_cap 上限）；
- provenance 契约（evidence_cards）不动：无关来源因"根本不被提供"而自然
  不进入 payload / provenance_map / 来源地图。

公开合成素材，隔离临时 vault；仅模型 provider 为本地桩。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.card_pipeline import collect_eligible_sources, discover_cards
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests.test_card_pipeline_integration import make_cfg

ROOT = Path(__file__).resolve().parents[1]

# -- 三个合成来源：A 相关（陶冷月/雁荡山摄影），B/C 明显无关 ------------------
REL_A = "raw/a-tao-lengyue-yandangshan.md"
TITLE_A = "陶冷月1937年雁荡山摄影档案"
TEXT_A = (
    "# 陶冷月1937年雁荡山摄影档案\n\n"
    "1937 年八月，画家陶冷月应邀赴雁荡山避暑，此行拍摄雁荡山风景照片达 51 幅。\n"
    "他把摄影当作绘画师造化的手段，每次出游都用照片酝酿画意，作为创作的视觉依据。\n"
    "这批照片经过后人存档保管，成为考察当时历史情境的视觉文献。\n"
)
Q_A1 = "1937 年八月，画家陶冷月应邀赴雁荡山避暑，此行拍摄雁荡山风景照片达 51 幅。"
Q_A2 = "他把摄影当作绘画师造化的手段，每次出游都用照片酝酿画意，作为创作的视觉依据。"
Q_A3 = "这批照片经过后人存档保管，成为考察当时历史情境的视觉文献。"

REL_B = "raw/b-help-me-edit.md"
TITLE_B = "Help Me Edit 提示词模板"
TEXT_B = (
    "# Help Me Edit 提示词模板\n\n"
    "这是一份关于 AI 写作助手的提示词模板，主题是帮我编辑（Help Me Edit）。\n"
    "模板要求先分析文本再给出修改建议，不直接代改，由作者本人决定取舍。\n"
)
Q_B1 = "这是一份关于 AI 写作助手的提示词模板，主题是帮我编辑（Help Me Edit）。"

REL_C = "raw/c-ai-prompts-newsletter.md"
TITLE_C = "AI 提示词周刊"
TEXT_C = (
    "# AI 提示词周刊\n\n"
    "这是一封 Gmail 收件存档的 AI 提示词周刊，收录 9 useful AI prompts。\n"
    "每条提示只给出节选，完整提示文本位于 Substack 重定向外链中。\n"
)
Q_C1 = "这是一封 Gmail 收件存档的 AI 提示词周刊，收录 9 useful AI prompts。"

SRC_A = "1937 年八月，画家陶冷月应邀赴雁荡山避暑，此行拍摄雁荡山风景照片达 51 幅。"


def _source_response(quote, summary):
    return {
        "summary": summary,
        "key_statements": [{"text": quote, "quote": quote, "kind": "assertion"}],
        "topics": [{"title": "合成主题", "content": "公开合成素材的主题框架"}],
        "limitations": ["合成限制：结论未经独立核实"],
        "quality_flags": [],
    }


RESP_A = _source_response(Q_A1, "陶冷月雁荡山摄影合成档案摘要")
RESP_B = _source_response(Q_B1, "Help Me Edit 提示词模板摘要")
RESP_C = _source_response(Q_C1, "AI 提示词周刊摘要")


def judgment_a(statement, quote, kind="fact"):
    return {"statement": statement, "kind": kind, "confidence": "medium",
            "evidence": [{"source": REL_A, "quote": quote, "relation": "supports"}]}


CASE_MECH_A = "陶冷月把摄影当作绘画师造化的手段，用照片酝酿画意"
CASE_INF_A = "照片能成为历史视觉文献，依赖存档与流传"


def case_response_a():
    return {
        "case_found": True,
        "cases": [{
            "title": "陶冷月1937年雁荡山摄影（合成案例）",
            "card_level": "project",
            "confidence": "medium",
            "context": "画家陶冷月1937年应邀赴雁荡山避暑。",
            "action": "他以摄影辅助绘画，用照片酝酿画意。",
            "result": {"figures": [{"claim": "陶冷月1937年在雁荡山拍摄照片51幅"}]},
            "reusable_mechanism_claim": CASE_MECH_A,
            "mechanism_inference_claim": CASE_INF_A,
            "applicability": {
                "conditions": [{"claim": "前提是照片被存档并流传"}],
                "uncertainties": ["51 幅的统计口径未独立核实"],
            },
            "judgments": [
                judgment_a("陶冷月1937年在雁荡山拍摄照片51幅", Q_A1),
                judgment_a(CASE_MECH_A, Q_A2),
                judgment_a(CASE_INF_A, Q_A3, kind="inference"),
            ],
            "related": [], "pending_paths": [],
        }],
        "provenance_map": [{"rel": REL_A, "provenance": "合成摄影档案（合成）",
                            "limitations": ["合成素材：数字未独立核实"]}],
        "shared_provenance": [],
    }


CONCEPT_DEF_A = "师造化摄影：画家用摄影记录画笔来不及捕捉的情景"


def concept_response_a():
    boundary = "它与单纯纪游拍照的区别在于服务于后续绘画创作"
    return {
        "concept_found": True,
        "concepts": [{
            "name": "师造化摄影",
            "aliases": [],
            "definition_claim": CONCEPT_DEF_A,
            "explanation": "来源把这种摄影与普通纪游区分开：它服务于后续的绘画创作。",
            "confidence": "medium",
            "source_defined_boundary": [{"evidence_claim": boundary}],
            "suggested_interpretation": [],
            "judgments": [
                judgment_a(CONCEPT_DEF_A, Q_A2),
                judgment_a(boundary, Q_A2),
            ],
            "related": [], "pending_paths": [],
        }],
        "provenance_map": [{"rel": REL_A, "provenance": "合成摄影档案（合成）",
                            "limitations": ["合成素材"]}],
        "shared_provenance": [],
    }


def make_note_dispatcher(*, concept=None, case=None):
    """Provider 桩：{"text": ...} 形态 = source 编译（按内容分派）；task 键 = typed 各类。"""
    calls = []

    def provider(cfg, system_prompt, payload):
        calls.append(payload)
        if isinstance(payload, dict) and "task" not in payload and "text" in payload:
            text = str(payload.get("text") or "")
            if Q_B1 in text or "Help Me Edit" in text:
                return json.dumps(RESP_B, ensure_ascii=False)
            if Q_C1 in text or "提示词周刊" in text:
                return json.dumps(RESP_C, ensure_ascii=False)
            return json.dumps(RESP_A, ensure_ascii=False)
        if isinstance(payload, dict) and payload.get("task") == "concept_extraction":
            value = concept if concept is not None else concept_response_a()
            if isinstance(value, BaseException):
                raise value
            return json.dumps(value, ensure_ascii=False)
        if isinstance(payload, dict) and payload.get("task") == "case_extraction":
            value = case if case is not None else case_response_a()
            if isinstance(value, BaseException):
                raise value
            return json.dumps(value, ensure_ascii=False)
        from tests import public_round_support as round_support
        return round_support.topic_response(payload)

    provider.calls = calls
    return provider


def write_note(root, rel, title, text):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(text.encode("utf-8"))
    return {"rel": rel, "title": title, "body": text,
            "metadata": {"material_kind": "synthetic"},
            "source_text": text,
            "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def compile_and_persist_card(root, cfg, note, response):
    """走真实 topic-research-compile 执行器沉淀一张来源卡（模拟此前 run 的产出）。"""
    from core.skill_executor import execute_skill

    def provider(cfg_, prompt, payload):
        return json.dumps(response, ensure_ascii=False)

    with patch("core.llm.call_chat_completion", provider):
        result = execute_skill(ROOT, "topic-research-compile",
                               {"config": cfg, "notes": [note], "use_llm": True})
    pages = result.get("created") or []
    assert pages, (note["rel"], result.get("issues"))
    page = pages[0]
    target = root / page["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page["content"], encoding="utf-8")
    return page["target"]


def make_relevance_cfg(root):
    cfg = make_cfg(root)
    cfg["initialize"] = {"seed_stage": False}
    return cfg


@pytest.fixture
def wide_pool_vault(tmp_path):
    """池里有 A/B/C 三张来源卡；三个 raw 都在盘上（模拟累计池 + 本轮 batch=A）。"""
    root = tmp_path
    cfg = make_relevance_cfg(root)
    for rel, title, text, resp in (
        (REL_A, TITLE_A, TEXT_A, RESP_A),
        (REL_B, TITLE_B, TEXT_B, RESP_B),
        (REL_C, TITLE_C, TEXT_C, RESP_C),
    ):
        compile_and_persist_card(root, cfg, write_note(root, rel, title, text), resp)
    return root, cfg


@pytest.fixture
def no_relevant_vault(tmp_path):
    """池里只有 B/C 两张卡；A 的 raw 在盘上（会成为 batch 输入）但没有来源卡。"""
    root = tmp_path
    cfg = make_relevance_cfg(root)
    for rel, title, text, resp in (
        (REL_B, TITLE_B, TEXT_B, RESP_B),
        (REL_C, TITLE_C, TEXT_C, RESP_C),
    ):
        compile_and_persist_card(root, cfg, write_note(root, rel, title, text), resp)
    write_note(root, REL_A, TITLE_A, TEXT_A)
    return root, cfg


def build_init_plan_batch1(cfg, providers):
    return steward.build_initialization_plan(
        cfg, plan_run_id=steward.run_id(), stamp=steward.stamp(),
        executor_plan_fn=steward.mvp_executor_plan,
        page_requires_manual_review=steward.page_requires_manual_review,
        duplicate_page_targets=steward.duplicate_page_targets,
        page_has_blocked_placeholder=steward.page_has_blocked_placeholder,
        planned_raw_coverage=steward.planned_raw_coverage,
        batch_size=1, use_llm=True, discover_providers=providers)


def _generation_stages(plan):
    return {a["stage"]: a for a in plan["actions"]
            if str(a.get("stage", "")).endswith("_generation")}


def _task_documents(dispatcher, task):
    docs = [p for p in dispatcher.calls
            if isinstance(p, dict) and p.get("task") == task]
    assert docs, f"provider 未被 {task} 调用"
    return [d.get("path") for d in docs[0].get("documents", [])]


# ---------------------------------------------------------------------------
# 1. 宽候选池边界：collect_eligible_sources 不过滤（架构语义保持）
# ---------------------------------------------------------------------------
def test_collect_eligible_sources_keeps_wide_pool(wide_pool_vault):
    root, cfg = wide_pool_vault
    index = build_index(cfg)
    collected = collect_eligible_sources(index, cfg)
    assert {n["rel"] for n in collected["notes"]} == {REL_A, REL_B, REL_C}, \
        "宽候选池语义不得收窄：过滤只能发生在 typed 生成输入组装"


# ---------------------------------------------------------------------------
# 2. RED/GREEN 主测试：init-kb 真实链路上 case/concept 输入只含本轮 focus 来源
# ---------------------------------------------------------------------------
def test_init_plan_case_concept_input_narrowed_to_focus(wide_pool_vault):
    root, cfg = wide_pool_vault
    dispatcher = make_note_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher):
        plan = build_init_plan_batch1(cfg, {"concept": dispatcher, "case": dispatcher})

    # batch 只含 A（batch_size=1，A 按 rel 排序最先），focus = [REL_A]
    case_docs = _task_documents(dispatcher, "case_extraction")
    assert case_docs == [REL_A], (
        f"Expected supplied = [{REL_A}]；Actual supplied = {case_docs} —— "
        "case 生成输入未按本轮输入范围收窄（RELEVANCE_FILTER_MISSING）")
    concept_docs = _task_documents(dispatcher, "concept_extraction")
    assert concept_docs == [REL_A], f"concept 输入未收窄：{concept_docs}"

    # §九 related_query 回归：不再由无关来源标题拼接污染
    stages = _generation_stages(plan)
    case_query = str((stages["case_generation"].get("retrieval") or {}).get("query") or "")
    assert "陶冷月" in case_query, case_query
    assert "Help Me Edit" not in case_query, case_query
    assert "提示词周刊" not in case_query, case_query


# ---------------------------------------------------------------------------
# 3. 无相关来源：不强行生成、不调用 provider（topic 既有语义的 case/concept 版）
# ---------------------------------------------------------------------------
def test_no_focus_relevant_source_skips_generation(no_relevant_vault):
    root, cfg = no_relevant_vault
    dispatcher = make_note_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher):
        plan = build_init_plan_batch1(cfg, {"concept": dispatcher, "case": dispatcher})

    stages = _generation_stages(plan)
    for kind in ("case_generation", "concept_generation"):
        assert stages[kind]["state"] == "zero", (kind, stages[kind])
        assert stages[kind]["reason"] == "no_relevant_sources", (kind, stages[kind])
        assert stages[kind]["provider_calls"] == 0, kind
    typed_calls = [p for p in dispatcher.calls
                   if isinstance(p, dict) and p.get("task") in
                   ("case_extraction", "concept_extraction")]
    assert typed_calls == [], "无相关来源时不得调用生成模型"


# ---------------------------------------------------------------------------
# 4. discover_cards 直接契约：有 focus → 收窄；无 focus → 维持现行为（finalize 决策点）
# ---------------------------------------------------------------------------
def test_discover_cards_focus_contract(wide_pool_vault):
    root, cfg = wide_pool_vault
    index = build_index(cfg)

    focused = make_note_dispatcher()
    out = discover_cards(index, cfg, run_id="r-focus", use_llm=True,
                         kinds=("case",), providers={"case": focused},
                         focus_rels=[REL_A])
    assert out["stages"]["case"]["provider_calls"] == 1
    docs = [d.get("path") for d in focused.calls[0].get("documents", [])]
    assert docs == [REL_A], docs

    # 空 focus = 本轮无新输入的积压 run：保持既有全池契约（跨源积压类型化）
    backlog = make_note_dispatcher()
    out_backlog = discover_cards(index, cfg, run_id="r-backlog", use_llm=True,
                                 kinds=("case",), providers={"case": backlog},
                                 focus_rels=[])
    docs_backlog = [d.get("path") for d in backlog.calls[0].get("documents", [])]
    assert docs_backlog == [REL_A, REL_B, REL_C], docs_backlog
    assert out_backlog["stages"]["case"]["provider_calls"] == 1

    # focus_rels=None = finalize 等未给输入范围的入口：维持现行为（已登记的产品决策点）
    unfocused = make_note_dispatcher()
    out2 = discover_cards(index, cfg, run_id="r-wide", use_llm=True,
                          kinds=("case",), providers={"case": unfocused})
    docs2 = [d.get("path") for d in unfocused.calls[0].get("documents", [])]
    assert docs2 == [REL_A, REL_B, REL_C], docs2
    assert out2["stages"]["case"]["provider_calls"] == 1
