from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable

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
        if rel_path and page_target_exists(cfg, page):
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
    target = (Path(cfg["write"][rel_dir_key]) / f"{readable_filename(title, kind)}.md").as_posix()
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
        "review_required: false",
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
        "- 这是初始化 pipeline 自动生成的候选页，可直接落盘进入 growing 状态。",
        "- 后续应在跨批次合并阶段确认边界、命名、证据充分性和 related 链接。",
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
        "review_required": False,
        "confidence": "medium",
    }


def promote_candidate_pages(cfg: dict[str, Any], notes: list[Note], plan_run_id: str) -> list[dict[str, Any]]:
    sources = [note.rel for note in notes]
    if not sources:
        return []
    text = "\n".join(f"{note.title}\n{note.body[:1200]}" for note in notes)
    pages: list[dict[str, Any]] = []
    if len(sources) >= int(cfg.get("quality_gate", {}).get("min_sources_for_topic", 3)):
        pages.append(make_promote_candidate_page(
            cfg,
            kind="topic",
            title="温州人工智能创新发展路径",
            rel_dir_key="topics_dir",
            sources=sources[:8],
            plan_run_id=plan_run_id,
            body=(
                "## 主题边界\n"
                "围绕温州如何通过政策、机构、产业平台和场景应用推动人工智能发展，"
                "梳理其路径、约束和可验证证据。\n\n"
                "## 待验证问题\n"
                "- 温州 AI 发展的核心抓手是什么？\n"
                "- 政策目标、产业基础和应用场景之间是否形成闭环？"
            ),
        ))
    if any(marker in text for marker in ("人工智能局", "先行市", "示范应用第一城")):
        pages.append(make_promote_candidate_page(
            cfg,
            kind="concept",
            title="人工智能创新发展先行市",
            rel_dir_key="concepts_dir",
            sources=sources[:8],
            plan_run_id=plan_run_id,
            body=(
                "## 概念定义候选\n"
                "该概念指向地方政府围绕 AI 基础设施、产业集群、示范应用和治理机制"
                "进行系统部署的一类城市发展目标。\n\n"
                "## 需要补证\n"
                "- 官方定义或政策出处\n"
                "- 目标指标和时间表\n"
                "- 与具体产业、公共服务场景的关系"
            ),
        ))
    case_sources = [
        n.rel for n in notes
        if any(m in f"{n.title}\n{n.body[:1000]}" for m in ("揭牌", "瓯海", "财政", "车间", "智能眼镜"))
    ]
    if case_sources:
        pages.append(make_promote_candidate_page(
            cfg,
            kind="case",
            title="温州AI应用与机构建设案例线索",
            rel_dir_key="cases_dir",
            sources=case_sources[:8],
            plan_run_id=plan_run_id,
            body=(
                "## 案例线索\n"
                "本页收集初始化阶段识别出的案例候选，后续应拆分为具备主体、行动、"
                "场景、结果的独立案例。\n\n"
                "## 候选方向\n"
                "- 温州人工智能局挂牌\n"
                "- AI 赋能制造或财政监督\n"
                "- 智能眼镜产业生态建设"
            ),
        ))
    if len(sources) >= int(cfg.get("quality_gate", {}).get("min_evidence_items_for_material_pack", 5)):
        pages.append(make_promote_candidate_page(
            cfg,
            kind="material-pack",
            title="温州AI政策与产业研究资料包",
            rel_dir_key="materials_dir",
            sources=sources[:12],
            plan_run_id=plan_run_id,
            body=(
                "## 用途\n"
                "为后续写作、研究或项目汇报提供一组可追溯的温州 AI 政策与产业资料。\n\n"
                "## 后续整理\n"
                "- 按政策规划、产业生态、应用案例、治理机制分组\n"
                "- 标注可引用事实和待核验信息"
            ),
        ))
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
            current_quick_batch, processed_index, plan_run_id, use_llm=False,
        )
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
        "apply_instruction": "审阅 plan 后运行 apply-plan；若存在 planned_pages_require_review，则先 review approve 或重新生成。",
    }
