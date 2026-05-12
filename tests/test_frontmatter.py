import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import personal_kb_steward as steward


class FrontmatterTests(unittest.TestCase):
    def test_frontmatter_uses_sources_and_stage(self):
        text = steward.frontmatter(
            "测试",
            "seed-card",
            "growing",
            ["quicknote/a.md"],
            stage="seed",
        )
        self.assertIn("sources:", text)
        self.assertIn("origin:", text)
        self.assertIn("quicknote/a.md", text)
        self.assertIn("stage: seed", text)
        self.assertNotIn("\nsource:", text)

    def test_topic_research_templates_emit_single_frontmatter_block(self):
        result = steward.execute_skill(steward.ROOT, "topic-research-compile", {
            "config": {},
            "notes": [{
                "rel": "raw/article.md",
                "title": "Research Article",
                "body": "Long article body",
                "summary": "Long article summary",
                "metadata": {},
            }],
            "use_llm": False,
        })

        self.assertGreaterEqual(len(result["created"]), 1)
        for page in result["created"]:
            content = page["content"]
            delimiters = [line for line in content.splitlines() if line.strip() == "---"]
            self.assertEqual(delimiters, ["---", "---"])
            self.assertTrue(content.startswith("---\n"))
            self.assertIn("updated:", content)
            self.assertIn("related:", content)
            self.assertIn("review_required:", content)
            self.assertIn("origin:", content)

        source = result["created"][0]["content"]
        self.assertIn("type: source-note", source)
        self.assertIn("status: growing", source)
        self.assertIn("confidence: high", source)

        self.assertFalse(any("Mock summary for dry-run" in page["content"] for page in result["created"]))

    def test_topic_research_keeps_topics_as_candidates_inside_source_note(self):
        result = steward.execute_skill(steward.ROOT, "topic-research-compile", {
            "config": {},
            "notes": [{
                "rel": "raw/article.md",
                "title": "Research Article",
                "body": "Long article body",
                "summary": "Long article summary",
                "metadata": {},
            }],
            "use_llm": False,
        })

        source_page = result["created"][0]

        self.assertEqual(len(result["created"]), 1)
        self.assertTrue(source_page["target"].startswith("wiki/sources/"))
        self.assertIn("## 提取的专题", source_page["content"])
        self.assertNotIn("[[wiki/topics/", source_page["content"])


if __name__ == "__main__":
    unittest.main()
