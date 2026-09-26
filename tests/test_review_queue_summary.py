"""B12 review queue summary accounting."""
from __future__ import annotations

from datetime import datetime, timezone

from core.review_queue import _stamp, format_queue_summary


def test_summary_accounts_for_applied_and_unknown_statuses():
    items = [
        {"status": "pending"},
        {"status": "approved"},
        {"status": "rejected"},
        {"status": "applied"},
        {"status": "legacy_status"},
    ]
    summary = format_queue_summary(items)
    assert "队列总计：5" in summary
    assert "待确认：1" in summary
    assert "已批准：1" in summary
    assert "已拒绝：1" in summary
    assert "已应用：1" in summary
    assert "未知：1" in summary


def test_new_queue_timestamps_are_explicit_utc():
    value = datetime.fromisoformat(_stamp())
    assert value.tzinfo is not None
    assert value.utcoffset() == timezone.utc.utcoffset(value)
