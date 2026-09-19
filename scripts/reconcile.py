#!/usr/bin/env python3
"""Propose one topic reconciliation; apply it through the existing review CLI."""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config, kb_root
from core.llm import LLMError
from core.reconcile import ReconcileConflict, make_reconcile_plan
from scripts import personal_kb_steward as steward


def present_plan(cfg: dict, plan: dict, *, label: str = "Reconcile") -> int:
    """One preview/review path for explicit reconcile and retrieved synthesis."""
    info = plan["reconcile"]
    print(f"{label}: {info['decision']}\n{info['reason']}")
    if info["decision"] == "noop":
        return 0  # No extra plans, review tickets, revisions, or processed markers.
    before = ""
    if plan["planned_pages"] and info["decision"] == "update":
        before = (kb_root(cfg) / info["target"]).read_bytes().decode("utf-8")
    path = steward.write_execution_plan(cfg, plan)
    queued = steward.write_manual_review_queue(cfg, plan)
    print(f"计划：{path}\n人工审核项：{queued}")
    if info["decision"] == "conflict":
        print("未生成可执行写入。请解决冲突后重新生成，不能仅批准冲突记录就执行。")
        return 2
    page = plan["planned_pages"][0]
    print("\n".join(difflib.unified_diff(before.splitlines(), page["content"].splitlines(),
                                       fromfile=info["target"], tofile=info["target"], lineterm="")))
    print("当前为 dry-run。使用原 review show / approve / apply-approved 流程审核与应用。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="专题增量更新：只生成待审核计划，不直接写入知识页")
    parser.add_argument("topic", help="主题名；无 --target 时只做精确标题匹配")
    parser.add_argument("--source", action="append", required=True, help="来源相对路径，可重复指定")
    parser.add_argument("--target", help="已有主题页的 object_id 或知识库相对路径")
    args = parser.parse_args(argv)
    cfg = config()
    try:
        plan = make_reconcile_plan(cfg, args.topic, args.source, target=args.target, plan_run_id=steward.run_id())
        return present_plan(cfg, plan)
    except (LLMError, ReconcileConflict, OSError, ValueError) as exc:
        print(f"Reconcile 未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
