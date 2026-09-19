import json
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_related_obsidian_short_link_resolves_to_provided_source_path(self):
        payload = {
            "items": [{
                "title": "地方媒体AI转型为什么容易停在蓝图阶段？",
                "type": "topic-card",
                "status": "growing",
                "stage": "promising",
                "sources": ["raw/剪藏/地方媒体AI转型战略规划.md"],
                "summary": "同一实践者的策略反转本身构成可写张力。",
                "related": ["[[地方媒体AI转型战略规划]]"],
                "pending_links": [],
                "confidence": "medium",
                "review_required": True,
            }]
        }
        documents = [{
            "path": "raw/剪藏/地方媒体AI转型战略规划.md",
            "title": "地方媒体AI转型战略规划",
            "content": "战略蓝图与后续反思。",
        }]
        with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(payload, ensure_ascii=False)):
            result = run_skill_runtime(ROOT, {}, "topic-insight-miner", "发现选题", documents)

        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["items"][0]["related"], ["raw/剪藏/地方媒体AI转型战略规划.md"])

    def test_related_title_must_resolve_uniquely(self):
        payload = {
            "items": [{
                "title": "歧义链接测试",
                "type": "topic-card",
                "status": "growing",
                "stage": "candidate",
                "sources": ["raw/a.md"],
                "summary": "测试。",
                "related": ["[[同名资料]]"],
                "pending_links": [],
                "confidence": "medium",
                "review_required": True,
            }]
        }
        documents = [
            {"path": "raw/a.md", "title": "同名资料", "content": "a"},
            {"path": "raw/b.md", "title": "同名资料", "content": "b"},
        ]
        with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(payload, ensure_ascii=False)):
            result = run_skill_runtime(ROOT, {}, "topic-insight-miner", "发现选题", documents)

        self.assertFalse(result["ok"])
        self.assertTrue(any("related link is not known or pending" in issue for issue in result["issues"]))

    def test_related_unknown_link_still_fails(self):
        payload = {
            "items": [{
                "title": "不存在链接测试",
                "type": "topic-card",
                "status": "growing",
                "stage": "candidate",
                "sources": ["raw/a.md"],
                "summary": "测试。",
                "related": ["[[不存在的资料]]"],
                "pending_links": [],
                "confidence": "medium",
                "review_required": True,
            }]
        }
        documents = [{"path": "raw/a.md", "title": "真实资料", "content": "a"}]
        with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(payload, ensure_ascii=False)):
            result = run_skill_runtime(ROOT, {}, "topic-insight-miner", "发现选题", documents)

        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
