# -*- coding: utf-8 -*-
"""T6 checkpoint A2: typed generation adapters + actual plan/review/apply flow.

Actual isolated workflow with the REAL generators, renderers, executor and
CLI apply/review machinery; ONLY the model provider is a local stub at the
existing generate_* call_provider seam. No network, no real model, public
synthetic fixtures, isolated temp vaults.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.card_pipeline import discover_cards
from core.claims import read_claims, validate_claims
from core.config import card_pipeline_mode
from core.vault import build_index, extract_wikilinks, parse_frontmatter
from scripts import personal_kb_steward as steward

ROOT = Path(__file__).resolve().parents[1]

RAW_REL = "raw/doc.md"
RAW_TEXT = (
    "# 合成文档\n\n"
    "本节描述一个可复用的回顾触发器概念。回顾触发器必须绑定到已经存在的卡片上。\n"
    "青梧书店（合成）在周末读书会试行书单绑定活动，店主讲完后把当期主题三本书列成书单现场提供。\n"
    "绑定回顾触发器的卡片30天后再访问率自报约62%（未独立核实）。\n"
    "书单绑定活动试行一个月后，周销售额自报上升了两成（无对照组）。\n"
    "该机制依赖已有知识对象而不是单纯的时间提醒。\n"
    "书单绑定的适用前提是卡片网络已经建立。\n"
)
Q_DEF = "回顾触发器必须绑定到已经存在的卡片上。"
Q_SALES = "书单绑定活动试行一个月后，周销售额自报上升了两成（无对照组）。"
Q_MECH = "该机制依赖已有知识对象而不是单纯的时间提醒。"
Q_COND = "书单绑定的适用前提是卡片网络已经建立。"
Q_STAT = "绑定回顾触发器的卡片30天后再访问率自报约62%（未独立核实）。"
SRC_STATEMENT = "回顾触发器必须绑定到已经存在的卡片上"


def make_cfg(root, mode=None):
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    cfg["knowledge_base"] = str(root)
    cfg["state_file"] = str(root / ".state.json")
    for key, filename in {
        "plans_dir": "plans", "runs_dir": "runs",
        "processed_index": "processed-index.json",
        "manual_review_queue": "manual-review/queue.jsonl",
        "backup_dir": "backups", "operation_log": "operation-log.jsonl",
    }.items():
        cfg["safety"][key] = str(root / ".openclaw" / filename)
    cfg["llm"]["api_key_env"] = "STEWARD_TEST_UNUSED_KEY"
    if mode:
        cfg["card_pipeline"] = {"mode": mode}
    return cfg


def write_raw(root):
    target = root / RAW_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(RAW_TEXT, encoding="utf-8")
    return target


# -- provider boundary stubs -------------------------------------------------
def judgment(statement, quote, kind="fact"):
    return {"statement": statement, "kind": kind, "confidence": "medium",
            "evidence": [{"source": RAW_REL, "quote": quote, "relation": "supports"}]}


def source_answer():
    return json.dumps({
        "summary": "合成资料摘要",
        "key_statements": [{"text": SRC_STATEMENT, "quote": Q_DEF, "kind": "assertion"}],
        "topics": [{"title": "回顾触发器", "content": "围绕回顾触发器的研究框架"}],
        "limitations": ["合成限制：结论未经独立核实"],
        "quality_flags": [],
    }, ensure_ascii=False)


def concept_response():
    def_claim = "回顾触发器必须引用已存在的卡片或问题，而非单纯时间点"
    boundary = "来源把回顾触发器与定时提醒区分：定时提醒只依赖时间"
    return {
        "concept_found": True,
        "concepts": [{
            "name": "回顾触发器",
            "aliases": [],
            "definition_claim": def_claim,
            "explanation": "来源将其与普通日历提醒区分开：它必须引用已存在的卡片或问题。",
            "confidence": "medium",
            "source_defined_boundary": [{"evidence_claim": boundary}],
            "suggested_interpretation": [],
            "judgments": [
                judgment(def_claim, Q_DEF),
                judgment(boundary, Q_MECH),
            ],
            "related": [], "pending_paths": [],
        }],
        "provenance_map": [{"rel": RAW_REL, "provenance": "合成概念素材",
                            "limitations": ["数字为自报，未独立核对"]}],
        "shared_provenance": [],
    }


def concept_zero_response():
    return {"concept_found": False, "reason": "来源中没有可独立成立的概念"}


CASE_MECH = "书单绑定依赖已建立的卡片网络，是回顾触发器的具体应用"
CASE_INF = "该机制起效可能依赖卡片间的相互引用而非清单本身"


def case_response():
    sales = "书单绑定活动试行一个月后，周销售额自报上升了两成（无对照组）"
    return {
        "case_found": True,
        "cases": [{
            "title": "青梧书店书单绑定活动（合成案例）",
            "card_level": "project",
            "confidence": "medium",
            "context": "青梧书店（合成）在周末读书会试行书单绑定活动。",
            "action": "店主讲完后把当期主题三本书列成书单现场提供。",
            "result": {"figures": [{"claim": sales}]},
            "reusable_mechanism_claim": CASE_MECH,
            "mechanism_inference_claim": CASE_INF,
            "applicability": {
                "conditions": [{"claim": "书单绑定的适用前提是卡片网络已经建立"}],
                "uncertainties": ["无对照组，上升两成是否归因于活动待研究"],
            },
            "judgments": [
                judgment(sales, Q_SALES),
                judgment(CASE_MECH, Q_MECH),
                judgment("书单绑定的适用前提是卡片网络已经建立", Q_COND),
                judgment(CASE_INF, Q_STAT, kind="inference"),
            ],
            "related": [], "pending_paths": [],
        }],
        "provenance_map": [{"rel": RAW_REL, "provenance": "店主自报台账（合成）",
                            "limitations": ["无对照组", "数字未核实"]}],
        "shared_provenance": [],
    }


def make_dispatcher(*, concept=None, case=None, source=None, topic=None):
    """Provider boundary stub: dispatch by payload task; records every call."""
    calls = []

    def provider(cfg, system_prompt, payload):
        calls.append(payload)
        if isinstance(payload, dict) and payload.get("task") == "concept_extraction":
            value = concept if concept is not None else concept_response()
            if isinstance(value, BaseException):
                raise value
            return json.dumps(value, ensure_ascii=False)
        if isinstance(payload, dict) and payload.get("task") == "case_extraction":
            value = case if case is not None else case_response()
            if isinstance(value, BaseException):
                raise value
            return json.dumps(value, ensure_ascii=False)
        if isinstance(payload, dict) and payload.get("task") == "question_led_topic_synthesis":
            if isinstance(topic, BaseException):
                raise topic
            if callable(topic):
                return topic(payload)
            if topic is not None:
                return json.dumps(topic, ensure_ascii=False)
            from tests import public_round_support as round_support
            return round_support.topic_response(payload)
        return source() if callable(source) else source_answer()

    provider.calls = calls
    return provider


# -- real producer path ------------------------------------------------------
def compile_source_card(root, cfg):
    """Run the REAL topic-research-compile executor once and persist its page."""
    from core.skill_executor import execute_skill
    raw_bytes = (root / RAW_REL).read_bytes()
    note = {"rel": RAW_REL, "title": "合成文档", "body": raw_bytes.decode("utf-8"),
            "metadata": {"material_kind": "synthetic"},
            "source_text": raw_bytes.decode("utf-8"),
            "source_sha256": hashlib.sha256(raw_bytes).hexdigest()}
    with patch("core.llm.call_chat_completion", make_dispatcher()):
        result = execute_skill(ROOT, "topic-research-compile",
                               {"config": cfg, "notes": [note], "use_llm": True})
    pages = result.get("created") or []
    assert pages, result.get("issues")
    page = pages[0]
    target = root / page["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page["content"], encoding="utf-8")
    return target.relative_to(root).as_posix()


def build_init_plan(cfg, *, use_llm=True, providers=None):
    return steward.build_initialization_plan(
        cfg, plan_run_id=steward.run_id(), stamp=steward.stamp(),
        executor_plan_fn=steward.mvp_executor_plan,
        page_requires_manual_review=steward.page_requires_manual_review,
        duplicate_page_targets=steward.duplicate_page_targets,
        page_has_blocked_placeholder=steward.page_has_blocked_placeholder,
        planned_raw_coverage=steward.planned_raw_coverage,
        batch_size=6, use_llm=use_llm, discover_providers=providers)


def apply_through_review(cfg, plan, rid):
    """Actual saved-plan -> review approve -> review apply-approved -> apply."""
    plan["run_id"] = rid
    path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        if item.get("run_id") == rid:
            assert steward.command_review(cfg, SimpleNamespace(
                review_command="approve", id=item["id"], reason="fixture")) == 0
    return steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id=rid))


def card_state_of(path):
    meta, _ = parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    return meta


def raw_documents(root):
    raw = (root / RAW_REL).read_bytes()
    return [{"path": RAW_REL, "content": raw.decode("utf-8"),
             "sha256": hashlib.sha256(raw).hexdigest()}]


@pytest.fixture
def vault(tmp_path):
    root = tmp_path
    cfg = make_cfg(root)
    write_raw(root)
    return root, cfg


# ---------------------------------------------------------------------------
# 1. actual two-phase workflow: init -> review/apply sources; init -> discovery
#    -> review/apply concept/case; reload claims; pins; originals unchanged
# ---------------------------------------------------------------------------
def test_two_phase_workflow_with_real_apply(vault):
    root, cfg = vault
    raw_before = (root / RAW_REL).read_bytes()

    # Phase 1: discovery discloses no eligible persisted sources; the only
    # generation is the source compile of the pending raw batch.
    dispatcher1 = make_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher1):
        plan1 = build_init_plan(cfg, providers={"concept": dispatcher1, "case": dispatcher1})
    stages1 = {a["stage"]: a for a in plan1["actions"] if a.get("stage", "").endswith("_generation")}
    assert set(stages1) == {"concept_generation", "case_generation", "topic_generation"}
    assert stages1["concept_generation"]["state"] == "blocked"
    assert stages1["concept_generation"]["reason"] == "no_eligible_sources"
    assert stages1["case_generation"]["state"] == "blocked"
    # topic: the question-config gate precedes the input gate — with no
    # configured topic_questions the stage is disabled/not_configured and
    # makes no provider call, even before any source exists.
    assert stages1["topic_generation"]["state"] == "disabled"
    assert stages1["topic_generation"]["reason"] == "not_configured"
    assert stages1["topic_generation"]["provider_calls"] == 0
    assert not [p for p in plan1["planned_pages"] if p.get("origin", {}).get("promotion") == "typed_card_pipeline"]
    assert any(a.get("stage") == "source_compile" for a in plan1["actions"])
    assert apply_through_review(cfg, plan1, "run-a1") == 0
    source_cards = list((root / "wiki" / "sources").glob("*.md"))
    assert len(source_cards) == 1

    # Phase 2: subsequent init discovers concept/case from the persisted,
    # applied source card — exactly ONE provider call per kind.
    dispatcher2 = make_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher2):
        plan2 = build_init_plan(cfg, providers={"concept": dispatcher2, "case": dispatcher2})
    concept_pages = [p for p in plan2["planned_pages"] if p["rel_path"].startswith("wiki/concepts/")]
    case_pages = [p for p in plan2["planned_pages"] if p["rel_path"].startswith("wiki/cases/")]
    assert len(concept_pages) == 1 and len(case_pages) == 1
    generation_calls = [c for c in dispatcher2.calls if isinstance(c, dict) and "task" in c]
    assert len(generation_calls) == 2, "one bounded call per kind, no extra requests"
    source_stage2 = next(a for a in plan2["actions"] if a.get("stage") == "source_compile")
    assert source_stage2["outcome"] == "no_inputs"
    assert source_stage2["provider_calls"] == 0, "applied source must not be recompiled"
    assert apply_through_review(cfg, plan2, "run-a2") == 0

    # reload BOTH compiled claims against the original snapshots
    for page, card_type in ((concept_pages[0], "concept-page"),
                            (case_pages[0], "case-story")):
        meta = card_state_of(root / page["rel_path"])
        state = meta["card_state"]
        assert state["version"] == 1 and state["type"] == card_type
        claims = read_claims(state)
        assert claims, page["rel_path"]
        assert validate_claims(state, raw_documents(root)) == claims
        # BOTH original bytes AND the upstream source-card snapshot are pinned
        pins = page["retrieval_source_hashes"]
        assert pins[RAW_REL] == hashlib.sha256(raw_before).hexdigest()
        card_rel = source_cards[0].relative_to(root).as_posix()
        assert pins[card_rel] == hashlib.sha256(source_cards[0].read_bytes()).hexdigest()
        # no dangling wikilinks in applied pages
        for target in extract_wikilinks((root / page["rel_path"]).read_text(encoding="utf-8")):
            assert (root / target).exists() or target in meta.get("sources", []), target
    # Chinese content intact; originals byte-identical
    assert "回顾触发器" in (root / concept_pages[0]["rel_path"]).read_text(encoding="utf-8")
    assert (root / RAW_REL).read_bytes() == raw_before


def test_finalize_discovers_from_cumulative_sources(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    dispatcher = make_dispatcher()
    plan = steward.make_finalize_plan(cfg, plan_run_id="fin-1", stamp=steward.stamp(),
                                      providers={"concept": dispatcher, "case": dispatcher})
    assert plan["entry"] == "finalize_kb"
    dirs = {p["rel_path"].split("/")[1] for p in plan["planned_pages"]}
    assert {"concepts", "cases"} <= dirs
    assert plan["plan_quality"]["eligible_sources"] == 1


# ---------------------------------------------------------------------------
# 2. single-source allowed; zero/disabled/error distinct and truthful
# ---------------------------------------------------------------------------
def test_single_source_zero_disabled_error_distinct(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)

    zero_dispatcher = make_dispatcher(concept=concept_zero_response())
    case_dispatcher = make_dispatcher()
    out = discover_cards(index, cfg, run_id="x", use_llm=True,
                         providers={"concept": zero_dispatcher, "case": case_dispatcher})
    assert out["stages"]["concept"]["state"] == "zero"
    assert out["stages"]["concept"]["reason"] == "zero_output"
    assert out["stages"]["concept"]["provider_calls"] == 1
    assert len(zero_dispatcher.calls) == 1
    assert out["stages"]["case"]["state"] == "full"
    assert out["stages"]["case"]["provider_calls"] == 1
    assert len(case_dispatcher.calls) == 1
    assert len(out["planned_pages"]) == 1  # single-source case is legitimate

    disabled_dispatcher = make_dispatcher()
    out = discover_cards(index, cfg, run_id="x", use_llm=False,
                         providers={"concept": disabled_dispatcher, "case": disabled_dispatcher})
    assert out["stages"]["concept"]["state"] == "disabled"
    assert out["stages"]["case"]["state"] == "disabled"
    assert out["stages"]["case"]["reason"] == "not_configured"
    assert out["stages"]["case"]["provider_calls"] == 0
    assert disabled_dispatcher.calls == [], "no-model must not touch the provider"
    assert out["planned_pages"] == []

    raising_dispatcher = make_dispatcher(case=RuntimeError("模型调用失败"))
    out = discover_cards(index, cfg, run_id="x", use_llm=True,
                         providers={"concept": make_dispatcher(),
                                    "case": raising_dispatcher})
    assert out["stages"]["concept"]["state"] == "full"
    assert out["stages"]["case"]["state"] == "error"
    assert out["stages"]["case"]["reason"] == "model_error"
    assert out["stages"]["case"]["provider_calls"] == 1
    assert len(raising_dispatcher.calls) == 1, "a raising attempt counts as a call"
    assert not [p for p in out["planned_pages"] if p["rel_path"].startswith("wiki/cases/")]


def test_preflight_blocks_count_zero_calls_and_pre_call_reason(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)
    tight = dict(cfg)
    tight["case_generation"] = {"max_context_chars": 10}
    dispatcher = make_dispatcher()
    out = discover_cards(index, tight, run_id="x", use_llm=True,
                         providers={"concept": make_dispatcher(), "case": dispatcher})
    assert out["stages"]["case"]["state"] == "blocked"
    assert out["stages"]["case"]["reason"] == "oversize_input_deferred"
    assert out["stages"]["case"]["provider_calls"] == 0
    assert dispatcher.calls == [], "budget refusal happens before the call"


# ---------------------------------------------------------------------------
# 3. changed original / changed upstream card blocks discovery
# ---------------------------------------------------------------------------
def test_changed_original_or_card_blocks_discovery(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)

    (root / RAW_REL).write_text(RAW_TEXT + "\n追加的新句子。\n", encoding="utf-8")
    out = discover_cards(build_index(cfg), cfg, run_id="x",
                         providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    assert out["eligible_sources"] == 0
    assert out["stages"]["concept"]["state"] == "blocked"
    assert out["stages"]["case"]["state"] == "blocked"
    assert out["planned_pages"] == []

    # changed upstream source-card snapshot against the captured index
    (root / RAW_REL).write_text(RAW_TEXT, encoding="utf-8")
    stale_card_index = build_index(cfg)
    card = next(rel for rel in stale_card_index.by_rel if rel.startswith("wiki/sources/"))
    path = root / card
    path.write_bytes(path.read_bytes() + "\n卡片被篡改。\n".encode("utf-8"))
    out = discover_cards(stale_card_index, cfg, run_id="x",
                         providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    assert out["eligible_sources"] == 0
    assert any("来源卡自身快照" in r["reason"] for r in out["rejected_sources"])


# ---------------------------------------------------------------------------
# 4. reject one candidate, accept the other: no dangling sibling links.
#    ACCURACY LABEL: this is SEPARATE-RUN isolation (two plans, two runs).
#    Same-plan partial approve/reject has separate subset integration tests.
# ---------------------------------------------------------------------------
def test_reject_one_candidate_leaves_no_dangling_links(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)
    dispatcher = make_dispatcher()

    concept_out = discover_cards(index, cfg, run_id="r-con", use_llm=True,
                                 kinds=("concept",), providers={"concept": dispatcher})
    case_out = discover_cards(index, cfg, run_id="r-case", use_llm=True,
                              kinds=("case",), providers={"case": dispatcher})

    def minimal_plan(out, rid):
        return {"run_id": rid, "entry": "finalize_kb", "task": "typed candidate",
                "primary_skill": "kb-finalize",
                "planned_pages": out["planned_pages"],
                "manual_review": [{"type": "planned_pages_require_review",
                                   "risk": "medium", "reason": "候选页需人工裁决"}]}
    for out, rid in ((concept_out, "r-con"), (case_out, "r-case")):
        plan = minimal_plan(out, rid)
        steward.write_execution_plan(cfg, plan)  # persisted plan (binds ids)
        steward.write_manual_review_queue(cfg, plan)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        command = "reject" if item.get("run_id") == "r-con" else "approve"
        assert steward.command_review(cfg, SimpleNamespace(
            review_command=command, id=item["id"], reason="fixture")) == 0
    # Fully rejected run is a terminal no-write outcome; sibling applies.
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id="r-con")) == 0
    assert all(item["status"] == "rejected" for item in
               steward.load_queue(steward.review_queue_path(cfg))
               if item.get("run_id") == "r-con")
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id="r-case")) == 0
    assert not [p for p in (root / "wiki" / "concepts").glob("*.md")
                if p.name != "README.md"]
    applied = [p for p in (root / "wiki" / "cases").glob("*.md") if p.name != "README.md"]
    assert len(applied) == 1
    for target in extract_wikilinks(applied[0].read_text(encoding="utf-8")):
        assert (root / target).exists(), f"dangling link: {target}"


# ---------------------------------------------------------------------------
# 5. case skill uses the same generator; typed skills get no second runtime
# ---------------------------------------------------------------------------
def test_case_skill_uses_shared_generator(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)
    dispatcher = make_dispatcher()
    result = steward.mvp_executor_plan(index, cfg, "案例库", "case-story-bank-builder",
                                       [], {}, "case-run", use_llm=True,
                                       providers={"case": dispatcher})
    assert len(result["planned_pages"]) == 1
    assert result["planned_pages"][0]["rel_path"].startswith("wiki/cases/")
    assert result["planned_pages"][0]["skill"] == "case-story-bank-builder"
    assert len(dispatcher.calls) == 1, "exactly ONE case generator call"
    # stage outcome is preserved through mvp dispatch, not dropped
    assert result["stages"]["case"]["provider_calls"] == 1
    assert result["stages"]["case"]["state"] == "full"


def test_typed_producers_call_provider_once_and_generic_runtime_never(vault):
    root, cfg = vault
    write_raw(root)
    (root / "quicknote").mkdir(exist_ok=True)
    (root / "quicknote").mkdir(exist_ok=True)
    (root / "quicknote" / "idea.md").write_text(
        "# 一个想法\n应先核对来源，再生长为 seed。#seed", encoding="utf-8")
    typed_calls = []

    def typed_provider(cfg, system_prompt, payload):
        typed_calls.append(payload)
        return "这不是合法的模型输出"  # malformed is fine: the CALL is what counts

    with patch("core.llm.call_chat_completion", side_effect=typed_provider), \
            patch.object(steward, "run_skill_runtime",
                         side_effect=AssertionError("generic runtime fired")):
        plan = steward.make_execution_plan(cfg, "整理知识库", use_llm=True)
    assert typed_calls, "typed producers (seed/source) must make real provider calls"
    # one authority per typed skill: seed via executor, source compile via executor
    assert plan.get("llm_runtime") is None


def test_seed_generation_topic_mode_retains_legacy_runtime(vault):
    root, cfg = vault
    cfg["seed_generation"] = {"mode": "topic"}
    write_raw(root)
    (root / "quicknote").mkdir(exist_ok=True)
    (root / "quicknote" / "idea.md").write_text("# 一个想法\n应先核对来源。#seed", encoding="utf-8")
    with patch.object(steward, "run_skill_runtime",
                      return_value={"items": [], "issues": [], "ok": True}) as runtime:
        plan = steward.make_execution_plan(cfg, "整理知识库", use_llm=True)
    # Explicit legacy behavior retained: mode=topic still lets the generic
    # runtime run for mindseed, as before A2.
    assert runtime.call_count == 1


def test_case_generation_routes_via_task_command(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    sentinel = make_dispatcher()
    with patch("core.llm.call_chat_completion", sentinel):
        plan = steward.make_execution_plan(cfg, "生成案例卡", use_llm=True)
    assert plan["primary_skill"] == "case-story-bank-builder"
    case_pages = [p for p in plan["planned_pages"] if p["rel_path"].startswith("wiki/cases/")]
    assert len(case_pages) == 1
    stage_actions = [a for a in plan["actions"] if a.get("stage") == "case_generation"]
    assert stage_actions and stage_actions[0]["provider_calls"] == 1
    assert len(sentinel.calls) == 1


def test_case_command_observable_without_llm_or_sources(vault):
    root, cfg = vault
    write_raw(root)
    compile_source_card(root, cfg)
    dispatcher = make_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher):
        plan = steward.make_execution_plan(cfg, "生成案例卡", use_llm=False)
    stage_actions = [a for a in plan["actions"] if a.get("stage") == "case_generation"]
    assert stage_actions, "stage outcome must be visible with no pages"
    assert stage_actions[0]["state"] == "disabled"
    assert stage_actions[0]["provider_calls"] == 0
    assert plan["planned_pages"] == []
    # and with no eligible persisted sources at all
    empty_root_cfg = make_cfg(root.parent / "case-empty-vault")
    (root.parent / "case-empty-vault" / "raw").mkdir(parents=True, exist_ok=True)
    plan2 = steward.make_execution_plan(empty_root_cfg, "生成案例卡", use_llm=True)
    stage2 = [a for a in plan2["actions"] if a.get("stage") == "case_generation"]
    assert stage2 and stage2[0]["state"] == "blocked"
    assert stage2[0]["reason"] == "no_eligible_sources"


def test_route_keywords_order_and_no_regressions():
    from core.router import route_item, load_router
    router = load_router()
    assert route_item("生成案例卡", router)["entry"] == "case_bank"
    # specific case request wins over the generic work-memory '项目' keyword
    assert route_item("生成项目案例卡", router)["entry"] == "case_bank"
    # healthcheck keeps priority over case keywords (root regression):
    # '检查案例卡质量' must route to healthcheck, not case_bank
    assert route_item("检查案例卡质量", router)["entry"] == "healthcheck"
    from core.router import route
    assert route("检查案例卡质量") == "kb-lint-healthcheck"
    assert route_item("生成案例卡", router)["primary_skill"] == "case-story-bank-builder"
    # generic flows unchanged
    assert route_item("项目复盘", router)["entry"] == "weave_work_memory"
    assert route_item("准备写作素材", router)["entry"] == "prepare_writing"
    assert route_item("整理知识库", router)["entry"] == "organize_kb"
    assert route_item("发现选题", router)["entry"] == "discover_topics"


# ---------------------------------------------------------------------------
# 6. config seam + collision surfacing
# ---------------------------------------------------------------------------
def test_card_pipeline_mode_seam():
    assert card_pipeline_mode({}) == "typed"
    assert card_pipeline_mode({"card_pipeline": {"mode": "legacy"}}) == "legacy"
    assert card_pipeline_mode({"card_pipeline": {}}) == "typed"
    with pytest.raises(ValueError):
        card_pipeline_mode({"card_pipeline": {"mode": "both"}})
    with pytest.raises(ValueError):
        card_pipeline_mode({"card_pipeline": "legacy"})


def test_existing_target_is_explicit_collision_not_silent_success(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)
    first = discover_cards(index, cfg, run_id="c1",
                           providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    assert len(first["planned_pages"]) == 2
    case_page = next(p for p in first["planned_pages"] if p["rel_path"].startswith("wiki/cases/"))
    target = root / case_page["rel_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(case_page["content"], encoding="utf-8")
    second = discover_cards(build_index(cfg), cfg, run_id="c2",
                            providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    assert second["stages"]["case"]["collisions"] == [case_page["rel_path"]]
    assert any("需人工确认身份" in issue for issue in second["issues"])
    assert not [p for p in second["planned_pages"] if p["rel_path"] == case_page["rel_path"]]


# ---------------------------------------------------------------------------
# A2 review corrections: bounded retriever context, item retention, pins
# ---------------------------------------------------------------------------
def test_planned_page_retains_exact_item(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    out = discover_cards(build_index(cfg), cfg, run_id="x",
                         providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    for page in out["planned_pages"]:
        assert isinstance(page.get("item"), dict), "exact candidate must be retained"
    concept_page = next(p for p in out["planned_pages"] if p["rel_path"].startswith("wiki/concepts/"))
    assert concept_page["item"]["concept_name"] == "回顾触发器"
    case_page = next(p for p in out["planned_pages"] if p["rel_path"].startswith("wiki/cases/"))
    assert case_page["item"]["title"] == "青梧书店书单绑定活动（合成案例）"


def test_unrelated_notes_never_reach_the_model(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    # 35 irrelevant notes that must NOT be sent as related candidates
    unrelated_dir = root / "wiki" / "topics"
    unrelated_dir.mkdir(parents=True, exist_ok=True)
    for i in range(35):
        (unrelated_dir / f"无关资料{i:02d}.md").write_text(
            f"# 无关资料{i}\n\n民国摄影史与陶冷月画册出版研究资料，与本书店案例无关。\n",
            encoding="utf-8")
    index = build_index(cfg)
    dispatcher = make_dispatcher()
    out = discover_cards(index, cfg, run_id="x",
                         providers={"concept": dispatcher, "case": dispatcher})
    cap = cfg.get("card_pipeline", {}).get("related_paths_cap", 6)
    for payload in dispatcher.calls:
        sent_known = payload.get("known_paths", [])
        assert len(sent_known) <= cap, "bounded candidate cap must hold on a large index"
        assert not any(p.startswith("wiki/topics/无关资料") for p in sent_known)
        # documents are exactly the eligible originals, never the whole vault
        assert [d["path"] for d in payload["documents"]] == [RAW_REL]
    assert out["related_candidates"] == out["stages"]["concept"]["related_candidates"]
    assert out["stages"]["case"]["retrieval"] is not None, "actual search report disclosed"
    # stage outcomes are consistent even when nothing is linked
    assert out["stages"]["case"]["state"] == "full"


def compile_second_source_card(root, cfg, second_rel="raw/second.md"):
    from core.skill_executor import execute_skill
    second_text = "# 第二份合成文档\n\n第二份资料记录了青梧书店读书会的第二次复用尝试。\n"
    target = root / second_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes: keep the exact bytes that the snapshot hash covers (no
    # Windows newline translation).
    target.write_bytes(second_text.encode("utf-8"))
    note = {"rel": second_rel, "title": "第二份合成文档", "body": second_text,
            "metadata": {}, "source_text": second_text,
            "source_sha256": hashlib.sha256(second_text.encode("utf-8")).hexdigest()}
    with patch("core.llm.call_chat_completion", make_dispatcher(
            source=lambda: json.dumps({
                "summary": "第二份资料摘要",
                "key_statements": [{"text": "第二份资料记录了青梧书店读书会的第二次复用尝试",
                                    "quote": "第二份资料记录了青梧书店读书会的第二次复用尝试。",
                                    "kind": "assertion"}],
                "topics": [], "limitations": ["合成限制B"], "quality_flags": [],
            }, ensure_ascii=False))):
        result = execute_skill_path(ROOT, "topic-research-compile",
                                    {"config": cfg, "notes": [note], "use_llm": True})
    pages = result.get("created") or []
    assert pages, result.get("issues")
    page = pages[0]
    path = root / (page["target"].replace(".md", "-second.md"))
    path.write_text(page["content"], encoding="utf-8")
    return path.relative_to(root).as_posix()


def execute_skill_path(root, skill, context):
    from core.skill_executor import execute_skill
    return execute_skill(root, skill, context)


def test_plan_applies_then_changed_original_blocks_apply_before_any_write(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    second_card = compile_second_source_card(root, cfg)
    index = build_index(cfg)
    out = discover_cards(index, cfg, run_id="pin-1",
                         providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    assert out["eligible_sources"] == 2, out["rejected_sources"]
    # The case cites only raw/doc.md, but BOTH originals and both cards were
    # supplied to the model and must be pinned in the dependency set.
    case_page = next(p for p in out["planned_pages"] if p["rel_path"].startswith("wiki/cases/"))
    pins = case_page["retrieval_source_hashes"]
    assert "raw/second.md" in pins, "supplied-but-uncited original is still pinned"
    assert second_card in pins and len(pins) >= 4
    # cited-only fields stay limited to actual cited evidence
    assert case_page["sources"] == [RAW_REL]
    assert case_page["item"]["source_hashes"] == {RAW_REL: pins[RAW_REL]}

    # genuine save-reviewed-plan -> mutate original -> apply-approved must be
    # rejected BEFORE any write; the deliberate test mutation is retained and
    # the queue is not falsely marked applied.
    plan = {"run_id": "pin-1", "entry": "finalize_kb", "task": "pin check",
            "primary_skill": "kb-finalize", "planned_pages": out["planned_pages"],
            "manual_review": [{"type": "planned_pages_require_review",
                               "risk": "medium", "reason": "候选页需人工裁决"}]}
    assert steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        assert steward.command_review(cfg, SimpleNamespace(
            review_command="approve", id=item["id"], reason="fixture")) == 0
    second_original = root / "raw" / "second.md"
    second_original.write_text(second_original.read_text(encoding="utf-8") + "\n计划保存后追加。\n",
                               encoding="utf-8")
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id="pin-1")) == 1
    assert not (root / case_page["rel_path"]).exists(), "rejected before ANY write"
    assert "计划保存后追加" in second_original.read_text(encoding="utf-8"), "mutation retained"
    items = steward.load_queue(steward.review_queue_path(cfg))
    assert all(i.get("status") != "applied" for i in items if i.get("run_id") == "pin-1")


def test_plan_applies_then_changed_upstream_card_blocks_apply(vault):
    root, cfg = vault
    compile_source_card(root, cfg)
    index = build_index(cfg)
    out = discover_cards(index, cfg, run_id="pin-2",
                         providers={"concept": make_dispatcher(), "case": make_dispatcher()})
    plan = {"run_id": "pin-2", "entry": "finalize_kb", "task": "pin check",
            "primary_skill": "kb-finalize", "planned_pages": out["planned_pages"],
            "manual_review": [{"type": "planned_pages_require_review",
                               "risk": "medium", "reason": "候选页需人工裁决"}]}
    assert steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    for item in steward.load_queue(steward.review_queue_path(cfg)):
        assert steward.command_review(cfg, SimpleNamespace(
            review_command="approve", id=item["id"], reason="fixture")) == 0
    card = next(p for p in (root / "wiki" / "sources").glob("*.md") if p.name != "README.md")
    card.write_bytes(card.read_bytes() + "\n卡片被篡改。\n".encode("utf-8"))
    assert steward.command_review(cfg, SimpleNamespace(
        review_command="apply-approved", run_id="pin-2")) == 1
    assert not [p for p in (root / "wiki" / "cases").glob("*.md") if p.name != "README.md"]


# ---------------------------------------------------------------------------
# B1a: topic joins the typed pipeline (question seam, bounded selection,
# truthful stage envelopes). Canonical public three-case family; provider =
# tests/public_round_support offline mock (never expected annotations).
# ---------------------------------------------------------------------------
import tests.public_round_support as round_support


def compile_case_family_cards(root, cfg, log=None, only=None):
    """Persist REAL source cards through plan -> save -> review -> apply."""
    provider = round_support.make_offline_provider(log or round_support.CallLog())
    cards = {}
    for fid, rel in round_support.ROUND_SOURCES.items():
        if rel not in round_support.CASE_FAMILY:
            continue
        if only is not None and fid not in only:
            continue
        fix = round_support.load_fixture(fid)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fix["text"].encode("utf-8"))
        index = build_index(cfg)
        note = index.by_rel[rel]
        with patch("core.llm.call_chat_completion", provider):
            result = steward.mvp_executor_plan(
                index, cfg, "source card compilation", "topic-research-compile",
                [note], {}, f"source-{fid}", use_llm=True)
        run = f"source-{fid}"
        pages = result.get("planned_pages", [])
        assert pages, result.get("issues")
        source_plan = {
            "run_id": run,
            "entry": "init_kb",
            "task": "source card compilation",
            "primary_skill": "topic-research-compile",
            "planned_pages": pages,
            "manual_review": [{"type": "source_card_review", "risk": "medium",
                               "reason": "fixture source card review"}],
        }
        assert apply_through_review(cfg, source_plan, run) == 0
        cards[rel] = pages[0]["target"]
    return cards


def topic_cfg(cfg, question=None):
    typed = dict(cfg)
    section = dict(typed.get("card_pipeline") or {})
    section["topic_questions"] = [question] if question else []
    typed["card_pipeline"] = section
    return typed


def test_topic_full_round_discovery_apply_and_reload(vault):
    root, cfg = vault
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    cards = compile_case_family_cards(root, typed)
    assert len(cards) == 3
    originals_before = {rel: (root / rel).read_bytes() for rel in cards}
    log = round_support.CallLog()
    provider = round_support.make_offline_provider(log)
    out = discover_cards(build_index(typed), typed, run_id="t1",
                         providers={"concept": provider, "case": provider,
                                    "topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "full"
    assert stage["provider_calls"] == 1
    assert stage["question"] == round_support.ROUND_QUESTION
    assert stage["question_source"] == "configured"
    assert log.stage_count("topic:") == 1
    topic_pages = [p for p in out["planned_pages"] if p["rel_path"].startswith("wiki/topics/")]
    assert len(topic_pages) == 1
    page = topic_pages[0]
    assert page["item"]["research_question"] == round_support.ROUND_QUESTION
    # >=3 genuinely cited originals for a full topic; all supplied deps pinned
    page_meta, _ = parse_frontmatter(page["content"])
    assert len(page_meta["card_state"]["analysis"]["usable_sources"]) == 3
    pins = page["retrieval_source_hashes"]
    for rel in cards:
        assert pins[rel] == hashlib.sha256((root / rel).read_bytes()).hexdigest()
        assert pins[cards[rel]] == hashlib.sha256((root / cards[rel]).read_bytes()).hexdigest()
    # actual saved plan -> review -> apply
    plan = {"run_id": "topic-1", "entry": "finalize_kb", "task": "topic discovery",
            "primary_skill": "kb-finalize", "planned_pages": [page],
            "manual_review": [{"type": "planned_pages_require_review",
                               "risk": "medium", "reason": "候选页需人工裁决"}]}
    assert apply_through_review(cfg, plan, "topic-1") == 0
    applied = root / page["rel_path"]
    meta = card_state_of(applied)
    state = meta["card_state"]
    assert state["version"] == 1 and state["type"] == "topic-page"
    claims = read_claims(state)
    assert claims
    documents = [{"path": rel, "content": (root / rel).read_bytes().decode("utf-8"),
                  "sha256": hashlib.sha256((root / rel).read_bytes()).hexdigest()}
                 for rel in cards]
    assert validate_claims(state, documents) == claims
    for rel, before in originals_before.items():
        assert (root / rel).read_bytes() == before, "originals byte-identical"


def test_source_update_runs_through_production_prepare_and_preserves_identity(vault):
    """Source create/update/noop uses the real executor and plan gates."""
    from core.card_pipeline import collect_eligible_sources

    root, cfg = vault

    def source_plan(run):
        index = build_index(cfg)
        with patch("core.llm.call_chat_completion", make_dispatcher()):
            return steward.mvp_executor_plan(
                index, cfg, "source version", "topic-research-compile",
                [index.by_rel[RAW_REL]], {}, run, use_llm=True)

    first = source_plan("source-b1b-create")
    assert first["planned_pages"]
    assert first["typed_update_outcomes"][0]["outcome"] == "create"
    assert first["input_outcomes"][0]["updater_disposition"] == "create"
    assert first["input_outcomes"][0]["required_targets"] == [first["planned_pages"][0]["target"]]
    source_rel = first["planned_pages"][0]["rel_path"]
    assert apply_through_review(cfg, {
        "run_id": "source-b1b-create", "entry": "init_kb",
        "task": "source create", "primary_skill": "topic-research-compile",
        "planned_pages": first["planned_pages"],
        "manual_review": [{"type": "source_review", "risk": "medium", "reason": "fixture"}],
    }, "source-b1b-create") == 0
    created = card_state_of(root / source_rel)
    object_id, revision = created["object_id"], int(created["revision"])
    old_hash = hashlib.sha256((root / RAW_REL).read_bytes()).hexdigest()

    raw = root / RAW_REL
    raw.write_bytes(raw.read_bytes() + "\n新增版本段落：该段只用于验证来源版本更新。\n".encode("utf-8"))
    second = source_plan("source-b1b-update")
    assert second["typed_update_outcomes"][0]["outcome"] == "update"
    assert second["input_outcomes"][0]["updater_disposition"] == "update"
    assert second["input_outcomes"][0]["required_targets"] == [source_rel]
    assert second["planned_pages"][0]["operation"] == "update"
    assert apply_through_review(cfg, {
        "run_id": "source-b1b-update", "entry": "init_kb",
        "task": "source update", "primary_skill": "topic-research-compile",
        "planned_pages": second["planned_pages"],
        "manual_review": [{"type": "source_review", "risk": "medium", "reason": "fixture"}],
    }, "source-b1b-update") == 0
    updated = card_state_of(root / source_rel)
    assert (updated["object_id"], int(updated["revision"])) == (object_id, revision + 1)
    new_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert updated["source_hashes"][RAW_REL] == new_hash
    collected = collect_eligible_sources(build_index(cfg), cfg)
    assert collected["rejected"] == []
    assert collected["notes"][0]["source_sha256"] == new_hash

    repeat = source_plan("source-b1b-repeat")
    assert repeat["planned_pages"] == []
    assert repeat["typed_update_outcomes"][0]["outcome"] == "noop"
    assert repeat["input_outcomes"][0]["updater_disposition"] == "noop"
    assert repeat["input_outcomes"][0]["required_targets"] == [source_rel]
    repeat_index = build_index(cfg)
    assert repeat_index.by_rel[source_rel].object_id == object_id
    assert repeat_index.by_rel[source_rel].revision == revision + 1
    assert old_hash != new_hash


def test_source_generator_success_does_not_hide_manual_update_block(vault):
    """A generated source edit blocks the proposal and processing credit."""
    root, cfg = vault

    def source_plan(run):
        index = build_index(cfg)
        with patch("core.llm.call_chat_completion", make_dispatcher()):
            return steward.mvp_executor_plan(
                index, cfg, "source version", "topic-research-compile",
                [index.by_rel[RAW_REL]], {}, run, use_llm=True)

    first = source_plan("source-b1b-block-create")
    source_rel = first["planned_pages"][0]["rel_path"]
    assert apply_through_review(cfg, {
        "run_id": "source-b1b-block-create", "entry": "init_kb",
        "task": "source create", "primary_skill": "topic-research-compile",
        "planned_pages": first["planned_pages"],
        "manual_review": [{"type": "source_review", "risk": "medium", "reason": "fixture"}],
    }, "source-b1b-block-create") == 0
    card = root / source_rel
    text = card.read_text(encoding="utf-8")
    assert "<!-- pks:generated:start -->" in text
    card.write_text(text.replace("<!-- pks:generated:start -->",
                                 "<!-- pks:generated:start -->\n手工编辑生成区，禁止静默覆盖。", 1),
                    encoding="utf-8")

    blocked = source_plan("source-b1b-blocked")
    outcome = blocked["input_outcomes"][0]
    assert blocked["generator_result"]["processed"] == 1
    assert blocked["generator_result"]["planned_pages"][0]["rel_path"] == source_rel
    assert blocked["processed"] == 0
    assert outcome["generator_outcome"] == "ok"
    assert outcome["generator_complete"] is True
    assert outcome["updater_disposition"] == "blocked"
    assert outcome["outcome"] == "blocked"
    assert outcome["complete"] is False
    assert outcome["required_targets"] == [source_rel]
    assert blocked["planned_pages"] == []


def test_typed_update_gate_maps_all_same_batch_targets(vault):
    from core.executor_adapters import prepare_typed_executor_pages

    root, cfg = vault
    target = "wiki/concepts/same-title.md"
    pages = [
        {"rel_path": target, "target": target, "sources": [RAW_REL], "content": "a"},
        {"rel_path": target, "target": target, "sources": [RAW_REL], "content": "b"},
    ]
    outcomes = [
        {"rel_path": target, "chosen_target": "wiki/concepts/same-title-a.md",
         "outcome": "create", "reason": "稳定后缀 a"},
        {"rel_path": target, "chosen_target": "wiki/concepts/same-title-b.md",
         "outcome": "create", "reason": "稳定后缀 b"},
    ]
    result = {
        "processed": 1,
        "input_outcomes": [{"rel": RAW_REL, "outcome": "ok", "complete": True,
                             "targets": [target, target]}],
    }
    with patch("core.typed_card_updates.prepare_typed_updates",
               return_value={"pages": pages, "outcomes": outcomes, "issues": []}):
        accepted = prepare_typed_executor_pages(build_index(cfg), cfg, pages, result)
    outcome = result["input_outcomes"][0]
    assert accepted == pages
    assert outcome["updater_disposition"] == "create"
    assert outcome["required_targets"] == [
        "wiki/concepts/same-title-a.md", "wiki/concepts/same-title-b.md"]
    assert outcome["targets"] == outcome["required_targets"]


def test_topic_no_question_means_not_configured_no_call(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    typed = topic_cfg(cfg, question=None)  # default empty list
    provider = make_dispatcher()
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "disabled"
    assert stage["reason"] == "not_configured"
    assert stage["provider_calls"] == 0
    assert provider.calls == []
    # persisted hints stay clearly-labeled proposals, never auto-sent
    assert stage["proposed_topic_hints"] == out["topic_hints"]


def test_topic_malformed_question_config_rejected_without_call(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    index = build_index(cfg)
    for bad in ("只给了一个字符串", [["嵌套"]], [""], ["问题一", "问题二"], 42):
        provider = make_dispatcher()
        typed = dict(cfg)
        typed["card_pipeline"] = {**cfg["card_pipeline"], "topic_questions": bad}
        out = discover_cards(index, typed, run_id="x", kinds=("topic",),
                             providers={"topic": provider})
        stage = out["stages"]["topic"]
        assert stage["state"] == "error", bad
        assert stage["reason"] == "invalid_topic_question_config"
        assert stage["provider_calls"] == 0
        assert provider.calls == []


def test_topic_impossible_min_sources_no_call(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    typed["topic_generation"] = {"min_full_sources": 0}  # impossible
    provider = make_dispatcher()
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "error"
    assert stage["reason"] == "pre_call_error"
    assert stage["provider_calls"] == 0
    assert provider.calls == []

    # A positive floor can still be impossible when the bounded topic source
    # cap is smaller; this must fail before retrieval can reach the provider.
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    typed["topic_generation"] = {"min_full_sources": 7}
    provider = make_dispatcher()
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "error"
    assert stage["reason"] == "pre_call_error"
    assert stage["provider_calls"] == 0
    assert provider.calls == []


def test_topic_stub_when_fewer_than_min_cited_sources(vault):
    root, cfg = vault
    # only ONE canonical case source persisted
    fid = "project_case_01"
    rel = round_support.ROUND_SOURCES[fid]
    cards = compile_case_family_cards(root, cfg, only={fid})

    # topic response citing ONLY the one supplied source => honest stub
    def single_source_topic_response(payload):
        response = json.loads(round_support.topic_response(payload))
        response["source_map"] = [m for m in response["source_map"] if m["rel"] == rel]
        response["judgments"] = [j for j in response["judgments"]
                                 if all(e["source"] == rel for e in j["evidence"])]
        response["tensions"] = [t for t in response["tensions"]
                                if all(s == rel for s in t["sources"])]
        return json.dumps(response, ensure_ascii=False)

    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    provider = make_dispatcher(topic=single_source_topic_response)
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "stub", stage
    assert stage["reason"] == "partial_input"
    assert stage["planned_items"] == 1
    topic_page = out["planned_pages"][0]
    assert topic_page["item"]["status"] == "manual_review"
    assert topic_page["review_required"] is True
    assert set(topic_page["retrieval_source_hashes"]) >= {rel}


def test_topic_provider_error_is_model_error_with_one_call(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    dispatcher = make_dispatcher(topic=RuntimeError("模型调用失败"))
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": dispatcher})
    stage = out["stages"]["topic"]
    assert stage["state"] == "error"
    assert stage["reason"] == "model_error"
    assert stage["provider_calls"] == 1
    assert out["planned_pages"] == []


def test_topic_no_relevant_selection_is_zero_without_call(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    typed = topic_cfg(cfg, "量子计算机散热架构的可靠性评估如何开展？")
    provider = make_dispatcher()
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": provider})
    stage = out["stages"]["topic"]
    assert stage["state"] == "zero"
    assert stage["reason"] == "no_relevant_sources"
    assert stage["provider_calls"] == 0
    assert provider.calls == []


def test_topic_cap_filters_derived_hits_before_selection(vault):
    root, cfg = vault
    compile_case_family_cards(root, cfg)
    derived = root / "wiki" / "topics" / "derived-match.md"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text(
        "---\ntitle: 青梧书店派生页\ntype: topic-page\nstatus: growing\n"
        "stage: candidate\nsources: []\nreview_required: true\n---\n"
        "青梧书店 分段转化做法。\n",
        encoding="utf-8",
    )
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    typed["card_pipeline"] = {**typed["card_pipeline"], "topic_source_cap": 1}
    typed["topic_generation"] = {"min_full_sources": 1}
    calls = []

    def zero_topic(_cfg, _system, payload):
        calls.append(payload)
        return json.dumps({"topic_viable": False, "reason": "fixture zero"}, ensure_ascii=False)

    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": zero_topic})
    stage = out["stages"]["topic"]
    assert stage["state"] == "zero"
    assert stage["provider_calls"] == 1
    assert len(calls) == 1
    paths = [doc["path"] for doc in calls[0]["documents"]]
    assert len(paths) == 1
    assert paths[0].startswith("raw/")
    assert "wiki/topics/derived-match.md" not in paths
    assert all(hit["path"].startswith("raw/")
               for hit in stage["topic_selection_report"]["hits"])


def test_topic_default_retriever_keeps_eligible_sources_ahead_of_uncompiled_hits(vault):
    from core.derived_index import rebuild

    root, cfg = vault
    compile_case_family_cards(root, cfg)
    for i in range(12):
        (root / "raw" / f"uncompiled-{i}.md").write_text(
            "# " + round_support.ROUND_QUESTION + "\n"
            + round_support.ROUND_QUESTION * 5,
            encoding="utf-8",
        )
    typed = topic_cfg(cfg, round_support.ROUND_QUESTION)
    # Rebuild the SQLite derived index so the regression covers the cache
    # recall boundary as well as newly scanned raw inputs.
    rebuild(typed)
    calls = []

    def zero_topic(_cfg, _system, payload):
        calls.append(payload)
        return json.dumps({"topic_viable": False, "reason": "fixture zero"}, ensure_ascii=False)

    # No injected/fake Retriever: this exercises the production default path.
    out = discover_cards(build_index(typed), typed, run_id="x", kinds=("topic",),
                         providers={"topic": zero_topic})
    stage = out["stages"]["topic"]
    assert stage["state"] == "zero"
    assert stage["provider_calls"] == 1
    assert len(calls) == 1
    assert len(calls[0]["documents"]) == 3
    assert all(doc["path"].startswith("raw/project_case_01")
               for doc in calls[0]["documents"])


def test_executor_stage_preserves_explicit_all_zero(vault):
    from core.card_pipeline import executor_stage

    stage = executor_stage(
        "init_kb", "source_compile", "topic-research-compile",
        {"inputs": ["raw/empty.md"], "processed": 0,
         "input_outcomes": [{"rel": "raw/empty.md", "outcome": "zero",
                              "complete": True}]},
    )
    assert stage["outcome"] == "zero"
    assert stage["outcome_counts"] == {"zero": 1}


def test_initializer_no_inputs_and_finalizer_topic_wording_are_explicit(vault):
    root, cfg = vault
    (root / RAW_REL).unlink()
    plan = build_init_plan(cfg, use_llm=True)
    source = next(a for a in plan["actions"] if a.get("stage") == "source_compile")
    seed = next(a for a in plan["actions"] if a.get("stage") == "seed_cluster")
    assert source["outcome"] == seed["outcome"] == "no_inputs"
    assert source["provider_calls"] == seed["provider_calls"] == 0
    assert source["planned_inputs"] == seed["planned_inputs"] == 0
    assert "没有未处理" in seed["reason_detail"]
    (root / "quicknote").mkdir(exist_ok=True)
    (root / "quicknote" / "idea.md").write_text(
        "# 原子想法\n\n先保留一个可追溯观察。", encoding="utf-8")
    seeded = build_init_plan(cfg, use_llm=False)
    seed_run = next(a for a in seeded["actions"] if a.get("stage") == "seed_cluster")
    assert "原子化" in seed_run["reason"]
    finalized = steward.make_finalize_plan(cfg, plan_run_id="wording", stamp=steward.stamp(),
                                           use_llm=False)
    assert all("专题" in action["pipeline_reason"] for action in finalized["actions"])


def test_source_stage_envelope_carries_accepted_input_outcomes(vault):
    root, cfg = vault
    write_raw(root)
    dispatcher = make_dispatcher()
    with patch("core.llm.call_chat_completion", dispatcher):
        plan = build_init_plan(cfg, providers={"concept": dispatcher, "case": dispatcher})
    source_stage = next(a for a in plan["actions"] if a.get("stage") == "source_compile")
    assert source_stage["input_outcomes"], "accepted executor input_outcomes preserved"
    outcome = source_stage["input_outcomes"][0]
    assert outcome["rel"] == RAW_REL
    assert outcome["outcome"] in ("ok", "partial")
    assert source_stage["outcome"] in ("executed", "partial_input")
    # success comes from the structured outcome, never issue strings
    assert source_stage["processed"] == source_stage["outcome_counts"].get("ok", 0)
