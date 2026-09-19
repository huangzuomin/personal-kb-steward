#!/usr/bin/env python3
"""Research synthesis with explicit destination and mandatory existing review/apply."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config
from core.llm import LLMError
from core.synthesis import make_synthesis_plan
from scripts.personal_kb_steward import run_id
from scripts.reconcile import present_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检索、综合、生成证据化提案；不直接写入知识页")
    parser.add_argument("question", help="研究问题，关键词可用空格分开")
    parser.add_argument("--topic", required=True, help="稳定主题名，不用每次提问新建一个页面")
    parser.add_argument("--target", help="已有主题页的 object_id 或相对路径；否则精确标题匹配")
    parser.add_argument("--discussion", default="", help="待核对的讨论要点，不作为可引用证据")
    parser.add_argument("--limit", type=int, default=8, help="新增检索资料上限，1至50，默认8")
    args = parser.parse_args(argv)
    cfg = config()
    try:
        plan = make_synthesis_plan(cfg, args.question, topic=args.topic, target=args.target,
                                   discussion=args.discussion, limit=args.limit, plan_run_id=run_id())
        for report in plan.get("retrieval", []):
            print(f"检索：{report['engine']}；实际来源：{len(report['hits'])}")
            print(report["notice"])
            if report.get("fallback_reason"):
                print(report["fallback_reason"])
            for hit in report["hits"]:
                print(f"  {hit['path']}：{hit['dependency_state']}")
        return present_plan(cfg, plan, label="Synthesis")
    except (LLMError, OSError, ValueError) as exc:
        print(f"综合未完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
