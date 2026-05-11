from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import kb_root, resolve_path


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_root(cfg: dict[str, Any]) -> Path:
    expr = cfg.get("safety", {}).get("backup_dir", "${AGENT_HOME}\\.openclaw\\backups")
    return resolve_path(str(expr), kb_home=str(kb_root(cfg)))


def operation_log_path(cfg: dict[str, Any]) -> Path:
    expr = cfg.get("safety", {}).get("operation_log", "${AGENT_HOME}\\.openclaw\\operation-log.jsonl")
    return resolve_path(str(expr), kb_home=str(kb_root(cfg)))


def rel_to_kb(cfg: dict[str, Any], path: Path) -> str:
    root = kb_root(cfg).resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)


def append_operation_log(cfg: dict[str, Any], event: dict[str, Any]) -> None:
    target = operation_log_path(cfg)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": _stamp(), **event}
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def backup_existing_file(
    cfg: dict[str, Any],
    target: Path,
    *,
    run_id: str,
    operation: str,
    reason: str,
) -> dict[str, Any] | None:
    if not target.exists():
        return None
    root = kb_root(cfg).resolve()
    resolved = target.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        rel = Path(resolved.name)
    backup_path = backup_root(cfg) / run_id / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved, backup_path)
    record = {
        "operation": "backup",
        "for_operation": operation,
        "reason": reason,
        "run_id": run_id,
        "target": rel_to_kb(cfg, resolved),
        "backup_path": str(backup_path),
    }
    append_operation_log(cfg, record)
    return record


def safe_write_text(
    cfg: dict[str, Any],
    target: Path,
    content: str,
    *,
    run_id: str,
    operation: str,
    reason: str,
) -> dict[str, Any]:
    backup = backup_existing_file(cfg, target, run_id=run_id, operation=operation, reason=reason)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    event = {
        "operation": operation,
        "run_id": run_id,
        "target": rel_to_kb(cfg, target),
        "backup_path": backup.get("backup_path") if backup else None,
        "reason": reason,
    }
    append_operation_log(cfg, event)
    return event


def safe_delete_file(
    cfg: dict[str, Any],
    target: Path,
    *,
    run_id: str,
    operation: str,
    reason: str,
) -> dict[str, Any]:
    backup = backup_existing_file(cfg, target, run_id=run_id, operation=operation, reason=reason)
    target.unlink()
    event = {
        "operation": operation,
        "run_id": run_id,
        "target": rel_to_kb(cfg, target),
        "backup_path": backup.get("backup_path") if backup else None,
        "reason": reason,
    }
    append_operation_log(cfg, event)
    return event


def recovery_hint(cfg: dict[str, Any], run_id: str) -> str:
    return (
        f"恢复路径：备份目录 {backup_root(cfg) / run_id}；"
        f"操作日志 {operation_log_path(cfg)}；"
        f"可尝试回滚命令 python scripts\\personal_kb_steward.py rollback {run_id}"
    )


def user_next_step(error: BaseException | str) -> str:
    text = str(error)
    manual_review_markers = (
        "人工审核",
        "需要人工",
        "manual review",
        "manual_review",
        "review_required",
        "low-confidence",
        "low confidence",
        "confidence",
        "浜哄伐瀹℃牳",
        "瀹℃牳",
        "闇€瑕佷汉宸",
        "宸ュ鏍",
    )
    if isinstance(error, PermissionError) or "Permission denied" in text or "Access is denied" in text:
        return "请检查目标目录权限，关闭占用该目录的程序，或改用有写入权限的知识库路径后重试。"
    if isinstance(error, FileNotFoundError) or "找不到" in text or "No such file" in text:
        return "请确认 plan 引用和 knowledge_base 路径存在，再重新运行 dry-run plan。"
    if isinstance(error, json.JSONDecodeError) or "JSON" in text or "Expecting" in text:
        return "请重新生成 plan 文件；当前 plan 内容不是有效 JSON，不能安全应用。"
    if any(marker in text for marker in manual_review_markers):
        return "请先处理 manual review queue，确认内容后重新生成不需要人工审核的 plan，再执行 apply-plan。"
    if "hash" in text:
        return "请重新生成 plan；当前 plan 内容与记录的 hash 不一致。"
    if "受保护目录" in text or "不安全目标路径" in text or "越界" in text:
        return "请修改 plan 目标路径，只允许写入派生目录，不能写入 raw/quicknote/inbox 或知识库外部。"
    return "请查看 failed run manifest 和 operation-log，确认问题后重新生成 plan 或执行 rollback。"
