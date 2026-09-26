"""M1-source quality contract: full-text attributable analysis over ORIGINAL text.

All model output in these tests is a local stub provider (no network); the
stubbed responses are fixtures, not real-model quality acceptance.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core import source_analysis as sa  # noqa: E402
from core.claims import digest, normalized_text  # noqa: E402
from core.skill_executor import load_executor  # noqa: E402
from core.vault import parse_frontmatter  # noqa: E402
import personal_kb_steward as steward  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "source-quality"


def _load_source_executor():
    import importlib.util
    skill_dir = ROOT / "skills" / "topic-research-compile"
    spec = importlib.util.spec_from_file_location("src_executor_m1_test", skill_dir / "executor.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(skill_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(skill_dir))
    return module


_SRC_EXEC = _load_source_executor()


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_note(name: str, rel: str | None = None) -> dict:
    raw = fixture_bytes(name)
    text = raw.decode("utf-8")  # keeps BOM/CRLF exactly as stored
    meta, body = parse_frontmatter(text.removeprefix("﻿"))
    title = str(meta.get("title") or name)
    return {
        "rel": rel or f"raw/{name}",
        "title": title,
        "body": body,
        "summary": "",
        "metadata": meta,
        "source_text": text,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def stub_llm(payload_by_call=None, quote_of=None):
    """Stub provider: returns one JSON response per call, capturing payloads."""
    calls: list[dict] = []

    def provider(cfg, system_prompt, user_payload):
        text = user_payload["text"]
        calls.append({"system": system_prompt, "payload": text})
        if payload_by_call is not None:
            return json.dumps(payload_by_call[len(calls) - 1])
        quote = quote_of(text) if quote_of else None
        if quote:
            return json.dumps({
                "chunk_viable": True,
                "summary": "片段摘要。",
                "key_statements": [{"text": "模型关键陈述。", "quote": quote, "kind": "assertion"}],
                "limitations": ["片段级局限。"],
                "quality_flags": [],
            })
        # explicit zero chunk: read but no independently useful information
        return json.dumps({"chunk_viable": False, "reason": "该片段无可沉淀的独立信息。",
                           "key_statements": [], "topics": [],
                           "limitations": [], "quality_flags": []})

    return provider, calls


class ChunkPlanTests(unittest.TestCase):
    def test_plan_is_bounded_and_records_excluded_ranges(self):
        norm = "x" * 10000
        plan = sa.plan_chunks(norm, 4000, 2)
        self.assertEqual(plan["coverage"], "partial")
        self.assertEqual(plan["read_chars"], 8000)
        self.assertEqual(plan["excluded_ranges"], [{"start": 8000, "end": 10000}])
        self.assertEqual([c["start"] for c in plan["chunks"]], [0, 4000])

    def test_full_plan_covers_everything(self):
        plan = sa.plan_chunks("x" * 5000, 4000, 12)
        self.assertEqual(plan["coverage"], "full")
        self.assertEqual(plan["excluded_ranges"], [])
        self.assertEqual(plan["chunks"][-1]["end"], 5000)

    def test_settings_reject_invalid_config(self):
        with self.assertRaises(sa.SourceAnalysisError):
            sa.analysis_settings({"source_analysis": {"chunk_chars": "big"}})
        with self.assertRaises(sa.SourceAnalysisError):
            sa.analysis_settings({"source_analysis": {"max_chunks": 0}})


class QuoteVerificationTests(unittest.TestCase):
    def test_quote_maps_bom_crlf_original(self):
        raw = fixture_bytes("long-article.md").decode("utf-8")
        norm = normalized_text(raw)
        self.assertFalse(norm.startswith("﻿"))
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        self.assertGreater(sa.locate_quote(norm, pivot)["start"], 6000 - len(pivot))
        located = sa.locate_quote(norm, pivot)
        self.assertEqual(norm[located["start"]:located["end"]], pivot)

    def test_repeated_quote_requires_start_line(self):
        raw = fixture_bytes("long-article.md").decode("utf-8")
        norm = normalized_text(raw)
        marker = "结论部分：以上数字由合成数据生成，仅用于测试。"
        norm = norm + "\n" + marker  # second identical occurrence
        with self.assertRaises(sa.SourceAnalysisError):
            sa.locate_quote(norm, marker)
        first = sa.locate_quote(norm, marker, start_line=norm.count("\n", 0, norm.find(marker)) + 1)
        second = sa.locate_quote(norm, marker, start_line=norm.count("\n", 0, norm.rfind(marker)) + 1)
        self.assertLess(first["start"], second["start"])

    def test_invalid_quote_is_rejected(self):
        norm = "完全无关的原文内容。"
        with self.assertRaises(sa.SourceAnalysisError):
            sa.locate_quote(norm, "原文里不存在的话。")

    def test_merge_marks_unusable_quote_never_verified(self):
        norm = "这是唯一一句原文。"
        flags: list[str] = []
        errors: list[str] = []
        result = sa.merge_llm_chunk_result(
            {"index": 0},
            {"key_statements": [{"text": "声称", "quote": "原文没有这句", "kind": "assertion"}]},
            norm, flags, errors)
        self.assertFalse(result["units"][0]["verified"])
        self.assertTrue(any("不可用" in flag for flag in flags))
        self.assertNotIn("verified", [u.get("status") for u in result["units"]])


class ClassifyTests(unittest.TestCase):
    def test_dialogue_with_speakers(self):
        note = fixture_note("dialogue.md")
        kind = sa.classify_source(note["title"], normalized_text(note["source_text"]), note["metadata"])
        self.assertEqual(kind["source_type"], "dialogue")
        self.assertIn("顾问", kind["speakers"])
        self.assertIn("用户", kind["speakers"])

    def test_ai_synthesis_and_oral_and_unknown(self):
        ai = fixture_note("ai-synthesis.md")
        self.assertEqual(sa.classify_source(ai["title"], normalized_text(ai["source_text"]),
                                            ai["metadata"])["source_type"], "ai-synthesis")
        oral = fixture_note("oral-case.md")
        self.assertEqual(sa.classify_source(oral["title"], normalized_text(oral["source_text"]),
                                            oral["metadata"])["source_type"], "oral-case")
        unclear = fixture_note("unclear.md")
        self.assertEqual(sa.classify_source(unclear["title"], normalized_text(unclear["source_text"]),
                                            unclear["metadata"])["source_type"], "unknown")


class ExecutorAnalysisTests(unittest.TestCase):
    def test_full_mode_includes_evidence_after_6000(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        norm = normalized_text(note["source_text"])
        provider, calls = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        cfg = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12}, "write": {}}
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            data = _SRC_EXEC.analyze_note(note, cfg, use_llm=True)
        self.assertEqual(data["coverage"], "full")
        self.assertEqual(data["source_hashes"], {note["rel"]: note["source_sha256"]})
        self.assertEqual(data["analysis_mode"], "llm")
        self.assertTrue(any(u["verified"] and u["quote"] == norm[u["start"]:u["end"]]
                            and pivot in u["quote"] for u in data["info_units"]))
        # chunked: more than one bounded call, each with offset header
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn("字符偏移 0-", calls[0]["payload"])

    def test_fenced_json_response_is_accepted_without_relaxing_evidence_checks(self):
        note = fixture_note("dialogue.md")
        quote = "顾问：您目前的知识库主要堆积在哪类资料？"
        payload = json.dumps({
            "chunk_viable": True,
            "summary": "对话记录了知识库资料整理需求。",
            "key_statements": [{
                "text": "顾问询问知识库资料类型。",
                "quote": quote,
                "kind": "assertion",
            }],
            "topics": [],
            "limitations": [],
            "quality_flags": [],
        }, ensure_ascii=False)

        def fenced_provider(cfg, system_prompt, user_payload):
            return f"```json\n{payload}\n```"

        with patch.object(_SRC_EXEC, "call_chat_completion", fenced_provider):
            data = _SRC_EXEC.analyze_note(note, {"write": {}}, use_llm=True)
        self.assertEqual(data["analysis_mode"], "llm")
        self.assertTrue(any(unit["verified"] and unit["quote"] == quote
                            for unit in data["info_units"]))

    def test_budget_limited_mode_cannot_claim_complete(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        provider, calls = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        cfg = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 1}, "write": {}}
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            data = _SRC_EXEC.analyze_note(note, cfg, use_llm=True)
        self.assertEqual(data["coverage"], "partial")
        self.assertEqual(data["chunk_plan"]["excluded_ranges"][0]["start"], data["chunk_plan"]["read_chars"])
        self.assertTrue(any("覆盖不足" in flag or "未分析" in flag or "未读取" in flag
                            for flag in data["quality_flags"]))
        self.assertTrue(any("未读取范围" in lim or "分析失败范围" in lim
                            for lim in data["limitations"]))
        # pivotal evidence beyond the budget is NOT claimed as analyzed
        self.assertFalse(any(u.get("verified") and pivot in u.get("quote", "")
                             for u in data["info_units"]))

    def test_missing_snapshot_yields_unknown_provenance(self):
        note = fixture_note("dialogue.md")
        note.pop("source_text")
        note.pop("source_sha256")
        data = _SRC_EXEC.analyze_note(note, {"write": {}}, use_llm=False)
        self.assertEqual(data["coverage"], "unknown")
        self.assertEqual(data["source_hashes"], {})

    def test_provider_failure_falls_back_visibly(self):
        note = fixture_note("dialogue.md")

        def failing(cfg, system_prompt, payload):
            raise RuntimeError("network disabled in tests")

        with patch.object(_SRC_EXEC, "call_chat_completion", failing):
            data = _SRC_EXEC.analyze_note(note, {"write": {}}, use_llm=True)
        self.assertEqual(data["analysis_mode"], "heuristic-fallback")
        self.assertTrue(any("LLM 全部分块失败" in flag for flag in data["quality_flags"]))

    def test_execute_renders_contract_complete_card(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        provider, _ = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [note], "config": {"write": {}}, "use_llm": True})
        page, = result["created"]
        self.assertEqual(page["skill"], "topic-research-compile")
        meta, body = parse_frontmatter(page["content"])
        self.assertEqual(meta["schema_version"], "m0-1")
        self.assertEqual(meta["analysis_mode"], "llm")
        self.assertEqual(meta["coverage"], "full")
        self.assertEqual(meta["source_hashes"], {note["rel"]: note["source_sha256"]})
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        self.assertEqual(headings,
                         ["## 原始来源", "## 核心摘要", "## 关键事实", "## 提取的专题", "## 质量标记"])
        self.assertIn("来源类型：article", page["content"])

    def test_partial_card_is_manual_review(self):
        note = fixture_note("long-article.md")
        cfg = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 1}, "write": {}}
        data = _SRC_EXEC.analyze_note(note, cfg, use_llm=False)
        page, = _SRC_EXEC.render(data)
        self.assertTrue(page["review_required"])
        self.assertIn("status: manual_review", page["content"])
        self.assertIn("coverage: partial", page["content"])


class ReviewRoundTwoTests(unittest.TestCase):
    """Astra round-2 acceptance: coverage/error ranges, speakers, blocked input,
    secret screening, card_state persistence."""

    CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12}, "write": {}}

    def test_tail_chunk_provider_failure_yields_partial_with_error_ranges(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        calls = {"n": 0}

        def provider(cfg, system_prompt, payload):
            calls["n"] += 1
            if calls["n"] > 1:  # only the tail chunk fails
                raise RuntimeError("synthetic tail failure")
            return json.dumps({"chunk_viable": False, "reason": "头部片段无可沉淀信息。",
                               "key_statements": [], "topics": [], "limitations": [],
                               "quality_flags": []})

        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            data = _SRC_EXEC.analyze_note(note, self.CFG, use_llm=True)
        self.assertEqual(data["status"], "partial")
        self.assertEqual(data["coverage"], "partial")
        self.assertEqual(data["analysis_mode"], "heuristic-fallback")
        error_ranges = data["coverage_info"]["error_ranges"]
        self.assertEqual(len(error_ranges), 1)
        self.assertEqual(error_ranges[0]["end"], data["coverage_info"]["total_chars"])
        self.assertGreater(error_ranges[0]["start"], 0)  # tail chunk, not the head
        self.assertTrue(data["coverage_info"]["read_ranges"])
        self.assertTrue(any("分析失败范围" in lim for lim in data["limitations"]))

    def test_mixed_notes_processed_counts_only_clean_success(self):
        good = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        provider, _ = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [good, fixture_note("empty.md")],
                                        "config": self.CFG, "use_llm": True})
        self.assertEqual(len(result["created"]), 1)
        self.assertEqual(result["processed"], 1)  # blocked note never counts
        self.assertTrue(any("不可分析" in issue for issue in result["issues"]))

    def test_bold_dialogue_speakers_and_ai_not_attributed_to_user(self):
        note = fixture_note("bold-dialogue.md")
        data = _SRC_EXEC.analyze_note(note, self.CFG, use_llm=False)
        self.assertEqual(data["source_type"], "dialogue")
        self.assertIn("助手", data["speakers"])
        self.assertIn("用户", data["speakers"])
        payload = json.dumps({"summary": "", "key_statements": [
            {"text": "助手建议只留增长率结论。", "quote": "可以，我建议只留增长率结论，其余删掉。",
             "speaker": "助手", "kind": "assertion"},
            {"text": "伪造归属的结论。", "quote": "好的，我建议保留三个要点：范围、数据、风险。",
             "speaker": "用户", "kind": "assertion"}],
            "limitations": [], "quality_flags": [], "topics": []})

        def fixed_payload_provider(cfg, system_prompt, user_payload):
            return payload

        with patch.object(_SRC_EXEC, "call_chat_completion", fixed_payload_provider):
            data2 = _SRC_EXEC.analyze_note(note, self.CFG, use_llm=True)
        units = {u["text"]: u for u in data2["info_units"] if u["verified"]}
        self.assertEqual(units["助手建议只留增长率结论。"]["speaker"], "助手")
        self.assertTrue(units["助手建议只留增长率结论。"]["speaker_verified"])
        # fabricated attribution is NEVER persisted as trusted: speaker becomes
        # unknown, the conflict is recorded, and review is forced
        fabricated = units["伪造归属的结论。"]
        self.assertIsNone(fabricated["speaker"])
        self.assertEqual(fabricated["speaker_mismatch"], "助手")
        self.assertTrue(any("说话人标注" in flag and "不符" in flag
                            for flag in data2["quality_flags"]))
        # per-unit attribution is displayed in the rendered card
        page, = _SRC_EXEC.render({**data2, "sources_dir": "wiki/sources"})
        self.assertIn("（助手）助手建议只留增长率结论。", page["content"])

    def test_uncited_report_still_flags_absent_references_and_numbers(self):
        note = fixture_note("uncited-report.md")
        flags = _SRC_EXEC.analyze_note(note, self.CFG, use_llm=False)["quality_flags"]
        joined = " ".join(flags)
        self.assertIn("无引用或出处标记", joined)
        self.assertIn("数字按未核实处理", joined)
        self.assertNotIn("暂无明显质量标记", joined)

    def test_empty_and_damaged_input_are_blocked_without_pages(self):
        provider, _ = stub_llm(quote_of=lambda text: None)
        damaged = {"rel": "raw/damaged.md", "title": "损坏样本", "body": "",
                   "summary": "", "metadata": {},
                   "source_error": "'utf-8' codec can't decode byte 0xff"}
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [fixture_note("empty.md"), damaged],
                                        "config": self.CFG, "use_llm": True})
        self.assertEqual(result["created"], [])
        self.assertEqual(result["processed"], 0)
        self.assertEqual(len(result["issues"]), 2)

    def test_repeated_source_text_does_not_inflate_units(self):
        note = fixture_note("repeated.md")
        data = _SRC_EXEC.analyze_note(note, self.CFG, use_llm=False)
        quotes = [u["quote"] for u in data["info_units"]]
        self.assertEqual(len(quotes), len(set(quotes)))

    def test_snapshot_hash_mismatch_is_blocked_not_rebound(self):
        note = fixture_note("dialogue.md")
        note["source_sha256"] = "0" * 64
        provider, _ = stub_llm(quote_of=lambda text: None)
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [note], "config": self.CFG, "use_llm": True})
        self.assertEqual(result["created"], [])
        self.assertTrue(any("不一致" in issue or "不可信" in issue for issue in result["issues"]))

    def test_secret_in_unused_response_field_is_blocked(self):
        note = fixture_note("long-article.md")

        def leaky_provider(cfg, system_prompt, payload):
            return json.dumps({"summary": "ok", "key_statements": [],
                               "unused": "api_key=sk-secret1234567890abcd",
                               "limitations": [], "quality_flags": []})

        from core.content_safety import SensitiveContentError
        with patch.object(_SRC_EXEC, "call_chat_completion", leaky_provider):
            with self.assertRaises(SensitiveContentError):
                _SRC_EXEC.execute({"notes": [note], "config": self.CFG, "use_llm": True})

    def test_card_state_in_rendered_card_agrees_with_payload(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        provider, _ = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [note], "config": self.CFG, "use_llm": True})
        page, = result["created"]
        meta, _ = parse_frontmatter(page["content"])
        state = meta["card_state"]
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["type"], "source-note")
        self.assertEqual(state["analysis"]["coverage"], page["analysis_mode"] and meta["coverage"])
        self.assertEqual(state["analysis"]["source_hashes"], {note["rel"]: note["source_sha256"]})
        for unit in state["info_units"]:
            self.assertEqual(unit["source"], note["rel"])
            self.assertEqual(unit["source_sha256"], note["source_sha256"])
        verified = [u for u in state["info_units"] if u["verified"]]
        self.assertTrue(verified)
        self.assertIn("2025年9月", verified[0]["quote"])
        # pending topic targets remain plain text (no invented links)
        self.assertNotIn("[[wiki/topics/", page["content"])

    def test_out_of_chunk_quote_rejected(self):
        quote = "远离片段的引用文本zzzzzzzzzz"
        norm = "a" * 9000 + quote
        chunk = {"index": 0, "start": 0, "end": 4000}
        flags: list[str] = []
        errors: list[str] = []
        result = sa.merge_llm_chunk_result(
            chunk, {"key_statements": [{"text": "远处事实", "quote": quote}]},
            norm, flags, errors)
        self.assertFalse(result["units"][0]["verified"])
        self.assertIn("片段之外", result["units"][0]["unusable_reason"])
        self.assertTrue(any("不可核验" in flag for flag in flags))

    def test_statement_field_validation_without_stringifying(self):
        flags: list[str] = []
        errors: list[str] = []
        result = sa.merge_llm_chunk_result(
            {"index": 0, "start": 0, "end": 100},
            {"key_statements": [
                {"text": "正常陈述", "quote": "正常陈述", "kind": "assertion"},
                {"text": 12345},
                {"text": "坏kind", "kind": "opinion"},
                ["not", "a", "dict"],
            ]},
            "正常陈述 坏kind", flags, errors)
        self.assertEqual(len(result["units"]), 1)
        self.assertTrue(result["units"][0]["verified"])
        self.assertEqual(len(errors), 3)

    def test_invalid_analysis_config_is_bounded_error_not_recursion(self):
        note = fixture_note("dialogue.md")
        with patch.object(_SRC_EXEC, "call_chat_completion", lambda *a: "{}"):
            result = _SRC_EXEC.execute({"notes": [note],
                                        "config": {"source_analysis": {"chunk_chars": "bad"},
                                                   "write": {}},
                                        "use_llm": True})
        self.assertEqual(result["created"], [])
        self.assertTrue(any("不可分析" in issue for issue in result["issues"]))

    def test_processed_index_semantics_through_plan_path(self):
        import tempfile
        import json as jsonlib
        from core.vault import build_index
        good = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        provider, _ = stub_llm(quote_of=lambda text: pivot if pivot in text else None)
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            raw_dir = kb / "raw"
            raw_dir.mkdir()
            (raw_dir / "long-article.md").write_bytes(fixture_bytes("long-article.md"))
            (raw_dir / "empty.md").write_bytes(b"")
            cfg = jsonlib.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
            cfg["knowledge_base"] = str(kb)
            cfg["state_file"] = str(kb / ".state.json")
            cfg["safety"] = {
                "plans_dir": str(kb / ".o" / "plans"), "runs_dir": str(kb / ".o" / "runs"),
                "processed_index": str(kb / ".o" / "processed-index.json"),
                "manual_review_queue": str(kb / ".o" / "q.jsonl"),
                "backup_dir": str(kb / ".o" / "backups"),
                "operation_log": str(kb / ".o" / "op.jsonl")}
            cfg["source_analysis"] = self.CFG["source_analysis"]
            index = build_index(cfg)
            notes = [index.by_rel[n] for n in ("raw/long-article.md", "raw/empty.md")]
            with patch.object(_SRC_EXEC, "call_chat_completion", provider):
                result = _SRC_EXEC.execute({"notes": steward.executor_notes(notes),
                                            "config": cfg, "use_llm": True})
            pages = steward.planned_pages_from_executor_result(cfg, result, "m1-round2")
            self.assertEqual(len(pages), 1)  # blocked note produces no planned page
            self.assertEqual(result["processed"], 1)
            ops = [{"operation": "create", "rel_path": p["rel_path"],
                    "sources": p["sources"], "content_sha256": p["content_sha256"],
                    "skill": "topic-research-compile", "page_id": p["rel_path"]}
                   for p in pages]
            steward.update_processed_index(index, cfg, ops)
            stored = jsonlib.loads(Path(cfg["safety"]["processed_index"]).read_text(encoding="utf-8"))
            self.assertTrue(stored)


    def test_all_invalid_quotes_execute_yields_zero_processed(self):
        note = fixture_note("long-article.md")
        payload = json.dumps({"summary": "凭空摘要。",
                              "key_statements": [{"text": "不可核验陈述", "quote": "原文中根本不存在的句子",
                                                  "kind": "assertion"}],
                              "topics": [], "limitations": [], "quality_flags": []})
        with patch.object(_SRC_EXEC, "call_chat_completion", lambda *a: payload):
            result = _SRC_EXEC.execute({"notes": [note], "config": self.CFG, "use_llm": True})
        self.assertEqual(result["processed"], 0)  # zero usable units never counts as success
        # a diagnostic review card may exist, explicitly marked partial/unusable
        page, = result["created"]
        meta, _ = parse_frontmatter(page["content"])
        self.assertEqual(meta["status"], "manual_review")
        self.assertIn("不可用", " ".join(page["quality_flags"]))
        self.assertIn("没有任何可核验的原文证据", page["content"])

    def test_model_wikilinks_never_escape_into_rendered_card(self):
        note = fixture_note("long-article.md")
        pivot = "2025年9月，该市试点线路的准点率从71%提升至89%"
        payload = json.dumps({
            "summary": "摘要提及 [[wiki/topics/伪造专题]]。",
            "key_statements": [{"text": "关键陈述指向 [[wiki/topics/伪造]]。",
                                "quote": pivot, "kind": "assertion"}],
            "topics": [{"title": "[[wiki/topics/坏链接]]", "content": "边界"}],
            "limitations": ["模型局限引用 [[某不存在的页面]]。"],
            "quality_flags": []})

        def provider(cfg, system_prompt, user_payload):
            return payload if pivot in user_payload["text"] else json.dumps(
                {"summary": "", "key_statements": [], "limitations": [], "quality_flags": []})

        with patch.object(_SRC_EXEC, "call_chat_completion", provider):
            result = _SRC_EXEC.execute({"notes": [note], "config": self.CFG, "use_llm": True})
        page, = result["created"]
        self.assertNotIn("[[wiki/topics/伪造", page["content"])
        self.assertNotIn("[[wiki/topics/坏链接", page["content"])
        self.assertNotIn("[[某不存在的页面", page["content"])
        self.assertIn("［［", page["content"])  # rendered as literal text
        # the only real link is the validated actual source path
        meta, _ = parse_frontmatter(page["content"])
        self.assertEqual(meta["sources"], [note["rel"]])
        # structured state keeps the verbatim verification QUOTE (display text
        # is sanitized, but evidence is never altered)
        state = meta["card_state"]
        verified = [u for u in state["info_units"] if u["verified"]]
        self.assertTrue(any(u["quote"] == pivot and u["start"] is not None for u in verified))


class QualityAssessmentTests(unittest.TestCase):
    def test_ai_numbers_unverified_and_uncited_flag(self):
        note = fixture_note("ai-synthesis.md")
        norm = normalized_text(note["source_text"])
        flags = sa.assess_quality("ai-synthesis", [], norm, note["metadata"])
        self.assertTrue(any("未标注任何引用来源" in flag for flag in flags))
        self.assertTrue(any("未经独立来源核实" in flag for flag in flags))
        # and no generic "no obvious issues" ever appears for missing citations
        self.assertNotIn("暂无明显质量标记", flags)

    def test_oral_case_single_party_statement(self):
        note = fixture_note("oral-case.md")
        flags = sa.assess_quality("oral-case", ["张工"], normalized_text(note["source_text"]),
                                  note["metadata"])
        self.assertTrue(any("单方陈述" in flag for flag in flags))

    def test_article_numbers_without_citation(self):
        flags = sa.assess_quality("article", [], "该厂产量为1200吨。" * 3, {})
        self.assertTrue(any("数字按未核实处理" in flag for flag in flags))


class StewardSeamTests(unittest.TestCase):
    def make_cfg(self, kb: Path) -> dict:
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        cfg["knowledge_base"] = str(kb)
        cfg["state_file"] = str(kb / ".state.json")
        cfg["safety"] = {
            "plans_dir": str(kb / ".openclaw" / "plans"),
            "runs_dir": str(kb / ".openclaw" / "runs"),
            "processed_index": str(kb / ".openclaw" / "processed-index.json"),
            "manual_review_queue": str(kb / ".openclaw" / "manual-review" / "queue.jsonl"),
            "backup_dir": str(kb / ".openclaw" / "backups"),
            "operation_log": str(kb / ".openclaw" / "operation-log.jsonl"),
        }
        return cfg

    def test_executor_notes_provide_full_snapshot_and_raw_hash(self):
        import tempfile
        from core.vault import build_index
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            raw_dir = kb / "raw"
            raw_dir.mkdir(parents=True)
            (raw_dir / "sample.md").write_bytes(fixture_bytes("long-article.md"))
            cfg = self.make_cfg(kb)
            index = build_index(cfg)
            notes, = [[n for n in index.notes if n.rel == "raw/sample.md"]]
            items = steward.executor_notes(notes)
            item = items[0]
            self.assertIn("source_text", item)
            self.assertEqual(item["source_text"], fixture_bytes("long-article.md").decode("utf-8"))
            self.assertEqual(item["source_sha256"], hashlib.sha256(fixture_bytes("long-article.md")).hexdigest())
            # existing keys preserved
            for key in ("rel", "title", "body", "summary", "metadata"):
                self.assertIn(key, item)

    def test_executor_notes_surface_changed_snapshot(self):
        import tempfile
        from core.reconcile import ReconcileConflict
        from core.vault import build_index
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            raw_dir = kb / "raw"
            raw_dir.mkdir(parents=True)
            path = raw_dir / "sample.md"
            path.write_bytes(fixture_bytes("dialogue.md"))
            cfg = self.make_cfg(kb)
            index = build_index(cfg)
            note = next(n for n in index.notes if n.rel == "raw/sample.md")
            path.write_bytes(fixture_bytes("oral-case.md"))  # changed after indexing
            items = steward.executor_notes([note])
            self.assertIn("source_error", items[0])
            self.assertNotIn("source_text", items[0])

    def test_mvp_context_carries_vault_index_and_retriever(self):
        import inspect
        source = inspect.getsource(steward.mvp_executor_plan)
        self.assertIn('"vault_index": index', source)
        self.assertIn('"retriever": retriever', source)


if __name__ == "__main__":
    unittest.main()
