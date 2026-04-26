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
        self.assertIn("stage: seed", text)
        self.assertNotIn("\nsource:", text)


if __name__ == "__main__":
    unittest.main()
