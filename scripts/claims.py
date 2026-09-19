#!/usr/bin/env python3
"""Read-only inspection of stored claims and their current source-match status."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.claims import evidence_status, read_claims
from core.config import config
from core.reconcile import _managed, _read, _resolve, _text
from core.vault import build_index


def inspect(cfg: dict, target: str) -> dict:
    index = build_index(cfg)
    _, note = _resolve(index, "", target, cfg["write"]["topics_dir"])
    _, state = _managed(_text(note), note.metadata)
    records = read_claims(state) if state.get("version") == 2 else []
    documents = {}
    for source in {e.source for claim in records for e in claim.evidence}:
        try:
            n = _read(index, source)
            documents[source] = {"sha256": n.sha256, "content": _text(n)}
        except (OSError, ValueError, UnicodeError):
            documents[source] = None
    claims = []
    for claim in records:
        item = claim.to_dict()
        for evidence, record in zip(claim.evidence, item["evidence"]):
            record["match_status"] = evidence_status(evidence, documents[evidence.source])
        claims.append(item)
    return {"object_id": note.object_id, "revision": note.revision, "path": note.rel,
            "legacy": state.get("version") != 2, "claims": claims,
            "notice": "matched 仅表示片段与版本匹配，不表示该判断已经证实。"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读查看判断、原文片段及来源版本状态，不调用模型")
    parser.add_argument("target", help="主题页相对路径或 kb:<UUID>")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(config(), args.target), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"无法读取判断依据：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
