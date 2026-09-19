#!/usr/bin/env python3
"""Explicit cache rebuild and read-only retrieval for humans and Agents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config
from core.dependencies import impact, stale
from core.derived_index import rebuild, search, show, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SQLite 派生索引：只重建缓存，不改知识页；查询不调用模型")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rebuild", help="从 Markdown 完整重建 .kb/index.sqlite")
    commands.add_parser("status", help="查看构建时间、计数和警告")
    commands.add_parser("stale", help="只读检查来源变更，列出需复查的判断和主题")
    affected = commands.add_parser("impact", help="查看来源路径或对象 ID 的潜在下游影响")
    affected.add_argument("source")
    detail = commands.add_parser("show", help="按路径或对象 ID 查判断和证据")
    detail.add_argument("target")
    find = commands.add_parser("search", help="关键词检索；空格分词，所有词均须命中")
    find.add_argument("query")
    find.add_argument("--kind", choices=["note", "claim", "evidence", "all"], default="note")
    find.add_argument("--type", dest="note_type", help="按所属页面 type 过滤")
    find.add_argument("--status", dest="note_status", help="按所属页面 status 过滤")
    find.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        cfg = config()
        if args.command == "rebuild":
            result = rebuild(cfg)
        elif args.command == "status":
            result = status(cfg)
        elif args.command == "stale":
            result = stale(cfg)
        elif args.command == "impact":
            result = impact(cfg, args.source)
        elif args.command == "show":
            result = show(cfg, args.target)
        else:
            result = search(cfg, args.query, kind=args.kind, note_type=args.note_type,
                            note_status=args.note_status, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"索引操作失败：{exc}。需要启用 FTS5/trigram 的 SQLite；索引不会修改原笔记。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
