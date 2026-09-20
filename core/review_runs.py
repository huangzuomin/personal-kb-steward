"""Run-scoped review application. No automatic approval or recovery replay.

The existing apply-plan function remains the write authority. Queue completion
is saved after each successful run, not at the end of a global batch. This does
not turn the queue and vault into a multi-file/concurrent-writer transaction.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .content_safety import safe_error_message
from .review_queue import load_queue, save_queue


class ReviewScopeError(ValueError):
    pass


def load_checked_queue(path: Path) -> list[dict[str, Any]]:
    # The legacy reader skips malformed JSON. That is not safe at a write gate:
    # a discarded line could be the pending item that should block this run.
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except ValueError:
                raise ReviewScopeError('审核队列存在损坏记录，停止应用；请先修复队列。') from None
            if not isinstance(item, dict):
                raise ReviewScopeError('审核队列记录不是对象，停止应用；请先修复队列。')
    return load_queue(path)


def review_blockers(items: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [item for item in items if item.get('run_id') == run_id
            and item.get('status', 'pending') not in {'approved', 'applied'}]


def print_review_blockers(items: list[dict[str, Any]], run_id: str) -> None:
    for item in review_blockers(items, run_id):
        print(f"阻塞 run {run_id}：id={item.get('id', '?')} type={item.get('type', '?')} status={item.get('status', 'pending')}")


def select_review_runs(items: list[dict[str, Any]], run_id: str | None, all_runs: bool) -> list[str]:
    if run_id is not None:
        if all_runs or not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', run_id):
            raise ReviewScopeError('--run-id 必须是完整有效 run_id，且不能与 --all 同用。')
        if not any(item.get('run_id') == run_id for item in items):
            raise ReviewScopeError('指定 run 没有审核记录；未应用任何计划。')
        return [run_id]
    approved = [item for item in items if item.get('status') == 'approved']
    if any(not isinstance(item.get('run_id'), str) or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', item['run_id']) for item in approved):
        raise ReviewScopeError('已批准项缺少有效 run_id；未应用任何计划。')
    runs = sorted({item['run_id'] for item in approved})
    if len(runs) > 1 and not all_runs:
        raise ReviewScopeError('有多个已批准 run；请指定 --run-id <完整ID> 或显式 --all，未应用任何计划。')
    return runs


def resolve_review_plan(plans_dir: Path, run_id: str) -> Path:
    # Filename prefix/substring alone is not authority: verify the stored ID.
    matches = []
    for path in sorted(plans_dir.glob('*.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if isinstance(value, dict) and value.get('run_id') == run_id:
            matches.append(path)
    if len(matches) != 1:
        raise ReviewScopeError(f'run {run_id} 对应的计划不唯一或不存在；未应用该 run。')
    return matches[0]


def apply_review_runs(queue_path: Path, plans_dir: Path, *, run_id: str | None,
                      all_runs: bool, apply_plan: Callable[[Path, str], int]) -> int:
    try:
        runs = select_review_runs(load_checked_queue(queue_path), run_id, all_runs)
    except (ReviewScopeError, OSError) as exc:
        print(safe_error_message(exc))
        return 1
    if not runs:
        print('无已批准待应用项。')
        return 0
    outcomes: list[dict[str, Any]] = []
    failed = False
    for rid in runs:
        try:
            items = load_checked_queue(queue_path)
        except (OSError, ValueError) as exc:
            failed = True
            outcomes.append({'run_id': rid, 'status': 'failed', 'error_type': type(exc).__name__})
            print(f'读取审核队列失败：{safe_error_message(exc)}；已完成 run 的记录不回退。')
            break
        related = [item for item in items if item.get('run_id') == rid]
        if not related or review_blockers(items, rid):
            print_review_blockers(items, rid)
            outcomes.append({'run_id': rid, 'status': 'blocked'})
            failed = True
            continue
        approved = [item for item in related if item.get('status') == 'approved']
        if not approved:
            outcomes.append({'run_id': rid, 'status': 'already_applied'})
            continue
        try:
            path = resolve_review_plan(plans_dir, rid)
            print(f'应用审核 run：{rid} | plan：{path}')
            if apply_plan(path, rid) != 0:
                raise ReviewScopeError('apply-plan 返回非零；审核状态未改为 applied。')
            # Keep unrelated edits appended while the run executed. Refuse to
            # overwrite a changed approval; its run manifest remains recoverable.
            current = load_checked_queue(queue_path)
            if [i for i in current if i.get('run_id') == rid] != related:
                raise ReviewScopeError('应用期间审核记录变化；保留 run manifest，请人工核对，禁止盲目重跑。')
            now = datetime.now(timezone.utc).isoformat()
            for item in current:
                if item.get('run_id') == rid and item.get('status') == 'approved':
                    item.update(status='applied', applied_at=now)
            save_queue(queue_path, current)
            outcomes.append({'run_id': rid, 'plan_path': str(path), 'status': 'applied', 'review_items': len(approved)})
        except (Exception, SystemExit) as exc:
            failed = True
            outcomes.append({'run_id': rid, 'status': 'failed', 'error_type': type(exc).__name__})
            print(f'审核应用失败 run {rid}：{safe_error_message(exc)}；请检查该 run 的 manifest，不自动重放。')
            break
    attempted = {item['run_id'] for item in outcomes}
    outcomes.extend({'run_id': rid, 'status': 'not_attempted'} for rid in runs if rid not in attempted)
    print('review apply-approved 汇总：' + json.dumps(outcomes, ensure_ascii=False))
    return 1 if failed else 0
