"""M1-seed atomic generation: granularity, verified attribution, honest limits, modes."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core import atomic_seed
from core.card_contracts import prepare_card_item, validate_card_item
from core.skill_executor import execute_skill, load_executor

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "atomic-seed"


def load_source(name: str, rel: str, **extra) -> dict:
    raw = (FIXTURES / name).read_bytes()
    return {"rel": rel, "title": name, "source_text": raw.decode("utf-8"),
            "source_sha256": hashlib.sha256(raw).hexdigest(), **extra}


def dialogue_note(**extra):
    return load_source("source-dialogue.md", "quicknote/dialogue.md", **extra)


def report_note(**extra):
    return load_source("source-report.md", "raw/weekly-report.md", **extra)


def snapshot(*notes) -> dict:
    return {n["rel"]: {"source_text": n["source_text"], "source_sha256": n["source_sha256"]}
            for n in notes}


def model_response(name: str, units: list[dict]):
    """Load a recorded model fixture and re-point unit_ids at the live unit list
    by the quote each thought is about (indexes depend on extraction order)."""
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    anchors = {"频繁死机": ["找了三次", "死机两次"],
               "旧借书记录": ["还能查到吗"],
               "检索服务观察": ["找了三次", "死机两次", "评审"]}
    for thought in data["thoughts"]:
        needles = [n for anchor, pool in anchors.items() if anchor in thought["title"] for n in pool]
        thought["unit_ids"] = [i for i, u in enumerate(units) if any(n in u["quote"] for n in needles)]
    return json.dumps(data, ensure_ascii=False)


def model_fn(payload_text: str):
    return lambda system, payload: payload_text


def to_card(item: dict, analysis="llm", hashes=None, coverage="full"):
    prepared = prepare_card_item(item, "seed-card", analysis,
                                 trusted_source_hashes=hashes, trusted_coverage=coverage)
    issues = validate_card_item(prepared, "seed-card")
    assert issues == [], issues
    return prepared


# ── Extraction: exact-byte provenance, full input, per-line speakers ────────

def test_full_dialogue_tail_coverage_and_line_speaker_attribution():
    units = atomic_seed.information_units(dialogue_note())
    quotes = [u["quote"] for u in units]
    # Tail coverage: the FINAL substantive line (管理员 proposal + boundary) is in.
    assert any("先不做大规模采购" in q for q in quotes)
    by_quote = {u["quote"]: u for u in units}
    reader = next(u for q, u in by_quote.items() if "找了三次" in q)
    keeper = next(u for q, u in by_quote.items() if "扩到两台" in q)
    assert reader["speaker"] and "读者" in reader["speaker"]
    assert keeper["speaker"] and "管理员" in keeper["speaker"]
    question = next(u for q, u in by_quote.items() if "还能查到吗" in q)
    assert question["kind"] == "question"
    # Note-level metadata must NOT blanket-attribute every line.
    plain = atomic_seed.information_units(dialogue_note(metadata={"speaker": "读者"}))
    assert any(u["speaker"] is None for u in plain)  # unlabelled lines stay unknown


def test_exact_byte_verification_and_blocked_invalid_snapshot():
    raw = (FIXTURES / "source-dialogue.md").read_bytes()
    exact = raw.decode("utf-8")
    assert atomic_seed._verify_snapshot(exact, hashlib.sha256(raw).hexdigest())
    # Normalized text paired with the ORIGINAL raw-byte hash must NOT verify.
    normalized = exact.replace("\r\n", "\n")
    if normalized == exact:
        normalized = exact.replace("\n", "\r\n")
    assert not atomic_seed._verify_snapshot(normalized, hashlib.sha256(raw).hexdigest())
    assert not atomic_seed._verify_snapshot("﻿" + exact, hashlib.sha256(raw).hexdigest())
    # A supplied-but-mismatched hash is a BLOCKED error before any provider call.
    wrong = dialogue_note()
    wrong["source_sha256"] = "0" * 64
    items, issues, meta = atomic_seed.generate_atomic_items([wrong])
    assert items == [] and meta["blocked_reason"]
    # Body-only notes carry no provenance claim: limited preview stays allowed.
    body_only = {"rel": "quicknote/b.md", "title": "b", "body": "读者反馈需要明确处理步骤并留记录。"}
    preview, _, meta = atomic_seed.generate_atomic_items([body_only])
    assert preview and meta["coverage"] == "unknown" and not meta["blocked_reason"]


def test_supplied_units_without_verified_snapshots_are_blocked():
    forged = [{"source": "raw/a.md", "quote": "任意捏造的原文片段", "kind": "assertion",
               "body_line": 3, "speaker": None}]
    items, issues, meta = atomic_seed.generate_atomic_items(units=forged, snapshots={})
    assert items == [] and meta["blocked_reason"]
    items, issues, meta = atomic_seed.generate_atomic_items(
        units=forged, model_fn=model_fn('{"thoughts": []}'),
        snapshots={"raw/a.md": {"source_text": "完全不同的正文。", "source_sha256":
                                hashlib.sha256("完全不同的正文。".encode("utf-8")).hexdigest()}})
    assert items == [] and meta["blocked_reason"]
    assert any("唯一定位" in i or "快照" in i for i in issues)


def test_supplied_units_verified_and_speaker_rederived_not_retained():
    note = report_note()
    units = atomic_seed.information_units(note)
    ok, issues = atomic_seed.verify_supplied_units(units, snapshot(note))
    assert ok and not issues
    assert all(u["verified"] and u["source_sha256"] == note["source_sha256"] for u in ok)
    assert all(u["start_line"] == u["body_line"] for u in ok)
    # A caller-forged speaker is replaced by the label verified in the source.
    forged = [dict(ok[0], speaker="完全捏造的角色")]
    checked, _ = atomic_seed.verify_supplied_units(forged, snapshot(note))
    assert checked[0]["speaker"] != "完全捏造的角色"


def test_repeated_quote_occurrence_hint_rules():
    text = "前导内容。\n同一句重复出现两次。\n中间内容。\n同一句重复出现两次。\n结尾。"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    unit = [{"source": "raw/dup.md", "quote": "同一句重复出现两次。", "body_line": None}]
    ok, issues = atomic_seed.verify_supplied_units(
        unit, {"raw/dup.md": {"source_text": text, "source_sha256": sha}})
    assert ok == [] and "唯一定位" in issues[0]  # ambiguous without hint
    hinted = [dict(unit[0], body_line=4)]
    ok2, _ = atomic_seed.verify_supplied_units(
        hinted, {"raw/dup.md": {"source_text": text, "source_sha256": sha}})
    assert ok2 and ok2[0]["start_line"] == 4  # hinted occurrence resolves
    wrong_hint = [dict(unit[0], body_line=99)]
    ok3, issues3 = atomic_seed.verify_supplied_units(
        wrong_hint, {"raw/dup.md": {"source_text": text, "source_sha256": sha}})
    assert ok3 == [] and issues3  # wrong hint cannot sneak a duplicate


def test_third_repeated_occurrence_and_wrong_unique_hint_follow_claims_contract():
    text = "\n".join(["首次出现占位。", "目标引文。", "第二段。", "目标引文。", "第三段。", "目标引文。", "结尾。"])
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    snaps = {"raw/trip.md": {"source_text": text, "source_sha256": sha}}
    # The THIRD occurrence with its correct line hint resolves.
    ok, _ = atomic_seed.verify_supplied_units(
        [{"source": "raw/trip.md", "quote": "目标引文。", "body_line": 6}], snaps)
    assert ok and ok[0]["start_line"] == 6
    # Occurrences are lines 2/4/6; hint line 1 has no occurrence -> rejected.
    ok2, issues2 = atomic_seed.verify_supplied_units(
        [{"source": "raw/trip.md", "quote": "目标引文。", "body_line": 1}], snaps)
    assert ok2 == [] and issues2
    # A unique quote with a WRONG line hint is rejected, not silently relocated.
    unique_text = "唯一的引文在这里。\n其他内容。"
    unique_snaps = {"raw/uniq.md": {"source_text": unique_text,
                                    "source_sha256": hashlib.sha256(unique_text.encode("utf-8")).hexdigest()}}
    ok3, issues3 = atomic_seed.verify_supplied_units(
        [{"source": "raw/uniq.md", "quote": "唯一的引文在这里。", "body_line": 2}], unique_snaps)
    assert ok3 == [] and issues3  # wrong hint on unique quote: rejected


def test_one_source_yields_two_distinct_thoughts_with_specific_growth():
    note = dialogue_note()
    units = atomic_seed.information_units(note)
    items, issues, meta = atomic_seed.generate_atomic_items(
        [note], model_fn=model_fn(model_response("model-two-thoughts.json", units)))
    assert meta["model"] == "llm" and meta["coverage"] == "full" and meta["complete"]
    assert len(items) == 2 and len({i["summary"] for i in items}) == 2
    for item in items:
        assert item["growth_directions"] and item["negative_scope"]
        assert item["thought_id"] and item["statement_sha256"]
        assert item["kind"] in ("question", "assertion")
    assert items[0]["growth_directions"] != items[1]["growth_directions"]


def test_thought_identity_is_evidence_based_not_index_based():
    a = atomic_seed.thought_identity("同一句话。", "assertion", ["unit:aaa"])
    assert a == atomic_seed.thought_identity("同一句话。", "assertion", ["unit:aaa"])  # stable
    assert a != atomic_seed.thought_identity("同一句话。", "assertion", ["unit:bbb"])  # source swap
    added = atomic_seed.thought_identity("同一句话。", "assertion", ["unit:aaa", "unit:bbb"])
    assert added not in (a,)  # added evidence → reviewed update, not early skip


def test_evidence_roundtrips_through_core_claims():
    from core.claims import read_claims
    note = dialogue_note()
    units = atomic_seed.information_units(note)
    items, _, _ = atomic_seed.generate_atomic_items(
        [note], model_fn=model_fn(model_response("model-two-thoughts.json", units)))
    assertion_rows = [r for i in items for r in i["evidence"] if r["kind"] == "assertion"]
    assert assertion_rows
    for row in assertion_rows:
        record = {"claim_id": row["claim_id"], "statement": row["quote"], "kind": "fact",
                  "confidence": "low",
                  "evidence": [{k: row[k] for k in atomic_seed._EVIDENCE_FIELDS}]}
        claims = read_claims({"claims": [record]})  # strict claims validation
        assert claims[0].evidence[0].source_sha256 == note["source_sha256"]
        assert claims[0].evidence[0].start_line == row["start_line"]
    # Questions persist traced evidence without a factual claim_id.
    question_rows = [r for i in items for r in i["evidence"] if r["kind"] == "question"]
    assert question_rows and all(not r.get("claim_id") for r in question_rows)


def test_two_sources_support_one_idea_and_card_signals_keep_speaker_labels():
    notes = [dialogue_note(), report_note()]
    units = atomic_seed.information_units(notes[0]) + atomic_seed.information_units(notes[1])
    items, _, meta = atomic_seed.generate_atomic_items(
        notes, model_fn=model_fn(model_response("model-one-idea-two-sources.json", units)))
    item, = items
    assert set(item["sources"]) == {"quicknote/dialogue.md", "raw/weekly-report.md"}
    prepared = to_card(item, hashes={n["rel"]: n["source_sha256"] for n in notes})
    assert prepared["coverage"] == "full"
    signal_text = "".join(item["signals"])
    assert "来源陈述：" in signal_text and "说话人：一位读者说" in signal_text
    assert "说话人未知" in signal_text  # unlabelled report line stays unknown
    assert all(u["verified"] for u in item["evidence"])
    # Compiled evidence persists source hash + coordinates, not just a claim_id.
    row = item["evidence"][0]
    assert row["source_sha256"] and row["start_line"] and row["claim_id"]


def test_question_kind_is_preserved_and_assertion_mismatch_is_flagged():
    note = dialogue_note()
    units = atomic_seed.information_units(note)
    items, _, _ = atomic_seed.generate_atomic_items(
        [note], model_fn=model_fn(model_response("model-two-thoughts.json", units)))
    question = [i for i in items if i["kind"] == "question"]
    assert question and question[0]["is_question"]
    assert any("未决问题" in r for r in question[0]["manual_review"])

    def wrong_kind(system, payload):
        payload_units = payload["units"]
        return json.dumps({"thoughts": [{
            "title": "违规断言", "kind": "assertion", "statement": "旧记录一定可以迁移。",
            "unit_ids": [i for i, u in enumerate(payload_units) if "还能查到吗" in u["quote"]],
            "growth_directions": [{"action": "核对迁移条目。", "basis": "回应读者未决问题。"}],
            "negative_scope": ["不推测方案。"]}]}, ensure_ascii=False)
    flagged, _, _ = atomic_seed.generate_atomic_items([note], model_fn=wrong_kind)
    assert any("问题性证据被写成断言" in r for r in flagged[0]["manual_review"])
    assert flagged[0]["status"] == "manual_review"


def test_model_invented_wikilinks_are_neutralized_but_quotes_stay_raw():
    note = dialogue_note()

    def linky(system, payload):
        payload_units = payload["units"]
        return json.dumps({"thoughts": [{
            "title": "带[[虚构链接]]的念头", "kind": "assertion",
            "statement": "参见 [[完全不存在]] 的推断。",
            "unit_ids": [i for i, u in enumerate(payload_units) if "找了三次" in u["quote"]],
            "growth_directions": [{"action": "核对 [[编造页]]。", "basis": "回应复现未知。"}],
            "negative_scope": ["不扩展到 [[另一虚构]]。"]}]}, ensure_ascii=False)
    items, _, _ = atomic_seed.generate_atomic_items([note], model_fn=linky)
    item, = items
    blob = json.dumps({k: item[k] for k in ("title", "summary", "growth_directions",
                                            "negative_scope")}, ensure_ascii=False)
    assert "[[" not in blob and "［［" in blob  # model-invented links neutralized
    assert "[[" not in item["title"] and "[[" not in item["summary"]
    # Structured evidence keeps raw quote bytes for verification.
    assert item["evidence"][0]["quote"] in note["source_text"]


def test_malformed_candidates_are_rejected_not_silently_shrunk_or_zero():
    note = dialogue_note()
    bad = json.dumps({"thoughts": [
        {"title": "坏引用", "kind": "assertion", "statement": "引用不存在单元。",
         "unit_ids": [0, 99],
         "growth_directions": [{"action": "核对。", "basis": "回应未知。"}],
         "negative_scope": ["x"]},
        {"title": "空依据", "kind": "assertion", "statement": "缺少实质依据。",
         "unit_ids": [0],
         "growth_directions": [{"action": "核对。", "basis": ""}],
         "negative_scope": ["x"]},
        {"title": "超长", "kind": "assertion", "statement": "长" * 201,
         "unit_ids": [0],
         "growth_directions": [{"action": "核对。", "basis": "回应未知。"}],
         "negative_scope": ["x"]},
    ]}, ensure_ascii=False)
    items, issues, meta = atomic_seed.generate_atomic_items([note], model_fn=model_fn(bad))
    assert items == [] and meta["model"] == "invalid" and meta["blocked_reason"]
    assert not meta["zero_reason"]  # malformed ≠ valid zero output


def test_valid_zero_output_on_fully_checked_input_is_explicit_and_successful():
    note = dialogue_note()
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": [note], "config": {}, "use_llm": True,
                            "model_fn": lambda s, p: '{"thoughts": []}'})
    assert result["ok"] and result["pages"] == [] and result["processed"] == 1
    assert result["zero_reason"] and "零产出" in result["zero_reason"]


def test_model_error_yields_preview_with_processed_zero_and_safe_message():
    note = dialogue_note()

    def broken(system, payload):
        raise RuntimeError("provider down with password=Secret9!Example")
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": [note], "config": {}, "use_llm": True, "model_fn": broken})
    assert result["ok"] and result["pages"] and result["processed"] == 0
    assert result["items"][0]["analysis_mode"] == "heuristic-fallback"
    joined = json.dumps(result["issues"], ensure_ascii=False)
    assert "Secret9" not in joined and "RuntimeError" in joined  # safe error message only


def test_secret_in_unused_response_field_blocks_fail_closed():
    note = dialogue_note()

    def leaky(system, payload):
        return '{"thoughts": [], "internal_note": "api_key=sk-leak-1234567890"}'
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": [note], "config": {}, "use_llm": True, "model_fn": leaky})
    assert result["ok"] is False and result["pages"] == [] and result["processed"] == 0
    assert any("敏感内容筛查阻断" in i for i in result["issues"])


def test_invalid_snapshot_blocks_even_in_mixed_batches_before_provider():
    good, bad = dialogue_note(), dialogue_note()
    bad = dict(bad, rel="quicknote/bad.md", source_sha256="0" * 64)
    calls = []

    def provider(system, payload):
        calls.append(payload)
        return '{"thoughts": []}'
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": [good, bad], "config": {}, "use_llm": True,
                            "model_fn": provider})
    assert result["ok"] is False and result["processed"] == 0 and result["pages"] == []
    assert not calls  # no provider call on an invalid mixed batch


# ── Deterministic preview and modes ─────────────────────────────────────────

def test_unrelated_multi_source_preview_never_forces_a_merge():
    notes = [dialogue_note(), report_note()]
    items, issues, meta = atomic_seed.generate_atomic_items(notes)  # no model
    assert meta["model"] == "none" and len(items) >= 5  # bounded full input, no prefix cut
    assert all(i.get("limited_preview") and i["growth_directions"] == [] for i in items)
    assert any("受限预览" in issue for issue in issues)


def test_zero_content_input_yields_zero_output_with_reason():
    text = "# 晨间日记\n## 每日例程\n- [x] 阅读课程与整理笔记\n"
    notes = [{"rel": "quicknote/day.md", "title": "日记", "source_text": text,
              "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}]
    items, issues, meta = atomic_seed.generate_atomic_items(notes)
    assert items == [] and meta["zero_reason"] and "零产出" in issues[0]


def test_no_model_atomic_execution_is_a_truthful_limited_preview():
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": [dialogue_note()], "config": {}, "use_llm": False})
    assert result["mode"] == "atomic" and result["ok"] and result["pages"]
    assert result["processed"] == 0  # preview is reviewable but NOT a processed success
    item = result["items"][0]
    assert item["analysis_mode"] == "heuristic" and item["limited_preview"] is True
    assert item["status"] == "manual_review" and item["stage"] == "needs_context"
    assert any("受限预览" in issue for issue in result["issues"])
    assert "受限预览" in result["pages"][0]["content"]
    assert "card_state" in result["pages"][0]["content"]  # versioned persistence


def test_default_mode_is_atomic_without_invoking_clustering():
    with patch("core.clustering.cluster_inputs", side_effect=AssertionError("atomic must not cluster")):
        result = execute_skill(ROOT, "mindseed-grow",
                               {"notes": [dialogue_note()], "config": {}, "use_llm": False})
    assert result["mode"] == "atomic" and result["pages"]


def test_explicit_topic_mode_keeps_legacy_grouping_path():
    notes = [{"rel": "quicknote/a.md", "title": "日记", "body": "读者反馈需要明确处理步骤并留记录。"}]
    cluster = {"title": "地方媒体服务转型", "sources": ["quicknote/a.md"], "confidence": "high",
               "reasoning": "地方媒体需要把技术能力落实为可持续的服务。", "terms": ["媒体", "服务"]}
    cfg = {"seed_generation": {"mode": "topic"}}
    with patch("core.clustering.cluster_inputs", return_value=([cluster], [])):
        result = execute_skill(ROOT, "mindseed-grow", {"notes": notes, "config": cfg, "use_llm": False})
    assert result["mode"] == "topic" and result["pages"]
    assert "thought_units" not in result["items"][0]
    assert result["items"][0]["cluster_confidence"] == "high"


def test_schema_invalid_item_is_blocked_before_render():
    execute = load_executor(ROOT, "mindseed-grow")
    rendered = []
    with patch("core.atomic_seed._thought_item", lambda t, u: {"bad": "item"}), \
         patch.dict(execute.__globals__, {"render": lambda item: rendered.append(item) or "# x"}):
        result = execute({"notes": [dialogue_note()], "config": {}, "use_llm": True,
                          "model_fn": model_fn(json.dumps(
                              {"thoughts": [{"title": "t", "kind": "assertion", "statement": "合法念头。",
                                             "unit_ids": [0],
                                             "growth_directions": [{"action": "核对。", "basis": "回应未知。"}],
                                             "negative_scope": ["x"]}]}, ensure_ascii=False))})
    assert rendered == [] and result["pages"] == [] and result["processed"] == 0
    assert result["ok"] is False and any("契约校验失败" in i for i in result["issues"])


def test_generator_accepts_preextracted_units_with_snapshots_for_integration():
    note = dialogue_note()
    units = atomic_seed.information_units(note)
    items, issues, meta = atomic_seed.generate_atomic_items(
        units=units, snapshots=snapshot(note),
        model_fn=model_fn(model_response("model-two-thoughts.json", units)))
    assert len(items) == 2 and meta["model"] == "llm" and not meta.get("blocked_reason")
