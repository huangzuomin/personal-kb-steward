import unittest
from pathlib import Path

from core.skill_loader import load_skill
from core.skill_runtime import run_skill_runtime


ROOT = Path(__file__).resolve().parents[1]


class LlmRuntimeTests(unittest.TestCase):
    def test_loads_skill_frontmatter(self):
        spec = load_skill(ROOT, "mindseed-grow")
        self.assertEqual(spec.slug, "mindseed-grow")
        self.assertTrue(spec.name)
        self.assertIn("seed", spec.body.lower())

    def test_mock_runtime_returns_contract_items(self):
        result = run_skill_runtime(
            ROOT,
            {"scan": {"max_source_chars": 6000}},
            "mindseed-grow",
            "整理知识库",
            [{"path": "quicknote/example.md", "title": "example", "content": "hello"}],
            mock=True,
        )
        self.assertTrue(result["enabled"])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("preview", result["previews"][0])


if __name__ == "__main__":
    unittest.main()
