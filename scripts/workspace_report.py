#!/usr/bin/env python3
"""Read-only Markdown projection of the existing stale report; no new state store."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config, kb_root
from core.dependencies import stale

ACTIONS = {
    "reconcile": "生成更新提案（仍须审核）",
    "review_upstream": "先复查上游",
    "refresh_index": "先重建索引并重新检查",
    "manual_review": "人工核对来源或页面",
}
REASONS = {
    "source_changed": "来源版本改变",
    "changed_since_index": "来源在索引构建后改变（没有写作时版本）",
    "evidence_mismatch": "证据片段或位置不匹配",
    "unavailable": "来源不可用",
    "unavailable_or_out_of_scope": "来源不可用或不在扫描范围内",
}


def text(value: Any) -> str:
    """Display untrusted titles/claims literally, never as embeds or HTML."""
    value = " ".join(str(value).splitlines())
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", html.escape(value, quote=False))


def note_link(root: Path, value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value
            or path.suffix.lower() != ".md" or any(c in value for c in "\\[]#|<>\r\n")):
        return text(value) + "（仅路径，未链接）"
    try:
        # Canonicalize the root too (notably Windows temporary-path aliases).
        root = root.resolve()
        candidate = root / value
        resolved = candidate.resolve()
        if (candidate.is_file() and resolved.is_relative_to(root)
                and resolved.relative_to(root).as_posix() == value):
            return f"[[{value}]]"
    except OSError:
        pass
    return text(value) + "（不可用，未链接）"


def render_report(cfg: dict[str, Any]) -> str:
    # Reuse the authoritative computation, including its order and coverage limits.
    report = stale(cfg)
    root = kb_root(cfg)
    coverage = report["coverage"]
    lines = ["# 依赖复查快照", "", "> [!important] 只读快照，不是实时待办或批准记录",
             "> stale 表示依据需要复查，不表示结论已经错误。此报告不改页面、版本或审核队列。",
             "", f"检查时间（UTC）：{text(report['checked_at'])}",
             f"索引时间（UTC）：{text(report['built_at'])}", "",
             f"待复查页面：{len(report['pending_updates'])}；检查来源：{coverage['checked_sources']}；"
             f"依赖：{coverage['dependencies']}；无写作时版本依赖：{coverage['unversioned_dependencies']}。",
             "", "页面的 review_required 是页面标记，不等于当前待审批任务；实际审批以 review 队列为准。",
             "无版本依赖、索引范围外或索引后新增的关系可能未覆盖。零条结果不代表全库已核实。", ""]
    if report.get("warnings"):
        lines += ["## 覆盖警告", ""]
        lines += ["- " + text(warning) for warning in report["warnings"]]
        lines.append("")
    if not report["pending_updates"]:
        lines += ["## 检查结果", "", "在本次已记录依赖范围内，未发现待复查项。", ""]
    for number, item in enumerate(report["pending_updates"], 1):
        lines += [f"## {number}. {text(item['title'])}", "",
                  "页面：" + note_link(root, item["path"]),
                  f"对象：{text(item.get('object_id') or 'legacy（尚无 ID）')}；"
                  f"版本：{text(item.get('revision') or '未记录')}。",
                  f"原生命周期：{text(item['status'])}；当前文件：{text(item['current_status'])}。",
                  "下一步：" + text(ACTIONS.get(item["action"], item["action"])), ""]
        if item["blocked_by"]:
            lines += ["先处理：" + "、".join(note_link(root, p) for p in item["blocked_by"]), ""]
        for cause in item["causes"]:
            reasons = sorted({REASONS.get(s["reason"], s["reason"]) for s in report["signals"]
                              if s["source"] == cause["source"] and s["dependent"] == cause["via"][1]})
            lines += ["- " + ("直接影响" if cause["direct"] else "间接影响") + "："
                      + " → ".join(note_link(root, p) for p in cause["via"])
                      + "；" + text("、".join(reasons))]
        for claim in item["claims"]:
            lines += [f"- 待核对判断 {text(claim['claim_id'])}：{text(claim['statement'])}"]
        if item.get("unavailable_sources"):
            lines += ["- 不可用来源：" + "、".join(note_link(root, p) for p in item["unavailable_sources"])]
        if "reconcile_args" in item:
            lines += ["", "提案参数（数据，不是自动执行命令）：", "", "```json",
                      json.dumps(item["reconcile_args"], ensure_ascii=False), "```"]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="输出 Obsidian 可读的依赖复查 Markdown；只读、不保存、不调用模型")
    parser.parse_args(argv)
    try:
        rendered = render_report(config())
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"复查报告未生成：{exc}。先核对配置或显式重建索引；未修改已有文件。", file=sys.stderr)
        return 1
    # Output only after the complete report is available; a failed scan is not zero findings.
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
