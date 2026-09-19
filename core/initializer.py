from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable

from .layout import knowledge_dirs
from .config import kb_root, sha256_text
from .state import changed_notes, load_processed_index, load_state, unprocessed_notes
from .vault import Note, build_index


ExecutorPlanFn = Callable[..., dict[str, Any] | None]
PageCheckFn = Callable[[dict[str, Any]], bool]


def readable_filename(title: str, fallback: str = "未命名页面") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title).strip()
    cleaned = re.sub(r"[，。；;、\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:80] or fallback


def batch_notes(notes: list[Note], batch_size: int) -> list[list[Note]]:
    size = max(1, batch_size)
    return [notes[i:i + size] for i in range(0, len(notes), size)]


def page_target_exists(cfg: dict[str, Any], page: dict[str, Any]) -> bool:
    rel_path = str(page.get("rel_path") or page.get("target") or "")
    if not rel_path:
        return False
    root = kb_root(cfg)
    return (root / rel_path).exists()


def split_existing_pages(cfg: dict[str, Any], pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    fresh: list[dict[str, Any]] = []
    skipped: list[str] = []
    for page in pages:
        rel_path = str(page.get("rel_path") or page.get("target") or "")
        if page.get("operation", "create") != "update" and rel_path and page_target_exists(cfg, page):
            skipped.append(rel_path)
        else:
            fresh.append(page)
    return fresh, skipped


def make_promote_candidate_page(
    cfg: dict[str, Any],
    *,
    kind: str,
    title: str,
    rel_dir_key: str,
    sources: list[str],
    body: str,
    plan_run_id: str,
) -> dict[str, Any]:
    target = (Path(knowledge_dirs(cfg)[rel_dir_key]) / f"{readable_filename(title, kind)}.md").as_posix()
    type_by_kind = {
        "topic": "topic-page",
        "concept": "concept-page",
        "case": "case-story",
        "material-pack": "material-pack",
    }
    today = dt.date.today().isoformat()
    content = "\n".join([
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {type_by_kind.get(kind, kind)}",
        "status: growing",
        "stage: candidate",
        f"created: {today}",
        f"updated: {today}",
        f"sources: {json.dumps(sources, ensure_ascii=False)}",
        "related: []",
        f"tags: {json.dumps(['kb-initialize', kind, 'candidate'], ensure_ascii=False)}",
        "confidence: medium",
        "review_required: true",
        f"origin: {json.dumps({'source_paths': sources, 'operation': 'kb-initialize', 'run_id': plan_run_id}, ensure_ascii=False)}",
        "---",
        "",
        f"# {title}",
        "",
        body,
        "",
        "## 来源",
        *[f"- [[{source}]]" for source in sources],
        "",
        "## 后续整理",
        "- 这是初始化 pipeline 自动生成的候选页，主题边界尚未人工确认。",
        "- 后续应在跨批次合并阶段确认边界、命名、证据充分性和 related 链接。",
        "- 转正为正式专题前，需核对全部来源是否确实支持本页主题。",
    ])
    return {
        "skill": "kb-initialize",
        "operation": "create",
        "rel_path": target,
        "target": target,
        "sources": sources,
        "origin": {"source_paths": sources, "operation": "kb-initialize", "run_id": plan_run_id},
        "content_sha256": sha256_text(content),
        "content": content,
        # Auto-generated candidate pages must never claim they are ready to
        # promote themselves; a human confirms the topic boundary first.
        "review_required": True,
        "confidence": "medium",
    }


def candidate_promotion_specs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidate-page rules, taken from config rather than hardcoded examples.

    An empty list means this vault has opted out of automatic promotion, which
    is the safer default: a batch of unrelated documents must not manufacture
    a "温州 AI 政策与产业" topic just because the batch is large enough.
    """
    specs = cfg.get("candidate_promotion")
    if not isinstance(specs, list):
        return []
    return [spec for spec in specs if isinstance(spec, dict) and spec.get("title")]


def promote_candidate_pages(cfg: dict[str, Any], notes: list[Note], plan_run_id: str) -> list[dict[str, Any]]:
    """Build candidate pages only when config declares rules and markers match.

    Nothing here names a city, an agency, or a project. Every title, marker and
    body comes from `cfg["candidate_promotion"]`, so a batch that shares no
    declared marker produces no page at all.
    """
    sources = [note.rel for note in notes]
    if not sources:
        return []
    specs = candidate_promotion_specs(cfg)
    if not specs:
        return []
    quality = cfg.get("quality_gate", {})
    min_keys = {"topic": "min_sources_for_topic", "material-pack": "min_evidence_items_for_material_pack"}
    pages: list[dict[str, Any]] = []
    for spec in specs:
        kind = str(spec.get("kind") or "").strip()
        if not kind or not spec.get("rel_dir_key"):
            continue
        markers = [str(m) for m in (spec.get("match_any") or []) if str(m).strip()]
        if not markers:
            continue  # No discriminating rule is not permission to promote the whole batch.
        floor_key = min_keys.get(kind, "min_sources_for_topic")
        floor = max(1, int(spec.get("min_sources") or quality.get(floor_key, 3)))
        scoped = [note.rel for note in notes
                  if any(marker.casefold() in f"{note.title}\n{note.body}".casefold() for marker in markers)]
        scoped = scoped[:max(1, int(spec.get("max_sources") or 8))]
        if len(scoped) < floor:
            continue
        pages.append(make_promote_candidate_page(
            cfg,
            kind=kind,
            title=str(spec["title"]),
            rel_dir_key=str(spec["rel_dir_key"]),
            sources=scoped,
            plan_run_id=plan_run_id,
            body="\n".join(str(line) for line in (spec.get("body") or [])).strip(),
        ))
    hashes = {note.rel: note.sha256 for note in notes}
    for page in pages:
        page["retrieval_source_hashes"] = {rel: hashes[rel] for rel in page["sources"]}
    fresh, _ = split_existing_pages(cfg, pages)
    return fresh


def make_initialization_plan(
    cfg: dict[str, Any],
    *,
    plan_run_id: str,
    stamp: str,
    executor_plan_fn: ExecutorPlanFn,
    page_requires_manual_review: PageCheckFn,
    duplicate_page_targets: Callable[[list[dict[str, Any]]], dict[str, int]],
    page_has_blocked_placeholder: PageCheckFn,
    planned_raw_coverage: Callable[[list[str], list[dict[str, Any]]], dict[str, Any]],
    batch_size: int = 6,
    use_llm: bool = True,
    include_all: bool = True,
) -> dict[str, Any]:
    index = build_index(cfg)
    state = load_state(cfg)
    changed = changed_notes(index, state)
    input_scope = index.notes if include_all else changed
    processed_index = load_processed_index(cfg)
    raw_candidates = [n for n in input_scope if n.rel.startswith("raw/")]
    quick_candidates = [n for n in input_scope if n.rel.startswith(("quicknote/", "inbox/"))]
    raw_unprocessed = unprocessed_notes(processed_index, raw_candidates, "topic-research-compile")
    quick_unprocessed = unprocessed_notes(processed_index, quick_candidates, "mindseed-grow")
    raw_batches = batch_notes(raw_unprocessed, batch_size)
    quick_batches = batch_notes(quick_unprocessed, max(batch_size, 10))
    current_raw_batch = raw_batches[0] if raw_batches else []
    current_quick_batch = quick_batches[0] if quick_batches else []
    planned_pages: list[dict[str, Any]] = []
    skipped_existing_pages: list[str] = []
    manual_review: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    if current_raw_batch:
        result = executor_plan_fn(
            index, cfg, "初始化知识库", "topic-research-compile",
            current_raw_batch, processed_index, plan_run_id, use_llm=use_llm,
        )
        raw_pages = result.get("planned_pages", []) if result else []
        fresh_raw_pages, skipped = split_existing_pages(cfg, raw_pages)
        planned_pages.extend(fresh_raw_pages)
        skipped_existing_pages.extend(skipped)
        actions.append({
            "operation": "pipeline_stage",
            "entry": "init_kb",
            "stage": "source_compile",
            "skill": "topic-research-compile",
            "risk": "medium",
            "reason": "分批把 raw 长文沉淀为 source note，并在 source note 中保留 topic 候选。",
            "execution_mode": "llm" if use_llm else "heuristic",
            "batch": 1,
            "planned_inputs": len(current_raw_batch),
            "planned_pages": len(fresh_raw_pages),
            "skipped_existing_pages": len(skipped),
        })
        if result and result.get("issues"):
            manual_review.append({
                "type": "source_compile_quality_issues",
                "risk": "medium",
                "reason": "source compile 存在 LLM 降级或质量提示，需要抽样检查。",
                "items": result.get("issues", [])[:20],
            })

    if current_quick_batch:
        result = executor_plan_fn(
            index, cfg, "初始化知识库", "mindseed-grow",
            current_quick_batch, processed_index, plan_run_id, use_llm=use_llm,
        )
        if result and result.get("issues"):
            manual_review.append({"type": "seed_quality_issues", "risk": "medium",
                                  "reason": "seed 存在主题/重复问题，请核对提案；未改动原始资料。",
                                  "items": result["issues"][:20]})
        seed_pages = result.get("planned_pages", []) if result else []
        fresh_seed_pages, skipped = split_existing_pages(cfg, seed_pages)
        planned_pages.extend(fresh_seed_pages)
        skipped_existing_pages.extend(skipped)
        actions.append({
            "operation": "pipeline_stage",
            "entry": "init_kb",
            "stage": "seed_cluster",
            "skill": "mindseed-grow",
            "risk": "low",
            "reason": "把 quicknote/inbox 聚类成 seed，作为后续晋级输入。",
            "batch": 1,
            "planned_inputs": len(current_quick_batch),
            "planned_pages": len(fresh_seed_pages),
            "skipped_existing_pages": len(skipped),
        })

    promote_pages = promote_candidate_pages(cfg, current_raw_batch, plan_run_id)
    planned_pages.extend(promote_pages)
    if promote_pages:
        actions.append({
            "operation": "pipeline_stage",
            "entry": "init_kb",
            "stage": "promote_candidates",
            "skill": "kb-initialize",
            "risk": "medium",
            "reason": "根据当前批次 source 生成 topic/concept/case/material-pack 候选。",
            "batch": 1,
            "planned_inputs": len(current_raw_batch),
            "planned_pages": len(promote_pages),
        })

    root = kb_root(cfg)
    pdf_files = sorted(str(p.relative_to(root)).replace("\\", "/") for p in (root / "raw").glob("*.pdf")) if (root / "raw").exists() else []
    if pdf_files:
        manual_review.append({
            "type": "needs_extraction",
            "risk": "medium",
            "reason": "PDF 暂未进入 Markdown 编译链路，已进入待抽取队列。",
            "items": pdf_files[:20],
        })
    review_pages = [p for p in planned_pages if page_requires_manual_review(p)]
    if review_pages:
        manual_review.append({
            "type": "planned_pages_require_review",
            "risk": "medium",
            "reason": "部分页面质量信号偏低；默认不直接 apply，需要 review approve 或重新生成。",
            "items": [p.get("rel_path") for p in review_pages[:20]],
        })

    return {
        "run_id": plan_run_id,
        "created_at": stamp,
        "mode": "dry-run",
        "task": "初始化知识库",
        "entry": "init_kb",
        "primary_skill": "kb-initialize",
        "pipeline_declared": ["intake", "source_compile", "seed_cluster", "promote_candidates", "quality_gate"],
        "pipeline_executed_now": [a["stage"] for a in actions],
        "knowledge_base": str(index.root),
        "scan_scope": "all" if include_all else "changed",
        "changed_files": len(changed),
        "candidate_files": len(input_scope),
        "changed_file_sample": [n.rel for n in changed[:30]],
        "batching": {
            "batch_size": batch_size,
            "current_batch": 1 if current_raw_batch or current_quick_batch else 0,
            "raw_total_unprocessed": len(raw_unprocessed),
            "quicknote_total_unprocessed": len(quick_unprocessed),
            "raw_batches": len(raw_batches),
            "quicknote_batches": len(quick_batches),
            "remaining_after_current": max(0, len(raw_unprocessed) - len(current_raw_batch)) + max(0, len(quick_unprocessed) - len(current_quick_batch)),
        },
        "batch_queue": {
            "raw": [{"batch": i + 1, "count": len(b), "items": [n.rel for n in b]} for i, b in enumerate(raw_batches)],
            "quicknote_inbox": [{"batch": i + 1, "count": len(b), "items": [n.rel for n in b]} for i, b in enumerate(quick_batches)],
            "pdf_needs_extraction": pdf_files,
        },
        "actions": actions,
        "planned_pages": planned_pages,
        "plan_quality": {
            "duplicate_targets": duplicate_page_targets(planned_pages),
            "blocked_placeholder_pages": [p.get("rel_path") for p in planned_pages if page_has_blocked_placeholder(p)],
            "raw_coverage": planned_raw_coverage([n.rel for n in raw_candidates], planned_pages),
            "pdf_needs_extraction": pdf_files,
            "skipped_existing_pages": skipped_existing_pages,
        },
        "manual_review": manual_review,
        "apply_instruction": "审阅 plan 后运行 apply-plan；若存在 planned_pages_require_review，则先 review approve，再 review apply-approved；不是丢弃本批。",
    }
