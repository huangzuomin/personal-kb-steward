"""Safe conversion of validated LLM topic items into reviewed plan pages.

The model supplies content and citations only. File locations, lifecycle downgrades,
origin metadata and review gating remain program-owned.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .config import sha256_text
from .markdown import bullet, frontmatter, slug


class LLMPlanError(ValueError):
    """LLM output is valid JSON but cannot safely become a write proposal."""


def _topics_dir(cfg: dict[str, Any]) -> str:
    raw = str(cfg.get("write", {}).get("topics_dir") or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise LLMPlanError("write.topics_dir 必须是知识库内的相对目录")
    return path.as_posix()


def _title(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n"):
        raise LLMPlanError("LLM 选题 title 必须是非空单行文本")
    return value.strip()


def _strings(item: dict[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise LLMPlanError(f"LLM 选题 {key} 必须是字符串列表")
    return [" ".join(v.splitlines()).strip() for v in value if v.strip()]


def _safe_filename(title: str) -> str:
    readable = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#]', "-", title)
    readable = re.sub(r"\s+", "-", readable).strip(" .-")[:70]
    return readable or slug(title, "topic")


def _append_text(lines: list[str], heading: str, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        lines.extend(["", f"## {heading}", "", value.strip()])


def _append_list(lines: list[str], heading: str, values: list[str]) -> None:
    if values:
        lines.extend(["", f"## {heading}", "", bullet(values, "").rstrip()])


def _render_topic(item: dict[str, Any], *, status: str, stage: str,
                  confidence: str, sources: list[str], origin: dict[str, Any]) -> str:
    title = _title(item.get("title"))
    summary = item.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise LLMPlanError(f"LLM 选题《{title}》缺少可展示的 summary")

    lines = [
        frontmatter(
            title,
            "topic-card",
            status,
            sources,
            related=_strings(item, "related"),
            tags=["选题卡", "LLM候选"],
            confidence=confidence,
            review_required=True,
            stage=stage,
            origin=origin,
        ).rstrip(),
        "",
        f"# {title}",
    ]
    one_sentence = item.get("one_sentence_topic")
    _append_text(lines, "一句话选题", one_sentence if isinstance(one_sentence, str) and one_sentence.strip() else summary)
    _append_text(lines, "选题张力", item.get("tension"))
    why_now = _strings(item, "why_now")
    if why_now:
        _append_list(lines, "为什么值得写", why_now)
    elif isinstance(one_sentence, str) and one_sentence.strip():
        _append_text(lines, "为什么值得写", summary)
    _append_list(lines, "信号", _strings(item, "signals"))
    _append_list(lines, "知识库证据", sources)
    _append_list(lines, "可用角度", _strings(item, "angles"))
    risks = _strings(item, "risks") + _strings(item, "manual_review")
    _append_list(lines, "反方与风险", list(dict.fromkeys(risks)))
    _append_list(lines, "缺口", _strings(item, "gaps"))
    _append_list(lines, "待创建链接", _strings(item, "pending_links"))
    score = item.get("score")
    if isinstance(score, str) and score.strip():
        _append_text(lines, "推荐等级", score)
    lines.extend([
        "",
        "## 下一步",
        "",
        "- 人工核对选题张力、来源覆盖和反方证据后再决定是否进入 evidence/material pack。",
        "- 本页由 LLM 生成候选内容，review_required 固定为 true；批准前不会落盘。",
        "",
    ])
    return "\n".join(lines)


def topic_pages_from_llm(cfg: dict[str, Any], llm_result: dict[str, Any],
                         plan_run_id: str) -> list[dict[str, Any]]:
    """Convert validated topic-insight items into create proposals.

    Model-supplied path/filename fields are deliberately ignored. The configured
    topics_dir is the only path authority.
    """
    if not llm_result.get("ok"):
        raise LLMPlanError("LLM runtime 未通过，不能生成可写提案")
    if llm_result.get("skill") != "topic-insight-miner":
        raise LLMPlanError("当前只允许 topic-insight-miner 使用 LLM writeback")
    items = llm_result.get("items")
    if not isinstance(items, list) or not items:
        raise LLMPlanError("LLM 没有返回可写的选题 items")

    rel_dir = _topics_dir(cfg)
    min_sources = int(cfg.get("quality_gate", {}).get("min_sources_for_topic", 3))
    pages: list[dict[str, Any]] = []
    targets: set[str] = set()

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise LLMPlanError(f"LLM items[{idx}] 不是对象")
        title = _title(item.get("title"))
        if item.get("type") != "topic-card":
            raise LLMPlanError(f"LLM 选题《{title}》type 必须是 topic-card")

        sources = _strings(item, "sources")
        if not sources:
            raise LLMPlanError(f"LLM 选题《{title}》没有具体来源，拒绝生成页面")

        proposed_status = item.get("status")
        proposed_stage = item.get("stage")
        proposed_confidence = item.get("confidence")
        status = "growing" if proposed_status == "growing" else "manual_review"
        stage = "promising" if proposed_stage == "promising" else "candidate"
        confidence = proposed_confidence if proposed_confidence in {"low", "medium", "high"} else "low"
        if len(sources) < min_sources:
            status, stage, confidence = "manual_review", "candidate", "low"

        origin = {
            "source_paths": sources,
            "operation": "topic-insight-miner",
            "producer": "llm_skill_runtime",
        }
        content = _render_topic(
            item,
            status=status,
            stage=stage,
            confidence=confidence,
            sources=sources,
            origin=origin,
        )
        filename = f"topic-card-{_safe_filename(title)}-{plan_run_id}.md"
        target = (PurePosixPath(rel_dir) / filename).as_posix()
        if target in targets:
            raise LLMPlanError(f"LLM 返回重复选题标题，目标冲突：{title}")
        targets.add(target)
        pages.append({
            "skill": "topic-insight-miner",
            "operation": "create",
            "rel_path": target,
            "sources": sources,
            "origin": origin,
            "content_sha256": sha256_text(content),
            "content": content,
            # v1 deliberately requires explicit human approval even when the
            # model says review_required=false.
            "review_required": True,
            "confidence": confidence,
            "analysis_mode": "llm_skill_runtime",
            "llm_item_index": idx,
        })
    return pages
