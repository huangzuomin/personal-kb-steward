from __future__ import annotations

import copy
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .config import sha256_text
from .knowledge_objects import ObjectIdentityError
from .layout import knowledge_dirs
from .initializer import readable_filename
from .plan_objects import update_base
from .vault import Note, build_index, parse_frontmatter


# `config.write` is the only source of truth for knowledge-object locations.
# Hardcoding these produced links into a tree that need not exist.
FINALIZE_DIR_KEYS = ("topics_dir", "materials_dir", "concepts_dir", "cases_dir", "sources_dir")
def write_dirs(cfg: dict[str, Any]) -> dict[str, str]:
    dirs = knowledge_dirs(cfg)
    return {key.removesuffix("_dir"): dirs[key] + "/" for key in FINALIZE_DIR_KEYS}


# Aggregation pages must be named after the material they summarise, never after
# a demo corpus. Upstream hardcoded city and agency names here, so every vault
# produced the same "温州 AI 政策与产业" pages no matter what the sources said.
FINALIZE_AGG_KINDS = ("topic", "material", "concept", "case")
FINALIZE_AGG_DIR = {"topic": "topics", "material": "materials", "concept": "concepts", "case": "cases"}
FINALIZE_AGG_TYPE = {
    "topic": "topic-page", "material": "material-pack",
    "concept": "concept-page", "case": "case-story",
}
# Kept separate from the kind so the emitted tag stays byte-identical to upstream.
FINALIZE_AGG_TAG = {
    "topic": "topic", "material": "material-pack",
    "concept": "concept", "case": "case",
}


def aggregation_specs(cfg: dict[str, Any], top_topics: list[str]) -> list[dict[str, Any]]:
    """Aggregation page specs: derived from the material first, config second.

    The topic title comes from the 「提取的专题」 entries that the source notes
    themselves carry, so the page is named after what was actually compiled.
    Material/concept/case pages need an explicit `cfg["finalize_aggregation"]`
    entry — without one they are simply not produced, which is the safer
    default: inventing an aggregation page is worse than omitting it.
    """
    configured = cfg.get("finalize_aggregation")
    configured = configured if isinstance(configured, dict) else {}
    specs: list[dict[str, Any]] = []
    for kind in FINALIZE_AGG_KINDS:
        spec = configured.get(kind)
        spec = spec if isinstance(spec, dict) else {}
        title = str(spec.get("title") or "").strip()
        if kind == "topic" and top_topics:
            title = top_topics[0]
        if not title:
            continue
        markers = [str(m) for m in (spec.get("match_any") or []) if str(m).strip()]
        specs.append({
            "kind": kind,
            "title": title,
            "type": FINALIZE_AGG_TYPE[kind],
            "tag": FINALIZE_AGG_TAG[kind],
            "dir": FINALIZE_AGG_DIR[kind],
            "markers": markers,
            "intro": str(spec.get("intro") or "").strip(),
        })
    return specs


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
        gaps.append("当前摘录未包含明显反方或风险线索，需回原文确认是否遗漏。")
    if not any(word in text for word in ["评估", "成效", "指标", "ROI", "投入产出", "转化率"]):
        gaps.append("当前摘录缺少评估线索，是否需要量化验证取决于具体研究问题。")
    if not any(word in text for word in ["企业", "市民", "学校", "医院", "基层", "一线"]):
        gaps.append("请核对来源作者、时间和观察范围，必要时补充独立来源。")
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
    for key in [*ordered, *(key for key in meta if key not in ordered)]:
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


def _page(kind: str, target: str, title: str, type_: str, sources: list[str], related: list[str], body: str, run_id: str, existing: Note | None) -> dict[str, Any]:
    if existing:
        from .reconcile import _text
        _text(existing)  # The generation snapshot must still match the actual file.
        origin = existing.metadata.get("origin", {})
        if (not isinstance(origin, dict) or origin.get("operation") != "kb-finalize"
                or existing.metadata.get("finalize_body_sha256") != sha256_text(existing.body)):
            raise ObjectIdentityError(f"Finalize target is not an unchanged owned aggregate: {target}; use Reconcile for reviewed updates")
    today = dt.date.today().isoformat()
    content = "\n".join([
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {type_}",
        "status: growing",
        "stage: candidate",
        f"created: {today}",
        f"updated: {today}",
        f"sources: {json.dumps(sources, ensure_ascii=False)}",
        f"related: {json.dumps(related, ensure_ascii=False)}",
        f"tags: {json.dumps(['kb-finalize', kind], ensure_ascii=False)}",
        "confidence: medium",
        "review_required: true",
        f"origin: {json.dumps({'source_paths': sources, 'operation': 'kb-finalize', 'run_id': run_id}, ensure_ascii=False)}",
        "---",
        "",
        f"# {title}",
        "",
        body,
    ])
    meta, rendered_body = parse_frontmatter(content)
    meta["finalize_body_sha256"] = sha256_text(rendered_body)
    if existing:
        from .reconcile import _patch_header, _HEADER
        patched = _patch_header(_text(existing), meta)
        content = patched[:_HEADER.match(patched).end()] + rendered_body
    else:
        content = _frontmatter(meta) + rendered_body
    return {**(update_base(existing) if existing else {}), "skill": "kb-finalize", "operation": "update" if existing else "create", "rel_path": target, "target": target, "sources": sources, "origin": {"source_paths": sources, "operation": "kb-finalize", "run_id": run_id}, "content_sha256": sha256_text(content), "content": content, "review_required": True, "confidence": "medium"}


def _update_source_note(note: Note, related: list[str], tags: list[str], run_id: str) -> dict[str, Any] | None:
    meta, body = copy.deepcopy(note.metadata), note.body
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
    from .reconcile import _patch_header, _text, _HEADER
    original = _text(note)
    header = _HEADER.match(original)
    if not header:
        raise ObjectIdentityError(f"Source note has no valid frontmatter: {note.rel}")
    newline = "\r\n" if "\r\n" in original else "\n"
    patched = _patch_header(original, {"related": merged_related, "tags": merged_tags, "updated": meta["updated"]})
    header = _HEADER.match(patched)
    content = patched[:header.end()] + updated_body.replace("\r\n", "\n").replace("\n", newline)
    return {**update_base(note), "skill": "kb-finalize", "operation": "update", "rel_path": note.rel, "target": note.rel, "sources": list(meta.get("sources") or []), "origin": {"source_paths": list(meta.get("sources") or []), "operation": "kb-finalize", "run_id": run_id}, "content_sha256": sha256_text(content), "content": content, "review_required": True, "confidence": "medium"}


def make_finalize_plan(cfg: dict[str, Any], *, plan_run_id: str, stamp: str, apply_updates: bool = False) -> dict[str, Any]:
    index = build_index(cfg)
    dirs = write_dirs(cfg)
    sources_prefix = dirs["sources"]
    source_notes = [n for n in index.notes if n.rel.startswith(sources_prefix) and n.metadata.get("type") == "source-note"]
    sources = [n.rel for n in source_notes]
    pages: list[dict[str, Any]] = []
    if len(source_notes) < 2:
        return {"run_id": plan_run_id, "created_at": stamp, "mode": "dry-run", "task": "finalize knowledge base", "entry": "finalize_kb", "primary_skill": "kb-finalize", "knowledge_base": str(index.root), "actions": [], "planned_pages": [], "manual_review": [{"type": "insufficient_sources", "risk": "P2", "reason": "需要至少 2 个 source-note 才能做跨源聚合。"}]}
    topic_labels = lambda n: {x.split("：", 1)[0].split(":", 1)[0].strip() for x in _section(n.body, "提取的专题")}
    counts = Counter(label for n in source_notes for label in sorted(topic_labels(n)))
    top_topics = [label for label, _ in counts.most_common(8) if label]
    specs = aggregation_specs(cfg, top_topics)
    links_by_source: dict[str, list[str]] = {n.rel: [] for n in source_notes}
    aggregate_count = 0
    selected = []
    for spec in specs:
        kind, title, markers = spec["kind"], spec["title"], spec["markers"]
        scoped = [n for n in source_notes if (
            title in topic_labels(n) if kind == "topic" else
            any(m.casefold() in (n.title + "\n" + n.body).casefold() for m in markers) if markers else True)]
        if scoped:
            selected.append((spec, scoped))
    for spec, scoped in selected:
        kind, title, markers = spec["kind"], spec["title"], spec["markers"]
        scoped_paths = [n.rel for n in scoped]
        facts = _dedupe_items([x for n in scoped for x in _section(n.body, "关键事实")], limit=24)
        quality = _dedupe_items([x for n in scoped for x in _section(n.body, "质量")], limit=10)
        critical = _critical_findings(facts, quality, scoped_paths)
        title_heading = {"topic": "综合判断", "material": "用途", "concept": "概念说明", "case": "案例线索"}[kind]
        fact_heading = {"topic": "去重后的关键事实", "material": "去重后的可用事实", "concept": "证据线索", "case": "可用案例"}[kind]
        body = "\n".join([f"## {title_heading}",
                          spec["intro"] or "以下为匹配来源的候选汇总；归属及语义支持仍需人工确认。", "",
                          f"## {fact_heading}", *[f"- {x}" for x in facts], "",
                          "## 反方证据与信息缺口", *[f"- {x}" for x in critical], "",
                          "## 来源索引", *[f"- [[{x}]]" for x in scoped_paths]])
        target = f"{dirs[spec['dir']]}{readable_filename(title, kind)}.md"
        existing = index.by_rel.get(target)
        related = [f"{dirs[other['dir']]}{readable_filename(other['title'], other['kind'])}.md"
                   for other, other_notes in selected if other is not spec
                   and set(scoped_paths) & {n.rel for n in other_notes}]
        if related:
            body += "\n\n" + "\n".join(_body_link_section(related))
        page = _page(spec["tag"], target, title, spec["type"], scoped_paths, related, body, plan_run_id, existing)
        page["retrieval_source_hashes"] = {n.rel: n.sha256 for n in scoped}
        pages.append(page)
        aggregate_count += 1
        for note in scoped:
            links_by_source[note.rel].append(target)
    token_map = {n.rel: _tokens(n.title + "\n" + n.body[:4000]) for n in source_notes}
    for note in source_notes:
        scores = [(len(token_map[note.rel] & toks), rel) for rel, toks in token_map.items() if rel != note.rel]
        related_sources = [rel for score, rel in sorted(scores, key=lambda x: (-x[0], x[1]))[:3] if score > 0]
        update = _update_source_note(note, related_sources + links_by_source[note.rel], ["linked", "kb-finalize"], plan_run_id)
        if update:
            update["retrieval_source_hashes"] = {rel: index.by_rel[rel].sha256 for rel in set(related_sources + update["sources"] + [note.rel]) if rel in index.by_rel}
            pages.append(update)
    return {"run_id": plan_run_id, "created_at": stamp, "mode": "dry-run", "task": "finalize knowledge base",
            "entry": "finalize_kb", "primary_skill": "kb-finalize", "knowledge_base": str(index.root),
            "actions": [{"operation": "pipeline_stage", "entry": "finalize_kb", "stage": "cross_source_aggregation",
                         "skill": "kb-finalize", "risk": "medium", "planned_inputs": len(source_notes), "planned_pages": len(pages)}],
            "planned_pages": pages, "plan_quality": {"source_notes": len(source_notes), "aggregation_pages": aggregate_count,
                                                     "source_note_updates": len(pages) - aggregate_count},
            "manual_review": [{"type": "finalize_review", "risk": "medium", "reason": "核对候选聚合归属及来源关联后再应用。"}] if pages else [],
            "apply_instruction": "审阅聚合与 related 更新后运行 review/apply。"}
