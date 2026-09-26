"""M2 concept generator tests.

All fixtures are public synthetic material (tests/fixtures/concept-case); the
provider is always a fake — no network, no real model, no private vault.
Fixture bytes are read via read_bytes().decode('utf-8') (lossless roundtrip:
whatever BOM/CRLF the file carries is preserved verbatim in source_text).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core import concept_generation as cg
from core.claims import read_claims, validate_claims
from core.vault import parse_frontmatter

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "concept-case"
CONCEPT_REL = "tests/fixtures/concept-case/concept_source_01.md"
CFG = {"concept_generation": {"max_source_chars": 20000, "max_context_chars": 60000}}

# Exact single-line fragments of the synthetic fixture (quote coordinates use
# the FULL raw snapshot, like core.topic_generation).
Q_DEF = "触发条件必须引用一条已经存在的卡片或问题"
Q_BOUNDARY = "定时提醒只依赖时间，回顾触发器依赖已有知识对象"
Q_ALIAS = "部分团队把它叫做复习钩子，含义与回顾触发器相同"
Q_STAT = "绑定回顾触发器的卡片 30 天后再访问率约为 62%"


def load_note(name: str = "concept_source_01.md", *, corrupt_hash: bool = False,
              drop_text: bool = False, rel: str | None = None,
              metadata: dict | None = None) -> dict:
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


def judgment(statement: str, quote: str, *, rel: str = CONCEPT_REL, kind: str = "fact",
             confidence: str = "medium", start_line: int | None = None) -> dict:
    evidence = {"source": rel, "quote": quote, "relation": "supports"}
    if start_line is not None:
        evidence["start_line"] = start_line
    return {"statement": statement, "kind": kind, "confidence": confidence,
            "evidence": [evidence]}


DEF_CLAIM = "回顾触发器必须引用已存在的卡片或问题，而非单纯时间点"
BOUNDARY_CLAIM = "来源把回顾触发器与定时提醒区分：定时提醒只依赖时间"
STAT_CLAIM = "绑定回顾触发器的卡片30天后再访问率自报约62%（未独立核实）"
ALIAS_CLAIM = "复习钩子是该概念的来源内别名"


def full_response(**overrides) -> dict:
    response = {
        "concept_found": True,
        "concepts": [{
            "name": "回顾触发器",
            "aliases": ["复习钩子"],
            "definition_claim": DEF_CLAIM,
            "explanation": "来源将其与普通日历提醒区分开：它必须引用已存在的卡片或问题。",
            "confidence": "medium",
            "source_defined_boundary": [
                {"evidence_claim": BOUNDARY_CLAIM},
            ],
            "suggested_interpretation": [
                {"text": "该机制可能提高卡片长期再访问率",
                 "supporting_claim": STAT_CLAIM,
                 "supporting_context": "来源记录了绑定卡片再访问率更高的自报数字"},
            ],
            "judgments": [
                judgment(DEF_CLAIM, Q_DEF),
                judgment(BOUNDARY_CLAIM, Q_BOUNDARY),
                judgment(ALIAS_CLAIM, Q_ALIAS, kind="inference"),
                judgment(STAT_CLAIM, Q_STAT),
            ],
            "related": [], "pending_paths": [],
        }],
        "provenance_map": [{"rel": CONCEPT_REL, "provenance": "合成概念素材",
                            "limitations": ["数字为自报，未独立核对"]}],
        "shared_provenance": [],
    }
    response.update(overrides)
    return response


def run(response=None, notes=None, cfg=CFG, **kwargs):
    provider = fake_provider(response if response is not None else full_response)
    out = cg.generate_concepts(notes if notes is not None else [load_note()],
                               cfg, call_provider=provider, now="2026-09-21", **kwargs)
    return out, provider


def parse_card_state(content: str) -> dict:
    meta, _ = parse_frontmatter(content)
    state = meta["card_state"]
    if isinstance(state, str):
        state = json.loads(state)
    return state


class TestFullConcept:
    def test_fixture_bytes_roundtrip(self):
        note = load_note()
        assert note["source_text"].encode("utf-8") == \
            (FIXTURES / "concept_source_01.md").read_bytes()

    def test_single_source_concept_is_full(self):
        # Single source can qualify: deliberately NO minimum source count.
        out, _ = run()
        assert out["state"] == "full"
        assert len(out["items"]) == 1
        cand = out["items"][0]
        assert cand["type"] == "concept-page"
        assert (cand["status"], cand["stage"]) == ("growing", "draft")
        assert cand["definition"]
        assert cand["schema_version"] == cg.CONCEPT_SCHEMA_VERSION
        assert cand["analysis_mode"] == "llm"
        assert cand["review_required"] is True
        assert cand["sources"] == [CONCEPT_REL]
        assert len(out["claims"]) == 4

    def test_definition_is_the_referenced_claim_statement(self):
        # ONE authoritative text: the definition IS the compiled claim's
        # statement, not a parallel model string.
        out, _ = run()
        cand = out["items"][0]
        assert cand["definition"] == DEF_CLAIM
        assert cand["definition_claim"] == DEF_CLAIM
        assert any(c["statement"] == DEF_CLAIM for c in cand["claims"])

    def test_unbound_definition_is_dropped(self):
        # original astra-M2-initial-probe scenario: free definition without a
        # compilable definition_claim is an error, never a page
        response = full_response()
        response["concepts"][0]["definition"] = "本概念指在没有任何干预时销量必定增长十倍。"
        response["concepts"][0]["source_defined_boundary"] = [
            {"text": "任何环境下都必然有效。", "evidence_claim": ["不存在的判断"]}]
        del response["concepts"][0]["definition_claim"]
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert out["items"] == []
        assert any("definition_claim" in i for i in out["issues"])
        assert "销量必定增长十倍" not in out.get("reason", "")

    def test_parallel_definition_text_ignored_with_valid_reference(self):
        # final-review regression: VALID reference intact, corrupted display
        # text — the invented text must not render and the page stays full
        response = full_response()
        response["concepts"][0]["definition"] = "销量必定增长十倍"
        out, _ = run(response=response)
        assert out["state"] == "full"
        body = out["pages"][0]["content"]
        cand = out["items"][0]
        assert "销量必定增长十倍" not in body
        assert cand["definition"] == DEF_CLAIM
        assert any("已忽略模型文本" in i for i in out["issues"])

    def test_parallel_boundary_text_ignored_with_valid_reference(self):
        response = full_response()
        response["concepts"][0]["source_defined_boundary"][0]["text"] = \
            "任何环境下都必然有效。"
        out, _ = run(response=response)
        assert out["state"] == "full"
        cand = out["items"][0]
        assert cand["source_defined_boundary"][0]["statement"] == BOUNDARY_CLAIM
        body = out["pages"][0]["content"]
        assert "任何环境下都必然有效" not in body
        assert any("边界文字以判断原句" in i for i in out["issues"])

    def test_page_renders_with_contract_frontmatter(self):
        out, _ = run()
        meta, _ = parse_frontmatter(out["pages"][0]["content"])
        assert meta["type"] == "concept-page"
        assert meta["status"] == "growing"
        assert meta["stage"] == "draft"
        assert meta["schema_version"] == cg.CONCEPT_SCHEMA_VERSION
        assert meta["analysis_mode"] == "llm"
        assert meta["coverage"] == "full"
        assert meta["review_required"] == "true"
        assert meta["source_hashes"][CONCEPT_REL]
        body = out["pages"][0]["content"]
        assert "回顾触发器" in body
        assert "标注为推断" in body
        assert "模型整理" in body  # explanation labeled as model organization
        assert "生成质量标注" in body

    def test_card_state_persisted_and_reloadable(self):
        out, _ = run()
        state = parse_card_state(out["pages"][0]["content"])
        assert state["version"] == cg.CARD_STATE_VERSION
        assert state["type"] == "concept-page"
        assert state["claims"] == out["items"][0]["claims"]
        claims = read_claims({"claims": state["claims"]})
        assert len(claims) == 4
        raw = (FIXTURES / "concept_source_01.md").read_bytes().decode("utf-8")
        documents = [{"path": CONCEPT_REL, "content": raw,
                      "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}]
        assert validate_claims({"claims": state["claims"]}, documents) == claims
        assert state["analysis"] == out["analysis"]["items"][0]

    def test_boundary_separated_from_interpretation(self):
        out, _ = run()
        cand = out["items"][0]
        boundary = cand["source_defined_boundary"][0]
        assert boundary["statement"] == BOUNDARY_CLAIM
        assert boundary["claim_ids"]
        interp = cand["suggested_interpretation"][0]
        assert interp["inference"] is True  # explicit inference label
        assert interp["claim_ids"]  # bound to compiled supporting claim
        assert "可能" in interp["text"]  # interpretive, not source-asserted

    def test_rejected_boundary_dropped_not_retained_as_interpretation(self):
        # probe for the astra-M2-initial-probe finding: rejected boundary
        # evidence must drop the WHOLE entry, never keep it as "interpretation"
        response = full_response()
        response["concepts"][0]["source_defined_boundary"].append(
            {"evidence_claim": "不存在的判断原句"})
        out, _ = run(response=response)
        cand = out["items"][0]
        assert len(cand["source_defined_boundary"]) == 1
        assert any("整条丢弃" in i for i in out["issues"])

    def test_interpretation_without_compiled_support_dropped(self):
        response = full_response()
        response["concepts"][0]["suggested_interpretation"].append(
            {"text": "无支撑的推断", "supporting_claim": "不存在的判断",
             "supporting_context": "证据缺失"})
        out, _ = run(response=response)
        cand = out["items"][0]
        assert all("无支撑的推断" not in item["text"]
                   for item in cand["suggested_interpretation"])
        assert any("supporting_claim" in i for i in out["issues"])

    def test_missing_boundary_evidence_is_limited_not_full(self):
        # near-concept boundary is a MINIMUM requirement: absence => review
        response = full_response()
        response["concepts"][0]["source_defined_boundary"] = []
        out, _ = run(response=response)
        assert out["state"] == "stub"
        cand = out["items"][0]
        assert (cand["status"], cand["stage"]) == ("manual_review", "needs_context")
        assert "边界" in out["reason"]
        assert "范围限制" in out["pages"][0]["content"]

    def test_multiple_distinct_concepts_from_one_call(self):
        second = {
            "name": "定时提醒",
            "aliases": [],
            "definition_claim": BOUNDARY_CLAIM,
            "explanation": "来源在边界讨论中提及，作为回顾触发器的对照。",
            "judgments": [judgment(BOUNDARY_CLAIM, Q_BOUNDARY)],
            "source_defined_boundary": [
                {"evidence_claim": BOUNDARY_CLAIM}],
            "suggested_interpretation": [],
            "related": [], "pending_paths": [],
        }
        response = full_response()
        response["concepts"].append(second)
        out, _ = run(response=response)
        assert out["state"] == "full"
        assert len(out["items"]) == 2
        assert len(out["pages"]) == 2
        names = {c["concept_name"] for c in out["items"]}
        assert names == {"回顾触发器", "定时提醒"}

    def test_exact_duplicate_concept_deduped_with_evidence_union(self):
        # duplicate candidate from a COMPLEMENTARY source: same statement,
        # different evidence — evidence must be UNIONED, sources recomputed
        alt_rel = "tests/fixtures/concept-case/case_source_01.md"
        alt_note = load_note("case_source_01.md")
        response = full_response()
        dup = dict(response["concepts"][0])
        dup["judgments"] = [
            judgment(DEF_CLAIM, Q_DEF),
            judgment(ALIAS_CLAIM, "把当期主题的三本书列成书单",
                     rel=alt_rel, kind="inference")]
        dup["definition_claim"] = DEF_CLAIM
        dup["source_defined_boundary"] = [
            {"evidence_claim": BOUNDARY_CLAIM}]
        dup["suggested_interpretation"] = []
        response["concepts"].append(dup)
        out, _ = run(notes=[load_note(), alt_note], response=response)
        assert out["state"] == "full"
        assert len(out["items"]) == 1
        merged = next(c for c in out["items"][0]["claims"]
                      if c["statement"] == ALIAS_CLAIM)
        assert {e["source"] for e in merged["evidence"]} == {CONCEPT_REL, alt_rel}
        assert set(out["items"][0]["sources"]) == {CONCEPT_REL, alt_rel}
        assert out["items"][0]["source_hashes"].get(alt_rel)
        assert any("新证据已合并" in i for i in out["issues"])
        # persisted state still reloads strictly after the union
        state = parse_card_state(out["pages"][0]["content"])
        claims = read_claims({"claims": state["claims"]})
        documents = []
        for note in (load_note(), alt_note):
            documents.append({"path": note["rel"], "content": note["source_text"],
                              "sha256": note["source_sha256"]})
        assert validate_claims({"claims": state["claims"]}, documents) == claims

    def test_same_alias_different_definitions_flagged_not_merged(self):
        response = full_response()
        response["concepts"].append({
            "name": "另一个概念", "aliases": ["复习钩子"],
            "definition_claim": ALIAS_CLAIM,
            "explanation": "与第一个概念同名别名但定义不同。",
            "judgments": [judgment(ALIAS_CLAIM, Q_ALIAS)],
            "source_defined_boundary": [
                {"evidence_claim": ALIAS_CLAIM}],
            "suggested_interpretation": [],
            "related": [], "pending_paths": [],
        })
        out, _ = run(response=response)
        assert len(out["items"]) == 2  # kept, not merged
        assert any("同义词冲突" in i for i in out["issues"])

    def test_model_owned_metadata_never_trusted(self):
        response = full_response()
        response["schema_version"] = "model-invented"
        response["concepts"][0]["confidence"] = "high"
        out, _ = run(response=response)
        cand = out["items"][0]
        assert cand["schema_version"] == cg.CONCEPT_SCHEMA_VERSION
        assert cand["generator_version"] == cg.CONCEPT_GENERATOR_VERSION
        assert cand["review_required"] is True
        assert cand["confidence"] == "high"  # valid model field, kept


class TestSourceVsInferredRoles:
    """Late-review regressions: mutate ONLY the bound claim's kind against the
    valid fact-role baseline; assert actual rendered role labels."""

    def test_inference_boundary_dropped_not_rendered_as_source(self):
        response = full_response()
        response["concepts"][0]["judgments"][1]["kind"] = "inference"
        out, _ = run(response=response)
        assert out["state"] == "stub"  # no source-defined boundary left
        cand = out["items"][0]
        assert cand["source_defined_boundary"] == []
        body = parse_frontmatter(out["pages"][0]["content"])[1]
        assert BOUNDARY_CLAIM not in body.split("## 判断与证据")[0]
        assert any("不能作为来源定义边界" in i for i in out["issues"])

    def test_inference_definition_labeled_not_source_definition(self):
        # a model abstraction may define the concept, but visibly as 建议性定义
        response = full_response()
        response["concepts"][0]["judgments"][0]["kind"] = "inference"
        out, _ = run(response=response)
        assert out["state"] == "full"  # fact boundary still supports full
        body = out["pages"][0]["content"]
        assert "## 建议性定义（模型推断）" in body
        assert "## 概念定义" not in body
        assert DEF_CLAIM in body  # bound canonical statement kept
        # kind persisted through the existing claims (no schema change)
        state = parse_card_state(out["pages"][0]["content"])
        kind = next(c["kind"] for c in state["claims"]
                    if c["statement"] == DEF_CLAIM)
        assert kind == "inference"

    def test_fact_definition_keeps_plain_source_heading(self):
        out, _ = run()
        body = out["pages"][0]["content"]
        assert "## 概念定义" in body
        assert "建议性定义" not in body


class TestUpstreamSourceMetadata:
    def test_upstream_limitations_survive_model_omission(self):
        # program-provided limitations are included in the payload, persisted
        # and rendered even when the model omits them; model cannot erase them
        note = load_note(metadata={"upstream_analysis": {
            "source_kind": "团队自报统计",
            "limitations": ["上游标注：数字未经独立核对"],
            "speakers": ["合成团队负责人"]}})
        response = full_response()
        response["provenance_map"] = [{"rel": CONCEPT_REL,
                                       "provenance": "合成概念素材",
                                       "limitations": []}]
        out, provider = run(notes=[note], response=response)
        payload = provider.calls["payload"]
        assert payload["upstream_source_analysis"][0]["limitations"] == \
            ["上游标注：数字未经独立核对"]
        entry = out["items"][0]["provenance_map"][0]
        assert entry["source_kind"] == "团队自报统计"
        assert "上游标注：数字未经独立核对" in entry["limitations"]
        body = out["pages"][0]["content"]
        assert "上游标注：数字未经独立核对" in body
        assert "团队自报统计" in body

    def test_model_cannot_overwrite_upstream_classification_or_limit(self):
        note = load_note(metadata={"upstream_analysis": {
            "source_kind": "读书会纪要",
            "limitations": ["上游限制A"]}})
        response = full_response()
        out, _ = run(notes=[note], response=response)
        entry = out["items"][0]["provenance_map"][0]
        assert entry["source_kind"] == "读书会纪要"
        assert "上游限制A" in entry["limitations"]

    def test_arbitrary_metadata_is_not_transmitted(self):
        note = load_note(metadata={"secret_index_dump": "x" * 5000,
                                   "upstream_analysis": "not-a-dict"})
        out, provider = run(notes=[note])
        payload = provider.calls["payload"]
        assert "secret_index_dump" not in json.dumps(payload)
        assert "upstream_source_analysis" not in payload
        assert out["state"] == "full"  # generation itself unaffected


class TestLinksAndSafety:
    def test_related_only_to_known_paths(self):
        response = full_response()
        response["concepts"][0]["related"] = ["wiki/concepts/review-trigger.md",
                                              "wiki/invented/target.md"]
        out, _ = run(response=response,
                     known_paths=["wiki/concepts/review-trigger.md"])
        cand = out["items"][0]
        assert cand["related"] == ["wiki/concepts/review-trigger.md"]
        assert "wiki/invented/target.md" in cand["pending_links"]
        assert "[[wiki/invented/target.md]]" not in out["pages"][0]["content"]

    def test_freeform_wikilinks_sanitized_everywhere(self):
        response = full_response()
        response["concepts"][0]["explanation"] = "嵌套 [[wiki/another]] 引用"
        response["concepts"][0]["suggested_interpretation"][0]["text"] = \
            "见 [[wiki/fake.md]] 的推断"
        out, _ = run(response=response)
        body = out["pages"][0]["content"]
        assert "[[wiki/fake.md]]" not in body
        assert "[[wiki/another]]" not in body
        assert any("链接语法" in i for i in out["issues"])

    def test_rendered_list_items_on_own_lines(self):
        # trim_blocks/newline-concatenation probe (topic had this bug)
        out, _ = run()
        body = out["pages"][0]["content"]
        assert f"## 概念定义\n\n{DEF_CLAIM}\n" in body
        assert "\n- 该机制可能提高卡片长期再访问率" in body
        assert "\n  - 支撑语境：" in body

    def test_body_uses_ordinal_refs_machine_ids_stay_in_card_state(self):
        # presentation check: visible body carries human-readable ordinal
        # evidence references; opaque claim IDs exist ONLY in card_state and
        # reload validation still passes
        out, _ = run()
        meta, body = parse_frontmatter(out["pages"][0]["content"])
        assert "claim:" not in body
        assert "依据判断" not in body and "权威文字" not in body
        assert "（证据 " in body and "证据 2）" in body  # ordinals from render order
        assert "来源中的边界" in body and "概念定义" in body
        state = parse_card_state(out["pages"][0]["content"])
        assert all(c["claim_id"].startswith("claim:") for c in state["claims"])
        claims = read_claims({"claims": state["claims"]})
        raw = (FIXTURES / "concept_source_01.md").read_bytes().decode("utf-8")
        documents = [{"path": CONCEPT_REL, "content": raw,
                      "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}]
        assert validate_claims({"claims": state["claims"]}, documents) == claims

    def test_unsafe_paths_rejected_bounded(self):
        for bad in ("C:\\abs\\path.md", "../escape.md", "wiki\\slash.md",
                    "wiki/../traverse.md", "raw//x.md", "/abs/root.md",
                    "wiki/x\x01.md"):
            out, provider = run(notes=[load_note(rel=bad)])
            assert out["state"] == "error", bad
            assert provider.calls["count"] == 0, bad

    def test_secret_in_payload_blocked_pre_call(self):
        note = load_note()
        note["body"] += " api_key = sk-abcdefghijklmnopqrs12345"
        note["source_text"] = note["body"]
        note["source_sha256"] = hashlib.sha256(note["source_text"].encode()).hexdigest()
        out, provider = run(notes=[note])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_secret_in_response_blocked_post_call(self):
        def secret_provider(cfg, system_prompt, payload):
            data = full_response()
            data["concepts"][0]["explanation"] = "password = hunter2secretvalue"
            return json.dumps(data, ensure_ascii=False)
        out = cg.generate_concepts([load_note()], CFG, call_provider=secret_provider)
        assert out["state"] == "error"
        assert "hunter2secretvalue" not in out["reason"]


class TestZeroStubError:
    def test_explicit_no_concept_is_legitimate_zero(self):
        out, _ = run(response={"concept_found": False,
                               "reason": "素材中没有可提取的概念，只有闲聊记录"})
        assert out["state"] == "zero"
        assert out["items"] == [] and out["pages"] == []
        assert "闲聊" in out["reason"]

    def test_chatter_fixture_is_zero(self):
        out, _ = run(notes=[load_note("neg_chatter.md")],
                     response={"concept_found": False, "reason": "素材无概念"})
        assert out["state"] == "zero"

    def test_missing_concept_found_is_error_not_zero(self):
        response = full_response()
        del response["concept_found"]
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert "concept_found" in out["reason"]

    def test_no_substance_is_zero(self):
        out, _ = run(notes=[load_note("neg_empty.md")])
        assert out["state"] == "zero"
        assert "无实质内容" in out["reason"]

    def test_all_evidence_rejected_is_error(self):
        response = full_response()
        for j in response["concepts"][0]["judgments"]:
            j["evidence"][0]["quote"] = "这句话不在任何来源里"
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert "已编译判断" in out["reason"]

    def test_invented_evidence_source_rejected_claim_dropped(self):
        response = full_response()
        response["concepts"][0]["judgments"].append(
            judgment("伪造路径判断", "任意", rel="raw/不存在的路径.md"))
        out, _ = run(response=response)
        assert out["state"] == "full"  # honest claims survive
        assert len(out["claims"]) == 4
        assert sum("证据编译失败" in i for i in out["issues"]) == 1

    def test_repeated_quote_requires_start_line(self):
        note = load_note("neg_repeated_quote.md")
        rel = note["rel"]
        raw = note["source_text"]
        line = next(i + 1 for i, l in enumerate(raw.splitlines())
                    if "同样的句子在文件里出现两次" in l)
        response = {"concept_found": True,
                    "concepts": [{
                        "name": "重复片段概念", "aliases": [],
                        "definition_claim": "无提示判断",
                        "explanation": "测试。",
                        "judgments": [judgment("无提示判断", "同样的句子在文件里出现两次。",
                                               rel=rel)],
                        "source_defined_boundary": [
                            {"evidence_claim": "无提示判断"}],
                        "suggested_interpretation": [],
                        "related": [], "pending_paths": []}],
                    "provenance_map": [{"rel": rel, "provenance": "p", "limitations": []}],
                    "shared_provenance": []}
        cfg = {"concept_generation": {"max_source_chars": 20000,
                                      "max_context_chars": 60000}}
        out, _ = run(response=response, notes=[note], cfg=cfg)
        assert out["state"] == "error"
        assert any("位置不唯一" in i or "编译失败" in i for i in out["issues"])
        response["concepts"][0]["judgments"][0]["evidence"][0]["start_line"] = line
        out2, _ = run(response=response, notes=[note], cfg=cfg)
        assert out2["state"] == "full"
        assert len(out2["claims"]) == 1

    def test_refused_input_no_provider_call(self):
        out, provider = run(notes=[load_note(drop_text=True)])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_hash_mismatch_refuses_note(self):
        out, _ = run(notes=[load_note(corrupt_hash=True)])
        assert out["state"] == "error"
        assert any("不匹配" in i for i in out["issues"])

    def test_oversized_source_no_call_no_truncation(self):
        cfg = {"concept_generation": {"max_source_chars": 10,
                                      "max_context_chars": 60000}}
        out, provider = run(cfg=cfg)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "max_source_chars" in out["reason"]

    def test_whole_payload_budget_includes_known_paths(self):
        huge_known = [f"wiki/objects/object-{i:05d}.md" for i in range(3000)]
        out, provider = run(known_paths=huge_known)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "max_context_chars" in out["reason"]

    def test_invalid_config_rejected(self):
        out, _ = run(cfg={"concept_generation": {"max_source_chars": "20000"}})
        assert out["state"] == "error"

    def test_non_llm_mode_is_honest(self):
        out, provider = run(analysis_mode="heuristic")
        assert out["state"] == "disabled"
        assert provider.calls["count"] == 0
        assert "非 LLM" in out["reason"]

    def test_provider_failure_surfaces_without_retry(self):
        def failing(cfg, system_prompt, payload):
            raise RuntimeError("boom")
        out = cg.generate_concepts([load_note()], CFG, call_provider=failing)
        assert out["state"] == "error"
        assert "boom" in out["reason"]

    def test_malformed_json_is_error(self):
        out = cg.generate_concepts([load_note()], CFG,
                                   call_provider=lambda c, s, p: "这不是 JSON")
        assert out["state"] == "error"
        assert "JSON" in out["reason"]

    def test_refused_source_keeps_coverage_partial(self):
        notes = [load_note(), load_note("neg_chatter.md", corrupt_hash=True)]
        out, _ = run(notes=notes)
        assert out["items"]
        assert out["analysis"]["coverage"] == "partial"
        assert any("不匹配" in i for i in out["issues"])


class TestSchemaRegistration:
    def test_concept_schema_loaded_from_file_single_truth(self):
        from core.card_contracts import _STORE, register_card_schema, validate_card_item
        # bad pairing rejected by the canonical schema
        issues = validate_card_item({"type": "concept-page", "status": "growing",
                                     "stage": "needs_context"}, "concept-page")
        assert issues
        # The M0 placeholder test (test_card_contracts) registers a stub with
        # the same $id into the global store; re-register the canonical FILE
        # contents and compare — single truth is the file on disk.
        on_disk = json.loads(cg._SCHEMA_PATH.read_text(encoding="utf-8-sig")
                             .replace("\r\n", "\n"))
        register_card_schema(on_disk)
        assert _STORE.get("concept-page.schema.json") == on_disk
        # canonical strictness holds after (re-)registration
        assert validate_card_item({"type": "concept-page", "status": "growing",
                                   "stage": "needs_context"}, "concept-page")

    def test_states_and_hashes_preserved_in_frontmatter(self):
        out, _ = run()
        meta, _ = parse_frontmatter(out["pages"][0]["content"])
        assert meta["source_hashes"] == {CONCEPT_REL: load_note()["source_sha256"]}
        assert meta["coverage"] == "full"
