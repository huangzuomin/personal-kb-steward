"""Safe conversion of validated LLM topic items into reviewed plan pages.

The model supplies content and citations only. File locations, lifecycle downgrades,
origin metadata and review gating remain program-owned.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Callable

from .config import sha256_text
from .markdown import bullet, frontmatter, slug
from .retrieval import Selection, annotate_pages
from .vault import Note


class LLMPlanError(ValueError):
    """LLM output is valid JSON but cannot safely become a write proposal."""


def _rel_output_dir(cfg: dict[str, Any], dir_key: str) -> str:
    raw = str(cfg.get("write", {}).get(dir_key) or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
        raise LLMPlanError(f"write.{dir_key} 必须是知识库内的相对目录")
    return path.as_posix()


def _topics_dir(cfg: dict[str, Any]) -> str:
    return _rel_output_dir(cfg, "topics_dir")


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


def integrate_topic_llm_writeback(
    cfg: dict[str, Any],
    planned_pages: list[dict[str, Any]],
    llm_result: dict[str, Any],
    input_notes: list[Note],
    retrieval_report: dict[str, Any] | None,
    plan_run_id: str,
    validate_page: Callable[[str, list[str]], list[str]],
) -> tuple[list[dict[str, Any]], str | None]:
    """Replace provisional executor topic pages with reviewed LLM pages.

    A requested LLM failure never falls back to the deterministic topic template.
    """
    non_primary = [p for p in planned_pages if p.get("skill") != "topic-insight-miner"]
    if not llm_result.get("ok"):
        llm_result["writeback_used"] = False
        llm_result["writeback_pages"] = 0
        return non_primary, None
    try:
        if retrieval_report is None:
            raise LLMPlanError("LLM 选题缺少可复核的检索快照，拒绝生成可写提案")
        pages = topic_pages_from_llm(cfg, llm_result, plan_run_id)
        annotate_pages(pages, Selection(input_notes, retrieval_report))
        issues = [issue for page in pages for issue in validate_page(page["content"], page.get("sources", []))]
        if issues:
            raise LLMPlanError("LLM 选题页未通过落盘校验：" + "；".join(issues[:10]))
        llm_result["writeback_used"] = True
        llm_result["writeback_pages"] = len(pages)
        return non_primary + pages, None
    except LLMPlanError as exc:
        llm_result["writeback_used"] = False
        llm_result["writeback_pages"] = 0
        llm_result.setdefault("issues", []).append(str(exc))
        return non_primary, str(exc)


# ---------------------------------------------------------------------------
# User-entry writeback (work-memory-weave / writing-material-pack).
# Same contract as topic writeback: the model supplies content and citations
# only; output directory, lifecycle downgrades, origin and review gating stay
# program-owned, and every failure is fail-closed with no executor fallback.
# ---------------------------------------------------------------------------

# Per-skill accepted page types (from each SKILL.md) and config output dir.
ENTRY_WRITEBACK_SKILLS: dict[str, dict[str, Any]] = {
    "work-memory-weave": {
        "types": {"work-memory", "decision-record", "project-timeline"},
        "dir_key": "work_memory_dir",
        "filename_prefix": "work-memory",
        "statuses": {"growing": "growing"},
        "stages": {"active": "active", "waiting": "waiting"},
        "tags": ["工作记忆", "LLM候选"],
    },
    "writing-material-pack": {
        "types": {"material-pack"},
        "dir_key": "materials_dir",
        "filename_prefix": "material-pack",
        "statuses": {"growing": "growing"},
        "stages": {"assembling": "assembling", "insufficient": "insufficient"},
        "tags": ["写作材料包", "LLM候选"],
    },
}


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LLMPlanError(f"LLM 条目缺少可展示的 {key}")
    return value.strip()


def _material_pack_content(item: dict[str, Any]) -> None:
    """writing-material-pack uses the EXISTING generic runtime contract
    (tension/why_now/signals/angles/risks/gaps/manual_review); no new mandatory
    schema. Optional specialized fields (facts/cases/...) are validated only
    when present — the program never fabricates facts or cases."""
    _required_str(item, "summary")


def _render_entry_body(item: dict[str, Any], skill: str) -> list[str]:
    lines: list[str] = []
    _append_text(lines, "摘要", _required_str(item, "summary"))
    # pending_links is EXPLICITLY for not-yet-existing targets; wiki-link
    # markup there would be flagged as a dangling link and block the whole
    # page. Render plain text, stripping only the [[ ]]/alias markup while
    # retaining the target text. Link validation itself is NOT relaxed:
    # unknown sources/related/body links stay blocked.
    pending = [re.sub(r"\[\[([^\[\]\r\n]+)\]\]",
                      lambda m: m.group(1).split("|", 1)[0].strip(), v).strip()
               for v in _strings(item, "pending_links")]
    if skill == "writing-material-pack":
        _append_text(lines, "核心张力", item.get("tension"))
        _append_list(lines, "为什么值得整理", _strings(item, "why_now"))
        _append_list(lines, "信号与线索", _strings(item, "signals"))
        _append_list(lines, "可选写作角度", _strings(item, "angles"))
        _append_list(lines, "风险与缺口", list(dict.fromkeys(_strings(item, "risks") + _strings(item, "gaps"))))
        # Optional specialized fields render ONLY the model's own validated
        # entries; absence means the section is omitted, never synthesized.
        facts = _strings(item, "facts")
        cases = _strings(item, "cases")
        data_points = _strings(item, "data_points")
        not_recommended = _strings(item, "not_recommended")
        if facts or cases or data_points:
            _append_list(lines, "可用事实", facts)
            _append_list(lines, "可用案例", cases)
            _append_list(lines, "可用数据", data_points)
        _append_list(lines, "不建议写法", not_recommended)
    else:
        _append_list(lines, "信号与要点", _strings(item, "signals"))
        _append_list(lines, "风险与阻塞", list(dict.fromkeys(_strings(item, "risks") + _strings(item, "gaps"))))
    _append_list(lines, "人工复核项", _strings(item, "manual_review"))
    _append_list(lines, "待创建链接", pending)
    return lines


def entry_pages_from_llm(cfg: dict[str, Any], llm_result: dict[str, Any],
                         plan_run_id: str) -> list[dict[str, Any]]:
    """Convert validated work-memory/material-pack items into create proposals.

    Model-supplied path fields are ignored; the configured output dir is the
    only path authority, and lifecycle claims are program-owned downgrades.
    """
    if not llm_result.get("ok"):
        raise LLMPlanError("LLM runtime 未通过，不能生成可写提案")
    skill = llm_result.get("skill")
    contract = ENTRY_WRITEBACK_SKILLS.get(skill)
    if contract is None:
        raise LLMPlanError(f"当前只允许已登记的用户入口使用 LLM writeback：{skill}")
    items = llm_result.get("items")
    if not isinstance(items, list) or not items:
        raise LLMPlanError("LLM 没有返回可写的条目")

    rel_dir = _rel_output_dir(cfg, contract["dir_key"])
    pages: list[dict[str, Any]] = []
    targets: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise LLMPlanError(f"LLM items[{idx}] 不是对象")
        title = _title(item.get("title"))
        if item.get("type") not in contract["types"]:
            raise LLMPlanError(f"LLM 条目《{title}》type 必须是 {sorted(contract['types'])[0]}")
        if skill == "writing-material-pack":
            _material_pack_content(item)
        sources = _strings(item, "sources")
        if not sources:
            raise LLMPlanError(f"LLM 条目《{title}》没有具体来源，拒绝生成页面")
        status = contract["statuses"].get(item.get("status"), "manual_review")
        stage = contract["stages"].get(item.get("stage"), "needs_review")
        confidence = item.get("confidence") if item.get("confidence") in {"low", "medium", "high"} else "low"
        origin = {
            "source_paths": sources,
            "operation": skill,
            "producer": "llm_skill_runtime",
        }
        lines = [
            frontmatter(
                title, item["type"], status, sources,
                related=_strings(item, "related"),
                tags=contract["tags"],
                confidence=confidence,
                review_required=True,
                stage=stage,
                origin=origin,
            ).rstrip(),
            "",
            f"# {title}",
            *_render_entry_body(item, skill),
            "",
            "## 下一步",
            "",
            "- 人工核对来源、事实与计划/已发生内容后再批准落盘。",
            "- 本页由 LLM 生成候选内容，review_required 固定为 true；批准前不会落盘。",
            "",
        ]
        content = "\n".join(lines)
        filename = f"{contract['filename_prefix']}-{_safe_filename(title)}-{plan_run_id}.md"
        target = (PurePosixPath(rel_dir) / filename).as_posix()
        if target in targets:
            raise LLMPlanError(f"LLM 返回重复条目标题，目标冲突：{title}")
        targets.add(target)
        pages.append({
            "skill": skill,
            "operation": "create",
            "rel_path": target,
            "sources": sources,
            "origin": origin,
            "content_sha256": sha256_text(content),
            "content": content,
            # v1 requires explicit human approval, mirroring topic writeback.
            "review_required": True,
            "confidence": confidence,
            "analysis_mode": "llm_skill_runtime",
            "llm_item_index": idx,
        })
    return pages


def integrate_entry_llm_writeback(
    cfg: dict[str, Any],
    planned_pages: list[dict[str, Any]],
    llm_result: dict[str, Any],
    input_notes: list[Note],
    plan_run_id: str,
    validate_page: Callable[[str, list[str]], list[str]],
    skill: str,
    retrieval_report: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Replace this skill's heuristic executor pages with reviewed LLM pages.

    A requested LLM failure — or an ok response that is not from this skill —
    never falls back to the deterministic template: the skill's provisional
    pages are dropped and the blocker is surfaced for review.
    """
    if llm_result.get("skill") != skill:
        llm_result["writeback_used"] = False
        llm_result["writeback_pages"] = 0
        issue = f"LLM runtime 响应的 skill 与入口不一致：{llm_result.get('skill')!r} != {skill!r}"
        llm_result.setdefault("issues", []).append(issue)
        return [p for p in planned_pages if p.get("skill") != skill], issue
    non_primary = [p for p in planned_pages if p.get("skill") != skill]
    if not llm_result.get("ok"):
        llm_result["writeback_used"] = False
        llm_result["writeback_pages"] = 0
        return non_primary, None
    try:
        pages = entry_pages_from_llm(cfg, llm_result, plan_run_id)
        if retrieval_report is not None:
            annotate_pages(pages, Selection(input_notes, retrieval_report))
        known = {note.rel: note.sha256 for note in input_notes}
        for page in pages:
            missing = [rel for rel in page["sources"] if rel not in known]
            if missing:
                raise LLMPlanError("LLM 条目引用了未提供的来源：" + "；".join(missing))
            page.setdefault("retrieval_source_hashes",
                            {rel: known[rel] for rel in page["sources"]})
        issues = [issue for page in pages for issue in validate_page(page["content"], page.get("sources", []))]
        if issues:
            raise LLMPlanError("LLM 入口页未通过落盘校验：" + "；".join(issues[:10]))
        llm_result["writeback_used"] = True
        llm_result["writeback_pages"] = len(pages)
        return non_primary + pages, None
    except LLMPlanError as exc:
        llm_result["writeback_used"] = False
        llm_result["writeback_pages"] = 0
        llm_result.setdefault("issues", []).append(str(exc))
        return non_primary, str(exc)
