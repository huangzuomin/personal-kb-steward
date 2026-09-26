# -*- coding: utf-8 -*-
"""T6 checkpoint A1: persisted source eligibility (core.card_pipeline).

Real producer path: the actual topic-research-compile executor + renderer
produce the persisted source card in a synthetic temp vault; the provider is
always a local stub (no network, no real model). collect_eligible_sources
itself performs no disk writes and no model calls. Direct persistence here is
fixture setup, not an end-to-end apply claim.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.card_pipeline import collect_eligible_sources
from core.vault import build_index, parse_frontmatter

ROOT = Path(__file__).resolve().parents[1]

ORIGINAL_TEXT = (
    "# 合成文档\n\n"
    "本节描述一个可复用的回顾触发器概念。回顾触发器必须绑定到已经存在的卡片上。\n"
    "第二句话说明该机制依赖已有知识对象而不是单纯的时间提醒。\n"
)
QUOTE = "回顾触发器必须绑定到已经存在的卡片上。"
LIMITATION_A = "合成限制A：结论未经独立核实"
LIMITATION_B = "合成限制B：第二次编译补充的限制"


def make_cfg(root):
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    cfg["knowledge_base"] = str(root)
    cfg["state_file"] = str(root / ".state.json")
    return cfg


def provider_answer(*, limitations=(LIMITATION_A,), quote=QUOTE,
                    topics=({"title": "回顾触发器", "content": "围绕回顾触发器的研究框架"},)):
    return json.dumps({
        "summary": "合成资料摘要",
        "key_statements": [
            {"text": "回顾触发器必须绑定到已经存在的卡片上", "quote": quote,
             "kind": "assertion"},
        ],
        "topics": list(topics),
        "limitations": list(limitations),
        "quality_flags": [],
    }, ensure_ascii=False)


class SourceEligibilityBase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cfg = make_cfg(self.root)
        self.raw_rel = "raw/doc.md"
        target = self.root / self.raw_rel
        target.parent.mkdir(parents=True)
        target.write_text(ORIGINAL_TEXT, encoding="utf-8")

    # -- fixture helpers ---------------------------------------------------
    def persist_compiled_card(self, *, use_llm=True, answer=None,
                              original_rel=None, target_rel=None):
        """Run the REAL executor+renderer once and persist the page it returns."""
        from core.skill_executor import execute_skill
        rel = original_rel or self.raw_rel
        raw_bytes = (self.root / rel).read_bytes()
        note = {
            "rel": rel,
            "title": "合成文档",
            "body": raw_bytes.decode("utf-8"),
            "metadata": {"material_kind": "synthetic"},
            "source_text": raw_bytes.decode("utf-8"),
            "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        }
        context = {"config": self.cfg, "notes": [note], "use_llm": use_llm}
        if use_llm:
            with patch("core.llm.call_chat_completion",
                       return_value=answer or provider_answer()):
                result = execute_skill(ROOT, "topic-research-compile", context)
        else:
            result = execute_skill(ROOT, "topic-research-compile", context)
        pages = result.get("created") or []
        self.assertTrue(pages, f"executor produced no page: {result.get('issues')}")
        page = pages[0]
        target = self.root / (target_rel or page["target"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page["content"], encoding="utf-8")
        return target.relative_to(self.root).as_posix()

    def rewrite_card_state(self, card_rel, mutate):
        """Rewrite only the card_state line of a persisted source card."""
        path = self.root / card_rel
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        state = copy.deepcopy(meta["card_state"])
        mutate(state)
        new_line = "card_state: " + json.dumps(state, ensure_ascii=False)
        updated, count = re.subn(r"card_state: [^\n]*", new_line, text, count=1)
        self.assertEqual(count, 1)
        path.write_text(updated, encoding="utf-8")

    def collect(self):
        return collect_eligible_sources(build_index(self.cfg), self.cfg)

    def rejected_reasons(self, result, card_rel):
        return [r["reason"] for r in result["rejected"] if r["source_note"] == card_rel]


class HappyPathTests(SourceEligibilityBase):
    def test_real_compiled_card_is_eligible_with_upstream_context(self):
        card = self.persist_compiled_card()
        result = self.collect()
        self.assertEqual(result["rejected"], [])
        self.assertEqual(len(result["notes"]), 1)
        note = result["notes"][0]
        self.assertEqual(note["rel"], self.raw_rel)
        raw_bytes = (self.root / self.raw_rel).read_bytes()
        self.assertEqual(note["source_text"], raw_bytes.decode("utf-8"))
        self.assertEqual(note["source_sha256"], hashlib.sha256(raw_bytes).hexdigest())
        upstream = note["metadata"]["upstream_analysis"]
        # Explicit limitations AND outer quality flags both survive.
        self.assertIn(LIMITATION_A, upstream["limitations"])
        self.assertTrue(any("未经独立来源核实" in x for x in upstream["limitations"]))
        self.assertEqual(upstream["speakers"], [])
        self.assertEqual(upstream["source_kind"], "unknown")
        self.assertEqual(result["source_note_paths"][self.raw_rel], [card])
        self.assertEqual(result["upstream_hashes"][card],
                         build_index(self.cfg).by_rel[card].sha256)
        self.assertEqual(result["topic_hints"],
                         [{"title": "回顾触发器",
                           "content": "围绕回顾触发器的研究框架",
                           "source_note": card}])

    def test_renderer_persists_limitations_and_topic_hints_in_card_state(self):
        card = self.persist_compiled_card()
        meta, _ = parse_frontmatter((self.root / card).read_text(encoding="utf-8"))
        analysis = meta["card_state"]["analysis"]
        self.assertIn(LIMITATION_A, analysis["limitations"])
        self.assertEqual(analysis["topic_hints"],
                         [{"title": "回顾触发器",
                           "content": "围绕回顾触发器的研究框架"}])


class ExclusionTests(SourceEligibilityBase):
    def test_legacy_card_without_card_state_is_excluded(self):
        card_dir = self.root / "wiki" / "sources"
        card_dir.mkdir(parents=True)
        (card_dir / "legacy-source.md").write_text(
            "---\ntitle: Legacy\ntype: source-note\nstatus: growing\n"
            "stage: compiled\nsources: [\"raw/doc.md\"]\n---\n# Legacy\n",
            encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertIn("缺少 card_state", self.rejected_reasons(result, "wiki/sources/legacy-source.md")[0])

    def test_heuristic_card_is_excluded(self):
        card = self.persist_compiled_card(use_llm=False)
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("analysis_mode 非 llm" in r
                            for r in self.rejected_reasons(result, card)))

    def test_partial_coverage_is_excluded(self):
        card = self.persist_compiled_card()

        def downgrade(state):
            state["analysis"]["coverage"] = "partial"
        self.rewrite_card_state(card, downgrade)
        # Outer frontmatter must agree with the stored analysis.
        path = self.root / card
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("\ncoverage: full\n", "\ncoverage: partial\n", 1),
                        encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("coverage 非 full" in r
                            for r in self.rejected_reasons(result, card)))

    def test_outer_inner_coverage_disagreement_is_excluded(self):
        card = self.persist_compiled_card()
        path = self.root / card
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("\ncoverage: full\n", "\ncoverage: partial\n", 1),
                        encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])

    def test_unwritten_planned_source_is_never_eligible(self):
        card_dir = self.root / "wiki" / "sources"
        card_dir.mkdir(parents=True)
        state = {
            "version": 1, "type": "source-note",
            "info_units": [{"text": "幽灵", "quote": "幽灵引用", "start": 0, "end": 4,
                            "start_line": 1, "end_line": 1, "verified": True,
                            "kind": "assertion", "source": "raw/ghost.md",
                            "source_sha256": "0" * 64}],
            "analysis": {"analysis_mode": "llm", "coverage": "full",
                         "source_type": "unknown", "speakers": [],
                         "source_hashes": {"raw/ghost.md": "0" * 64},
                         "errors": [], "limitations": [], "topic_hints": []},
        }
        (card_dir / "planned-source.md").write_text(
            "---\ntitle: Planned\ntype: source-note\nstatus: growing\n"
            "stage: compiling\nsources: [\"raw/ghost.md\"]\n"
            "analysis_mode: llm\ncoverage: full\n"
            f"card_state: {json.dumps(state, ensure_ascii=False)}\n---\n",
            encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("不在当前索引" in r
                            for r in self.rejected_reasons(result, "wiki/sources/planned-source.md")))

    def test_derived_source_loop_is_rejected(self):
        card = self.persist_compiled_card()
        path = self.root / card
        text = path.read_text(encoding="utf-8")
        updated = text.replace(
            f"sources: {json.dumps([self.raw_rel], ensure_ascii=False)}",
            f"sources: {json.dumps([card], ensure_ascii=False)}", 1)
        path.write_text(updated, encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("循环" in r for r in self.rejected_reasons(result, card)))


class ForgeryTests(SourceEligibilityBase):
    def setUp(self):
        super().setUp()
        self.card = self.persist_compiled_card()
        meta, _ = parse_frontmatter((self.root / self.card).read_text(encoding="utf-8"))
        self.unit = meta["card_state"]["info_units"][0]

    def test_forged_quote_is_refused(self):
        self.rewrite_card_state(self.card, lambda s: s["info_units"][0].update(
            quote="伪造的、不存在于原文的引用文字"))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("唯一定位" in r for r in self.rejected_reasons(result, self.card)))

    def test_forged_offset_is_refused(self):
        self.rewrite_card_state(self.card, lambda s: s["info_units"][0].update(
            start=s["info_units"][0]["start"] + 3))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("坐标与原文定位不一致" in r
                            for r in self.rejected_reasons(result, self.card)))

    def test_unverified_unit_invalidates_whole_card(self):
        self.rewrite_card_state(self.card, lambda s: s["info_units"][0].update(
            verified=False))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("未通过核验" in r for r in self.rejected_reasons(result, self.card)))

    def test_forged_declared_hash_is_refused(self):
        def forge(state):
            state["analysis"]["source_hashes"] = {self.raw_rel: "0" * 64}
        self.rewrite_card_state(self.card, forge)
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("声明 hash" in r for r in self.rejected_reasons(result, self.card)))


class StalenessTests(SourceEligibilityBase):
    def test_changed_original_with_captured_index_is_refused(self):
        self.persist_compiled_card()
        index = build_index(self.cfg)  # capture BEFORE the change
        original = self.root / self.raw_rel
        original.write_text(original.read_text(encoding="utf-8") + "\n追加的新句子。\n",
                            encoding="utf-8")
        result = collect_eligible_sources(index, self.cfg)
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("读取/校验失败" in r["reason"] for r in result["rejected"]))

    def test_stale_declared_hash_after_reindex_is_refused_and_not_refreshed(self):
        self.persist_compiled_card()
        original = self.root / self.raw_rel
        original.write_text(original.read_text(encoding="utf-8") + "\n追加的新句子。\n",
                            encoding="utf-8")
        result = self.collect()  # fresh index: captured hash is current
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("声明 hash" in r["reason"] for r in result["rejected"]))


class CumulativeAndDuplicateTests(SourceEligibilityBase):
    def test_two_cards_on_same_original_merge_restrictions(self):
        card_a = self.persist_compiled_card()
        answer_b = provider_answer(limitations=(LIMITATION_B,))
        card_b = self.persist_compiled_card(answer=answer_b,
                                            target_rel="wiki/sources/source-doc-b.md")
        self.assertNotEqual(card_a, card_b)
        result = self.collect()
        self.assertEqual(len(result["notes"]), 1, "same original must dedupe")
        upstream = result["notes"][0]["metadata"]["upstream_analysis"]
        self.assertIn(LIMITATION_A, upstream["limitations"])
        self.assertIn(LIMITATION_B, upstream["limitations"])
        self.assertEqual(upstream["limitations"], sorted(upstream["limitations"]))
        self.assertEqual(result["source_note_paths"][self.raw_rel], sorted([card_a, card_b]))
        self.assertEqual(set(result["upstream_hashes"]), {card_a, card_b})
        self.assertEqual(result["rejected"], [])

    def test_cumulative_sources_across_two_originals(self):
        second = self.root / "raw" / "second.md"
        second.write_text("# 第二份合成文档\n\n第二份资料同样描述回顾触发器的使用边界。\n",
                          encoding="utf-8")
        self.persist_compiled_card()
        self.persist_compiled_card(
            original_rel="raw/second.md",
            target_rel="wiki/sources/source-second.md",
            answer=provider_answer(
                quote="第二份资料同样描述回顾触发器的使用边界。"))
        result = self.collect()
        self.assertEqual([n["rel"] for n in result["notes"]],
                         sorted(["raw/doc.md", "raw/second.md"]))
        self.assertEqual(len(result["upstream_hashes"]), 2)


class ReviewCorrectionTests(SourceEligibilityBase):
    """Regressions for Astra's A1 review probes."""

    # -- 1. persisted CARD snapshot must be verified, per-card reasons -----
    def test_changed_source_card_after_capture_is_refused(self):
        card = self.persist_compiled_card()
        index = build_index(self.cfg)
        path = self.root / card
        path.write_bytes(path.read_bytes() + "\n卡片被篡改。\n".encode("utf-8"))
        result = collect_eligible_sources(index, self.cfg)
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("来源卡自身快照" in r["reason"]
                            for r in result["rejected"]))

    def test_deleted_source_card_after_capture_is_refused_not_raised(self):
        card = self.persist_compiled_card()
        index = build_index(self.cfg)
        (self.root / card).unlink()
        result = collect_eligible_sources(index, self.cfg)
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("来源卡自身快照" in r["reason"]
                            for r in result["rejected"]))

    # -- 2. exact persisted coordinates and version ------------------------
    def test_missing_coordinates_are_refused_not_reconstructed(self):
        card = self.persist_compiled_card()

        def strip(state):
            for key in ("start", "end", "start_line", "end_line"):
                state["info_units"][0].pop(key, None)
        self.rewrite_card_state(card, strip)
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("完整坐标" in r
                            for r in self.rejected_reasons(result, card)))

    def test_non_exact_int_coordinates_are_refused(self):
        for value in (True, 1.0, "12"):
            with self.subTest(value=value):
                fresh = SourceEligibilityBase()
                fresh.setUp()
                self.addCleanup(fresh.doCleanups)
                card = fresh.persist_compiled_card()
                fresh.rewrite_card_state(card, lambda s, v=value:
                                         s["info_units"][0].update(start=v))
                result = fresh.collect()
                self.assertEqual(result["notes"], [])
                self.assertTrue(any("精确整数" in r
                                    for r in fresh.rejected_reasons(result, card)))

    def test_bool_version_is_not_exact_int_one(self):
        card = self.persist_compiled_card()
        self.rewrite_card_state(card, lambda s: s.update(version=True))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("精确 version=1" in r
                            for r in self.rejected_reasons(result, card)))

    # -- 3. malformed shapes reject the card, others still collect ---------
    def test_malformed_hash_map_is_rejected_without_crash(self):
        card = self.persist_compiled_card()
        self.rewrite_card_state(card, lambda s:
                                s["analysis"].update(source_hashes=["not-a-map"]))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("source_hashes 不是" in r
                            for r in self.rejected_reasons(result, card)))

    def test_malformed_outer_quality_flags_are_rejected_without_crash(self):
        card = self.persist_compiled_card()
        path = self.root / card
        path.write_text(path.read_text(encoding="utf-8").replace(
            "\nquality_flags: [", "\nquality_flags: '非数组[", 1), encoding="utf-8")
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("quality_flags" in r
                            for r in self.rejected_reasons(result, card)))

    def test_malformed_limitations_are_rejected_without_crash(self):
        card = self.persist_compiled_card()
        self.rewrite_card_state(card, lambda s:
                                s["analysis"].update(limitations="不是数组"))
        result = self.collect()
        self.assertEqual(result["notes"], [])
        self.assertTrue(any("limitations 不是字符串数组" in r
                            for r in self.rejected_reasons(result, card)))

    def test_mixed_valid_and_malformed_cards(self):
        second = self.root / "raw" / "second.md"
        second.write_text("# 第二份合成文档\n\n第二份资料同样描述回顾触发器的使用边界。\n",
                          encoding="utf-8")
        good = self.persist_compiled_card(
            original_rel="raw/second.md",
            target_rel="wiki/sources/source-second-good.md",
            answer=provider_answer(quote="第二份资料同样描述回顾触发器的使用边界。"))
        bad = self.persist_compiled_card()
        self.rewrite_card_state(bad, lambda s:
                                s["analysis"].update(source_hashes=["bad"]))
        result = self.collect()
        self.assertEqual([n["rel"] for n in result["notes"]], ["raw/second.md"])
        self.assertEqual(self.rejected_reasons(result, bad) and True, True)
        self.assertEqual(self.rejected_reasons(result, good), [])

    # -- 4. order-independent source_kind resolution -----------------------
    def test_none_then_unknown_kind_merge_does_not_crash(self):
        card_a = self.persist_compiled_card()
        self.rewrite_card_state(card_a, lambda s:
                                s["analysis"].update(source_type=None))
        self.persist_compiled_card(target_rel="wiki/sources/z-second.md")
        result = self.collect()
        self.assertEqual(len(result["notes"]), 1)
        self.assertEqual(result["notes"][0]["metadata"]["upstream_analysis"]["source_kind"],
                         "unknown")

    def test_known_kind_with_unknown_preserves_known_kind(self):
        card_a = self.persist_compiled_card()
        self.rewrite_card_state(card_a, lambda s:
                                s["analysis"].update(source_type="dialogue"))
        self.persist_compiled_card(target_rel="wiki/sources/z-second.md")
        result = self.collect()
        self.assertEqual(len(result["notes"]), 1)
        upstream = result["notes"][0]["metadata"]["upstream_analysis"]
        self.assertEqual(upstream["source_kind"], "dialogue")
        self.assertTrue(any("混合来源" in x for x in upstream["limitations"]))

    def test_conflicting_known_kinds_stay_unknown_in_both_orders(self):
        for order in ("dialogue_first", "article_first"):
            with self.subTest(order=order):
                fresh = SourceEligibilityBase()
                fresh.setUp()
                self.addCleanup(fresh.doCleanups)
                kinds = ("dialogue", "article") if order == "dialogue_first" \
                    else ("article", "dialogue")
                first = fresh.persist_compiled_card()
                fresh.rewrite_card_state(first, lambda s, k=kinds[0]:
                                         s["analysis"].update(source_type=k))
                second = fresh.persist_compiled_card(
                    target_rel="wiki/sources/z-second.md")
                fresh.rewrite_card_state(second, lambda s, k=kinds[1]:
                                         s["analysis"].update(source_type=k))
                result = fresh.collect()
                self.assertEqual(len(result["notes"]), 1)
                upstream = result["notes"][0]["metadata"]["upstream_analysis"]
                self.assertEqual(upstream["source_kind"], "unknown")
                self.assertTrue(any("冲突" in x for x in upstream["limitations"]))
                self.assertTrue(any("冲突" in i for i in result["issues"]))

    def test_three_cards_conflicting_kinds_are_order_independent(self):
        kinds = ("dialogue", "article", "oral-case")
        cards = []
        cards.append(self.persist_compiled_card())
        self.rewrite_card_state(cards[0], lambda s:
                                s["analysis"].update(source_type=kinds[0]))
        cards.append(self.persist_compiled_card(target_rel="wiki/sources/z-second.md"))
        self.rewrite_card_state(cards[1], lambda s:
                                s["analysis"].update(source_type=kinds[1]))
        cards.append(self.persist_compiled_card(target_rel="wiki/sources/a-third.md"))
        self.rewrite_card_state(cards[2], lambda s:
                                s["analysis"].update(source_type=kinds[2]))
        result = self.collect()
        upstream = result["notes"][0]["metadata"]["upstream_analysis"]
        self.assertEqual(upstream["source_kind"], "unknown")
        for kind in kinds:
            self.assertTrue(any(kind in x for x in upstream["limitations"]))

    # -- 5. topic hints keep their ACTUAL origin card ----------------------
    def test_topic_hint_keeps_actual_origin_not_cards_first(self):
        card_a = self.persist_compiled_card()  # hint: 回顾触发器 (card A)
        self.persist_compiled_card(
            target_rel="wiki/sources/z-second.md",
            answer=provider_answer(
                topics=({"title": "第二条专题", "content": "只出现在第二张卡"},)))
        result = self.collect()
        self.assertEqual(result["topic_hints"], [
            {"title": "回顾触发器", "content": "围绕回顾触发器的研究框架",
             "source_note": card_a},
            {"title": "第二条专题", "content": "只出现在第二张卡",
             "source_note": "wiki/sources/z-second.md"},
        ])

    # -- 6. offsets semantics sanity: normalized char offsets, not bytes ---
    def test_multibyte_original_offsets_are_character_offsets(self):
        card = self.persist_compiled_card()
        meta, _ = parse_frontmatter((self.root / card).read_text(encoding="utf-8"))
        unit = meta["card_state"]["info_units"][0]
        norm = ORIGINAL_TEXT
        self.assertEqual(norm[unit["start"]:unit["end"]], unit["quote"])


if __name__ == "__main__":
    unittest.main()
