"""T10 hard gate: U+FFFD (decoding-damaged text) is rejected at every generator
entry seam BEFORE provider invocation; damaged model responses are errors.

Uses the ACTUAL canonical public fixture bytes; the raw invalid-byte adapter
case is covered elsewhere (executor_notes UnicodeDecodeError path).
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

from core import text_integrity as ti  # noqa: E402
from core.skill_executor import load_executor  # noqa: E402

SRC = load_executor(ROOT, "topic-research-compile")

NEG_DAMAGED = ROOT / "tests" / "fixtures" / "card-baseline" / "neg_damaged.md"
RAW = NEG_DAMAGED.read_bytes()
TEXT = RAW.decode("utf-8")  # valid UTF-8 containing U+FFFD
SHA = hashlib.sha256(RAW).hexdigest()
assert ti.REPLACEMENT in TEXT, "canonical fixture must contain U+FFFD"


def damaged_note(rel="raw/neg_damaged.md"):
    return {"rel": rel, "title": "损坏的公开合成输入", "body": TEXT, "summary": "",
            "metadata": {}, "source_text": TEXT, "source_sha256": SHA}


def zero_call_recorder():
    calls: list = []

    def provider(*args, **kwargs):
        calls.append(1)
        return "{}"

    return provider, calls


class ModuleTests(unittest.TestCase):
    def test_module_basics(self):
        self.assertTrue(ti.contains_replacement({"a": ["中�文"]}))
        self.assertFalse(ti.contains_replacement({"a": "正常？问号"}))
        reasons = ti.damaged_reasons(damaged_note(), "raw/x.md")
        self.assertTrue(reasons and "U+FFFD" in reasons[0] and "damaged_source" in reasons[0])
        # valid unicode stays valid: emoji, rare CJK, BOM, CRLF, question marks
        clean = {"source_text": "﻿罕见甙煊字与 emoji 🙂 ？\r\n行二", "body": "ok", "title": "题"}
        self.assertEqual(ti.damaged_reasons(clean, "raw/ok.md"), [])

    def test_clean_response_gate(self):
        with self.assertRaises(ValueError):
            ti.assert_clean_response('{"a": "坏�了", "unused": {"x": "�"}}', "w")
        ti.assert_clean_response('{"a": "好？的"}', "w")  # no raise

    def test_input_bytes_not_mutated(self):
        before = RAW
        ti.damaged_reasons(damaged_note(), "raw/x.md")
        self.assertEqual(NEG_DAMAGED.read_bytes(), before)


class SourceExecutorGateTests(unittest.TestCase):
    CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12}, "write": {}}

    def test_damaged_input_blocked_before_provider_with_no_card(self):
        provider, calls = zero_call_recorder()
        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [damaged_note()], "config": self.CFG,
                          "use_llm": True})
        self.assertEqual(calls, [])  # sentinel provider never invoked
        self.assertEqual(result["created"], [])
        self.assertEqual(result["processed"], 0)
        self.assertTrue(any("U+FFFD" in issue and "damaged" in issue
                            for issue in result["issues"]))

    def test_mixed_batch_processes_only_undamaged_sources(self):
        clean = {"rel": "raw/clean.md", "title": "干净样本", "body": "这是足够长的一句话，包含事实。",
                 "summary": "", "metadata": {},
                 "source_text": "这是足够长的一句话，包含事实。",
                 "source_sha256": hashlib.sha256("这是足够长的一句话，包含事实。".encode("utf-8")).hexdigest()}
        provider, calls = zero_call_recorder()
        with patch.dict(SRC.__globals__, {"call_chat_completion": provider}):
            result = SRC({"notes": [clean, damaged_note()],
                          "config": self.CFG, "use_llm": False})
        self.assertEqual(result["processed"], 1)  # only the clean source
        self.assertEqual(len(result["created"]), 1)
        self.assertTrue(any("U+FFFD" in issue for issue in result["issues"]))
        self.assertEqual(calls, [])  # heuristic run: no provider regardless

    def test_damaged_model_response_is_error_not_output(self):
        note = {"rel": "raw/clean2.md", "title": "干净样本", "body": "这是足够长的一句话，包含事实。",
                "summary": "", "metadata": {},
                "source_text": "这是足够长的一句话，包含事实。",
                "source_sha256": hashlib.sha256("这是足够长的一句话，包含事实。".encode("utf-8")).hexdigest()}

        def damaged_provider(cfg, system, payload):
            return json.dumps({"summary": "损�坏", "key_statements": [],
                               "unused": {"nested": "�"},
                               "limitations": [], "quality_flags": []})

        with patch.dict(SRC.__globals__, {"call_chat_completion": damaged_provider}):
            data = SRC.__globals__["analyze_note"](note, self.CFG, use_llm=True)
        self.assertEqual(data["status"], "partial")
        self.assertEqual(data["analysis_mode"], "heuristic-fallback")
        self.assertNotEqual(data["coverage"], "full")
        self.assertTrue(any("U+FFFD" in err for err in data["errors"]))


class AtomicSeedGateTests(unittest.TestCase):
    def test_damaged_note_blocks_before_provider(self):
        from core import atomic_seed
        calls: list = []

        def provider(*args, **kwargs):
            calls.append(1)
            return "{}"

        items, issues, meta = atomic_seed.generate_atomic_items(
            [damaged_note()], cfg={}, model_fn=provider)
        self.assertEqual(items, [])
        self.assertEqual(calls, [])
        self.assertEqual(meta["model"], "none")
        self.assertFalse(meta["complete"])
        self.assertIn("U+FFFD", meta["blocked_reason"])

    def test_ordinary_valid_note_still_extracts(self):
        from core import atomic_seed
        note = {"rel": "raw/ok.md", "title": "正常", "body": "普通但足够长的陈述句：该市完成了年度治理目标。",
                "source_text": "普通但足够长的陈述句：该市完成了年度治理目标。",
                "source_sha256": hashlib.sha256("普通但足够长的陈述句：该市完成了年度治理目标。".encode("utf-8")).hexdigest()}
        items, issues, meta = atomic_seed.generate_atomic_items([note], cfg={})
        self.assertTrue(items or meta["zero_reason"])

    def test_supplied_damaged_unit_or_snapshot_blocks(self):
        from core import atomic_seed
        unit = {"source": "raw/a.md", "quote": "带�的引用", "kind": "assertion"}
        snap = {"source_text": "干净原文", "source_sha256":
                hashlib.sha256("干净原文".encode("utf-8")).hexdigest()}
        items, issues, meta = atomic_seed.generate_atomic_items(
            units=[unit], snapshots={"raw/a.md": snap}, cfg={})
        self.assertEqual(items, [])
        self.assertFalse(meta["complete"])
        self.assertTrue(any("U+FFFD" in i for i in issues))

        good_unit = {"source": "raw/b.md", "quote": "干净引用", "kind": "assertion"}
        bad_snap = {"source_text": "原文带�", "source_sha256":
                    hashlib.sha256("原文带�".encode("utf-8")).hexdigest()}
        items, issues, meta = atomic_seed.generate_atomic_items(
            units=[good_unit], snapshots={"raw/b.md": bad_snap}, cfg={})
        self.assertEqual(items, [])
        self.assertTrue(any("U+FFFD" in i for i in issues))

    def test_damaged_model_response_falls_back_to_non_llm_preview(self):
        from core import atomic_seed
        note = {"rel": "raw/ok2.md", "title": "正常", "body": "另一句足够长的陈述：复核流程必须留下记录。",
                "source_text": "另一句足够长的陈述：复核流程必须留下记录。",
                "source_sha256": hashlib.sha256("另一句足够长的陈述：复核流程必须留下记录。".encode("utf-8")).hexdigest()}
        calls: list = []

        def damaged_provider(system, payload):
            calls.append(1)
            return json.dumps({"thoughts": [{"statement": "坏�", "kind": "assertion",
                                             "unit_ids": [0]}]}, ensure_ascii=False)

        items, issues, meta = atomic_seed.generate_atomic_items(
            [note], cfg={}, model_fn=damaged_provider)
        self.assertEqual(len(calls), 1)  # provider was called once on clean input
        self.assertEqual(meta["model"], "failed")  # preview is clearly NOT llm
        self.assertFalse(meta["complete"])
        self.assertTrue(any("U+FFFD" in i for i in issues))


class SharedConceptCaseGateTests(unittest.TestCase):
    """evidence_cards (concept/case shared entry) verify_snapshot refusal."""

    def test_damaged_note_refused_in_mixed_batch(self):
        from core import evidence_cards
        clean = {"rel": "raw/clean3.md", "title": "干净", "body": "有内容的句子。", "metadata": {},
                 "source_text": "有内容的句子。",
                 "source_sha256": hashlib.sha256("有内容的句子。".encode("utf-8")).hexdigest()}
        verified, issues = [], []
        for i, note in enumerate([clean, damaged_note()]):
            ok, note_issues = evidence_cards.verify_snapshot(note, i)
            issues.extend(note_issues)
            if ok is not None:
                verified.append(ok)
        self.assertEqual([n["rel"] for n in verified], ["raw/clean3.md"])
        self.assertTrue(any("U+FFFD" in i for i in issues))

    def test_bounded_call_rejects_damaged_response(self):
        from core import evidence_cards
        notes = [{"rel": "raw/clean4.md", "title": "干净", "body": "有内容的句子。", "metadata": {},
                  "source_text": "有内容的句子。",
                  "source_sha256": hashlib.sha256("有内容的句子。".encode("utf-8")).hexdigest()}]

        def damaged_provider(cfg, system, payload):
            return '{"concept_card_viable": true, "title": "坏�"}'

        context, terminal = evidence_cards.bounded_call(
            notes=notes, cfg={"evidence": {"max_source_chars": 1000, "max_context_chars": 4000}},
            section="evidence", system_prompt="s",
            payload_builder=lambda verified, known: {}, preflight=lambda: None,
            provider=damaged_provider, viability_key="concept_card_viable",
            analysis_mode="llm")
        self.assertIsNone(context)
        self.assertEqual(terminal["state"], "error")
        self.assertIn("U+FFFD", terminal["reason"])


class TopicGenerationGateTests(unittest.TestCase):
    def test_damaged_input_refused_and_response_rejected(self):
        from core import topic_generation as tg
        clean = {"rel": "raw/clean5.md", "title": "干净", "body": "有内容的句子。", "metadata": {},
                 "source_text": "有内容的句子。",
                 "source_sha256": hashlib.sha256("有内容的句子。".encode("utf-8")).hexdigest()}
        calls: list = []

        def recording_provider(cfg, system, payload):
            calls.append(1)
            return '{"topic_viable": true, "title": "坏�"}'

        result = tg.generate_topic("问题？", {}, [damaged_note()],
                                   call_provider=recording_provider)
        self.assertEqual(result["state"], "error")
        self.assertEqual(calls, [])  # all-damaged batch refused BEFORE provider
        self.assertTrue(any("U+FFFD" in i for i in result["issues"]))

        result = tg.generate_topic("问题？", {}, [clean], call_provider=recording_provider)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["state"], "error")  # damaged response
        self.assertIn("U+FFFD", result["reason"])


if __name__ == "__main__":
    unittest.main()
