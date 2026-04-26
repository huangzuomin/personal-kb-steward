#!/usr/bin/env python3
"""Initialize config.json for a target Markdown knowledge base."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def portable_path_expr(path: Path) -> str:
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:
        return str(path)
    return "${AGENT_HOME}\\" + rel.replace("/", "\\")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 personal-kb-steward 配置")
    parser.add_argument("--kb", required=True, help="知识库路径")
    args = parser.parse_args()

    kb = Path(args.kb).expanduser().resolve()
    if not kb.exists():
        raise SystemExit(f"知识库路径不存在：{kb}")
    if not kb.is_dir():
        raise SystemExit(f"知识库路径不是目录：{kb}")

    cfg = read_json(CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
    cfg["knowledge_base"] = portable_path_expr(kb)
    cfg["state_file"] = "${AGENT_HOME}\\.openclaw\\personal-kb-steward-state.json"
    cfg.setdefault("safety", {})
    cfg["safety"]["plans_dir"] = "${AGENT_HOME}\\.openclaw\\plans"
    cfg["safety"]["runs_dir"] = "${AGENT_HOME}\\.openclaw\\runs"
    cfg["safety"]["processed_index"] = "${AGENT_HOME}\\.openclaw\\processed-index.json"
    cfg["safety"]["manual_review_queue"] = "${AGENT_HOME}\\.openclaw\\manual-review\\queue.jsonl"
    write_json(CONFIG_PATH, cfg)

    print(f"已更新配置：{CONFIG_PATH}")
    print(f"知识库：{kb}")
    print(f"knowledge_base: {cfg['knowledge_base']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
