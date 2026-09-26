"""M2 case generator tests.

All fixtures are public synthetic material (tests/fixtures/concept-case); the
provider is always a fake — no network, no real model, no private vault.
Fixture bytes are read via read_bytes().decode('utf-8') (lossless roundtrip:
whatever BOM/CRLF the file carries is preserved verbatim in source_text).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core import case_generation as casegen
from core.claims import read_claims, validate_claims
from core.vault import parse_frontmatter

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "concept-case"
CASE1_REL = "tests/fixtures/concept-case/case_source_01.md"
CASE2_REL = "tests/fixtures/concept-case/case_source_02.md"
CFG = {"case_generation": {"max_source_chars": 20000, "max_context_chars": 60000}}

# Exact single-line fragments of the synthetic fixtures.
Q_RATE_UP = "活动参与者的图书转化率从原来的约 4% 上升到 11%"
Q_SALES = "当晚销售额约为 3200 元"
Q_MECHANISM = "机制是具象清单：把抽象兴趣换成当下可直接行动的具体条目"
Q_COND1 = "活动主题与商品强相关"
Q_DEP = "店主认为该机制依赖活动主题与商品存在天然关联"
Q_CLICK = "书单链接的点击率约为 3%，购书转化几乎为零"
Q_INFERENCE = "团长推断：具象清单必须搭配现场讲解使用，单独发链接无效"
Q_MECH2 = "照搬了具象清单机制"
Q_COND2 = "仅在有讲解语境的场合尝试"


def load_note(name: str, *, corrupt_hash: bool = False, drop_text: bool = False,
              rel: str | None = None, metadata: dict | None = None) -> dict:
    raw_bytes = (FIXTURES / name).read_bytes()
    raw = raw_bytes.decode("utf-8")  # lossless: keeps any BOM/CRLF as-is
    sha = hashlib.sha256(raw_bytes).hexdigest()
    if corrupt_hash:
        sha = "0" * 64
    return {
        "rel": rel or f"tests/fixtures/concept-case/{name}",
        "title": name,
        "body": raw,
        "metadata": {"material_kind": "synthetic", **(metadata or {})},
        "source_text": "" if drop_text else raw,
        "source_sha256": sha,
    }


def fake_provider(payload_builder):
    import inspect
    calls = {"count": 0, "payload": None}

    def provider(cfg, system_prompt, user_payload):
        calls["count"] += 1
        calls["payload"] = user_payload
        builder = payload_builder
        if callable(builder):
            try:
                params = inspect.signature(builder).parameters
                result = builder(user_payload) if params else builder()
            except TypeError:
                result = builder()
        else:
            result = builder
        return json.dumps(result, ensure_ascii=False)

    provider.calls = calls
    return provider


def judgment(statement: str, quote: str, *, rel: str = CASE1_REL, kind: str = "fact",
             confidence: str = "medium", start_line: int | None = None,
             relation: str = "supports") -> dict:
    evidence = {"source": rel, "quote": quote, "relation": relation}
    if start_line is not None:
        evidence["start_line"] = start_line
    return {"statement": statement, "kind": kind, "confidence": confidence,
            "evidence": [evidence]}


CLAIM_RATE = "绑定书单后参与者图书转化率自报从约4%升至11%"
CLAIM_SALES = "当晚销售额自报约为3200元"
CLAIM_MECHANISM = "店主把机制概括为具象清单：把抽象兴趣换成可直接行动的具体条目"
CLAIM_COND = "活动主题与商品强相关是书单活动的一个适用条件"
CLAIM_DEP = "店主认为该机制依赖活动主题与商品存在天然关联"
CLAIM_CLICK = "团长自报书单链接点击率约3%，购书转化几乎为零"
CLAIM_INFER = "团长推断具象清单必须搭配现场讲解使用"
CLAIM_MECH2 = "团长照搬了具象清单机制"
CLAIM_COND2 = "仅有讲解语境的场合是尝试条件"


def project_case(**overrides) -> dict:
    case = {
        "title": "读书会书单绑定活动（合成项目案例）",
        "card_level": "project",
        "confidence": "medium",
        "context": "青梧书店（合成）在周末读书会试行书单绑定活动。",
        "action": "店主讲完后把当期主题三本书列成书单，现场提供。",
        "result": {
            "figures": [
                {"claim": CLAIM_RATE},
                {"claim": CLAIM_SALES},
            ],
        },
        "reusable_mechanism_claim": CLAIM_MECHANISM,
        "mechanism_inference_claim": CLAIM_DEP,
        "applicability": {
            "conditions": [{"claim": CLAIM_COND}],
            "uncertainties": ["条目数上限是否影响效果（店主经验值，未做对照实验）"],
        },
        "judgments": [
            judgment(CLAIM_RATE, Q_RATE_UP),
            judgment(CLAIM_SALES, Q_SALES),
            judgment(CLAIM_MECHANISM, Q_MECHANISM),
            judgment(CLAIM_COND, Q_COND1),
            judgment(CLAIM_DEP, Q_DEP, kind="inference"),
        ],
        "related": [], "pending_paths": [],
    }
    case.update(overrides)
    return case


def mechanism_case(**overrides) -> dict:
    case = {
        "title": "具象清单机制的无语境复用失败（合成机制案例）",
        "card_level": "mechanism",
        "confidence": "low",
        "context": "某社区团购团长（合成）听说书单活动后照搬具象清单机制。",
        "action": "团长在群里直接发五本书的书单链接，无讲解无铺垫。",
        "result": {
            "figures": [{"claim": CLAIM_CLICK}],
        },
        "reusable_mechanism_claim": CLAIM_MECH2,
        "mechanism_inference_claim": CLAIM_INFER,
        "applicability": {
            "conditions": [{"claim": CLAIM_COND2}],
            "uncertainties": ["单次尝试样本极小，结论是否稳定待研究"],
        },
        "judgments": [
            judgment(CLAIM_CLICK, Q_CLICK, rel=CASE2_REL),
            judgment(CLAIM_MECH2, Q_MECH2, rel=CASE2_REL),
            judgment(CLAIM_COND2, Q_COND2, rel=CASE2_REL),
            judgment(CLAIM_INFER, Q_INFERENCE, rel=CASE2_REL, kind="inference"),
        ],
        "related": [], "pending_paths": [],
    }
    case.update(overrides)
    return case


def full_response(**overrides) -> dict:
    response = {
        "case_found": True,
        "cases": [project_case()],
        "provenance_map": [{"rel": CASE1_REL, "provenance": "店主自报台账（合成）",
                            "limitations": ["无对照组", "数字未核实"]}],
        "shared_provenance": [],
    }
    response.update(overrides)
    return response


def run(response=None, notes=None, cfg=CFG, **kwargs):
    provider = fake_provider(response if response is not None else full_response)
    if notes is None:
        notes = [load_note("case_source_01.md")]
    out = casegen.generate_cases(notes, cfg, call_provider=provider,
                                 now="2026-09-21", **kwargs)
    return out, provider


def parse_card_state(content: str) -> dict:
    meta, _ = parse_frontmatter(content)
    state = meta["card_state"]
    if isinstance(state, str):
        state = json.loads(state)
    return state


def snapshot_documents() -> list[dict[str, str]]:
    docs = []
    for rel, name in ((CASE1_REL, "case_source_01.md"), (CASE2_REL, "case_source_02.md")):
        raw = (FIXTURES / name).read_bytes().decode("utf-8")
        docs.append({"path": rel, "content": raw,
                     "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
    return docs


class TestFullCase:
    def test_fixture_bytes_roundtrip(self):
        note = load_note("case_source_01.md")
        assert note["source_text"].encode("utf-8") == \
            (FIXTURES / "case_source_01.md").read_bytes()

    def test_single_source_project_case_is_full(self):
        # No universal multi-source threshold: one well-evidenced source can
        # qualify a full case (qualitative outcomes also qualify — no quota).
        out, _ = run()
        assert out["state"] == "full"
        assert len(out["items"]) == 1
        cand = out["items"][0]
        assert cand["type"] == "case-story"
        assert (cand["status"], cand["stage"]) == ("growing", "draft")
        assert cand["card_level"] == "project"
        assert cand["schema_version"] == casegen.CASE_SCHEMA_VERSION
        assert len(out["claims"]) == 5

    def test_outcome_text_is_the_referenced_claim_statement(self):
        # ONE authoritative text: each figure's text IS the compiled claim's
        # statement (no parallel model description survives).
        out, _ = run()
        cand = out["items"][0]
        assert cand["result"]["source_asserted"] is True
        statements = {f["statement"] for f in cand["result"]["figures"]}
        assert statements == {CLAIM_RATE, CLAIM_SALES}
        assert cand["result"]["summary"] == ""
        for figure in cand["result"]["figures"]:
            assert figure["claim_ids"]

    def test_valid_reference_with_corrupted_description_is_ignored(self):
        # final-review regression (astra-M2-bound-text-probe): valid outcome
        # claim intact, invented description — invented text must not render,
        # page stays full, diagnostic recorded
        response = full_response()
        response["cases"][0]["result"]["figures"][0]["description"] = \
            "活动已经证实带来999倍净利润。"
        out, _ = run(response=response)
        assert out["state"] == "full"
        body = out["pages"][0]["content"]
        assert "999倍净利润" not in body
        assert any("结果文字以判断原句" in i for i in out["issues"])
        assert out["items"][0]["result"]["figures"][0]["statement"] == CLAIM_RATE

    def test_source_asserted_is_program_owned(self):
        # 'source_asserted' is program-owned true regardless of the model;
        # it does NOT claim a specific person self-reported — the actual
        # provenance stays in provenance_map.
        response = full_response()
        response["cases"][0]["result"]["source_asserted"] = False
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["result"]["source_asserted"] is True
        assert cand["provenance_map"][0]["provenance"] == "店主自报台账（合成）"

    def test_free_model_summary_is_rejected_not_persisted(self):
        response = full_response()
        response["cases"][0]["result"]["summary"] = "转化率飙升到99%， invented"
        out, _ = run(response=response)
        assert out["state"] == "full"
        body = out["pages"][0]["content"]
        cand = out["items"][0]
        assert "99%" not in body and "invented" not in cand["result"]["summary"]
        assert any("result.summary" in i for i in out["issues"])

    def test_mechanism_texts_bound_to_claims(self):
        # reusable mechanism = fact-kind claim; inference = inference-kind
        # claim; authoritative text is the referenced statement
        out, _ = run()
        cand = out["items"][0]
        assert cand["reusable_mechanism"] == CLAIM_MECHANISM
        assert cand["reusable_mechanism_claim_ids"]
        assert cand["mechanism_inference"] == CLAIM_DEP
        assert cand["mechanism_inference_claim_ids"]
        assert all(c["kind"] == "inference" for c in cand["claims"]
                   if c["statement"] == CLAIM_DEP)
        body = out["pages"][0]["content"]
        assert "标注为推断" in body
        assert "来源断言不等于独立验证" in body

    def test_parallel_mechanism_text_ignored_with_valid_reference(self):
        response = full_response()
        response["cases"][0]["reusable_mechanism"] = "该机制在任何场景必然有效"
        response["cases"][0]["mechanism_inference"] = "已证实带来千倍收益"
        out, _ = run(response=response)
        assert out["state"] == "full"
        body = out["pages"][0]["content"]
        assert "任何场景必然有效" not in body
        assert "千倍收益" not in body
        assert out["items"][0]["reusable_mechanism"] == CLAIM_MECHANISM
        assert any("机制文字以" in i for i in out["issues"])

    def test_inference_claim_requires_inference_kind(self):
        response = full_response()
        response["cases"][0]["mechanism_inference_claim"] = CLAIM_MECHANISM  # fact-kind
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["mechanism_inference"] == ""
        assert cand["mechanism_inference_claim_ids"] == []
        assert any("inference 判断" in i for i in out["issues"])

    def test_conditions_bound_to_claims(self):
        out, _ = run()
        cand = out["items"][0]
        expected_ids = [c["claim_id"] for c in cand["claims"]
                        if c["statement"] == CLAIM_COND]
        assert cand["applicability"]["conditions"] == [
            {"statement": CLAIM_COND, "claim_ids": expected_ids}]
        body = out["pages"][0]["content"]
        assert f"- {CLAIM_COND}（证据 " in body
        assert "待研究问题" in body  # uncertainties labeled as proposed questions

    def test_invalid_condition_dropped_case_limited(self):
        response = full_response()
        response["cases"][0]["applicability"]["conditions"] = [{"claim": "不存在的判断"}]
        out, _ = run(response=response)
        assert out["state"] == "stub"
        cand = out["items"][0]
        assert cand["applicability"]["conditions"] == []
        assert "适用条件" in out["reason"]
        assert any("整条丢弃" in i for i in out["issues"])

    def test_missing_mechanism_references_leave_limited_case(self):
        response = full_response()
        response["cases"][0]["reusable_mechanism_claim"] = "不存在的判断"
        response["cases"][0]["mechanism_inference_claim"] = "也不存在的判断"
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["reusable_mechanism"] == ""
        assert cand["mechanism_inference"] == ""
        assert out["state"] == "stub"
        assert "机制" in out["reason"]
        assert "编造" in out["pages"][0]["content"]

    def test_qualitative_outcomes_qualify_full_no_numeric_quota(self):
        # qualitative observed outcomes with valid evidence form a full case:
        # a numeric quota would pressure the model to invent metrics
        response = full_response()
        response["cases"][0] = project_case(
            result={"figures": [{"claim": CLAIM_RATE}]},
            judgments=[judgment(CLAIM_RATE, Q_RATE_UP),
                       judgment(CLAIM_MECHANISM, Q_MECHANISM),
                       judgment(CLAIM_COND, Q_COND1),
                       judgment(CLAIM_DEP, Q_DEP, kind="inference")])
        out, _ = run(response=response)
        assert out["state"] == "full"
        assert out["items"][0]["result"]["figures"][0]["claim_ids"]

    def test_page_renders_with_contract_frontmatter(self):
        out, _ = run()
        meta, _ = parse_frontmatter(out["pages"][0]["content"])
        assert meta["type"] == "case-story"
        assert meta["status"] == "growing"
        assert meta["stage"] == "draft"
        assert meta["schema_version"] == casegen.CASE_SCHEMA_VERSION
        assert meta["coverage"] == "full"
        assert meta["review_required"] == "true"
        body = out["pages"][0]["content"]
        assert "适用条件" in body
        assert "生成质量标注" in body

    def test_rendered_list_items_on_own_lines(self):
        # trim_blocks/newline-concatenation probe (topic had this bug)
        out, _ = run()
        body = out["pages"][0]["content"]
        assert f"\n- {CLAIM_RATE}（证据 " in body
        assert f"\n- {CLAIM_COND}（证据 " in body

    def test_body_uses_ordinal_refs_machine_ids_stay_in_card_state(self):
        # presentation check: visible body carries human-readable ordinal
        # evidence references; opaque claim IDs exist ONLY in card_state and
        # reload validation still passes
        out, _ = run()
        meta, body = parse_frontmatter(out["pages"][0]["content"])
        assert "claim:" not in body
        assert "依据判断" not in body and "权威文字" not in body
        assert "证据 1" in body
        assert "## 来源提出的可复用机制" in body and "## 适用条件" in body
        assert "证据等级以来源地图为准" in body
        state = parse_card_state(out["pages"][0]["content"])
        assert all(c["claim_id"].startswith("claim:") for c in state["claims"])
        claims = read_claims({"claims": state["claims"]})
        assert validate_claims({"claims": state["claims"]},
                               snapshot_documents()[:1]) == claims

    def test_card_state_persisted_and_reloadable(self):
        out, _ = run()
        state = parse_card_state(out["pages"][0]["content"])
        assert state["version"] == casegen.CARD_STATE_VERSION
        assert state["type"] == "case-story"
        assert state["claims"] == out["items"][0]["claims"]
        claims = read_claims({"claims": state["claims"]})
        assert len(claims) == 5
        assert validate_claims({"claims": state["claims"]},
                               snapshot_documents()) == claims
        assert state["analysis"] == out["analysis"]["items"][0]

    def test_project_and_mechanism_cards_distinct(self):
        response = full_response()
        response["cases"].append(mechanism_case())
        out, _ = run(notes=[load_note("case_source_01.md"),
                            load_note("case_source_02.md")],
                     response=response)
        assert out["state"] == "full"
        assert len(out["items"]) == 2
        levels = sorted(c["card_level"] for c in out["items"])
        assert levels == ["mechanism", "project"]
        mech = next(c for c in out["items"] if c["card_level"] == "mechanism")
        assert mech["result"]["summary"] == ""

    def test_repeated_candidate_deduped_across_titles_with_evidence_union(self):
        # same story rewritten under a different title: ONE card whose
        # evidence is unioned (never silently discarded)
        response = full_response()
        dup = project_case(title="换一个标题的同一个故事")
        dup["judgments"] = [
            judgment(CLAIM_RATE, Q_RATE_UP),
            judgment(CLAIM_RATE, Q_DEP),
            judgment(CLAIM_SALES, Q_SALES),
            judgment(CLAIM_MECHANISM, Q_MECHANISM),
            judgment(CLAIM_COND, Q_COND1),
            judgment(CLAIM_DEP, Q_DEP, kind="inference"),
        ]
        response["cases"].append(dup)
        out, _ = run(response=response)
        assert len(out["items"]) == 1
        merged = next(c for c in out["items"][0]["claims"]
                      if c["statement"] == CLAIM_RATE)
        assert len(merged["evidence"]) == 2
        assert any("新证据已合并" in i for i in out["issues"])
        state = parse_card_state(out["pages"][0]["content"])
        claims = read_claims({"claims": state["claims"]})
        assert validate_claims({"claims": state["claims"]},
                               snapshot_documents()[:1]) == claims

    def test_duplicate_from_complementary_source_unions_evidence(self):
        alt_rel = "tests/fixtures/concept-case/case_source_02.md"
        response = full_response()
        dup = project_case(title="第二个来源记录的同一活动")
        # identical claim SET, but the inference claim carries NEW evidence
        # from the complementary source — the union must keep both
        dup["judgments"] = [
            judgment(CLAIM_RATE, Q_RATE_UP),
            judgment(CLAIM_SALES, Q_SALES),
            judgment(CLAIM_MECHANISM, Q_MECHANISM),
            judgment(CLAIM_COND, Q_COND1),
            judgment(CLAIM_DEP, Q_DEP, kind="inference"),
            judgment(CLAIM_DEP, Q_INFERENCE, rel=alt_rel, kind="inference"),
        ]
        response["cases"].append(dup)
        out, _ = run(notes=[load_note("case_source_01.md"),
                            load_note("case_source_02.md")],
                     response=response)
        assert len(out["items"]) == 1
        cand = out["items"][0]
        merged = next(c for c in cand["claims"] if c["statement"] == CLAIM_DEP)
        assert {e["source"] for e in merged["evidence"]} == {CASE1_REL, alt_rel}
        assert set(cand["sources"]) == {CASE1_REL, alt_rel}
        assert cand["source_hashes"].get(alt_rel)
        assert any("新证据已合并" in i for i in out["issues"])
        state = parse_card_state(out["pages"][0]["content"])
        claims = read_claims({"claims": state["claims"]})
        assert validate_claims({"claims": state["claims"]},
                               snapshot_documents()) == claims

    def test_same_story_under_both_levels_is_ambiguous_not_two_full(self):
        response = full_response()
        response["cases"].append(mechanism_case(
            title="同一故事的机制级登记",
            judgments=project_case()["judgments"],
            reusable_mechanism_claim=CLAIM_MECHANISM,
            mechanism_inference_claim=CLAIM_DEP,
            applicability={"conditions": [{"claim": CLAIM_COND}],
                           "uncertainties": []},
            result=project_case()["result"]))
        out, _ = run(response=response)
        assert len(out["items"]) == 2  # both kept
        second = out["items"][1]
        assert second["card_level"] == "mechanism"
        # the ambiguous duplicate is review-gated, never a second full card
        assert (second["status"], second["stage"]) == ("manual_review", "needs_context")
        assert any("疑似重复登记" in i for i in out["issues"])

    def test_same_title_different_claims_is_review_not_merge(self):
        response = full_response()
        response["cases"].append(project_case(
            judgments=[judgment("另一个不同判断", Q_MECHANISM),
                       judgment(CLAIM_MECHANISM, Q_MECHANISM),
                       judgment(CLAIM_COND, Q_COND1),
                       judgment(CLAIM_DEP, Q_DEP, kind="inference")],
            result={"figures": [{"claim": "另一个不同判断"}]},
            reusable_mechanism_claim=CLAIM_MECHANISM,
            mechanism_inference_claim=CLAIM_DEP,
            applicability={"conditions": [{"claim": CLAIM_COND}], "uncertainties": []}))
        out, _ = run(response=response)
        assert len(out["items"]) == 2  # kept, ambiguous
        assert any("同题异实" in i for i in out["issues"])

    def test_shared_source_does_not_force_shared_object(self):
        # both cases cite the SAME source file; they are different objects
        response = full_response()
        response["shared_provenance"] = ["两个案例素材同属虚构书单案例族，共享背景设定"]
        shared_case = mechanism_case()
        shared_case["judgments"] = [
            judgment("团长自报点击率约3%（假借同一来源）", Q_RATE_UP, rel=CASE1_REL)]
        shared_case["result"] = {"figures": [
            {"claim": "团长自报点击率约3%（假借同一来源）"}]}
        shared_case["reusable_mechanism_claim"] = "团长自报点击率约3%（假借同一来源）"
        shared_case["applicability"] = {"conditions": [
            {"claim": "团长自报点击率约3%（假借同一来源）"}], "uncertainties": []}
        response["cases"].append(shared_case)
        out, _ = run(response=response)
        # The second "case" cites an honest quote from the shared source, so it
        # compiles; shared source is disclosed but no object merge happens.
        assert len(out["items"]) == 2
        assert any("共享来源" in i for i in out["issues"])

    def test_model_owned_metadata_never_trusted(self):
        response = full_response()
        response["schema_version"] = "model-invented"
        response["cases"][0]["confidence"] = "high"
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["schema_version"] == casegen.CASE_SCHEMA_VERSION
        assert cand["generator_version"] == casegen.CASE_GENERATOR_VERSION
        assert cand["review_required"] is True


class TestSourceVsInferredRoles:
    """Late-review regressions: mutate ONLY the bound claim's kind against the
    valid fact-role baseline; assert actual rendered role labels."""

    def test_inference_reusable_mechanism_rejected(self):
        response = full_response()
        response["cases"][0]["judgments"][2]["kind"] = "inference"  # CLAIM_MECHANISM
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["reusable_mechanism"] == ""
        assert cand["mechanism_inference"] == CLAIM_DEP  # inference stays inference-only
        assert any("不得冒充来源机制" in i for i in out["issues"])
        body = parse_frontmatter(out["pages"][0]["content"])[1]
        assert "## 来源提出的可复用机制" in body
        assert "来源中未明确可复用机制" in body
        assert CLAIM_MECHANISM not in body.split("## 机制推断")[0]

    def test_same_text_cannot_populate_mechanism_and_inference(self):
        # the T10 mock accident: one inference claim bound as BOTH
        # source-stated mechanism and mechanism inference
        response = full_response()
        response["cases"][0]["judgments"][2]["kind"] = "inference"  # CLAIM_MECHANISM
        response["cases"][0]["mechanism_inference_claim"] = CLAIM_MECHANISM
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["reusable_mechanism"] == ""      # rejected as source mechanism
        assert cand["mechanism_inference"] == CLAIM_MECHANISM  # inference only

    def test_inference_result_figure_rejected(self):
        response = full_response()
        response["cases"][0]["judgments"][0]["kind"] = "inference"  # CLAIM_RATE
        out, _ = run(response=response)
        cand = out["items"][0]
        assert all(f["statement"] != CLAIM_RATE for f in cand["result"]["figures"])
        assert any("不得冒充来源结果" in i for i in out["issues"])
        body = parse_frontmatter(out["pages"][0]["content"])[1]
        assert CLAIM_RATE not in body.split("## 判断与证据")[0]

    def test_inferred_condition_rendered_with_marker(self):
        response = full_response()
        response["cases"][0]["judgments"][3]["kind"] = "inference"  # CLAIM_COND
        response["cases"][0]["applicability"] = {
            "conditions": [{"claim": CLAIM_COND},
                           {"claim": CLAIM_DEP}],
            "uncertainties": []}
        response["cases"][0]["judgments"][4]["kind"] = "fact"  # CLAIM_DEP as fact
        out, _ = run(response=response)
        body = out["pages"][0]["content"]
        assert f"- {CLAIM_COND}（证据 " in body and "推断，非来源原话" in body
        # fact-kind condition carries no inference marker on its line
        cond_line = next(l for l in body.splitlines() if l.startswith(f"- {CLAIM_DEP}"))
        assert "推断" not in cond_line


class TestUpstreamSourceMetadata:
    def test_upstream_limitations_survive_model_omission(self):
        note = load_note("case_source_01.md", metadata={"upstream_analysis": {
            "source_kind": "店主台账",
            "limitations": ["上游标注：无对照组"],
            "speakers": ["店主（合成人物）"]}})
        response = full_response()
        response["provenance_map"] = [{"rel": CASE1_REL,
                                       "provenance": "合成案例素材",
                                       "limitations": []}]
        out, provider = run(notes=[note], response=response)
        payload = provider.calls["payload"]
        assert payload["upstream_source_analysis"][0]["limitations"] == ["上游标注：无对照组"]
        entry = out["items"][0]["provenance_map"][0]
        assert entry["source_kind"] == "店主台账"
        assert "上游标注：无对照组" in entry["limitations"]
        body = out["pages"][0]["content"]
        assert "上游标注：无对照组" in body
        assert "店主台账" in body

    def test_model_cannot_erase_upstream_limitation(self):
        note = load_note("case_source_01.md", metadata={"upstream_analysis": {
            "source_kind": "读书会纪要",
            "limitations": ["上游限制A"]}})
        response = full_response()
        response["provenance_map"] = [{"rel": CASE1_REL, "provenance": "模型口径",
                                       "limitations": ["模型限制"]}]
        out, _ = run(notes=[note], response=response)
        entry = out["items"][0]["provenance_map"][0]
        assert "上游限制A" in entry["limitations"]
        assert "模型限制" in entry["limitations"]

    def test_arbitrary_metadata_is_not_transmitted(self):
        note = load_note("case_source_01.md",
                         metadata={"dump": "x" * 5000, "upstream_analysis": 3})
        out, provider = run(notes=[note])
        assert "dump" not in json.dumps(provider.calls["payload"])
        assert "upstream_source_analysis" not in provider.calls["payload"]
        assert out["state"] == "full"


class TestZeroStubError:
    def test_explicit_no_case_is_legitimate_zero(self):
        out, _ = run(response={"case_found": False,
                               "reason": "素材只有抽象观点，没有具体案例"})
        assert out["state"] == "zero"
        assert out["items"] == []
        assert "抽象观点" in out["reason"]

    def test_chatter_fixture_is_zero(self):
        out, _ = run(notes=[load_note("neg_chatter.md")],
                     response={"case_found": False, "reason": "无案例"})
        assert out["state"] == "zero"

    def test_missing_case_found_is_error_not_zero(self):
        response = full_response()
        del response["case_found"]
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert "case_found" in out["reason"]

    def test_no_substance_is_zero(self):
        out, _ = run(notes=[load_note("neg_empty.md")])
        assert out["state"] == "zero"
        assert "无实质内容" in out["reason"]

    def test_all_evidence_rejected_is_error(self):
        response = full_response()
        for j in response["cases"][0]["judgments"]:
            j["evidence"][0]["quote"] = "这句话不在任何来源里"
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert "已编译判断" in out["reason"]

    def test_unattributed_figure_dropped_case_becomes_stub(self):
        response = full_response()
        response["cases"][0]["result"]["figures"] = [
            {"claim": "不存在的判断原句"}]
        out, _ = run(response=response)
        assert out["state"] == "stub"
        cand = out["items"][0]
        assert cand["result"]["figures"] == []
        assert (cand["status"], cand["stage"]) == ("manual_review", "needs_context")
        assert any("逐项归因" in i for i in out["issues"])
        assert "范围限制" in out["pages"][0]["content"]

    def test_missing_conditions_blocks_full(self):
        response = full_response()
        response["cases"][0]["applicability"] = {"conditions": [], "uncertainties": []}
        out, _ = run(response=response)
        assert out["state"] == "stub"
        assert "适用条件" in out["reason"]

    def test_missing_action_blocks_full(self):
        response = full_response()
        response["cases"][0]["action"] = ""
        out, _ = run(response=response)
        assert out["state"] == "stub"
        assert "行动记录" in out["reason"]

    def test_invalid_card_level_dropped(self):
        response = full_response()
        response["cases"][0]["card_level"] = "story"
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert any("card_level" in i for i in out["issues"])

    def test_repeated_quote_requires_start_line(self):
        note = load_note("neg_repeated_quote.md")
        rel = note["rel"]
        raw = note["source_text"]
        line = next(i + 1 for i, l in enumerate(raw.splitlines())
                    if "同样的句子在文件里出现两次" in l)
        response = {"case_found": True, "cases": [{
            "title": "重复片段案例", "card_level": "project",
            "context": "测试背景。", "action": "测试行动。",
            "result": {"figures": [{"claim": "无提示判断"}]},
            "reusable_mechanism_claim": "无提示判断",
            "applicability": {"conditions": [{"claim": "无提示判断"}],
                              "uncertainties": []},
            "judgments": [judgment("无提示判断", "同样的句子在文件里出现两次。", rel=rel)],
            "related": [], "pending_paths": []}],
            "provenance_map": [{"rel": rel, "provenance": "p", "limitations": []}],
            "shared_provenance": []}
        cfg = {"case_generation": {"max_source_chars": 20000,
                                   "max_context_chars": 60000}}
        out, _ = run(response=response, notes=[note], cfg=cfg)
        assert out["state"] == "error"
        response["cases"][0]["judgments"][0]["evidence"][0]["start_line"] = line
        out2, _ = run(response=response, notes=[note], cfg=cfg)
        assert out2["state"] == "full"

    def test_refused_input_no_provider_call(self):
        out, provider = run(notes=[load_note("case_source_01.md", drop_text=True)])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_hash_mismatch_refuses_note(self):
        out, _ = run(notes=[load_note("case_source_01.md", corrupt_hash=True)])
        assert out["state"] == "error"
        assert any("不匹配" in i for i in out["issues"])

    def test_oversized_source_no_call_no_truncation(self):
        cfg = {"case_generation": {"max_source_chars": 10,
                                   "max_context_chars": 60000}}
        out, provider = run(cfg=cfg)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "max_source_chars" in out["reason"]

    def test_non_llm_mode_is_honest(self):
        out, provider = run(analysis_mode="heuristic")
        assert out["state"] == "disabled"
        assert provider.calls["count"] == 0

    def test_provider_failure_surfaces_without_retry(self):
        def failing(cfg, system_prompt, payload):
            raise RuntimeError("boom")
        out = casegen.generate_cases([load_note("case_source_01.md")], CFG,
                                     call_provider=failing)
        assert out["state"] == "error"
        assert "boom" in out["reason"]

    def test_malformed_json_is_error(self):
        out = casegen.generate_cases([load_note("case_source_01.md")], CFG,
                                     call_provider=lambda c, s, p: "不是 JSON")
        assert out["state"] == "error"
        assert "JSON" in out["reason"]

    def test_refused_source_keeps_coverage_partial(self):
        notes = [load_note("case_source_01.md"),
                 load_note("case_source_02.md", corrupt_hash=True)]
        out, _ = run(notes=notes)
        assert out["items"]
        assert out["analysis"]["coverage"] == "partial"


class TestLinksAndSafety:
    def test_related_only_to_known_paths(self):
        response = full_response()
        response["cases"][0]["related"] = ["wiki/cases/known-case.md",
                                           "wiki/invented/x.md"]
        out, _ = run(response=response, known_paths=["wiki/cases/known-case.md"])
        cand = out["items"][0]
        assert cand["related"] == ["wiki/cases/known-case.md"]
        assert "wiki/invented/x.md" in cand["pending_links"]
        assert "[[wiki/invented/x.md]]" not in out["pages"][0]["content"]

    def test_freeform_wikilinks_sanitized(self):
        response = full_response()
        response["cases"][0]["context"] = "背景见 [[wiki/fake.md]]"
        response["cases"][0]["applicability"] = {
            "conditions": [{"claim": CLAIM_COND}],
            "uncertainties": ["见 [[wiki/another]] 的讨论"]}
        out, _ = run(response=response)
        body = out["pages"][0]["content"]
        assert "[[wiki/fake.md]]" not in body
        assert "[[wiki/another]]" not in body
        assert any("链接语法" in i for i in out["issues"])

    def test_unsafe_paths_rejected_bounded(self):
        for bad in ("C:\\abs\\path.md", "../escape.md", "wiki\\slash.md",
                    "wiki/../traverse.md", "/abs/root.md", "wiki/x\x01.md"):
            out, provider = run(notes=[load_note("case_source_01.md", rel=bad)])
            assert out["state"] == "error", bad
            assert provider.calls["count"] == 0, bad

    def test_secret_in_payload_blocked_pre_call(self):
        note = load_note("case_source_01.md")
        note["body"] += " api_key = sk-abcdefghijklmnopqrs12345"
        note["source_text"] = note["body"]
        note["source_sha256"] = hashlib.sha256(note["source_text"].encode()).hexdigest()
        out, provider = run(notes=[note])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_secret_in_response_blocked_post_call(self):
        def secret_provider(cfg, system_prompt, payload):
            data = full_response()
            data["cases"][0]["context"] = "password = hunter2secretvalue"
            return json.dumps(data, ensure_ascii=False)
        out = casegen.generate_cases([load_note("case_source_01.md")], CFG,
                                     call_provider=secret_provider)
        assert out["state"] == "error"
        assert "hunter2secretvalue" not in out["reason"]


class TestSchemaRegistration:
    def test_case_schema_loaded_from_file_single_truth(self):
        from core.card_contracts import _STORE, register_card_schema, validate_card_item
        issues = validate_card_item({"type": "case-story", "status": "growing",
                                     "stage": "needs_context"}, "case-story")
        assert issues
        on_disk = json.loads(casegen._SCHEMA_PATH.read_text(encoding="utf-8-sig")
                             .replace("\r\n", "\n"))
        register_card_schema(on_disk)
        assert _STORE.get("case-story.schema.json") == on_disk
        assert validate_card_item({"type": "case-story", "status": "growing",
                                   "stage": "needs_context"}, "case-story")
