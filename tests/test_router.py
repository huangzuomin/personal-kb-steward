import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import personal_kb_steward as steward


class RouterTests(unittest.TestCase):
    def test_product_entry_routes(self):
        cases = {
            "整理知识库": "mindseed-grow",
            "发现选题": "topic-insight-miner",
            "准备写作素材：地方媒体AI转型": "writing-material-pack",
            "沉淀工作记忆": "work-memory-weave",
            "检查知识库健康": "kb-lint-healthcheck",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(steward.route(text), expected)


if __name__ == "__main__":
    unittest.main()
