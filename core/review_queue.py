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

from .page_review_scope import PAGE_REVIEW_SCOPE, PAGE_REVIEW_TYPE, page_review_records
from .auto_apply_policy import evaluate_auto_apply_policy, POLICY_VERSION
from .config import kb_root, review_queue_path


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def is_page_review_item(item: dict[str, Any]) -> bool:
    """Return whether a queue row carries exact page review authority."""
    return item.get("type") == PAGE_REVIEW_TYPE and item.get("scope") == PAGE_REVIEW_SCOPE


def page_review_items(items: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [item for item in items if item.get("run_id") == run_id and is_page_review_item(item)]


class QueueMutationConflict(ValueError):
    """A reviewed page row no longer matches the exact apply authority."""


def mark_verified_applied(
    items: list[dict[str, Any]],
    run_id: str,
    review_ids: list[str],
    verified_targets: dict[str, dict[str, Any]],
    execution_run_id: str,
) -> list[str]:
    """Mark only approved page rows whose current output was verified.

    This helper deliberately requires full queue IDs and compares the target
    tuple returned by the writer/evidence reader before mutating any row.
    """
    if not isinstance(execution_run_id, str) or not execution_run_id.strip():
        raise QueueMutationConflict("subset execution ID is missing")
    if len(set(review_ids)) != len(review_ids) or not all(
        isinstance(value, str) and value for value in review_ids
    ):
        raise QueueMutationConflict("subset review IDs must be unique full strings")
    by_id = {
        item.get("id"): item
        for item in items
        if item.get("run_id") == run_id and is_page_review_item(item)
    }
    selected: list[dict[str, Any]] = []
    for review_id in review_ids:
        item = by_id.get(review_id)
        if item is None:
            raise QueueMutationConflict(f"page review ID is not in the selected run: {review_id}")
        if item.get("status") != "approved":
            raise QueueMutationConflict(f"page review ID is no longer approved: {review_id}")
        target = item.get("target")
        fact = verified_targets.get(target) if isinstance(target, str) else None
        if not isinstance(fact, dict):
            continue
        for key in ("canonical_path", "content_sha256", "object_id", "revision"):
            if fact.get(key) != item.get(key):
                raise QueueMutationConflict(f"verified output tuple differs for {target}: {key}")
        selected.append(item)
    applied_at = _stamp()
    for item in selected:
        item.update(
            status="applied",
            applied_at=applied_at,
            applied_execution_run_id=execution_run_id,
            applied_target=item.get("target"),
        )
    return [item["target"] for item in selected]


def append_plan_review_queue(path: Path, plan: dict[str, Any]) -> int:
    """Persist new page authority rows and retain genuine non-page blockers."""
    items = plan.get("manual_review", [])
    if not items:
        return 0
    queued = 0
    emitted: set[str] = set()
    records = page_review_records(plan) if plan.get("review_contract") == "page-scoped-v1" else None
    for item in items:
        if item.get("type") == "planned_pages_require_review" and records is not None:
            requested = item.get("items")
            targets = set(requested) if isinstance(requested, list) and all(isinstance(v, str) for v in requested) else None
            for record in records:
                target = record["target"]
                if target in emitted or (targets is not None and target not in targets):
                    continue
                append_item(path, {
                    "run_id": plan.get("run_id"), "entry": plan.get("entry"),
                    "task": plan.get("task"), "risk": item.get("risk", "medium"),
                    "reason": item.get("reason", "page requires review"), **record,
                })
                emitted.add(target)
                queued += 1
            continue
        append_item(path, {"run_id": plan.get("run_id"), "entry": plan.get("entry"),
                           "task": plan.get("task"), **item})
        queued += 1
    return queued


def apply_source_auto_apply_policy(cfg: dict[str, Any], plan: dict[str, Any]) -> dict[str, int]:
    """GP002 Auto-Apply v0.1：source 卡队列条目的机器处置（可开关，默认关闭）。

    复用现有 approve/reject 变更语义，只改 status 与审计字段；不绕过 apply 链——
    AUTO_APPLY 条目仍走 apply-approved 的 preflight/backup/write/reconcile。
    """
    counts = {"AUTO_APPLY": 0, "AUTO_REJECT": 0, "QUARANTINE": 0}
    if not (cfg.get("source_auto_apply") or {}).get("enabled"):
        return counts
    root = kb_root(cfg)
    queue_path = review_queue_path(cfg)
    if not queue_path.exists():
        return counts
    items = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    run_id = plan.get("run_id")
    pages = {str(p.get("rel_path") or p.get("target") or ""): p
             for p in plan.get("planned_pages") or [] if isinstance(p, dict)}
    mutated = False
    for item in items:
        if item.get("run_id") != run_id or item.get("status") != "pending":
            continue
        target = str(item.get("target") or "")
        page = pages.get(target)
        if page is None:
            continue
        decision = evaluate_auto_apply_policy(
            page, target_exists=(root / target).exists())
        kind = decision["decision"]
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "AUTO_APPLY":
            item["status"] = "approved"
            item["resolved_at"] = _stamp()
            item["resolved_by"] = f"system-policy:{POLICY_VERSION}"
            item["resolution_reason"] = "all source auto-apply gates passed: " +                 ", ".join(decision["reason_codes"])
            item["auto_apply"] = {"policy_version": POLICY_VERSION,
                                  "reason_codes": decision["reason_codes"]}
            mutated = True
        elif kind == "AUTO_REJECT":
            item["status"] = "rejected"
            item["rejection_type"] = "other"
            item["resolved_at"] = _stamp()
            item["resolved_by"] = f"system-policy:{POLICY_VERSION}"
            item["resolution_code"] = decision["reason_codes"][0]
            item["resolution_reason"] = "auto-reject: " + ", ".join(decision["reason_codes"])
            item["auto_apply"] = {"policy_version": POLICY_VERSION,
                                  "reason_codes": decision["reason_codes"]}
            mutated = True
        # QUARANTINE：保持 pending，等人工
    # 非 page 审计行（如 source_compile_quality_issues）：仅当该 run 的全部 page
    # 项都已 AUTO_APPLY 时同步批准（纯审计确认，不产生任何写入）；只要有 QUARANTINE
    # 页就保持 pending，让人工整体看这个 run（保守：混合 run 不半自动）。
    if counts["AUTO_APPLY"] > 0 and counts["QUARANTINE"] == 0:
        for item in items:
            if (item.get("run_id") == run_id and item.get("status") == "pending"
                    and item.get("type") != "planned_page_review"):
                item["status"] = "approved"
                item["resolved_at"] = _stamp()
                item["resolved_by"] = f"system-policy:{POLICY_VERSION}"
                item["resolution_reason"] = ("audit row acknowledged: all pages in this "
                                             "run were auto-applied")
                item["auto_apply"] = {"policy_version": POLICY_VERSION,
                                      "reason_codes": ["audit_row_all_pages_auto_applied"]}
                counts["AUTO_APPLY"] = counts.get("AUTO_APPLY", 0) + 1
                mutated = True
    if mutated:
        save_queue(queue_path, items)
    return counts


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


REJECTION_TYPES = ("duplicate", "quality", "policy", "other")


def configure_reject_parser(parser: Any) -> None:
    """GP002: review reject 参数注册（runner 行数上限收敛到 core）。"""
    parser.add_argument("id", help="记录 ID 或前缀")
    parser.add_argument("--reason", default="", help="拒绝理由")
    parser.add_argument("--rejection-type", dest="rejection_type",
                        choices=list(REJECTION_TYPES), default="other",
                        help="拒绝类型（duplicate 跨 producer contract 存续）")


def reject_item_typed(items: list[dict[str, Any]], item_id: str, reason: str,
                      rejection_type: str, queue_path: Path) -> int:
    """Reject + 落盘 + 回执语义（GP002）。返回进程退出码。"""
    if not reject_item(items, item_id, reason, rejection_type=rejection_type):
        print(f"未找到待确认项：{item_id}")
        return 1
    save_queue(queue_path, items)
    print(f"已拒绝：{item_id}")
    return 0


def reject_item(items: list[dict[str, Any]], item_id: str, reason: str = "",
                rejection_type: str = "other") -> bool:
    """Mark item as rejected. Returns True if found and updated.

    GP002: rejection_type 是唯一可计算语义（duplicate 跨 producer contract 存续；
    quality/policy/other 保持 contract-scoped）。自由文本 reason 仅作审计。
    """
    item = find_item(items, item_id)
    if not item:
        return False
    if rejection_type not in REJECTION_TYPES:
        rejection_type = "other"
    item["status"] = "rejected"
    item["rejection_type"] = rejection_type
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
    "applied": "📌",
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
    n_applied = len(filter_items(items, status="applied"))
    known = n_pending + n_approved + n_rejected + n_applied
    n_unknown = max(0, total - known)
    return (
        f"队列总计：{total}  "
        f"⏳待确认：{n_pending}  "
        f"✅已批准：{n_approved}  "
        f"❌已拒绝：{n_rejected}  "
        f"📌已应用：{n_applied}  "
        f"❔未知：{n_unknown}"
    )
