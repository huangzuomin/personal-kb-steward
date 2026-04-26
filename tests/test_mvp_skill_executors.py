import json
import unittest
from pathlib import Path

from core.skill_executor import execute_skill, load_executor


ROOT = Path(__file__).resolve().parents[1]
MVP_SKILLS = ["mindseed-grow", "topic-insight-miner", "writing-material-pack"]


class MvpSkillExecutorTests(unittest.TestCase):
    def test_mvp_skill_files_exist(self):
        for skill in MVP_SKILLS:
            with self.subTest(skill=skill):
                base = ROOT / "skills" / skill
                self.assertTrue((base / "SKILL.md").exists())
                self.assertTrue((base / "schema.json").exists())
                self.assertTrue((base / "renderer.py").exists())
                self.assertTrue((base / "executor.py").exists())
                json.loads((base / "schema.json").read_text(encoding="utf-8"))

    def test_executor_loader_loads_only_mvp_targets(self):
        for skill in MVP_SKILLS:
            with self.subTest(skill=skill):
                self.assertTrue(callable(load_executor(ROOT, skill)))

    def test_mindseed_executor_returns_page_specs(self):
        result = execute_skill(ROOT, "mindseed-grow", {
            "config": {"clustering": {"max_clusters": 3}},
            "notes": [
                {"rel": "quicknote/a.md", "title": "Cursor 课堂", "body": "Cursor AI 编程课堂演示", "summary": "Cursor 课堂"},
                {"rel": "quicknote/b.md", "title": "Cursor 复盘", "body": "Cursor 重构测试脚本", "summary": "Cursor 复盘"},
            ],
        })
        self.assertEqual(result["skill"], "mindseed-grow")
        self.assertGreaterEqual(len(result["pages"]), 1)
        self.assertEqual(result["pages"][0]["rel_dir_key"], "seed_dir")

    def test_topic_and_material_executors_return_expected_types(self):
        topic = execute_skill(ROOT, "topic-insight-miner", {
            "config": {"quality_gate": {"min_sources_for_topic": 2}},
            "query": "Cursor 课堂",
            "notes": [
                {"rel": "wiki/seeds/a.md", "title": "Cursor 课堂", "body": "", "summary": ""},
                {"rel": "wiki/seeds/b.md", "title": "AI 编程教学", "body": "", "summary": ""},
            ],
        })
        self.assertEqual(topic["pages"][0]["item"]["type"], "topic-card")

        material = execute_skill(ROOT, "writing-material-pack", {
            "config": {"quality_gate": {"min_evidence_items_for_material_pack": 2}},
            "query": "Cursor 课堂",
            "notes": [{"rel": "wiki/topics/a.md", "title": "Cursor", "body": "", "summary": ""}],
            "evidence_items": [
                {"source": "wiki/topics/a.md", "kind": "事实线索", "text": "事实"},
                {"source": "wiki/topics/a.md", "kind": "案例", "text": "案例"},
            ],
        })
        self.assertEqual(material["pages"][0]["item"]["type"], "material-pack")


if __name__ == "__main__":
    unittest.main()
