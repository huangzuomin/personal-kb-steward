"""Manual review queue module for personal-kb-steward.

Manages the JSONL-based review queue with:
- UUID-identified items with status tracking
- list / show / approve / reject / apply-approved / batch-approve
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── Load / Save ──────────────────────────────────────────────────────────────

def load_queue(path: Path) -> list[dict[str, Any]]:
    """Load all queue items from JSONL file. Backfills and persists IDs for legacy items."""
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    needs_persist = False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            # backfill id/status for legacy items
            if "id" not in item:
                item["id"] = str(uuid.uuid4())[:8]
                needs_persist = True
            item.setdefault("status", "pending")
            items.append(item)
        except json.JSONDecodeError:
            continue
    # persist backfilled IDs so they stay stable across loads
    if needs_persist:
        save_queue(path, items)
    return items


def save_queue(path: Path, items: list[dict[str, Any]]) -> None:
    """Write all queue items back to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def append_item(path: Path, item: dict[str, Any]) -> dict[str, Any]:
    """Append a single item to queue, assigning id and status."""
    item.setdefault("id", str(uuid.uuid4())[:8])
    item.setdefault("status", "pending")
    item.setdefault("queued_at", _stamp())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


# ── Query ─────────────────────────────────────────────────────────────────────

def find_item(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    """Find item by id prefix."""
    matches = [i for i in items if i.get("id", "").startswith(item_id)]
    return matches[0] if len(matches) == 1 else None


def filter_items(
    items: list[dict[str, Any]],
    *,
    status: str | None = None,
    item_type: str | None = None,
    risk: str | None = None,
) -> list[dict[str, Any]]:
    """Filter queue items by status, type, and/or risk level."""
    result = items
    if status:
        result = [i for i in result if i.get("status") == status]
    if item_type:
        result = [i for i in result if i.get("type") == item_type]
    if risk:
        result = [i for i in result if i.get("risk") == risk]
    return result


def pending_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return filter_items(items, status="pending")


def approved_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return filter_items(items, status="approved")


# ── Mutate ────────────────────────────────────────────────────────────────────

def approve_item(items: list[dict[str, Any]], item_id: str, reason: str = "") -> bool:
    """Mark item as approved. Returns True if found and updated."""
    item = find_item(items, item_id)
    if not item:
        return False
    item["status"] = "approved"
    item["resolved_at"] = _stamp()
    item["resolved_by"] = "user"
    if reason:
        item["resolution_reason"] = reason
    return True


def reject_item(items: list[dict[str, Any]], item_id: str, reason: str = "") -> bool:
    """Mark item as rejected. Returns True if found and updated."""
    item = find_item(items, item_id)
    if not item:
        return False
    item["status"] = "rejected"
    item["resolved_at"] = _stamp()
    item["resolved_by"] = "user"
    if reason:
        item["resolution_reason"] = reason
    return True


def batch_approve(items: list[dict[str, Any]], *, risk: str | None = None, item_type: str | None = None) -> int:
    """Batch-approve all pending items matching optional filters. Returns count."""
    count = 0
    for item in items:
        if item.get("status") != "pending":
            continue
        if risk and item.get("risk") != risk:
            continue
        if item_type and item.get("type") != item_type:
            continue
        item["status"] = "approved"
        item["resolved_at"] = _stamp()
        item["resolved_by"] = "batch"
        count += 1
    return count


# ── Display helpers ───────────────────────────────────────────────────────────

_STATUS_ICONS = {
    "pending": "⏳",
    "approved": "✅",
    "rejected": "❌",
}

_RISK_COLORS = {
    "P0": "🔴",
    "P1": "🟠",
    "P2": "🟡",
    "P3": "🟢",
}


def format_list_item(item: dict[str, Any], index: int) -> str:
    """Format a single queue item for list display."""
    icon = _STATUS_ICONS.get(item.get("status", ""), "❓")
    risk_icon = _RISK_COLORS.get(item.get("risk", ""), "")
    item_id = item.get("id", "?")[:8]
    entry = item.get("entry", "")
    item_type = item.get("type", "")
    reason = item.get("reason", "")[:60]
    queued_at = item.get("queued_at", "")
    return f"  {index:>3}. {icon} [{item_id}] {risk_icon}{item_type or entry}｜{reason}｜{queued_at}"


def format_show_item(item: dict[str, Any]) -> str:
    """Format a single queue item for detailed display."""
    lines = [
        "─" * 60,
        f"  ID：{item.get('id', '?')}",
        f"  状态：{_STATUS_ICONS.get(item.get('status', ''), '')} {item.get('status', '')}",
        f"  排队时间：{item.get('queued_at', '')}",
        f"  入口：{item.get('entry', '')}",
        f"  任务：{item.get('task', '')}",
        f"  类型：{item.get('type', '')}",
        f"  风险等级：{_RISK_COLORS.get(item.get('risk', ''), '')} {item.get('risk', '')}",
        f"  原因：{item.get('reason', '')}",
        f"  关联 run_id：{item.get('run_id', '')}",
    ]
    if item.get("resolved_at"):
        lines.append(f"  决议时间：{item['resolved_at']}")
        lines.append(f"  决议者：{item.get('resolved_by', '')}")
    if item.get("resolution_reason"):
        lines.append(f"  决议理由：{item['resolution_reason']}")
    # show related files if present
    sources = item.get("sources", [])
    if sources:
        lines.append("  关联来源：")
        for src in sources[:10]:
            lines.append(f"    - {src}")
    lines.append("─" * 60)
    return "\n".join(lines)


def format_queue_summary(items: list[dict[str, Any]]) -> str:
    """Format a summary of queue status."""
    total = len(items)
    n_pending = len(pending_items(items))
    n_approved = len(approved_items(items))
    n_rejected = len(filter_items(items, status="rejected"))
    return (
        f"队列总计：{total}  "
        f"⏳待确认：{n_pending}  "
        f"✅已批准：{n_approved}  "
        f"❌已拒绝：{n_rejected}"
    )
