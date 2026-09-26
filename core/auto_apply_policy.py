# -*- coding: utf-8 -*-
"""GP002 Source Card Auto-Apply v0.1 policy primitive（纯函数，无状态，无 I/O）。

输入 planned page dict + target_exists 事实，输出结构化决策。
禁止：写 queue/文件、调用 LLM、apply、修改 processed-index、读取 config。

v0.1 阈值来源（保守经验值，非永久质量标准）：
历史 4 张有明确事后质量标签的 Source Card：
  quality_flags 3 → 有条件合格；10 / 14 / 20 → 不合格。
阈值集中定义于 SOURCE_AUTO_APPLY_MAX_QUALITY_FLAGS，不要散落成魔法数字。
"""
from __future__ import annotations

import re

POLICY_VERSION = "source-auto-apply-v0.1"
SOURCE_AUTO_APPLY_MAX_QUALITY_FLAGS = 5

AUTO_APPLY = "AUTO_APPLY"
AUTO_REJECT = "AUTO_REJECT"
QUARANTINE = "QUARANTINE"

_SOURCE_TYPE = "source-note"
_FM_RE = re.compile(r"^---\n(.*?)\n---", re.S)


def _frontmatter(content: str) -> dict[str, str]:
    m = _FM_RE.match(content or "")
    out: dict[str, str] = {}
    if not m:
        return out
    block = m.group(1)
    for key in ("type", "analysis_mode", "coverage", "status"):
        mm = re.search(rf"^{key}: (.+)$", block, re.M)
        if mm:
            out[key] = mm.group(1).strip().strip('"')
    qm = re.search(r"^quality_flags: \[(.*)\]$", block, re.M)
    if qm:
        inner = qm.group(1).strip()
        out["quality_flags_count"] = 0 if not inner else inner.count('", "') + 1
    out["has_card_state"] = "card_state: " in block
    out["has_info_units"] = "info_units" in block
    return out


def _decision(decision: str, reason_codes: list[str]) -> dict[str, Any]:
    return {"decision": decision, "policy_version": POLICY_VERSION,
            "reason_codes": reason_codes}


def evaluate_auto_apply_policy(page: dict[str, Any], *,
                               target_exists: bool = False) -> dict[str, Any]:
    """GP002 Auto-Apply v0.1：source 卡队列条目的机器决策（纯判定）。

    范围：仅 type=source-note。其余类型一律 QUARANTINE。
    AUTO_REJECT 仅限机器确定性足够高的两种：heuristic 无写入资格、duplicate 目标。
    quality_flags > 5 是 QUARANTINE（高风险≠一定错误），不是 AUTO_REJECT。
    """
    content = page.get("content") or ""
    fm = _frontmatter(content)
    target = str(page.get("rel_path") or page.get("target") or "")

    if fm.get("type") != _SOURCE_TYPE:
        return _decision(QUARANTINE, ["non_source_card_type"])

    if page.get("analysis_mode") != "llm":
        return _decision(AUTO_REJECT, ["heuristic_no_write_eligibility"])

    if target_exists:
        return _decision(AUTO_REJECT, ["duplicate_target"])

    if fm.get("coverage") != "full":
        return _decision(QUARANTINE, ["coverage_not_full"])

    if not fm.get("has_card_state") or not fm.get("has_info_units"):
        return _decision(QUARANTINE, ["compiled_evidence_missing"])

    flags = int(fm.get("quality_flags_count") or 0)
    if flags > SOURCE_AUTO_APPLY_MAX_QUALITY_FLAGS:
        return _decision(QUARANTINE,
                         [f"quality_flags_{flags}_above_v01_threshold_"
                          f"{SOURCE_AUTO_APPLY_MAX_QUALITY_FLAGS}"])

    if page.get("review_required") is not True:
        return _decision(QUARANTINE, ["review_required_field_missing"])

    return _decision(AUTO_APPLY, [
        "analysis_mode_llm", "coverage_full", "compiled_evidence_present",
        "quality_flags_within_v01_threshold", "target_absent",
    ])
