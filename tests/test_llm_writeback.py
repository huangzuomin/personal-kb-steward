import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.llm_plan import LLMPlanError, topic_pages_from_llm
from scripts import personal_kb_steward as steward


ROOT = Path(__file__).resolve().parents[1]


class LlmTopicWritebackTests(unittest.TestCase):
    def make_cfg(self, kb: Path) -> dict:
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        cfg["knowledge_base"] = str(kb)
        cfg["state_file"] = str(kb / ".state.json")
        cfg["write"]["topics_dir"] = "_kb-steward/topics"
        cfg["safety"]["plans_dir"] = str(kb / ".openclaw" / "plans")
        cfg["safety"]["runs_dir"] = str(kb / ".openclaw" / "runs")
        cfg["safety"]["processed_index"] = str(kb / ".openclaw" / "processed-index.json")
        cfg["safety"]["manual_review_queue"] = str(kb / ".openclaw" / "manual-review" / "queue.jsonl")
        cfg["safety"]["backup_dir"] = str(kb / ".openclaw" / "backups")
        cfg["safety"]["operation_log"] = str(kb / ".openclaw" / "operation-log.jsonl")
        return cfg

    def seed(self, kb: Path) -> None:
        (kb / "raw").mkdir(parents=True)
        (kb / "quicknote").mkdir()
        (kb / "inbox").mkdir()
        for idx in range(3):
            (kb / "raw" / f"source-{idx}.md").write_text(
                f"# AI 媒体来源 {idx}\n\nAI 媒体转型、地方新闻服务与知识基础设施的可验证材料 {idx}。",
                encoding="utf-8",
            )

    def test_converter_ignores_model_path_and_uses_configured_topic_dir(self):
        result = {
            "ok": True,
            "skill": "topic-insight-miner",
            "items": [{
                "title": "地方媒体 AI 转型的真实问题",
                "type": "topic-card",
                "status": "growing",
                "stage": "promising",
                "sources": ["raw/a.md", "raw/b.md", "raw/c.md"],
                "summary": "把提效问题转成组织与服务能力问题。",
                "confidence": "high",
                "review_required": False,
                "path": "wiki/topics/phantom.md",
            }],
        }
        cfg = {"write": {"topics_dir": "_kb-steward/topics"},
               "quality_gate": {"min_sources_for_topic": 3}}
        page = topic_pages_from_llm(cfg, result, "run-1")[0]
        self.assertTrue(page["rel_path"].startswith("_kb-steward/topics/"))
        self.assertNotIn("wiki/topics/phantom.md", page["rel_path"])
        self.assertTrue(page["review_required"])
        self.assertIn('"producer": "llm_skill_runtime"', page["content"])

    def test_converter_rejects_non_topic_card(self):
        cfg = {"write": {"topics_dir": "_kb-steward/topics"},
               "quality_gate": {"min_sources_for_topic": 3}}
        result = {
            "ok": True,
            "skill": "topic-insight-miner",
            "items": [{
                "title": "错误类型",
                "type": "topic-page",
                "status": "growing",
                "stage": "candidate",
                "sources": ["raw/a.md"],
                "summary": "x",
                "confidence": "medium",
                "review_required": True,
            }],
        }
        with self.assertRaises(LLMPlanError):
            topic_pages_from_llm(cfg, result, "run-1")

    def test_mock_llm_items_replace_executor_template_in_real_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = self.make_cfg(kb)

            before = {p.relative_to(kb).as_posix() for p in kb.rglob("*.md")}
            plan = steward.make_execution_plan(
                cfg,
                "发现选题 AI 媒体",
                use_llm=True,
                mock_llm=True,
                include_all=True,
            )

            self.assertTrue(plan["llm_runtime"]["ok"])
            self.assertTrue(plan["llm_runtime"]["writeback_used"])
            self.assertEqual(plan["llm_runtime"]["writeback_pages"], 1)
            self.assertEqual(len(plan["planned_pages"]), 1)
            page = plan["planned_pages"][0]
            self.assertTrue(page["rel_path"].startswith("_kb-steward/topics/"))
            self.assertIn("Mock LLM output for runtime verification", page["content"])
            self.assertNotIn("围绕“发现选题 AI 媒体”", page["content"])
            self.assertTrue(page["review_required"])
            self.assertEqual(set(page["retrieval_source_hashes"]), {f"raw/source-{i}.md" for i in range(3)})
            self.assertIn("planned_pages_require_review", {x["type"] for x in plan["manual_review"]})
            after = {p.relative_to(kb).as_posix() for p in kb.rglob("*.md")}
            self.assertEqual(before, after)
            self.assertFalse((kb / "_kb-steward").exists())

    def test_llm_failure_does_not_fall_back_to_executor_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = self.make_cfg(kb)
            failure = {
                "enabled": True,
                "mock": False,
                "skill": "topic-insight-miner",
                "skill_path": "skills/topic-insight-miner/SKILL.md",
                "ok": False,
                "issues": ["provider timeout"],
                "items": [],
                "previews": [],
            }
            with patch.object(steward, "run_skill_runtime", return_value=failure):
                plan = steward.make_execution_plan(
                    cfg,
                    "发现选题 AI 媒体",
                    use_llm=True,
                    include_all=True,
                )

            self.assertFalse(plan["llm_runtime"]["writeback_used"])
            self.assertEqual(plan["planned_pages"], [])
            self.assertIn("llm_runtime_issues", {x["type"] for x in plan["manual_review"]})

    def test_documented_model_name_and_timeout_match_runtime_contract(self):
        docs = (ROOT / "docs" / "llm-setup.md").read_text(encoding="utf-8")
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        self.assertIn("OPENAI_MODEL=", docs)
        self.assertNotIn("\nLLM_MODEL=", docs)
        self.assertEqual(cfg["llm"]["timeout_seconds"], 300)


if __name__ == "__main__":
    unittest.main()
