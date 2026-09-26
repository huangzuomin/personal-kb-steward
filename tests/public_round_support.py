"""T10 checkpoint B (rev 2) — deterministic offline support for ONE public round.

TEST-ONLY support for the future public evaluation runner. See checkpoint-B
report. Rev 2 corrections over the first sample set:

- judgments are selected by EXPLICIT STABLE ROLE KEYS, never by a
  quote->judgment map (one verbatim quote may legitimately support
  different judgments — a source-mechanism definition AND a separately
  labeled inference);
- the mechanism DEFINITION defines the three-stage chain as the source
  describes it (fact-kind, unverified source claim); the causal-effect
  reading stays a separately labeled INFERENCE; the counterexample scope
  statement is an attributed source claim (fact-kind, still unverified),
  not a newly invented inference;
- the seed mock selects the concrete user insight (collecting unrelated to
  writing targets / thinking not retained) and AI proposal THREE (reverse
  filter) WITH its own tail boundary unit cited; growth steps are
  thought-specific, never quota-filling;
- the source stage runs the ACTUAL source executor execute() path (with
  per-source analysis captured) — 4 provider calls total, rendered source
  Markdown preserved.

PHYSICAL SEPARATION: the mock answers in this file belong to the test
provider only. Nothing in core/ or skills/ imports this module. The future
runner may load these responses ONLY in explicit smoke mode; the
production/live path must never see them.

These are curated MOCK examples, not live quality acceptance; no semantic
pass is claimed by schema alone.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

from core.claims import normalized_text

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "card-baseline"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# Future isolated-vault relative paths for the canonical baseline round.
ROUND_SOURCES = {
    "research_summary_uncited_01": "raw/research_summary_uncited_01.md",
    "project_case_01": "raw/project_case_01.md",
    "project_case_01_followup": "raw/project_case_01_followup.md",
    "project_case_01_counterexample": "raw/project_case_01_counterexample.md",
}
ROUND_DIALOGUE = ("dialogue_user_ai_01", "quicknote/dialogue_user_ai_01.md")
CASE_FAMILY = ["raw/project_case_01.md", "raw/project_case_01_followup.md",
               "raw/project_case_01_counterexample.md"]

# Explicit question written for this mock round; NOT copied from any
# manifest annotation (topic_groups / expected_* fields never feed prompts).
ROUND_QUESTION = "合成案例中，青梧书店的分段转化做法在哪些条件下有效，哪些条件下会失效？"

EXPECTED_CALL_SCHEDULE = [
    "source:research_summary_uncited_01",
    "source:project_case_01",
    "source:project_case_01_followup",
    "source:project_case_01_counterexample",
    "seed:dialogue_user_ai_01",
    "concept:case_family",
    "case:case_family",
    "topic:case_family",
]

# Verbatim quotes pinned to the CURRENT fixture bytes (quote contracts).
Q = {
    "research_1": "潮汐淤积本质上是\"居住-就业用地比例失衡\"在两轮车上的投影，单靠调度只能缓解、不能消除。",
    "research_2": "政府侧考核如果只看\"车辆总数\"而不看\"周转率\"，会激励企业过量投放。",
    "case_rate": "活动参与者的图书转化率从原来的约 4% 上升到 11%",
    "case_mech": "\"现场体验 → 即时可购的具象清单 → 低成本回访\"三段转化链",
    "case_cond": "该机制依赖活动主题与商品存在天然关联",
    "follow_30d": "活动参与者在活动后 30 天内的图书转化率约为 6.5%，非活动期日常转化率约 5%",
    "follow_advisor": "财务顾问的解读是：三段转化链\"可能有正效应，但当晚口径夸大了它\"",
    "follow_owner": "店主则认为\"活动当场本来就该单独算，当晚口径才是机制的直接体现\"",
    "follow_attrib": "财务顾问认为无法把增量单独归于书单绑定",
    "counter_click": "三个月内（虚构时间线）书单链接的点击率约为 3%，购书转化几乎为零",
    "counter_free": "成员可直接免费获取，\"有限且与当下体验相关的选择集\"不成立",
    "counter_scope": "失败的是\"照搬链条后两段、且缺少销售语境\"这一组合，不能据此断言转化链在一切非商业场景无效",
}

SOURCE_CALL_PLAN = {
    "research_summary_uncited_01": [
        {"text": "潮汐淤积被描述为居住-就业用地比例失衡的投影，单靠调度只能缓解（未核实定性观点）",
         "quote": Q["research_1"], "kind": "assertion"},
        {"text": "材料称考核指标会激励过量投放（无出处的定性判断）",
         "quote": Q["research_2"], "kind": "assertion"},
    ],
    "project_case_01": [
        {"text": "店主自报活动参与者图书转化率从约 4% 上升到 11%（示意性数字，未核实）",
         "quote": Q["case_rate"], "kind": "assertion"},
        {"text": "案例叙述的可复用机制是三段转化链",
         "quote": Q["case_mech"], "kind": "assertion"},
        {"text": "案例自述机制依赖活动主题与商品的天然关联",
         "quote": Q["case_cond"], "kind": "assertion"},
    ],
    "project_case_01_followup": [
        {"text": "财务顾问复核：30 天口径约 6.5%，日常口径约 5%（示意性数字，未核实）",
         "quote": Q["follow_30d"], "kind": "assertion"},
        {"text": "财务顾问解读：当晚口径夸大了效应",
         "quote": Q["follow_advisor"], "kind": "assertion"},
        {"text": "店主解读：当晚口径才是机制的直接体现",
         "quote": Q["follow_owner"], "kind": "assertion"},
    ],
    "project_case_01_counterexample": [
        {"text": "读书会尝试的点击率约 3%、购书转化几乎为零（组织者自述，示意性数字）",
         "quote": Q["counter_click"], "kind": "assertion"},
        {"text": "反例条件之一：免费替代品使有限选择集不成立",
         "quote": Q["counter_free"], "kind": "assertion"},
        {"text": "反例边界：仅否定照搬后两段且缺少销售语境的组合",
         "quote": Q["counter_scope"], "kind": "assertion"},
    ],
}

SOURCE_LIMITATIONS = ["素材为合成示意内容，数字均无外部来源、未核实，不得作为已验证事实引用"]

_UNANNOTATED_KEYS = ("expected_units", "expected_speaker_markers", "prohibited_overclaims")


# ---------------------------------------------------------------------------
# Exact-byte fixture access (public synthetic corpus only)
# ---------------------------------------------------------------------------


def load_fixture(fixture_id: str) -> dict[str, str]:
    """Return {text, sha256, rel, title} with EXACT raw bytes semantics."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = next((f for f in manifest["fixtures"] if f["id"] == fixture_id), None)
    if entry is None or not entry.get("synthetic"):
        raise ValueError(f"fixture not in canonical synthetic manifest: {fixture_id!r}")
    path = FIXTURE_DIR / Path(entry["path"]).name
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    rel = ROUND_SOURCES.get(fixture_id) or (
        ROUND_DIALOGUE[1] if fixture_id == ROUND_DIALOGUE[0] else f"raw/{fixture_id}.md")
    title = text.splitlines()[0].lstrip("# ").strip() if text.splitlines() else fixture_id
    return {"text": text, "sha256": hashlib.sha256(raw).hexdigest(), "rel": rel,
            "title": title, "manifest_path": entry["path"]}


def public_note(fixture_id: str) -> dict[str, Any]:
    """Synthetic Note input in the generators' verified-snapshot contract."""
    fix = load_fixture(fixture_id)
    return {"rel": fix["rel"], "title": fix["title"], "body": fix["text"],
            "metadata": {}, "source_text": fix["text"], "source_sha256": fix["sha256"]}


def round_notes() -> dict[str, dict[str, Any]]:
    """All five canonical round notes, keyed by fixture id."""
    ids = list(ROUND_SOURCES) + [ROUND_DIALOGUE[0]]
    return {fid: public_note(fid) for fid in ids}


# ---------------------------------------------------------------------------
# Judgments with EXPLICIT STABLE ROLE KEYS (never quote->one-judgment maps)
# ---------------------------------------------------------------------------

P1, P2, P3 = CASE_FAMILY

JUDGMENT_ROLES: dict[str, dict[str, Any]] = {
    # observed self-report, labeled unverified (fact-kind, source-asserted)
    "fact_rate": {
        "statement": "青梧书店店主自报活动参与者图书转化率从约 4% 上升到 11%（店主台账，未核实）",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P1, "quote": Q["case_rate"], "relation": "supports"}]},
    # the DEFINITION of the three-stage chain AS THE SOURCE DESCRIBES it
    # (fact-kind attribution of the source's own mechanism wording)
    "fact_mech_definition": {
        "statement": "案例叙述的可复用机制是「现场体验 → 即时可购的具象清单 → 低成本回访」三段转化链",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P1, "quote": Q["case_mech"], "relation": "supports"}]},
    "fact_cond": {
        "statement": "案例自述该机制依赖活动主题与商品存在天然关联",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P1, "quote": Q["case_cond"], "relation": "supports"}]},
    "fact_30d": {
        "statement": "财务顾问复核显示活动参与者 30 天图书转化率约 6.5%、非活动期日常约 5%（店主台账，未核实）",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P2, "quote": Q["follow_30d"], "relation": "supports"}]},
    "fact_advisor": {
        "statement": "财务顾问认为当晚口径夸大了转化链的效应量级",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P2, "quote": Q["follow_advisor"], "relation": "supports"}]},
    "fact_owner": {
        "statement": "店主认为活动当晚口径才是机制的直接体现",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P2, "quote": Q["follow_owner"], "relation": "supports"}]},
    "fact_attrib": {
        "statement": "转化率上升期间叠加了店内动线改造，财务顾问认为增量无法单独归于书单绑定",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P2, "quote": Q["follow_attrib"], "relation": "supports"}]},
    "fact_counter_failure": {
        "statement": "拾光读书会照搬链条后两段的尝试效果极弱：点击率约 3%、购书转化几乎为零（组织者自述）",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P3, "quote": Q["counter_click"], "relation": "supports"}]},
    # attributed source claims (fact-kind, still unverified): the counterexample
    # records these conditions/scope itself; they are NOT newly invented
    "fact_free_alternative": {
        "statement": "反例素材记录：读书会成员可直接免费获取书目，「有限且与当下体验相关的选择集」不成立",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P3, "quote": Q["counter_free"], "relation": "supports"}]},
    "fact_counter_scope": {
        "statement": "反例素材明确的边界：仅否定「照搬链条后两段且缺少销售语境」的组合，不能据此断言转化链在一切非商业场景无效（素材自述，未验证）",
        "kind": "fact", "confidence": "low",
        "evidence": [{"source": P3, "quote": Q["counter_scope"], "relation": "supports"}]},
    # genuinely INFERRED commentary (causal readings beyond the source text)
    "inference_mechanism": {
        "statement": "推断：转化链起效在于把一次性注意力即时挂接到可购的有限选择集并由低成本回访承接；该因果解释未经对照检验",
        "kind": "inference", "confidence": "low",
        "evidence": [{"source": P1, "quote": Q["case_mech"], "relation": "supports"}]},
    "inference_free_constraint": {
        "statement": "推断：选择集可免费获得或信任语境与销售动机冲突时，链条各环节的转化作用可能减弱（由反例条件推断，未经检验）",
        "kind": "inference", "confidence": "low",
        "evidence": [{"source": P3, "quote": Q["counter_free"], "relation": "supports"}]},
}

# Stable test-response role bindings (consumed by tests and the mock only).
CONCEPT_DEFINITION_STATEMENT = JUDGMENT_ROLES["fact_mech_definition"]["statement"]
CONCEPT_BOUNDARY_STATEMENT = JUDGMENT_ROLES["fact_counter_scope"]["statement"]
CASE_REUSABLE_STATEMENT = JUDGMENT_ROLES["fact_mech_definition"]["statement"]
CASE_INFERENCE_STATEMENT = JUDGMENT_ROLES["inference_mechanism"]["statement"]
CASE_FIGURE_STATEMENT = JUDGMENT_ROLES["fact_rate"]["statement"]


def judgments() -> list[dict[str, Any]]:
    return [dict(v, statement=v["statement"], kind=v["kind"],
                 evidence=[dict(e) for e in v["evidence"]])
            for v in JUDGMENT_ROLES.values()]


def judgment_statement(role: str) -> str:
    return JUDGMENT_ROLES[role]["statement"]


def _provenance_map() -> list[dict[str, Any]]:
    prov = {
        P1: "合成项目叙述案例（虚构青梧书店），数字为店主台账自报、未核实",
        P2: "同案例族的后续观察（虚构财务顾问复核），解释分歧未裁决",
        P3: "同案例族的反例应用（虚构社区读书会），组织者自述、无第三方核验",
    }
    return [{"rel": rel, "provenance": prov[rel], "limitations": SOURCE_LIMITATIONS}
            for rel in CASE_FAMILY]


# ---------------------------------------------------------------------------
# Task-specific mock responses
# ---------------------------------------------------------------------------


def concept_response(payload: dict[str, Any]) -> str:
    del payload
    return json.dumps({
        "concept_found": True,
        "concepts": [{
            "name": "三段转化链",
            "aliases": ["现场体验-具象清单-低成本回访"],
            # definition IS the source-described mechanism chain (fact judgment)
            "definition_claim": CONCEPT_DEFINITION_STATEMENT,
            "explanation": "模型组织（转述，非来源定义）：把一次性的现场注意力立刻挂接到具体、有限、"
                           "与体验相关的选择集，再以低成本回访承接，形成可迁移的转化链条。",
            "confidence": "low",
            # source-defined boundary = the counterexample's own scope statement
            # (attributed source claim, fact-kind, still unverified)
            "source_defined_boundary": [{"evidence_claim": CONCEPT_BOUNDARY_STATEMENT}],
            "suggested_interpretation": [{
                "text": "解释性提案：选择集的「不可免费获得」可能是转化链条成立的必要条件之一",
                "supporting_claim": judgment_statement("inference_free_constraint"),
                "supporting_context": "反例场景中成员可直接免费获取书目",
            }],
            "judgments": judgments(),
            "related": [],
            "pending_paths": [],
        }],
        "provenance_map": _provenance_map(),
        "shared_provenance": ["三个案例族来源同属合成青梧书店案例族，非独立来源"],
    }, ensure_ascii=False)


def case_response(payload: dict[str, Any]) -> str:
    del payload
    return json.dumps({
        "case_found": True,
        "cases": [{
            "title": "青梧书店活动-书目绑定的三段转化链（合成案例）",
            "card_level": "project",
            "confidence": "low",
            "context": "据合成素材自述：虚构青梧书店活动满座但与图书销售几乎脱节（背景为店主叙述）。",
            "action": "据合成素材自述：活动-书目绑定、活动后 48 小时回访、主讲人共创推荐语三步。",
            "result": {
                # observed self-report kept as an attributed, unverified figure
                "figures": [{"claim": CASE_FIGURE_STATEMENT}],
            },
            # mechanism wording (source-described, fact-kind) vs causal-effect
            # reading (inference-kind) are DISTINCT roles with DISTINCT claims:
            "reusable_mechanism_claim": CASE_REUSABLE_STATEMENT,
            "mechanism_inference_claim": CASE_INFERENCE_STATEMENT,
            "applicability": {
                "conditions": [{"claim": judgment_statement("fact_cond")},
                               {"claim": judgment_statement("fact_free_alternative")}],
                "uncertainties": [
                    "主讲人共创规模化后的推荐语质量（素材提及，未检验）",
                    "线下课程附讲义书单等未覆盖场景（反例素材明确未检验）",
                ],
            },
            "judgments": judgments(),
            "related": [],
            "pending_paths": [],
        }],
        "provenance_map": _provenance_map(),
        "shared_provenance": ["三个案例族来源同属合成青梧书店案例族，非独立来源"],
    }, ensure_ascii=False)


def topic_response(payload: dict[str, Any]) -> str:
    del payload
    js = judgments()
    rel_case, rel_follow, rel_counter = CASE_FAMILY
    gaps = [
        {"gap": "缺乏错峰或对照组的转化记录，无法裁决当晚口径与全周期口径的量级分歧",
         "affected": [judgment_statement("fact_owner"), judgment_statement("fact_advisor")]},
        {"gap": "线下课程附讲义书单等未覆盖场景没有记录，失效边界不完整",
         "affected": [judgment_statement("fact_counter_scope")]},
        {"gap": "回访点击到最终购买的链路数据缺失，转化率与销售结果的连接未观察",
         "affected": [judgment_statement("fact_30d")]},
    ]
    return json.dumps({
        "topic_viable": True,
        "title": "三段转化链的有效与失效条件（合成多源主题）",
        "theme_boundary": "仅限合成青梧书店案例族内的转化机制条件，不涵盖真实商业案例",
        "summary": "合成案例族显示：转化链在体验-商品可关联、选择集不可免费获得、回访渠道有效的条件下起效；"
                   "在免费替代品可得、信任语境冲突、渠道弱时失效。当晚口径与全周期口径的量级分歧未获裁决。",
        "confidence": "low",
        "source_map": [
            {"rel": rel_case, "provenance": "合成项目叙述案例（店主台账自报）",
             "limitations": SOURCE_LIMITATIONS},
            {"rel": rel_follow, "provenance": "同案例族后续观察（财务顾问复核与双方解读）",
             "limitations": SOURCE_LIMITATIONS},
            {"rel": rel_counter, "provenance": "同案例族反例应用（组织者自述）",
             "limitations": SOURCE_LIMITATIONS},
        ],
        "shared_provenance": ["三个来源同属合成青梧书店案例族，非独立来源"],
        "judgments": js,
        "tensions": [
            {   # measurement-window difference: context, NOT a data conflict
                "statement": "约 4%→11% 与约 6.5% 的量级差异来自测量窗口不同（当晚三小时 vs 活动 30 天）",
                "classification": "context_difference",
                "sources": [rel_case, rel_follow],
                "claim_statements": [CASE_FIGURE_STATEMENT,
                                     judgment_statement("fact_30d")],
                "note": "口径与分母不同，不构成事实矛盾。",
            },
            {   # interpretation dispute over the same ledger: unresolved
                "statement": "店主与财务顾问对同一台账效应量级的解读存在分歧，现有记录无法裁决",
                "classification": "unverified_tension",
                "sources": [rel_follow],
                "claim_statements": [judgment_statement("fact_owner"),
                                     judgment_statement("fact_advisor")],
                "note": "双方各自明确主张，素材原文说明台账无法裁决。",
            },
            {   # condition difference between application scenes
                "statement": "书店场景的起效与读书会场景的失效是适用条件差异，不是机制普遍失效",
                "classification": "context_difference",
                "sources": [rel_case, rel_counter],
                "claim_statements": [judgment_statement("fact_cond"),
                                     judgment_statement("fact_free_alternative")],
                "note": "场景条件不同，边界仅否定照搬后两段且缺少销售语境的组合。",
            },
        ],
        "evidence_gaps": gaps,
        "next_actions": [
            {"action": "在素材设定内补记一次错峰或对照条件的转化台账", "priority": 1,
             "addresses_gap": gaps[0]["gap"]},
            {"action": "补记线下课程附讲义书单场景的应用结果以检验失效边界", "priority": 2,
             "addresses_gap": gaps[1]["gap"]},
            {"action": "为回访消息增加最终购买字段的台账记录", "priority": 3,
             "addresses_gap": gaps[2]["gap"]},
        ],
        "related": [],
        "pending_paths": [],
    }, ensure_ascii=False)


# Stable seed mock expectations (shared by the mock and the tests).
SEED_INSIGHT_MARKERS = ("我想写的东西", "错配", "复制粘贴式收藏", "思考没有跟着存")
SEED_TAIL_MARKERS = ("反向过滤", "写作目标清单")
SEED_BOUNDARY_MARKERS = ("暂不判断", "漂移")
SEED_INSIGHT_TITLE = "收藏与写作目标错配的自我归因"
SEED_TAIL_TITLE = "AI 提案：写作目标清单反向过滤（含提案边界）"
# The user card stays ATOMIC about the mismatch only; the growth step is a
# model-proposed next action specific to this thought (never attributed as a
# historical user action), and the boundary limits the self-report's reach.
SEED_INSIGHT_STATEMENT = ("林舟自我归因：收藏大多凭「觉得有用」，"
                          "与想写的主题无关——收藏与写作目标错配。")
SEED_INSIGHT_GROWTH = ("模型建议的下一步：新增收藏时先写明它打算服务的具体写作选题，"
                       "再决定是否入库")
SEED_INSIGHT_SCOPE = ["本卡仅记录林舟的自我报告：不能推断笔记总是损害产出，"
                      "也不能推广到其他人的收藏实践"]
SEED_TAIL_GROWTH = ("先试两周反向过滤并保留低门槛「暂不判断」状态，"
                    "季度末复核被暂缓材料中是否有长期价值")


def _pick_unit(units: list[dict[str, Any]], markers: tuple[str, ...]) -> dict[str, Any]:
    for marker in markers:
        for unit in units:
            if marker in str(unit.get("quote", "")):
                return unit
    raise ValueError(f"seed mock: no prompt unit matches any of {markers}; "
                     "refusing to invent unit references")


def seed_response(payload: dict[str, Any]) -> str:
    """Atomic-seed response built ADAPTIVELY from the units actually sent.

    Selects the concrete USER insight (collecting unrelated to writing
    targets) and AI proposal THREE (reverse filter) together with its OWN
    tail boundary (stable-topic assumption / possible mistaken deletion /
    tentative state) — proposal and boundary are separate sentence-level
    units, and BOTH ids are cited as evidence.
    """
    units = payload.get("units", [])
    insight = _pick_unit(units, SEED_INSIGHT_MARKERS)
    tail = _pick_unit(units, SEED_TAIL_MARKERS)
    # the tail boundary lives in a SEPARATE unit (sentence-level excerpts):
    # cite BOTH the proposal unit and its own boundary unit
    boundary = _pick_unit(units, SEED_BOUNDARY_MARKERS)
    tail_ids = list(dict.fromkeys([tail["id"], boundary["id"]]))
    thoughts = [
        {
            "title": SEED_INSIGHT_TITLE,
            # ATOMIC: only the mismatch insight — no second thought appended
            "statement": SEED_INSIGHT_STATEMENT,
            "kind": "assertion",
            "unit_ids": [insight["id"]],
            "growth_directions": [{
                "action": SEED_INSIGHT_GROWTH,
                "basis": "依据用户自述原文：收藏的东西大多和「我想写的东西」无关，纯粹是「觉得有用」。",
            }],
            # boundary about the SELF-REPORT's reach, not the AI method's scope
            "negative_scope": SEED_INSIGHT_SCOPE,
        },
        {
            "title": SEED_TAIL_TITLE,
            "statement": "AI 助手提案（保留 AI 归属）：用「写作目标清单」反向过滤收藏，"
                         "只有能挂到具体选题的材料才入库，其余进临时区季度末统一丢弃。",
            "kind": "assertion",
            "unit_ids": tail_ids,
            "growth_directions": [{
                "action": SEED_TAIL_GROWTH,
                "basis": "提案边界原文：如果选题经常漂移，反向过滤可能误删有长期价值的材料，"
                         "需保留低门槛「暂不判断」状态。",
            }],
            "negative_scope": ["提案为 AI 建议，未经用户实践验证；"
                               "若选题经常漂移，反向过滤可能误删有长期价值的材料，"
                               "需保留低门槛「暂不判断」状态"],
        },
    ]
    return json.dumps({"thoughts": thoughts}, ensure_ascii=False)


def source_chunk_response(payload: dict[str, Any], fixture_id: str) -> str:
    """Chunk response with quotes pinned to the CURRENT fixture bytes.

    Every quote is asserted present in the chunk text the model actually
    received before answering — the mock never answers from memory.
    """
    chunk = str(payload.get("text", ""))
    statements = []
    for entry in SOURCE_CALL_PLAN[fixture_id]:
        if entry["quote"] not in chunk:
            raise ValueError(
                f"mock quote not present in the chunk actually sent ({fixture_id}): "
                f"{entry['quote'][:20]}…")
        statements.append(dict(entry, speaker=None))
    return json.dumps({
        "summary": f"本片段为合成素材「{fixture_id}」的连续片段。",
        "key_statements": statements,
        "topics": [],
        "limitations": SOURCE_LIMITATIONS,
        "quality_flags": ["示意性数字未核实，不得作为已验证事实引用"],
    }, ensure_ascii=False)


def make_offline_provider(log: "CallLog") -> Callable[..., str]:
    """Factory for the test-only offline provider.

    Accepts both generator shapes: (cfg, system_prompt, payload) and
    (system_prompt, payload). Fails closed on unrecognized payloads.
    """
    fixtures = {
        fid: normalized_text(load_fixture(fid)["text"])
        for fid in list(ROUND_SOURCES) + [ROUND_DIALOGUE[0]]
    }

    def provider(*args: Any) -> str:
        cfg = None
        if len(args) == 3:
            cfg, system_prompt, payload = args
        elif len(args) == 2:
            system_prompt, payload = args
        else:
            raise ValueError("offline provider accepts (cfg, system, payload) or (system, payload)")
        del cfg
        if isinstance(payload, dict) and payload.get("task") == "atomic_seed":
            stage = "seed:dialogue_user_ai_01"
            response = seed_response(payload)
        elif isinstance(payload, dict) and payload.get("task") == "concept_extraction":
            stage = "concept:case_family"
            response = concept_response(payload)
        elif isinstance(payload, dict) and payload.get("task") == "case_extraction":
            stage = "case:case_family"
            response = case_response(payload)
        elif isinstance(payload, dict) and payload.get("task") == "question_led_topic_synthesis":
            stage = "topic:case_family"
            response = topic_response(payload)
        elif isinstance(payload, dict) and isinstance(payload.get("text"), str):
            # payload text = "Title: …\n[片段 …]\n\n" header + chunk body
            body = payload["text"].split("\n\n", 1)[-1]
            matches = [fid for fid, text in fixtures.items() if body in text]
            if len(matches) != 1:
                raise ValueError(f"chunk does not match exactly one round fixture: {matches}")
            stage = f"source:{matches[0]}"
            response = source_chunk_response({"text": body}, matches[0])
        else:
            raise ValueError("offline provider refuses unrecognized payload shape")
        log.record(stage, system_prompt, payload, response)
        return response

    return provider


# ---------------------------------------------------------------------------
# Round runner over the ACTUAL executors/generators
# ---------------------------------------------------------------------------


class CallLog:
    """Records every provider call for prompt-capture assertions."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, stage: str, system_prompt: str, payload: Any, response: str) -> None:
        self.calls.append({
            "stage": stage,
            "system_prompt": system_prompt,
            "payload": payload,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "response": response,
        })

    def stage_count(self, prefix: str) -> int:
        return sum(1 for c in self.calls if c["stage"].startswith(prefix))


def load_source_executor_module():
    """Load the real topic-research-compile executor MODULE (execute + render)."""
    path = REPO_ROOT / "skills" / "topic-research-compile" / "executor.py"
    spec = importlib.util.spec_from_file_location(
        "personal_kb_steward_skill_topic_research_compile", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    previous = sys.modules.pop("renderer", None)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("renderer", None)
        if previous is not None:
            sys.modules["renderer"] = previous
        sys.path.remove(str(path.parent))
    return module


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


def _page_markdown(result: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract (filename-hint, markdown) rendered pages from a generator result."""
    pages = []
    for page in result.get("pages") or []:
        content = page.get("content") or ""
        if content:
            pages.append((str(page.get("filename") or page.get("rel_path_hint") or "page"),
                          content))
    page = result.get("page")
    if isinstance(page, dict) and page.get("content"):
        pages.append((page.get("rel_path_hint") or "page", page["content"]))
    return pages


def run_public_round(output_dir: Path | None = None) -> dict[str, Any]:
    """Run ONE representative round over the ACTUAL executors/generators, offline.

    Expected live call schedule is 8 calls: the source stage runs the
    ACTUAL source executor execute() path (analyze_note per source +
    rendered source Markdown) with 4 provider calls total; seed 1;
    concept/case/topic 1 each. Asserts the offline provider was called
    exactly 8 times with the expected stage split and proves every fixture
    fits its chunk bound. Writes curated artifacts into ``output_dir``
    (must be empty or nonexistent).
    """
    from core.case_generation import generate_cases
    from core.concept_generation import generate_concepts
    from core.topic_generation import generate_topic
    from core.source_analysis import analysis_settings, plan_chunks
    from core.skill_executor import execute_skill

    log = CallLog()
    provider = make_offline_provider(log)
    notes = round_notes()
    cfg: dict[str, Any] = {}
    source_settings = analysis_settings(cfg)

    chunk_report: dict[str, Any] = {}
    for fid, rel in ROUND_SOURCES.items():
        norm = normalized_text(notes[fid]["source_text"])
        plan = plan_chunks(norm, source_settings["chunk_chars"], source_settings["max_chunks"])
        chunk_report[fid] = {"rel": rel, "total_chars": plan["total_chars"],
                             "chunk_count": len(plan["chunks"]),
                             "coverage": plan["coverage"],
                             "chunk_chars_bound": source_settings["chunk_chars"],
                             "max_chunks_bound": source_settings["max_chunks"]}

    # -- source stage: ACTUAL executor execute() path, 4 provider calls total.
    # Per-source analysis is captured by wrapping analyze_note (still the
    # function execute() itself calls); rendered source Markdown comes from
    # the executor's own render path.
    source_module = load_source_executor_module()
    orig_provider = source_module.call_chat_completion
    orig_analyze = source_module.analyze_note
    captured_analysis: dict[str, dict[str, Any]] = {}

    def wrapped_analyze(note: dict[str, Any], run_cfg: dict[str, Any], use_llm: bool):
        data = orig_analyze(note, run_cfg, use_llm)
        if note.get("rel"):
            captured_analysis[str(note["rel"])] = data
        return data

    source_module.call_chat_completion = provider
    source_module.analyze_note = wrapped_analyze
    try:
        source_run = source_module.execute({
            "notes": [notes[fid] for fid in ROUND_SOURCES],
            "config": {}, "use_llm": True,
        })
    finally:
        source_module.call_chat_completion = orig_provider
        source_module.analyze_note = orig_analyze

    # -- seed stage: the ACTUAL mindseed-grow executor (atomic mode) --
    seed_result = execute_skill(REPO_ROOT, "mindseed-grow", {
        "config": {}, "use_llm": True, "model_fn": provider,
        "notes": [notes[ROUND_DIALOGUE[0]]],
    })

    # -- concept / case / topic stages: the ACTUAL generators --
    case_notes = [notes["project_case_01"], notes["project_case_01_followup"],
                  notes["project_case_01_counterexample"]]
    concept_result = generate_concepts(case_notes, cfg, call_provider=provider)
    case_result = generate_cases(case_notes, cfg, call_provider=provider)
    topic_result = generate_topic(ROUND_QUESTION, cfg, case_notes, call_provider=provider)

    assert len(log.calls) == len(EXPECTED_CALL_SCHEDULE), (
        f"expected {len(EXPECTED_CALL_SCHEDULE)} provider calls, got {len(log.calls)}: "
        f"{[c['stage'] for c in log.calls]}")
    stages = [c["stage"] for c in log.calls]
    assert stages == EXPECTED_CALL_SCHEDULE, (
        f"call schedule mismatch:\nstages={stages!r}\nexpected={EXPECTED_CALL_SCHEDULE!r}")

    by_rel = {load_fixture(fid)["rel"]: fid for fid in ROUND_SOURCES}
    source_states = {by_rel[rel]: data.get("status")
                     for rel, data in captured_analysis.items()}
    source_modes = {by_rel[rel]: data.get("analysis_mode")
                    for rel, data in captured_analysis.items()}
    quote_hashes = sorted({
        hashlib.sha256(u["quote"].encode("utf-8")).hexdigest()
        for data in captured_analysis.values()
        for u in (data.get("info_units") or []) if u.get("verified")
    })
    summary = {
        "call_count": len(log.calls),
        "stages": stages,
        "expected_schedule": EXPECTED_CALL_SCHEDULE,
        "chunk_report": chunk_report,
        "source_states": source_states,
        "source_modes": source_modes,
        "source_rendered_pages": len(source_run.get("created", [])),
        "source_processed": source_run.get("processed"),
        "seed": {"skill": seed_result.get("skill"), "mode": seed_result.get("mode"),
                 "items": len(seed_result.get("items", [])),
                 "processed": seed_result.get("processed"),
                 "ok": seed_result.get("ok")},
        "concept_state": concept_result.get("state"),
        "case_state": case_result.get("state"),
        "topic_state": topic_result.get("state"),
        "type_states": {
            "source": sorted(set(source_states.values())),
            "seed": "items>0" if seed_result.get("items") else "none",
            "concept": concept_result.get("state"),
            "case": case_result.get("state"),
            "topic": topic_result.get("state"),
        },
        "verified_quote_hash_count": len(quote_hashes),
        "quote_hashes": quote_hashes,
        "question": ROUND_QUESTION,
        "role_bindings": {
            "concept_definition": CONCEPT_DEFINITION_STATEMENT,
            "concept_boundary": CONCEPT_BOUNDARY_STATEMENT,
            "case_reusable_mechanism": CASE_REUSABLE_STATEMENT,
            "case_mechanism_inference": CASE_INFERENCE_STATEMENT,
            "case_figure": CASE_FIGURE_STATEMENT,
        },
        "limitation": ("Curated MOCK round for offline preparation only; responses come from "
                       "the test provider, not a live model. No semantic pass is claimed. "
                       "The source heuristic-fallback path is NOT exercised by this "
                       "success-only fixture set."),
    }

    if output_dir is not None:
        output_dir = Path(output_dir)
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(f"refusing to overwrite non-empty output dir: {output_dir}")
        # All writes stay under the requested directory (relative names only).
        raw_dir = output_dir / "prompts-and-responses"
        analysis_dir = output_dir / "analysis"
        md_dir = output_dir / "markdown"
        results_dir = output_dir / "raw-results"
        for d in (raw_dir, analysis_dir, md_dir, results_dir):
            d.mkdir(parents=True, exist_ok=True)
        for i, call in enumerate(log.calls, 1):
            (raw_dir / f"call-{i:02d}-{call['stage'].replace(':', '_')}.json").write_text(
                json.dumps({"stage": call["stage"], "system_prompt": call["system_prompt"],
                            "payload": call["payload"],
                            "response": json.loads(call["response"])},
                           ensure_ascii=False, indent=1), encoding="utf-8")
        for rel, data in captured_analysis.items():
            (analysis_dir / f"source-{by_rel[rel]}.json").write_text(
                json.dumps(_jsonable(data), ensure_ascii=False, indent=1), encoding="utf-8")
        for page in source_run.get("created", []):
            content = page.get("content") or ""
            if content:
                src_rel = (page.get("sources") or ["page"])[0]
                (md_dir / f"source-{str(src_rel).replace('/', '_')}").write_text(
                    content, encoding="utf-8")
        for name, result in (("seed", seed_result), ("concept", concept_result),
                             ("case", case_result), ("topic", topic_result)):
            (results_dir / f"stage-{name}.json").write_text(
                json.dumps(_jsonable(result), ensure_ascii=False, indent=1), encoding="utf-8")
            for j, (hint, content) in enumerate(_page_markdown(result), 1):
                hint = hint.removesuffix(".md")  # avoid ".md.md" artifacts
                safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in hint)
                (md_dir / f"{name}-{j:02d}-{safe}.md").write_text(content, encoding="utf-8")
        (output_dir / "metrics.json").write_text(
            json.dumps(_jsonable(summary), ensure_ascii=False, indent=1), encoding="utf-8")

    return {"summary": summary, "log": log, "source_run": source_run,
            "source_analysis": captured_analysis, "seed_result": seed_result,
            "concept_result": concept_result, "case_result": case_result,
            "topic_result": topic_result, "notes": notes, "cfg": cfg}


def manifest_annotation_keys() -> tuple[str, ...]:
    return _UNANNOTATED_KEYS


def manifest_prohibited_overclaims() -> list[str]:
    """Reviewer-only annotation strings used by tests to prove no injection."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    claims: list[str] = []
    for fix in manifest["fixtures"]:
        claims.extend(fix.get("prohibited_overclaims", []))
    return claims
