from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import sha256_text
from .vault import Note, build_index, parse_frontmatter


def _section(body: str, title_prefix: str) -> list[str]:
    lines = body.splitlines()
    out: list[str] = []
    active = False
    for line in lines:
        if line.startswith("## "):
            active = line[3:].strip().startswith(title_prefix)
            continue
        if active and line.strip().startswith("- "):
            item = line.strip()[2:].strip()
            if item and "待补充" not in item and "暂无" not in item:
                out.append(item)
    return out


def _tokens(text: str) -> set[str]:
    return {
        item.lower()
        for item in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,8}", text)
        if item not in {"source", "note", "raw", "wiki", "来源", "专题", "关键", "事实"}
    }


def _normalize_item(text: str) -> str:
    lowered = text.lower()
    for sep in ("，", "：", ":"):
        head, found, tail = lowered.partition(sep)
        if found and len(tail) >= 12:
            lowered = tail
            break
    lowered = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", lowered)
    lowered = re.sub(r"[，。；：、“”‘’（）()\[\]【】《》,.!?:;\"'\s-]+", "", lowered)
    lowered = re.sub(r"(据.*?报道|报道称|资料显示|核心摘要|关键事实)", "", lowered)
    return lowered[:120]


def _dedupe_items(items: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: list[str] = []
    for item in items:
        clean = item.strip()
        if not clean:
            continue
        key = _normalize_item(clean)
        if not key:
            continue
        duplicate = False
        for old in seen:
            overlap = len(set(key) & set(old)) / max(1, min(len(set(key)), len(set(old))))
            if key == old or key in old or old in key or (len(key) > 28 and overlap > 0.88):
                duplicate = True
                break
        if duplicate:
            continue
        seen.append(key)
        result.append(clean)
        if limit and len(result) >= limit:
            break
    return result


def _body_link_section(links: list[str]) -> list[str]:
    return ["## 关联页面", *[f"- [[{link}]]" for link in links], ""]


def _critical_findings(facts: list[str], quality: list[str], sources: list[str]) -> list[str]:
    findings = _dedupe_items(quality, limit=8)
    text = "\n".join(facts + quality)
    gaps: list[str] = []
    if not any(word in text for word in ["失败", "争议", "质疑", "反对", "风险", "成本", "隐私", "安全"]):
        gaps.append("当前资料以政策进展和正向案例为主，缺少失败案例、反方观点和成本约束信息。")
    if not any(word in text for word in ["评估", "成效", "指标", "ROI", "投入产出", "转化率"]):
        gaps.append("资料中对应用成效的量化评估不足，后续需要补充投入产出、用户采用率和持续运营数据。")
    if not any(word in text for word in ["企业", "市民", "学校", "医院", "基层", "一线"]):
        gaps.append("资料主要来自政策和媒体叙述，来自企业、一线使用者或公众的直接反馈仍不足。")
    if len(sources) < 5:
        gaps.append("跨来源数量偏少，当前聚合结论只适合作为初步线索。")
    return _dedupe_items([*findings, *gaps], limit=10)


def _replace_or_append_section(body: str, heading: str, lines: list[str]) -> str:
    section = "\n".join([f"## {heading}", *lines]).rstrip() + "\n"
    pattern = re.compile(rf"^## {re.escape(heading)}\n.*?(?=^## |\Z)", re.M | re.S)
    if pattern.search(body):
        return pattern.sub(section, body).rstrip() + "\n"
    return body.rstrip() + "\n\n" + section


def _frontmatter(meta: dict[str, Any]) -> str:
    ordered = ["title", "type", "status", "stage", "created", "updated", "sources", "related", "tags", "confidence", "review_required", "origin"]
    lines = ["---"]
    for key in ordered:
        if key not in meta:
            continue
        value = meta[key]
        if isinstance(value, (list, dict)):
            value_text = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            value_text = str(value).lower()
        else:
            value_text = str(value)
        lines.append(f"{key}: {value_text}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _page(kind: str, target: str, title: str, type_: str, sources: list[str], related: list[str], body: str, run_id: str, exists: bool) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    content = "\n".join([
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {type_}",
        "status: growing",
        "stage: synthesized",
        f"created: {today}",
        f"updated: {today}",
        f"sources: {json.dumps(sources, ensure_ascii=False)}",
        f"related: {json.dumps(related, ensure_ascii=False)}",
        f"tags: {json.dumps(['kb-finalize', kind], ensure_ascii=False)}",
        "confidence: medium",
        "review_required: false",
        f"origin: {json.dumps({'source_paths': sources, 'operation': 'kb-finalize', 'run_id': run_id}, ensure_ascii=False)}",
        "---",
        "",
        f"# {title}",
        "",
        body,
    ])
    return {"skill": "kb-finalize", "operation": "update" if exists else "create", "rel_path": target, "target": target, "sources": sources, "origin": {"source_paths": sources, "operation": "kb-finalize", "run_id": run_id}, "content_sha256": sha256_text(content), "content": content, "review_required": False, "confidence": "medium"}


def _update_source_note(note: Note, related: list[str], tags: list[str], run_id: str) -> dict[str, Any] | None:
    text = note.path.read_text(encoding="utf-8-sig", errors="replace")
    meta, body = parse_frontmatter(text)
    current_related = list(meta.get("related") or [])
    current_tags = list(meta.get("tags") or [])
    merged_related = sorted(dict.fromkeys([*current_related, *related]))
    merged_tags = sorted(dict.fromkeys([*current_tags, *tags]))
    body_links = [f"- [[{item}]]" for item in related[:5]]
    updated_body = _replace_or_append_section(body, "关联页面", body_links) if body_links else body
    if merged_related == current_related and merged_tags == current_tags and updated_body == body:
        return None
    meta["related"] = merged_related
    meta["tags"] = merged_tags
    meta["updated"] = dt.date.today().isoformat()
    meta.setdefault("origin", {"source_paths": meta.get("sources", []), "operation": "topic-research-compile"})
    content = _frontmatter(meta) + updated_body
    return {"skill": "kb-finalize", "operation": "update", "rel_path": note.rel, "target": note.rel, "sources": list(meta.get("sources") or []), "origin": {"source_paths": list(meta.get("sources") or []), "operation": "kb-finalize", "run_id": run_id}, "content_sha256": sha256_text(content), "content": content, "review_required": False, "confidence": "medium"}


def make_finalize_plan(cfg: dict[str, Any], *, plan_run_id: str, stamp: str, apply_updates: bool = False) -> dict[str, Any]:
    index = build_index(cfg)
    source_notes = [n for n in index.notes if n.rel.startswith("wiki/sources/") and n.metadata.get("type") == "source-note"]
    sources = [n.rel for n in source_notes]
    pages: list[dict[str, Any]] = []
    if len(source_notes) < 2:
        return {"run_id": plan_run_id, "created_at": stamp, "mode": "dry-run", "task": "finalize knowledge base", "entry": "finalize_kb", "primary_skill": "kb-finalize", "knowledge_base": str(index.root), "actions": [], "planned_pages": [], "manual_review": [{"type": "insufficient_sources", "risk": "P2", "reason": "需要至少 2 个 source-note 才能做跨源聚合。"}]}
    facts = _dedupe_items([item for n in source_notes for item in _section(n.body, "关键事实")], limit=80)
    topics = _dedupe_items([item for n in source_notes for item in _section(n.body, "提取")], limit=40)
    quality = _dedupe_items([item for n in source_notes for item in _section(n.body, "质量")], limit=30)
    topic_counts = Counter(topic.split("：", 1)[0].split(":", 1)[0].strip() for topic in topics)
    top_topics = [item for item, _ in topic_counts.most_common(8) if item]
    related_agg = ["wiki/topics/温州人工智能创新发展路径.md", "wiki/material-packs/温州AI政策与产业研究资料包.md", "wiki/concepts/人工智能创新发展先行市.md", "wiki/cases/温州AI应用与机构建设案例线索.md"]
    case_facts = _dedupe_items([x for x in facts if any(k in x for k in ["揭牌", "瓯海", "财政", "车间", "智能眼镜", "应用", "平台"])], limit=16)
    concept_facts = _dedupe_items([x for x in facts if any(k in x for k in ["人工智能局", "先行市", "政策", "目标", "算力"])], limit=12)
    critical = _critical_findings(facts, quality, sources)
    topic_body = "\n".join([
        "## 综合判断",
        "温州 AI 资料呈现出政策牵引、机构建设、产业平台、场景应用和公共治理并行推进的路径。",
        "",
        *_body_link_section([x for x in related_agg if not x.startswith("wiki/topics/")]),
        "## 高频专题",
        *[f"- {x}" for x in top_topics[:8]],
        "",
        "## 去重后的关键事实",
        *[f"- {x}" for x in facts[:20]],
        "",
        "## 反方证据与信息缺口",
        *[f"- {x}" for x in critical],
        "",
        "## 来源索引",
        *[f"- [[{x}]]" for x in sources[:24]],
    ])
    material_case_facts = [item for item in case_facts[:16] if item not in facts[:24]]
    if not material_case_facts:
        material_case_facts = ["案例条目已在上方事实区去重呈现，详见 [[wiki/cases/温州AI应用与机构建设案例线索.md]]。"]
    material_body = "\n".join([
        "## 用途",
        "为研究、汇报和写作提供可追溯的温州 AI 政策与产业资料包。",
        "",
        *_body_link_section(["wiki/topics/温州人工智能创新发展路径.md", "wiki/concepts/人工智能创新发展先行市.md", "wiki/cases/温州AI应用与机构建设案例线索.md"]),
        "## 去重后的可用事实",
        *[f"- {x}" for x in facts[:24]],
        "",
        "## 可用案例",
        *[f"- {x}" for x in material_case_facts],
        "",
        "## 反方证据与信息缺口",
        *[f"- {x}" for x in critical],
        "",
        "## 质量风险",
        *[f"- {x}" for x in quality[:10]],
        "",
        "## 来源索引",
        *[f"- [[{x}]]" for x in sources[:24]],
    ])
    concept_body = "\n".join([
        "## 概念说明",
        "人工智能创新发展先行市是地方政府围绕 AI 基础设施、产业生态、示范应用和治理机制进行系统部署的城市发展目标。",
        "",
        *_body_link_section(["wiki/topics/温州人工智能创新发展路径.md", "wiki/material-packs/温州AI政策与产业研究资料包.md", "wiki/cases/温州AI应用与机构建设案例线索.md"]),
        "## 证据线索",
        *[f"- {x}" for x in concept_facts],
        "",
        "## 概念边界与待验证问题",
        *[f"- {x}" for x in critical[:6]],
    ])
    case_body = "\n".join([
        "## 案例线索",
        "以下案例来自 source-note 的关键事实抽取，后续可拆成独立 case-story。",
        "",
        *_body_link_section(["wiki/topics/温州人工智能创新发展路径.md", "wiki/material-packs/温州AI政策与产业研究资料包.md", "wiki/concepts/人工智能创新发展先行市.md"]),
        *[f"- {x}" for x in case_facts],
        "",
        "## 案例缺口",
        *[f"- {x}" for x in critical[:6]],
    ])
    for target, title, type_, body, kind in [
        ("wiki/topics/温州人工智能创新发展路径.md", "温州人工智能创新发展路径", "topic-page", topic_body, "topic"),
        ("wiki/material-packs/温州AI政策与产业研究资料包.md", "温州AI政策与产业研究资料包", "material-pack", material_body, "material-pack"),
        ("wiki/concepts/人工智能创新发展先行市.md", "人工智能创新发展先行市", "concept-page", concept_body, "concept"),
        ("wiki/cases/温州AI应用与机构建设案例线索.md", "温州AI应用与机构建设案例线索", "case-story", case_body, "case"),
    ]:
        pages.append(_page(kind, target, title, type_, sources, [x for x in related_agg if x != target], body, plan_run_id, (index.root / target).exists()))
    token_map = {n.rel: _tokens(n.title + "\n" + n.body[:4000]) for n in source_notes}
    for note in source_notes:
        scores = [(len(token_map[note.rel] & toks), rel) for rel, toks in token_map.items() if rel != note.rel]
        related_sources = [rel for score, rel in sorted(scores, reverse=True)[:3] if score >= 2]
        update = _update_source_note(note, related_sources + related_agg[:2], ["linked", "kb-finalize"], plan_run_id)
        if update:
            pages.append(update)
    return {"run_id": plan_run_id, "created_at": stamp, "mode": "dry-run", "task": "finalize knowledge base", "entry": "finalize_kb", "primary_skill": "kb-finalize", "knowledge_base": str(index.root), "actions": [{"operation": "pipeline_stage", "entry": "finalize_kb", "stage": "cross_source_aggregation", "skill": "kb-finalize", "risk": "medium", "planned_inputs": len(source_notes), "planned_pages": len(pages)}], "planned_pages": pages, "plan_quality": {"source_notes": len(source_notes), "aggregation_pages": 4, "source_note_updates": max(0, len(pages) - 4)}, "manual_review": [], "apply_instruction": "审阅聚合与 related 更新后运行 apply-plan。"}
