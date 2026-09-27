"""Semantic critic layer: tiers, taxonomy, contract, review, plan integration."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.semantic_critic import (  # noqa: E402
    OBJECTION_CODES,
    CriticError,
    apply_semantic_critic,
    build_critic_payload,
    tier_for_page,
    validate_critic_report,
    TIER_LIGHT,
    TIER_STRICT,
)
from core.llm import LLMError  # noqa: E402


def _report(**kw):
    base = {"verdict": "pass", "objections": [], "summary": "无问题"}
    base.update(kw)
    return base


def _objection(**kw):
    base = {"code": "unsupported_claim", "severity": "flag",
            "quote_card": "卡片说 A", "quote_source": "", "note": "来源无对应内容"}
    base.update(kw)
    return base


class TierTests(unittest.TestCase):
    def test_seed_card_is_light(self):
        self.assertEqual(tier_for_page({"type": "seed-card"}), TIER_LIGHT)

    def test_topic_and_concept_are_strict(self):
        for t in ("topic-card", "topic-page", "concept-card", "claim-check"):
            self.assertEqual(tier_for_page({"type": t}), TIER_STRICT)

    def test_unknown_defaults_to_strict(self):
        self.assertEqual(tier_for_page({"type": "mystery"}), TIER_STRICT)
        self.assertEqual(tier_for_page({}), TIER_STRICT)

    def test_skill_fallback(self):
        self.assertEqual(tier_for_page({"skill": "mindseed-grow"}), TIER_STRICT)


class ContractTests(unittest.TestCase):
    def test_valid_pass_report(self):
        self.assertEqual(validate_critic_report(_report()), [])

    def test_valid_block_report(self):
        r = _report(verdict="block",
                    objections=[_objection(severity="block", code="fabricated_detail")])
        self.assertEqual(validate_critic_report(r), [])

    def test_bad_verdict(self):
        self.assertTrue(validate_critic_report(_report(verdict="maybe")))

    def test_bad_code(self):
        r = _report(verdict="flag", objections=[_objection(code="nope")])
        self.assertTrue(validate_critic_report(r))

    def test_pass_with_objections_rejected(self):
        r = _report(verdict="pass", objections=[_objection()])
        problems = validate_critic_report(r)
        self.assertTrue(any("pass" in p for p in problems))

    def test_block_severity_requires_block_verdict(self):
        r = _report(verdict="flag", objections=[_objection(severity="block")])
        problems = validate_critic_report(r)
        self.assertTrue(any("block" in p for p in problems))

    def test_non_dict_rejected(self):
        self.assertTrue(validate_critic_report([1, 2]))

    def test_taxonomy_covers_expected_codes(self):
        for code in ("unsupported_claim", "question_as_fact", "bad_citation",
                     "link_mismatch", "overgeneralization", "missing_limitation",
                     "fabricated_detail", "critic_error"):
            self.assertIn(code, OBJECTION_CODES)


class ReviewTests(unittest.TestCase):
    def _run(self, llm_output):
        import core.semantic_critic as sc
        page = {"title": "T", "type": "topic-card", "rel_path": "k/t.md",
                "content": "内容", "sources": ["raw/a.md"]}
        with mock.patch.object(sc, "llm_generate", return_value=llm_output):
            return sc.critic_review({"llm": {"backend": "api"}}, page,
                                    {"raw/a.md": "原文"})

    def test_pass_through(self):
        report = self._run(json.dumps(_report(), ensure_ascii=False))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["tier"], TIER_STRICT)
        self.assertIn("checked_at", report)

    def test_transport_failure_raises(self):
        import core.semantic_critic as sc
        page = {"content": "x", "sources": ["raw/a.md"]}
        with mock.patch.object(sc, "llm_generate",
                               side_effect=LLMError("boom")):
            with self.assertRaises(CriticError):
                sc.critic_review({}, page, {"raw/a.md": "t"})

    def test_bad_json_raises(self):
        with self.assertRaises(CriticError):
            self._run("not json at all")

    def test_contract_violation_raises(self):
        bad = json.dumps(_report(verdict="pass",
                                objections=[_objection()]), ensure_ascii=False)
        with self.assertRaises(CriticError):
            self._run(bad)

    def test_payload_carries_card_and_sources(self):
        page = {"title": "T", "content": "卡片内容", "sources": ["raw/a.md"]}
        payload = build_critic_payload(page, {"raw/a.md": "原文"}, TIER_LIGHT)
        self.assertEqual(payload["task"], "critic-review")
        self.assertEqual(payload["card"]["content"], "卡片内容")
        self.assertEqual(payload["sources"][0]["rel"], "raw/a.md")


class ApplyTests(unittest.TestCase):
    def _cfg(self, tmp: Path):
        kb = tmp / "kb"
        kb.mkdir()
        (kb / "raw").mkdir()
        (kb / "raw" / "a.md").write_text("来源原文", encoding="utf-8")
        runs = tmp / "runs"
        return {"knowledge_base": str(kb),
                "safety": {"runs_dir": str(runs)}}

    def _plan(self):
        return {
            "run_id": "r1",
            "planned_pages": [
                {"rel_path": "k/t.md", "content": "# T\n断言",
                 "sources": ["raw/a.md"], "type": "topic-card"},
                {"rel_path": "k/s.md", "content": "# S\n种子",
                 "sources": ["raw/a.md"], "type": "seed-card"},
                {"rel_path": "k/nosrc.md", "content": "# N", "sources": []},
            ],
            "manual_review": [],
        }

    def test_block_flags_page_and_queue(self):
        import core.semantic_critic as sc
        tmp_cfg = self._cfg(Path(__import__("tempfile").mkdtemp()))
        # runs_dir needs a real location; point .openclaw at tmp
        plan = self._plan()
        block = _report(verdict="block", summary="编造",
                        objections=[_objection(severity="block",
                                              code="fabricated_detail")])

        def fake_review(cfg, page, texts, tier=None):
            return dict(block, tier=TIER_STRICT,
                        checked_at="2026-01-01T00:00:00+00:00")

        with mock.patch.object(sc, "critic_review", side_effect=fake_review):
            stats = sc.apply_semantic_critic(tmp_cfg, tmp_cfg, plan)
        page = plan["planned_pages"][0]
        self.assertTrue(page["review_required"])
        self.assertIn("critic_report", page)
        self.assertEqual(page["critic_verdict"], "block")
        self.assertEqual(stats["blocked"], 2)  # both sourced pages blocked
        self.assertEqual(stats["skipped"], 1)  # no-source page skipped
        types = [m["type"] for m in plan["manual_review"]]
        self.assertTrue(all(t == "semantic_critic_block" for t in types))
        self.assertIn("fabricated_detail",
                      plan["manual_review"][0]["objection_codes"])

    def test_critic_error_degrades_to_flag(self):
        import core.semantic_critic as sc
        tmp_cfg = self._cfg(Path(__import__("tempfile").mkdtemp()))
        plan = self._plan()
        with mock.patch.object(sc, "critic_review",
                               side_effect=CriticError("timeout")):
            stats = sc.apply_semantic_critic(tmp_cfg, tmp_cfg, plan)
        self.assertEqual(stats["errors"], 2)
        self.assertEqual(stats["passed"], 0)
        page = plan["planned_pages"][0]
        self.assertTrue(page["review_required"])
        self.assertEqual(page["critic_verdict"], "flag")
        codes = plan["manual_review"][0]["objection_codes"]
        self.assertIn("critic_error", codes)

    def test_pass_leaves_page_untouched(self):
        import core.semantic_critic as sc
        tmp_cfg = self._cfg(Path(__import__("tempfile").mkdtemp()))
        plan = self._plan()
        ok = _report()

        def fake_review(cfg, page, texts, tier=None):
            return dict(ok, tier=tier or TIER_STRICT,
                        checked_at="2026-01-01T00:00:00+00:00")

        with mock.patch.object(sc, "critic_review", side_effect=fake_review):
            stats = sc.apply_semantic_critic(tmp_cfg, tmp_cfg, plan)
        self.assertEqual(stats["passed"], 2)
        self.assertNotIn("review_required", plan["planned_pages"][0])
        self.assertEqual(plan["manual_review"], [])


class CliCriticWiringTests(unittest.TestCase):
    def _load_cli(self):
        import importlib.util
        path = ROOT / "scripts" / "personal_kb_steward.py"
        spec = importlib.util.spec_from_file_location("pks_cli2", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["pks_cli2"] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_critic_flags_reach_command(self):
        mod = self._load_cli()
        captured = {}
        mod.config = lambda: {"llm": {"backend": "api"}}

        def fake_init_kb(cfg, **kwargs):
            captured.update(kwargs)
            return 0

        mod.command_init_kb = fake_init_kb
        rc = mod.main(["init-kb", "--critic", "--critic-backend", "agent"])
        self.assertEqual(rc, 0)
        self.assertTrue(captured["critic"])
        self.assertEqual(captured["critic_backend"], "agent")

    def test_critic_defaults_off(self):
        mod = self._load_cli()
        captured = {}
        mod.config = lambda: {"llm": {"backend": "api"}}

        def fake_init_kb(cfg, **kwargs):
            captured.update(kwargs)
            return 0

        mod.command_init_kb = fake_init_kb
        rc = mod.main(["init-kb"])
        self.assertEqual(rc, 0)
        self.assertFalse(captured["critic"])
        self.assertIsNone(captured["critic_backend"])


if __name__ == "__main__":
    unittest.main()
