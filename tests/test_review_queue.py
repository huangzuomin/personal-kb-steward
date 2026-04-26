"""Tests for core.review_queue module."""
import json
import tempfile
import unittest
from pathlib import Path

from core.review_queue import (
    append_item,
    approve_item,
    batch_approve,
    filter_items,
    find_item,
    format_list_item,
    format_queue_summary,
    load_queue,
    pending_items,
    reject_item,
    save_queue,
)


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.queue_path = Path(self.tmpdir) / "queue.jsonl"

    def test_append_and_load(self):
        append_item(self.queue_path, {"type": "low_confidence", "reason": "test"})
        append_item(self.queue_path, {"type": "broken_link", "reason": "test2"})
        items = load_queue(self.queue_path)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.get("id") for i in items))
        self.assertTrue(all(i.get("status") == "pending" for i in items))

    def test_approve_and_reject(self):
        append_item(self.queue_path, {"type": "test_item", "reason": "approve me"})
        items = load_queue(self.queue_path)
        item_id = items[0]["id"]

        self.assertTrue(approve_item(items, item_id, "looks good"))
        self.assertEqual(items[0]["status"], "approved")
        self.assertEqual(items[0]["resolution_reason"], "looks good")
        self.assertIn("resolved_at", items[0])

    def test_reject(self):
        append_item(self.queue_path, {"type": "test_item", "reason": "reject me"})
        items = load_queue(self.queue_path)
        item_id = items[0]["id"]

        self.assertTrue(reject_item(items, item_id, "not relevant"))
        self.assertEqual(items[0]["status"], "rejected")

    def test_batch_approve_by_risk(self):
        append_item(self.queue_path, {"type": "a", "risk": "P3", "reason": "low risk"})
        append_item(self.queue_path, {"type": "b", "risk": "P0", "reason": "high risk"})
        append_item(self.queue_path, {"type": "c", "risk": "P3", "reason": "low risk 2"})
        items = load_queue(self.queue_path)

        count = batch_approve(items, risk="P3")
        self.assertEqual(count, 2)
        self.assertEqual(items[0]["status"], "approved")
        self.assertEqual(items[1]["status"], "pending")  # P0 untouched
        self.assertEqual(items[2]["status"], "approved")

    def test_find_item_by_prefix(self):
        append_item(self.queue_path, {"type": "test"})
        items = load_queue(self.queue_path)
        item_id = items[0]["id"]
        # find by first 4 chars
        found = find_item(items, item_id[:4])
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], item_id)

    def test_filter_items(self):
        append_item(self.queue_path, {"type": "broken_link", "risk": "P0"})
        append_item(self.queue_path, {"type": "low_confidence", "risk": "P3"})
        items = load_queue(self.queue_path)
        p0 = filter_items(items, risk="P0")
        self.assertEqual(len(p0), 1)
        self.assertEqual(p0[0]["type"], "broken_link")

    def test_save_and_reload_preserves_state(self):
        append_item(self.queue_path, {"type": "test"})
        items = load_queue(self.queue_path)
        approve_item(items, items[0]["id"])
        save_queue(self.queue_path, items)
        reloaded = load_queue(self.queue_path)
        self.assertEqual(reloaded[0]["status"], "approved")

    def test_pending_items_filters_correctly(self):
        append_item(self.queue_path, {"type": "a"})
        append_item(self.queue_path, {"type": "b"})
        items = load_queue(self.queue_path)
        approve_item(items, items[0]["id"])
        save_queue(self.queue_path, items)
        reloaded = load_queue(self.queue_path)
        pend = pending_items(reloaded)
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["type"], "b")

    def test_format_summary(self):
        append_item(self.queue_path, {"type": "a"})
        append_item(self.queue_path, {"type": "b"})
        items = load_queue(self.queue_path)
        approve_item(items, items[0]["id"])
        summary = format_queue_summary(items)
        self.assertIn("2", summary)  # total
        self.assertIn("1", summary)  # pending

    def test_format_list_item(self):
        append_item(self.queue_path, {"type": "broken_link", "reason": "test reason"})
        items = load_queue(self.queue_path)
        line = format_list_item(items[0], 1)
        self.assertIn("broken_link", line)
        self.assertIn("test reason", line)


if __name__ == "__main__":
    unittest.main()
