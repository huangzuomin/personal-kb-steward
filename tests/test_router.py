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

    def test_case_generation_route_priority(self):
        """case_bank sits AFTER healthcheck but BEFORE generic work-memory.

        Specific case requests must reach case generation even when they also
        contain the generic '项目' keyword, while healthcheck keeps priority
        for quality-check phrasings that merely mention 案例卡.
        """
        cases = {
            "生成案例卡": "case-story-bank-builder",
            "生成项目案例卡": "case-story-bank-builder",
            "案例库整理": "case-story-bank-builder",
            "检查案例卡质量": "kb-lint-healthcheck",
            "项目复盘": "work-memory-weave",
            "会议决定与待办": "work-memory-weave",
            "准备写作素材": "writing-material-pack",
            "整理知识库": "mindseed-grow",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(steward.route(text), expected)


if __name__ == "__main__":
    unittest.main()
