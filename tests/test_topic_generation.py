"""M3/T7 topic generator tests (post first Astra review).

All fixtures are the public synthetic card-baseline materials; the provider is
always a fake — no network, no real model, no private vault access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core import topic_generation as tg
from core.claims import read_claims, validate_claims
from core.vault import parse_frontmatter

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "card-baseline"
CASE_FAMILY = [
    "project_case_01.md",
    "project_case_01_followup.md",
    "project_case_01_counterexample.md",
]
CASE_RELS = [f"tests/fixtures/card-baseline/{n}" for n in CASE_FAMILY]
QUESTION = "三段转化链（现场体验→具象清单→低成本回访）在什么条件下有效、在什么条件下失效？"
CFG = {"topic_generation": {"min_full_sources": 3, "max_source_chars": 20000,
                            "max_context_chars": 60000}}


def load_note(name: str, *, corrupt_hash: bool = False, drop_text: bool = False) -> dict:
    raw = (FIXTURES / name).read_text(encoding="utf-8")  # keeps BOM/CRLF as-is
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if corrupt_hash:
        sha = "0" * 64
    return {
        "rel": f"tests/fixtures/card-baseline/{name}",
        "title": name,
        "body": raw,
        "metadata": {"material_kind": "synthetic"},
        "source_text": "" if drop_text else raw,
        "source_sha256": sha,
    }


def fake_provider(payload_builder):
    """Provider returning JSON from payload_builder (dict or 0/1-arg callable)."""
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


def judgment(rel: str, statement: str, quote: str, *, kind: str = "fact",
             confidence: str = "medium", start_line: int | None = None,
             relation: str = "supports") -> dict:
    evidence = {"source": rel, "quote": quote, "relation": relation}
    if start_line is not None:
        evidence["start_line"] = start_line
    return {"statement": statement, "kind": kind, "confidence": confidence,
            "evidence": [evidence]}


def full_response():
    case, follow, counter = CASE_RELS
    return {
        "topic_viable": True,
        "title": "三段转化链的有效与失效条件（合成案例族）",
        "theme_boundary": "围绕三段转化链的机制、生效条件与失败条件。",
        "summary": "案例、复核与反例共同刻画了转化链的边界。",
        "confidence": "medium",
        "source_map": [
            {"rel": case, "provenance": "店主自述台账（合成）", "limitations": ["无对照组", "数字未核实"]},
            {"rel": follow, "provenance": "财务顾问复核（合成）", "limitations": ["口径差异"]},
            {"rel": counter, "provenance": "读书会组织者自述（合成）", "limitations": ["无第三方核验"]},
        ],
        "shared_provenance": [],
        "judgments": [
            judgment(case, "绑定书单后活动参与者图书转化率（当晚口径，未核实）从约4%升至11%",
                     "活动参与者的图书转化率从原来的约 4% 上升到 11%"),
            judgment(follow, "30 天口径下活动参与者转化率约 6.5%，与日常约 5% 接近",
                     "活动参与者在活动后 30 天内的图书转化率约为 6.5%，非活动期日常转化率约 5%"),
            judgment(counter, "照搬链条后两段且缺少销售语境的尝试失败（点击率约 3%，转化近零）",
                     "书单链接的点击率约为 3%，购书转化几乎为零"),
            # interpretation-disagreement sides: each speaker's own stated position
            judgment(follow, "店主认为活动当场本来就该单独算，当晚口径才是机制的直接体现",
                     '店主则认为"活动当场本来就该单独算，当晚口径才是机制的直接体现"'),
            judgment(follow, "财务顾问认为三段转化链可能有正效应，但当晚口径夸大了它",
                     '财务顾问的解读是：三段转化链"可能有正效应，但当晚口径夸大了它"'),
        ],
        "tensions": [
            {"statement": "当晚口径 11% 与 30 天口径 6.5% 对机制效果的读数不同",
             "classification": "context_difference",
             "sources": [case, follow],
             "claim_statements": ["绑定书单后活动参与者图书转化率（当晚口径，未核实）从约4%升至11%",
                                  "30 天口径下活动参与者转化率约 6.5%，与日常约 5% 接近"],
             "note": "测量窗口与分母差异，属口径不同，不是数据矛盾"},
            {"statement": "原案例（店主台账自报）记录当晚转化率上升，反例（组织者自述）记录"
                          "照搬后转化近零——记录场景与条件不同",
             "classification": "context_difference",
             "sources": [case, counter],
             "claim_statements": ["绑定书单后活动参与者图书转化率（当晚口径，未核实）从约4%升至11%",
                                  "照搬链条后两段且缺少销售语境的尝试失败（点击率约 3%，转化近零）"],
             "note": "均为自报/记录值（未核实），场景与适用条件不同，"
                     "未建立受控因果效果，不构成同一对象上的事实冲突"},
            {"statement": "店主与财务顾问就当晚口径的量级解读存在分歧（双方均有原话记录，语义待人工复核）",
             "classification": "unverified_tension",
             "sources": [follow],
             "claim_statements": ["店主认为活动当场本来就该单独算，当晚口径才是机制的直接体现",
                                  "财务顾问认为三段转化链可能有正效应，但当晚口径夸大了它"],
             "note": "同一来源内记录的双方解读分歧；双方均同意现有台账无法裁决，"
                     "缺乏裁决性证据，不定为事实冲突"},
        ],
        "evidence_gaps": [{"gap": "缺乏错峰或对照条件下的效果记录", "affected": ["量级分歧"]},
                          {"gap": "线下课程等非销售可关联场景未检验", "affected": ["适用范围"]}],
        "next_actions": [{"action": "补齐错峰对照记录以裁决量级分歧", "priority": 1,
                          "addresses_gap": "缺乏错峰或对照条件下的效果记录"},
                         {"action": "收集线下课程等场景的应用记录以检验适用范围", "priority": 2,
                          "addresses_gap": "线下课程等非销售可关联场景未检验"}],
        "related": [], "pending_paths": [],
    }


def copies_response():
    """Model payload coherent with three path-distinct but byte-identical notes."""
    return {
        "topic_viable": True,
        "title": "三段转化链机制记录（合成）",
        "theme_boundary": "转化链机制的行动、结果与边界。",
        "summary": "三条路径记录同一机制的机制叙述、边界与依赖。",
        "confidence": "medium",
        "source_map": [
            {"rel": "wiki/a.md", "provenance": "案例叙述（合成）", "limitations": ["未核实数字"]},
            {"rel": "wiki/b.md", "provenance": "同上记录的复制", "limitations": ["未核实数字"]},
            {"rel": "wiki/c.md", "provenance": "同上记录的复制", "limitations": ["未核实数字"]},
        ],
        "shared_provenance": ["三条记录内容相同"],
        "judgments": [
            judgment("wiki/a.md", "绑定书单后活动参与者图书转化率（未核实）从约4%升至11%",
                     "活动参与者的图书转化率从原来的约 4% 上升到 11%"),
            judgment("wiki/b.md", "机制依赖活动主题与商品存在天然关联",
                     "该机制依赖活动主题与商品存在天然关联"),
            judgment("wiki/c.md", "主讲人共创环节的推荐语质量在规模化后不可控",
                     "主讲人共创环节依赖主讲人配合意愿，规模化后推荐语质量不可控"),
        ],
        "tensions": [],
        "evidence_gaps": [{"gap": "缺少对照组数据"}],
        "next_actions": [{"action": "补充对照组销售记录", "priority": 1,
                          "addresses_gap": "缺少对照组数据"}],
        "related": [], "pending_paths": [],
    }


def stub_response():
    """Model payload scoped EXACTLY to the two-source input set: no references
    to the absent counterexample anywhere (map, judgments, tensions, summary)."""
    case, follow = CASE_RELS[0], CASE_RELS[1]
    return {
        "topic_viable": True,
        "title": "三段转化链的有效条件：案例与测量复核（合成，受限）",
        "theme_boundary": "围绕转化链在书店场景中的行动与结果测量口径。",
        "summary": "案例与后续复核记录了转化链使用场景中的转化率变化与测量口径差异"
                   "（数字为记录值，未核实，不构成因果效果证明）；"
                   "失效条件因缺少反例素材本专题暂不覆盖。",
        "confidence": "low",
        "source_map": [
            {"rel": case, "provenance": "店主自述台账（合成）", "limitations": ["无对照组", "数字未核实"]},
            {"rel": follow, "provenance": "财务顾问复核（合成）", "limitations": ["口径差异"]},
        ],
        "shared_provenance": ["两条素材同属虚构青梧书店案例族，共享同一背景设定"],
        "judgments": [
            judgment(case, "绑定书单后活动参与者图书转化率（当晚口径，未核实）从约4%升至11%",
                     "活动参与者的图书转化率从原来的约 4% 上升到 11%"),
            judgment(follow, "30 天口径下活动参与者转化率约 6.5%，与日常约 5% 接近",
                     "活动参与者在活动后 30 天内的图书转化率约为 6.5%，非活动期日常转化率约 5%"),
        ],
        "tensions": [{
            "statement": "当晚口径 11% 与 30 天口径 6.5% 对机制效果的读数不同",
            "classification": "context_difference",
            "sources": [case, follow],
            "claim_statements": ["绑定书单后活动参与者图书转化率（当晚口径，未核实）从约4%升至11%",
                                 "30 天口径下活动参与者转化率约 6.5%，与日常约 5% 接近"],
            "note": "测量窗口差异，属口径不同",
        }],
        "evidence_gaps": [{"gap": "缺乏错峰或对照条件下的效果记录", "affected": ["量级分歧"]},
                          {"gap": "缺少失效场景素材，无法评估失效条件", "affected": ["适用范围"]}],
        "next_actions": [
            {"action": "补充对照或错峰销售记录", "priority": 1,
             "addresses_gap": "缺乏错峰或对照条件下的效果记录"},
            {"action": "收集失效场景的素材以扩展专题", "priority": 2,
             "addresses_gap": "缺少失效场景素材，无法评估失效条件"},
        ],
        "related": [], "pending_paths": [],
    }


def run(response=None, notes=None, cfg=CFG, **kwargs):
    provider = fake_provider(response if response is not None else full_response)
    out = tg.generate_topic(QUESTION, cfg, notes if notes is not None
                            else [load_note(n) for n in CASE_FAMILY],
                            call_provider=provider, now="2026-09-21", **kwargs)
    return out, provider


def parse_card_state(content: str) -> dict:
    meta, _ = parse_frontmatter(content)
    state = meta["card_state"]
    if isinstance(state, str):
        state = json.loads(state)
    return state


class TestFullTopic:
    def test_full_topic_from_case_family(self):
        out, _ = run()
        assert out["state"] == "full"
        assert out["candidate"]["type"] == "topic-page"
        assert out["candidate"]["status"] == "growing"
        assert out["candidate"]["stage"] == "assembling"
        assert len(out["candidate"]["source_map"]) == 3
        assert all(entry["provenance"] for entry in out["candidate"]["source_map"])
        assert out["candidate"]["analysis_mode"] == "llm"
        assert out["candidate"]["schema_version"] == tg.TOPIC_SCHEMA_VERSION
        assert len(out["claims"]) == 5
        kinds = {t["classification"] for t in out["candidate"]["tensions"]}
        assert kinds == {"context_difference", "unverified_tension"}
        # applicability difference is NOT labeled real_conflict
        by_stmt = {t["statement"]: t for t in out["candidate"]["tensions"]}
        assert by_stmt["原案例（店主台账自报）记录当晚转化率上升，反例（组织者自述）记录"
                       "照搬后转化近零——记录场景与条件不同"][
            "classification"] == "context_difference"
        # the interpretation tension is backed by the two speaker-position claims
        interp = by_stmt["店主与财务顾问就当晚口径的量级解读存在分歧（双方均有原话记录，语义待人工复核）"]
        assert interp["classification"] == "unverified_tension"
        speaker_ids = {c["claim_id"] for c in out["claims"]
                       if "店主认为活动当场" in c["statement"]
                       or "财务顾问认为" in c["statement"]}
        assert set(interp["claim_ids"]) == speaker_ids
        assert set(out["analysis"]["usable_sources"]) == set(CASE_RELS)

    def test_page_renders_with_contract_frontmatter(self):
        out, _ = run()
        meta, _ = parse_frontmatter(out["page"]["content"])
        assert meta["type"] == "topic-page"
        assert meta["status"] == "growing"
        assert meta["stage"] == "assembling"
        assert meta["schema_version"] == tg.TOPIC_SCHEMA_VERSION
        assert meta["analysis_mode"] == "llm"
        assert meta["coverage"] == "full"
        assert len(meta["source_hashes"]) == 3
        assert meta["review_required"] == "true"
        body = out["page"]["content"]
        assert "三段转化链" in body
        assert "证据缺口" in body
        assert "生成质量标注" in body

    def test_card_state_persisted_and_reloadable_from_rendered_page(self):
        out, _ = run()
        meta, _ = parse_frontmatter(out["page"]["content"])
        state = parse_card_state(out["page"]["content"])
        assert state["version"] == tg.CARD_STATE_VERSION
        assert state["type"] == "topic-page"
        # persisted claims equal returned claims and reload strictly
        assert state["claims"] == out["claims"]
        claims = read_claims({"claims": state["claims"]})
        assert len(claims) == 5
        # validate against the SAME original snapshots (raw fixture bytes)
        documents = [{"path": rel, "content": (FIXTURES / name).read_text(encoding="utf-8"),
                      "sha256": hashlib.sha256(
                          (FIXTURES / name).read_bytes()).hexdigest()}
                     for rel, name in zip(CASE_RELS, CASE_FAMILY)]
        assert validate_claims({"claims": state["claims"]}, documents) == claims
        assert state["analysis"] == out["analysis"]

    def test_response_following_exact_prompt_contract_passes(self):
        # Regression: a response using ONLY fields declared in output_contract
        # must compile; nothing silently richer.
        response = full_response()
        assert all(e.get("relation") in ("supports", "contradicts")
                   for j in response["judgments"] for e in j["evidence"])
        out, _ = run(response=response)
        assert out["state"] == "full"

    def test_model_owned_metadata_never_trusted(self):
        response = full_response()
        response["schema_version"] = "model-invented"
        out, _ = run(response=response)
        cand = out["candidate"]
        assert cand["schema_version"] == tg.TOPIC_SCHEMA_VERSION
        assert cand["generator_version"] == tg.TOPIC_GENERATOR_VERSION
        assert cand["review_required"] is True

    def test_actions_ordered_by_priority(self):
        response = full_response()
        response["evidence_gaps"].append({"gap": "回访点击与购买的链路数据缺失"})
        response["next_actions"] = [
            {"action": "第二优先：补链路数据", "priority": 2,
             "addresses_gap": "回访点击与购买的链路数据缺失"},
            {"action": "第一优先：补对照记录", "priority": 1,
             "addresses_gap": "缺乏错峰或对照条件下的效果记录"},
        ]
        out, _ = run(response=response)
        assert out["state"] == "full"
        assert out["candidate"]["next_actions"][0]["action"].startswith("第一优先")


class TestStubZeroAndCoverage:
    def test_single_source_full_coverage_is_insufficient_stub(self):
        # read coverage full, source sufficiency insufficient: separate states
        response = full_response()
        response["judgments"] = [response["judgments"][0]]
        response["source_map"] = [response["source_map"][0]]
        response["tensions"] = []
        out, _ = run(response=response, notes=[load_note(CASE_FAMILY[0])])
        assert out["state"] == "stub"
        assert out["candidate"]["coverage"] == "full"  # fully read single source
        assert out["candidate"]["status"] == "manual_review"
        assert out["candidate"]["stage"] == "insufficient"
        assert "少于" in out["reason"]
        meta, _ = parse_frontmatter(out["page"]["content"])
        assert meta["coverage"] == "full"
        assert meta["status"] == "manual_review"
        assert "受限" in out["page"]["content"]

    def test_refused_source_keeps_coverage_partial(self):
        # 3 supplied, 1 refused: survivors cannot magically regain full coverage
        notes = [load_note(CASE_FAMILY[0]), load_note(CASE_FAMILY[1]),
                 load_note(CASE_FAMILY[2], corrupt_hash=True)]
        out, provider = run(notes=notes)
        assert out["state"] == "stub"
        assert out["candidate"]["coverage"] == "partial"
        assert any("不匹配" in i for i in out["issues"])
        assert "少于" in out["reason"]

    def test_shared_provenance_note_alone_keeps_full_with_limitation(self):
        # The approved case family: three distinct records about one bookstore.
        # A disclosed shared-background note caps confidence but is NOT a
        # blanket ban on a full topic.
        response = full_response()
        response["shared_provenance"] = ["三条素材同属虚构青梧书店案例族，共享同一背景设定"]
        response["confidence"] = "high"
        out, _ = run(response=response)
        assert out["state"] == "full"
        assert out["candidate"]["shared_provenance"]
        assert out["candidate"]["confidence"] == "medium"  # capped, not high
        assert any("共享" in i for i in out["issues"])
        assert "共享" in out["page"]["content"]  # disclosure visible

    def test_three_byte_identical_copies_collapse_to_stub(self):
        shared = load_note(CASE_FAMILY[0])
        notes = [dict(shared, rel=p) for p in ("wiki/a.md", "wiki/b.md", "wiki/c.md")]
        out, _ = run(response=copies_response(), notes=notes)
        assert out["state"] == "stub"
        assert out["candidate"]["shared_provenance"]
        assert "少于" in out["reason"]

    def test_explicit_same_original_identity_collapses(self):
        shared = load_note(CASE_FAMILY[0])
        notes = [dict(shared, rel=p, metadata={"original_source_id": "src-1"})
                 for p in ("wiki/a.md", "wiki/b.md", "wiki/c.md")]
        out, _ = run(response=copies_response(), notes=notes)
        assert out["state"] == "stub"
        assert "少于" in out["reason"]

    def test_three_sources_but_only_one_cited_is_not_full(self):
        response = full_response()
        response["judgments"] = [response["judgments"][0]]
        response["tensions"] = []
        out, _ = run(response=response)
        assert out["state"] == "stub"  # usable (cited) sources = 1 < 3

    def test_zero_claims_is_error_not_stub(self):
        response = full_response()
        for j in response["judgments"]:
            j["evidence"][0]["quote"] = "这句话不在任何来源里"
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert out["page"] is None and out["candidate"] is None
        assert "判断通过证据编译" in out["reason"]

    def test_missing_topic_viable_is_error_not_zero(self):
        response = {"title": "t", "summary": "s", "theme_boundary": "b",
                    "source_map": [], "judgments": [], "tensions": [],
                    "evidence_gaps": [], "next_actions": []}
        out, _ = run(response=response)
        assert out["state"] == "error"
        assert "topic_viable" in out["reason"]

    def test_explicit_false_viable_is_legitimate_zero(self):
        out, _ = run(response={"topic_viable": False, "reason": "素材与该研究问题无关"})
        assert out["state"] == "zero"
        assert out["reason"] == "素材与该研究问题无关"

    def test_gaps_and_actions_render_as_separate_lines(self):
        # Regression: inline Jinja if/end blocks used to eat newlines under
        # trim_blocks, concatenating consecutive gap/action items into one line.
        out, _ = run()
        body = out["page"]["content"].splitlines()
        gap_lines = [ln for ln in body
                     if ln.startswith("- ") and ("效果记录" in ln or "链路数据" in ln
                                                 or "错峰" in ln)]
        action_lines = [ln for ln in body if ln.startswith("- 1. ") or ln.startswith("- 2. ")]
        assert len(gap_lines) >= 1
        # each item occupies its own rendered line; no concatenated "）- " seams
        assert not any("）- " in ln for ln in body)
        for ln in action_lines:
            assert ln.count(". ") >= 1 and ln.startswith("- ")
        # scoped stub likewise renders two actions on two real lines
        stub, _ = run(response=stub_response(),
                      notes=[load_note(CASE_FAMILY[0]), load_note(CASE_FAMILY[1])])
        stub_body = stub["page"]["content"].splitlines()
        assert sum(1 for ln in stub_body if ln.startswith("- 1. 补充")
                   or ln.startswith("- 2. 收集")) == 2
        assert sum(1 for ln in stub_body if ln.startswith("- 缺乏")
                   or ln.startswith("- 缺少")) == 2

    def test_clean_scoped_stub_page(self):
        out, _ = run(response=stub_response(),
                     notes=[load_note(CASE_FAMILY[0]), load_note(CASE_FAMILY[1])])
        assert out["state"] == "stub"
        assert len(out["claims"]) == 2
        body = out["page"]["content"]
        assert "拾光读书会" not in body
        assert CASE_RELS[2] not in body
        assert "照搬链条" not in body  # no dead counterexample narrative
        assert "暂不覆盖" in body  # scope limitation stated instead

    def test_unrelated_evidence_is_zero_with_reason(self):
        out, _ = run(response={"topic_viable": False, "reason": "素材与该研究问题无关"})
        assert out["state"] == "zero"
        assert out["reason"] == "素材与该研究问题无关"
        assert out["candidate"] is None

    def test_no_substance_is_zero(self):
        out, _ = run(notes=[load_note("neg_empty.md")])
        assert out["state"] == "zero"
        assert "无实质内容" in out["reason"]


class TestEvidenceIntegrity:
    def test_fake_evidence_rejected(self):
        response = full_response()
        response["judgments"].append(judgment(CASE_RELS[0], "伪造判断", "这句话根本不在来源里"))
        response["judgments"].append(judgment("raw/不存在的路径.md", "伪造路径判断", "任意"))
        out, _ = run(response=response)
        assert out["state"] == "full"  # the five honest claims still stand
        assert len(out["claims"]) == 5
        assert sum("证据编译失败" in i for i in out["issues"]) == 2

    def test_duplicate_quote_requires_start_line(self):
        text = "重复粘贴标记\n\n同样的句子出现两次。\n中间填充。\n同样的句子出现两次。\n结尾"
        note = {"rel": "tests/fixtures/card-baseline/neg_repeated_quote.md",
                "title": "重复", "body": text, "metadata": {},
                "source_text": text,
                "source_sha256": hashlib.sha256(text.encode()).hexdigest()}
        response = {"topic_viable": True, "title": "t", "theme_boundary": "b",
                    "summary": "s", "confidence": "low",
                    "source_map": [{"rel": note["rel"], "provenance": "p",
                                    "limitations": []}],
                    "shared_provenance": [],
                    "judgments": [judgment(note["rel"], "无提示判断", "同样的句子出现两次。")],
                    "tensions": [],
                    "evidence_gaps": [{"gap": "g"}],
                    "next_actions": [{"action": "补充对照记录", "priority": 1,
                                      "addresses_gap": "g"}],
                    "related": [], "pending_paths": []}
        cfg = {"topic_generation": {"min_full_sources": 3}}
        out, _ = run(response=response, notes=[note], cfg=cfg)
        # the only judgment failed to compile -> zero claims -> bounded error
        assert out["state"] == "error"
        assert any("位置不唯一" in i or "编译失败" in i for i in out["issues"])
        response["judgments"] = [judgment(note["rel"], "有提示判断", "同样的句子出现两次。",
                                          start_line=5)]
        out2, _ = run(response=response, notes=[note], cfg=cfg)
        assert len(out2["claims"]) == 1

    def test_both_sides_supports_quotes_are_valid_evidence(self):
        # a supports quote for claim A and a supports quote for opposing claim B
        # is valid evidence of both recorded statements — no global relation gate.
        # ENGINE coverage only: the exemplar labels this unverified_tension; the
        # test explicitly overrides to real_conflict to exercise the mechanism.
        response = full_response()
        response["judgments"][2]["evidence"][0]["relation"] = "supports"
        response["tensions"][2]["classification"] = "real_conflict"
        out, _ = run(response=response)
        conflict = [t for t in out["candidate"]["tensions"]
                    if t["classification"] == "real_conflict"][0]
        cited = {c["claim_id"] for c in out["claims"] if c["claim_id"] in conflict["claim_ids"]}
        assert len(cited) == 2  # both sides traceable to distinct compiled claims
        claims = read_claims({"claims": out["claims"]})
        assert all(c.evidence for c in claims if c.claim_id in cited)
        # the program never claims machine semantic verification
        assert "待人工复核" in tg._CLASSIFICATION_LABELS["real_conflict"]
        assert "未经程序核实" in out["page"]["content"]

    def test_agreeing_pair_proposed_as_opposed_stays_review_required(self):
        # two agreeing claims proposed as opposed: state remains
        # semantic-review-required, never a confirmed contradiction
        response = full_response()
        response["judgments"][2]["evidence"][0]["relation"] = "supports"
        response["tensions"] = [{
            "statement": "两条一致的支持性判断被提议为对立",
            "classification": "real_conflict",
            "sources": [CASE_RELS[0], CASE_RELS[2]],
            "claim_statements": [response["judgments"][0]["statement"],
                                 response["judgments"][2]["statement"]],
        }]
        out, _ = run(response=response)
        conflict = [t for t in out["candidate"]["tensions"]
                    if t["classification"] == "real_conflict"]
        assert conflict  # retained as model-proposed, not machine-confirmed
        assert "待人工复核" in tg._CLASSIFICATION_LABELS["real_conflict"]

    def test_unsided_tension_dropped_whole(self):
        # both cited statements resolve to ONE compiled claim -> unusable,
        # dropped entirely (never downgraded into the narrative)
        response = full_response()
        response["tensions"] = [{
            "statement": "同一判断重复引用制造双方假象",
            "classification": "real_conflict",
            "sources": [CASE_RELS[0]],
            "claim_statements": [response["judgments"][0]["statement"],
                                 response["judgments"][0]["statement"]],
        }]
        out, _ = run(response=response)
        assert out["candidate"]["tensions"] == []
        assert any("丢弃" in i for i in out["issues"])

    def test_context_difference_without_claims_dropped(self):
        response = full_response()
        response["tensions"] = [{
            "statement": "口径差异但未引用任何判断",
            "classification": "context_difference",
            "sources": [CASE_RELS[0]], "claim_statements": [],
        }]
        out, _ = run(response=response)
        assert out["candidate"]["tensions"] == []
        assert any("仅保留在诊断信息中" in i for i in out["issues"])

    def test_tension_with_rejected_source_dropped_not_trimmed(self):
        # the referenced claim belongs to a source NOT provided: the whole
        # tension must be dropped, never kept minus the dead references
        response = full_response()
        response["tensions"][0]["sources"] = ["wiki/invented/path.md"]
        out, _ = run(response=response)
        kept = [t for t in out["candidate"]["tensions"]
                if t["statement"] == response["tensions"][0]["statement"]]
        assert not kept
        assert any("整体丢弃" in i for i in out["issues"])

    def test_two_source_stub_keeps_no_dead_counterexample_narrative(self):
        # negative scenario: model payload still references the absent
        # counterexample -> those tensions are dropped, not trimmed
        notes = [load_note(CASE_FAMILY[0]), load_note(CASE_FAMILY[1])]
        out, _ = run(notes=notes)  # full_response references CASE_RELS[2]
        assert out["state"] == "stub"
        for t in out["candidate"]["tensions"]:
            assert CASE_RELS[2] not in t["sources"]
            assert "反例" not in t["statement"]
            assert "双方均有证据" not in t.get("note", "")
        assert any("整体丢弃" in i for i in out["issues"])
        assert "照搬链条后两段且缺少销售语境的尝试失败" not in [
            j["statement"] for j in out["candidate"]["supported_judgments"]]

    def test_duplicate_exact_claims_merged_and_roundtrip(self):
        # duplicate statement+kind with complementary evidence in another source:
        # one merged claim, both evidence pieces, reloads via validate_claims
        response = full_response()
        dup = judgment(CASE_RELS[1],
                       response["judgments"][0]["statement"],
                       '店主则认为"活动当场本来就该单独算，当晚口径才是机制的直接体现"')
        response["judgments"].append(dup)
        out, _ = run(response=response)
        # 5 distinct statements survive; the duplicate merged into its original
        assert len(out["claims"]) == 5
        merged = [c for c in out["claims"]
                  if c["statement"] == response["judgments"][0]["statement"]][0]
        assert len(merged["evidence"]) == 2
        assert {e["source"] for e in merged["evidence"]} == {CASE_RELS[0], CASE_RELS[1]}
        claims = read_claims({"claims": out["claims"]})
        assert len(claims) == 5
        assert sum("完全重复" in i for i in out["issues"]) >= 1
        # strictly reloadable with same original snapshots
        documents = [{"path": rel,
                      "content": (FIXTURES / name).read_text(encoding="utf-8"),
                      "sha256": hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()}
                     for rel, name in zip(CASE_RELS, CASE_FAMILY)]
        from core.claims import evidence_status
        assert all(evidence_status(e, next(d for d in documents if d["path"] == e.source))
                   == "matched" for c in claims for e in c.evidence)

    def test_related_only_to_known_paths(self):
        response = full_response()
        response["related"] = ["wiki/concepts/conversion-chain.md",
                               "wiki/invented/model-target.md"]
        out, _ = run(response=response, known_paths=["wiki/concepts/conversion-chain.md"])
        assert out["candidate"]["related"] == ["wiki/concepts/conversion-chain.md"]
        assert "wiki/invented/model-target.md" in out["candidate"]["pending_links"]
        assert "[[wiki/invented/model-target.md]]" not in out["page"]["content"]

    def test_freeform_wikilinks_sanitized(self):
        response = full_response()
        response["theme_boundary"] = "见 [[wiki/fake-link.md]] 的推导"
        response["summary"] = "嵌套 [[wiki/another]] 引用"
        out, _ = run(response=response)
        body = out["page"]["content"]
        assert "[[wiki/fake-link.md]]" not in body
        assert "[[wiki/another]]" not in body
        assert any("链接语法" in i for i in out["issues"])

    def test_unsafe_paths_rejected_bounded(self):
        for bad in ("C:\\abs\\path.md", "../escape.md", "wiki\\slash.md",
                    "wiki/../traverse.md", "raw//x.md", "raw/./x.md",
                    "/abs/root.md", "wiki/x\x01.md"):
            notes = [load_note(CASE_FAMILY[0])]
            notes[0]["rel"] = bad
            out, provider = run(notes=notes)
            assert out["state"] == "error", bad
            assert provider.calls["count"] == 0, bad

    def test_duplicate_rel_same_hash_deduped(self):
        note = load_note(CASE_FAMILY[0])
        out, _ = run(notes=[note, dict(note)])
        assert out["state"] == "stub"  # single usable source
        assert sum("重复提供且快照一致" in i for i in out["issues"]) == 1

    def test_duplicate_rel_different_hash_is_error(self):
        note = load_note(CASE_FAMILY[0])
        altered = note["source_text"] + "\n补充段落"
        tampered2 = dict(note, source_text=altered,
                         source_sha256=hashlib.sha256(altered.encode()).hexdigest())
        out, provider = run(notes=[note, tampered2])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "两个不同的原始快照" in out["reason"]

    def test_refused_input_visible_on_partial_coverage_full_topic(self):
        # 3 usable + 1 refused: a supported narrower topic may still be full,
        # but partial coverage and the scope limitation stay visible.
        notes = [load_note(n) for n in CASE_FAMILY] + \
                [load_note(CASE_FAMILY[0], corrupt_hash=True)]
        notes[3] = dict(notes[3], rel="wiki/extra.md")
        out, _ = run(notes=notes)
        assert out["state"] == "full"
        assert out["candidate"]["coverage"] == "partial"
        assert out["candidate"]["manual_review"]
        assert "范围受限" in out["page"]["content"]


class TestRefusals:
    def test_missing_snapshot_is_error_without_provider_call(self):
        out, provider = run(notes=[load_note(CASE_FAMILY[0], drop_text=True)])
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_hash_mismatch_refuses_all_notes(self):
        notes = [load_note(CASE_FAMILY[0], corrupt_hash=True)]
        out, provider = run(notes=notes)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert any("不匹配" in i for i in out["issues"])

    def test_oversized_single_source_no_call_no_truncation(self):
        cfg = {"topic_generation": {"min_full_sources": 3, "max_source_chars": 10,
                                    "max_context_chars": 60000}}
        out, provider = run(cfg=cfg)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "max_source_chars" in out["reason"]
        assert "截断" in out["reason"]

    def test_whole_payload_budget_includes_question_and_known_paths(self):
        cfg = {"topic_generation": {"min_full_sources": 3,
                                    "max_source_chars": 20000,
                                    "max_context_chars": 60000}}
        huge_known = [f"wiki/objects/object-{i:05d}.md" for i in range(3000)]
        out, provider = run(cfg=cfg, known_paths=huge_known)
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "max_context_chars" in out["reason"]

    def test_invalid_config_rejected(self):
        out, provider = run(cfg={"topic_generation": {"min_full_sources": "3"}})
        assert out["state"] == "error"
        assert provider.calls["count"] == 0

    def test_non_llm_mode_is_honest(self):
        out, provider = run(analysis_mode="heuristic")
        assert out["state"] == "disabled"
        assert provider.calls["count"] == 0
        assert "非 LLM" in out["reason"]

    def test_provider_failure_surfaces_without_retry(self):
        def failing(cfg, system_prompt, payload):
            raise RuntimeError("boom")
        out = tg.generate_topic(QUESTION, CFG, [load_note(n) for n in CASE_FAMILY],
                                call_provider=failing)
        assert out["state"] == "error"
        assert "boom" in out["reason"]

    def test_malformed_json_is_error(self):
        out = tg.generate_topic(QUESTION, CFG, [load_note(n) for n in CASE_FAMILY],
                                call_provider=lambda c, s, p: "这不是 JSON")
        assert out["state"] == "error"
        assert "JSON" in out["reason"]


class TestActionsAndQuality:
    def test_action_with_unknown_gap_blocks_full(self):
        response = full_response()
        response["next_actions"][0]["addresses_gap"] = "不存在的缺口"
        out, _ = run(response=response)
        assert out["state"] == "stub"
        assert any("未对应已记录缺口" in i for i in out["issues"])
        assert out["candidate"]["next_actions"][0]["addresses_gap"] is None

    def test_generic_short_action_dropped(self):
        response = full_response()
        response["next_actions"] = [{"action": "继续", "priority": 1,
                                     "addresses_gap": "缺乏错峰或对照条件下的效果记录"}]
        out, _ = run(response=response)
        assert out["state"] == "stub"
        assert out["candidate"]["next_actions"] == []

    def test_issues_rendered_visibly_not_just_a_flag(self):
        response = full_response()
        response["theme_boundary"] = "含 [[wiki/fake.md]] 的边界"
        out, _ = run(response=response)
        body = out["page"]["content"]
        assert "生成质量标注" in body
        assert any(issue in body for issue in out["issues"])
        assert "topic_generation_issues" in out["candidate"]["quality_flags"]


class TestSecrets:
    def test_secret_in_payload_blocked_pre_call(self):
        # the secret must be part of the actual outbound payload (question text)
        out, provider = tg_generate_with_secret_question()
        assert out["state"] == "error"
        assert provider.calls["count"] == 0
        assert "sk-abcdefghijklmnopqrs12345" not in out["reason"]

    def test_secret_in_response_blocked_post_call(self):
        def secret_provider(cfg, system_prompt, payload):
            return json.dumps({"topic_viable": True, "title": "t",
                               "summary": "password = hunter2secretvalue",
                               "theme_boundary": "b", "source_map": [],
                               "judgments": [], "tensions": [],
                               "evidence_gaps": [], "next_actions": []})
        out = tg.generate_topic(QUESTION, CFG, [load_note(n) for n in CASE_FAMILY],
                                call_provider=secret_provider)
        assert out["state"] == "error"
        assert "hunter2secretvalue" not in out["reason"]


def tg_generate_with_secret_question():
    provider = fake_provider(full_response)
    secret_question = QUESTION + " api_key = sk-abcdefghijklmnopqrs12345"
    out = tg.generate_topic(secret_question, CFG,
                            [load_note(n) for n in CASE_FAMILY],
                            call_provider=provider, now="2026-09-21")
    return out, provider


class TestSchemaRegistration:
    def test_topic_page_schema_loaded_from_file_single_truth(self):
        from core.card_contracts import validate_card_item
        # bad pairing rejected by the canonical schema
        issues = validate_card_item({"type": "topic-page", "status": "growing",
                                     "stage": "compiled"}, "topic-page")
        assert issues
        # module registers the exact file contents (no Python duplicate)
        from core.card_contracts import _STORE
        registered = _STORE.get("topic-page.schema.json")
        on_disk = json.loads(tg._SCHEMA_PATH.read_text(encoding="utf-8-sig")
                             .replace("\r\n", "\n"))
        assert registered == on_disk
