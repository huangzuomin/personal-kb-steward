"""B07: model-omitted contract metadata must not discard a grounded candidate.

Regression target: a real run returned a fully grounded work-memory item that
omitted only ``confidence`` and ``review_required``; the whole candidate was
dropped and produced zero reviewable pages, while the CLI still exited 0.

Content-bearing keys (title/summary/sources/...) are never invented — those
items stay invalid. Only contract metadata is defaulted, always to the most
conservative value, and the degradation is recorded instead of being silent.

Fixtures here are synthetic: the real reproduction lives in
iteration-artifacts/2026-09-21-live-realgate (not committed upstream).
"""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from core.skill_runtime import run_skill_runtime


ROOT = Path(__file__).resolve().parents[1]

DOCUMENTS = [
    {
        "path": "4-项目/AI课程案例/示例训练营活动.md",
        "title": "示例训练营活动",
        "content": "分工会发布第一期训练营通知，为期四周，名额约十人，需在指定日期前报名。",
    },
    {
        "path": "quicknote/示例日记.md",
        "title": "示例日记",
        "content": "原计划做一个视频短片，因素材不可控改用了其他工具，学习曲线打乱了进展。",
    },
]

BASE_ITEM = {
    "title": "示例训练营（第一期）",
    "type": "work-memory",
    "status": "growing",
    "stage": "active",
    "sources": ["4-项目/AI课程案例/示例训练营活动.md"],
    "summary": "分工会发布第一期训练营通知；报名与参训结果无记录佐证。",
    "related": [],
    "pending_links": [],
}


def _run(item):
    payload = {"items": [dict(item)]}
    with patch(
        "core.skill_runtime.call_chat_completion",
        return_value=json.dumps(payload, ensure_ascii=False),
    ):
        return run_skill_runtime(
            ROOT, {}, "work-memory-weave", "沉淀工作记忆", [dict(d) for d in DOCUMENTS]
        )


class ContractMetadataDefaultsTests(unittest.TestCase):
    def test_missing_confidence_and_review_required_is_defaulted_not_discarded(self):
        result = _run(BASE_ITEM)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["confidence"], "low")
        self.assertIs(result["items"][0]["review_required"], True)
        self.assertTrue(result["previews"])

    def test_defaulting_is_recorded_not_silent(self):
        result = _run(BASE_ITEM)
        notes = result.get("contract_notes") or []
        self.assertEqual(len(notes), 1)
        self.assertIn("confidence", notes[0])
        self.assertIn("review_required", notes[0])
        self.assertIn("人工复核", notes[0])

    def test_complete_item_produces_no_notes(self):
        item = dict(BASE_ITEM, confidence="medium", review_required=True)
        result = _run(item)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result.get("contract_notes"), [])
        self.assertEqual(result["items"][0]["confidence"], "medium")

    def test_omitted_confidence_forces_review_even_when_model_says_false(self):
        item = dict(BASE_ITEM, review_required=False)
        result = _run(item)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["items"][0]["confidence"], "low")
        self.assertIs(result["items"][0]["review_required"], True)

    def test_blank_confidence_is_treated_as_missing(self):
        item = dict(BASE_ITEM, confidence="   ", review_required=True)
        result = _run(item)
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual(result["items"][0]["confidence"], "low")

    def test_content_key_missing_is_still_rejected(self):
        item = dict(BASE_ITEM, confidence="medium", review_required=True)
        item.pop("summary")
        result = _run(item)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing keys" in i and "summary" in i for i in result["issues"]))
        self.assertEqual(result["items"][0].get("summary", None), None)

    def test_unknown_source_still_rejected_after_defaulting(self):
        item = dict(BASE_ITEM, sources=["raw/剪藏/并不存在的材料.md"])
        result = _run(item)
        self.assertFalse(result["ok"])
        self.assertTrue(any("source not provided" in i for i in result["issues"]))


if __name__ == "__main__":
    unittest.main()
