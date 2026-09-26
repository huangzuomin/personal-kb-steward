"""Source explicit useful-content zero contract (chunk_viable).

Canonical negative fixtures drive ACTUAL executor runs; the mock provider is a
local deterministic fixture, not a real-model quality claim.
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

from core import source_analysis as sa  # noqa: E402
from core.skill_executor import load_executor  # noqa: E402

SRC = load_executor(ROOT, "topic-research-compile")
CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12},
       "write": {"sources_dir": "wiki/sources"}}


def canonical(name: str, rel: str | None = None) -> dict:
    raw = (ROOT / "tests" / "fixtures" / "card-baseline" / f"{name}.md").read_bytes()
    text = raw.decode("utf-8")
    return {"rel": rel or f"raw/{name}.md", "title": name, "body": text, "summary": "",
            "metadata": {}, "source_text": text,
            "source_sha256": hashlib.sha256(raw).hexdigest()}


def zero_response(reason="无可沉淀的独立信息"):
    return json.dumps({"chunk_viable": False, "reason": reason, "key_statements": [],
                       "topics": [], "limitations": [], "quality_flags": []},
                      ensure_ascii=False)


def positive_response(quote, text="模型关键陈述"):
    return json.dumps({"chunk_viable": True, "summary": "片段摘要。",
                       "key_statements": [{"text": text, "quote": quote,
                                           "kind": "assertion"}],
                       "topics": [], "limitations": [], "quality_flags": []},
                      ensure_ascii=False)


class ExplicitZeroTests(unittest.TestCase):
    def test_canonical_neg_irrelevant_explicit_zero_no_card(self):
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            return zero_response("该来源为日常闲聊，无任何可沉淀的独立信息。")

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [canonical("neg_irrelevant")],
                          "config": CFG, "use_llm": True})
        self.assertEqual(len(calls), 1)  # actually read
        self.assertEqual(result["created"], [])
        self.assertEqual(result["processed"], 0)
        self.assertTrue(any("显式零" in i for i in result["issues"]))
        outcome, = result["input_outcomes"]
        self.assertEqual(outcome["outcome"], "zero")
        self.assertTrue(outcome["complete"])
        self.assertEqual(outcome["targets"], [])
        self.assertEqual(outcome["analysis_mode"], "llm")
        self.assertEqual(outcome["coverage"], "full")

    def test_old_contract_empty_output_is_not_a_zero_or_ok(self):
        """Root's before-probe response (source_viable, empty candidates, no
        chunk_viable) is now a malformed/empty error chunk — partial fallback,
        never processed, never a successful zero."""
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            return json.dumps({"summary": "日常闲聊，无可沉淀的独立信息。", "key_statements": [],
                               "topics": [], "limitations": [], "quality_flags": [],
                               "source_viable": False,
                               "reason": "无可沉淀的独立信息"}, ensure_ascii=False)

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [canonical("neg_irrelevant")],
                          "config": CFG, "use_llm": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["processed"], 0)
        outcome, = result["input_outcomes"]
        self.assertNotIn(outcome["outcome"], ("ok", "zero"))
        self.assertFalse(outcome["complete"])

    def test_neg_empty_blocked_with_zero_calls(self):
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            return zero_response()

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [canonical("neg_empty")],
                          "config": CFG, "use_llm": True})
        self.assertEqual(calls, [])
        self.assertEqual(result["created"], [])
        self.assertEqual(result["processed"], 0)
        outcome, = result["input_outcomes"]
        self.assertEqual(outcome["outcome"], "blocked")

    def test_null_viability_with_candidates_is_malformed(self):
        """Present chunk_viable must be an exact boolean; null is malformed even
        when positive candidates exist (root before-probe regression)."""
        flags: list[str] = []
        errors: list[str] = []
        with self.assertRaises(sa.SourceAnalysisError):
            sa.merge_llm_chunk_result(
                {"index": 0, "start": 0, "end": 100},
                {"chunk_viable": None, "key_statements": [{"text": "旧式陈述",
                                                          "quote": "旧式陈述"}]},
                "旧式陈述", flags, errors)
        # string/int forms are equally malformed
        for bad in ("false", 1):
            with self.assertRaises(sa.SourceAnalysisError):
                sa.merge_llm_chunk_result(
                    {"index": 0, "start": 0, "end": 100},
                    {"chunk_viable": bad, "reason": "x", "key_statements": []},
                    "旧式陈述", flags, errors)
        # genuine omission with candidates stays backward compatible
        result = sa.merge_llm_chunk_result(
            {"index": 0, "start": 0, "end": 100},
            {"key_statements": [{"text": "旧式陈述", "quote": "旧式陈述"}]},
            "旧式陈述", flags, errors)
        self.assertEqual(result["chunk_outcome"], "ok")

    def test_neg_damaged_blocked_outcome(self):
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            return zero_response()

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [canonical("neg_damaged")],
                          "config": CFG, "use_llm": True})
        self.assertEqual(calls, [])
        outcome, = result["input_outcomes"]
        self.assertEqual(outcome["outcome"], "blocked")
        self.assertIn("U+FFFD", outcome["reason"])

    def test_neg_repeated_quote_single_unit(self):
        note = canonical("neg_repeated_quote")
        quote = "临川市（虚构）共享单车调度的主要矛盾是潮汐淤积，即车辆在居住区与商务区之间随通勤单向流动导致的分布失衡。"
        # repeated identical quote: the provider MUST disambiguate via start_line
        start_line = note["source_text"].count("\n", 0, note["source_text"].find(quote)) + 1
        payload = json.dumps({"chunk_viable": True, "summary": "片段摘要。",
                              "key_statements": [{"text": "共享单车潮汐淤积是主要矛盾。",
                                                  "quote": quote, "start_line": start_line,
                                                  "kind": "assertion"}],
                              "topics": [], "limitations": [], "quality_flags": []},
                             ensure_ascii=False)
        with patch.dict(SRC.__globals__, {"call_chat_completion": lambda *a: payload}):
            data = SRC.__globals__["analyze_note"](note, CFG, use_llm=True)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["key_facts"]), 1)  # repeats don't inflate units

    def test_mixed_positive_and_zero_chunks_is_full_analysis(self):
        note = canonical("neg_repeated_quote")
        quote = "预期：提炼流程应识别独立信息单元仅有一条，不因篇幅长而高估素材价值。"
        cfg = {"source_analysis": {"chunk_chars": 200, "max_chunks": 12}, "write": {}}

        def provider(cfg, system, payload):
            if "片段 2" in payload["text"]:
                return json.dumps({"chunk_viable": True, "summary": "片段摘要。",
                                   "key_statements": [{"text": "独立信息单元仅一条。",
                                                       "quote": quote, "kind": "assertion"}],
                                   "topics": [], "limitations": [],
                                   "quality_flags": []}, ensure_ascii=False)
            return zero_response("第一片段无可沉淀信息")

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            data = SRC.__globals__["analyze_note"](note, cfg, use_llm=True)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["coverage"], "full")
        self.assertEqual(data["coverage_info"]["error_ranges"], [])
        self.assertEqual(len(data["key_facts"]), 1)
        self.assertTrue(any("显式零片段" in lim for lim in data["limitations"]))

    def test_failed_plus_zero_chunk_stays_partial(self):
        note = canonical("neg_repeated_quote")
        # small chunks force a genuinely multi-chunk read (fixture ~360 chars)
        cfg = {"source_analysis": {"chunk_chars": 200, "max_chunks": 12}, "write": {}}
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("chunk one dead")
            return zero_response("零片段")

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            data = SRC.__globals__["analyze_note"](note, cfg, use_llm=True)
        self.assertGreaterEqual(len(calls), 2)  # failed chunk AND zero chunk both ran
        self.assertEqual(data["status"], "partial")
        self.assertNotEqual(data["coverage"], "full")
        self.assertEqual(len(data["coverage_info"]["error_ranges"]), 1)
        self.assertTrue(any("显式零片段" in lim for lim in data["limitations"]))

    def test_budget_excluded_zero_chunks_stay_partial(self):
        note = canonical("neg_repeated_quote")
        cfg = {"source_analysis": {"chunk_chars": 200, "max_chunks": 1}, "write": {}}

        def provider(cfg, system, payload):
            return zero_response("零片段")

        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            data = SRC.__globals__["analyze_note"](note, cfg, use_llm=True)
        self.assertEqual(data["status"], "partial")
        self.assertEqual(data["coverage"], "partial")
        self.assertTrue(data["coverage_info"]["excluded_ranges"])

    def test_invalid_viability_type_is_chunk_error(self):
        flags: list[str] = []
        errors: list[str] = []
        with self.assertRaises(sa.SourceAnalysisError):
            sa.merge_llm_chunk_result({"index": 0, "start": 0, "end": 10},
                                      {"chunk_viable": "false", "reason": "x",
                                       "key_statements": []},
                                      "0123456789", flags, errors)

    def test_contradictory_zero_with_candidates_is_error(self):
        flags: list[str] = []
        errors: list[str] = []
        with self.assertRaises(sa.SourceAnalysisError):
            sa.merge_llm_chunk_result({"index": 0, "start": 0, "end": 100},
                                      {"chunk_viable": False, "reason": "没有内容",
                                       "key_statements": [{"text": "矛盾候选", "quote": "矛盾候选"}]},
                                      "矛盾候选", flags, errors)

    def test_old_positive_response_without_viability_stays_compatible(self):
        flags: list[str] = []
        errors: list[str] = []
        result = sa.merge_llm_chunk_result(
            {"index": 0, "start": 0, "end": 100},
            {"summary": "旧式正向响应。", "key_statements": [{"text": "旧式陈述", "quote": "旧式陈述"}]},
            "旧式陈述", flags, errors)
        self.assertEqual(result["chunk_outcome"], "ok")
        self.assertTrue(result["units"][0]["verified"])

    def test_per_input_mixed_success_and_zero_mapping(self):
        calls: list = []

        def provider(cfg, system, payload):
            calls.append(1)
            return zero_response("无可沉淀信息")

        clean = {"rel": "raw/clean.md", "title": "干净", "body": "这是足够长的一句话，包含事实。",
                 "summary": "", "metadata": {},
                 "source_text": "这是足够长的一句话，包含事实。",
                 "source_sha256": hashlib.sha256("这是足够长的一句话，包含事实。".encode("utf-8")).hexdigest()}

        def mixed_provider(cfg, system, payload):
            if "这是足够长的一句话" in payload["text"]:
                return positive_response("这是足够长的一句话，包含事实。")
            return zero_response("无可沉淀信息")

        with patch.dict(SRC.__globals__, {"call_chat_completion": mixed_provider}):
            result = SRC({"notes": [clean, canonical("neg_irrelevant")],
                          "config": CFG, "use_llm": True})
        self.assertEqual(result["processed"], 1)
        outcomes = {o["rel"]: o for o in result["input_outcomes"]}
        self.assertEqual(outcomes["raw/clean.md"]["outcome"], "ok")
        self.assertTrue(outcomes["raw/clean.md"]["complete"])
        self.assertEqual(len(outcomes["raw/clean.md"]["targets"]), 1)
        self.assertEqual(outcomes["raw/neg_irrelevant.md"]["outcome"], "zero")
        self.assertTrue(outcomes["raw/neg_irrelevant.md"]["complete"])
        self.assertEqual(outcomes["raw/neg_irrelevant.md"]["targets"], [])
        # zero notes produce no card; the only page belongs to the clean source
        self.assertEqual(len(result["created"]), 1)


if __name__ == "__main__":
    unittest.main()
