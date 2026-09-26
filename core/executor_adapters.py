"""Thin executor adapters moved out of the CLI to keep its line budget.
They convert notes and reconcile pure typed-update results; they perform no
filesystem writes, provider calls, or identity allocation.
"""
from __future__ import annotations

from typing import Any

from .markdown import note_summary
from .knowledge_objects import identity_from_metadata
from .reconcile import ReconcileConflict, _text as snapshot_text
from .vault import Note


def executor_notes(notes: list[Note]) -> list[dict[str, Any]]:
    """Convert Notes to executor-note dicts with FULL original snapshots."""
    result = []
    for note in notes:
        item = {
            "rel": note.rel, "title": note.title, "body": note.body,
            "summary": note_summary(note, 180), "metadata": note.metadata,
        }
        try:
            # FULL original text + raw-byte hash; changed snapshot or bad bytes
            # surface explicitly via source_error, never silently as complete.
            item["source_text"] = snapshot_text(note)
            item["source_sha256"] = note.sha256
        except (ReconcileConflict, UnicodeDecodeError) as exc:
            item["source_error"] = str(exc)
        result.append(item)
    return result


def work_memory_candidate(note: Note) -> bool:
    text = note.rel + "\n" + note.title + "\n" + note.body[:1500]
    patterns = ["会议", "周报", "项目", "复盘", "决定", "决策", "待办", "行动项", "课程", "上课", "开会", "产品优化"]
    return any(p in text for p in patterns)


def work_memory_llm_candidates(cfg: dict[str, Any], scope: list[Note]) -> list[Note]:
    """Work-memory inputs come from the ACTUAL configured scan locations
    (scan.include_dirs), not a hardcoded quicknote/inbox list; project plans
    and diaries living in configured project directories stay eligible.
    raw/ stays a restricted input per the skill contract, and configured
    knowledge OUTPUT dirs (e.g. wiki/work-memory, _kb-steward) are excluded so
    generated pages are never re-ingested as inputs."""
    from .layout import knowledge_dirs

    prefixes = tuple(f"{d.strip('/')}/" for d in cfg["scan"]["include_dirs"])
    output_prefixes = tuple(f"{d}/" for d in knowledge_dirs(cfg).values())
    return [n for n in scope
            if not n.rel.startswith("raw/") and n.rel.startswith(prefixes)
            and not n.rel.startswith(output_prefixes)
            and work_memory_candidate(n)]


def prepare_typed_executor_pages(index: Any, cfg: dict[str, Any],
                                 pages: list[dict[str, Any]],
                                 result: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the accepted typed updater and reconcile per-input outcomes.

    The generator's outcome is retained on each input so a successful source
    analysis cannot be mistaken for an accepted write proposal.  ``pages`` is
    replaced only with create/update proposals accepted by the updater;
    noop/blocked candidates remain visible through their disposition and
    required targets.
    """
    from .typed_card_updates import prepare_typed_updates

    candidates = [p for p in pages if isinstance(p, dict)]
    original_outcomes = [dict(item) for item in result.get("input_outcomes", [])
                         if isinstance(item, dict)]
    result.setdefault("generator_result", {
        "processed": result.get("processed", 0),
        "input_outcomes": original_outcomes,
        "planned_pages": [dict(page) for page in candidates],
    })
    # Non-LLM source previews are intentionally unwritable (the apply guard
    # remains strict). Isolate them BEFORE identity allocation/review planning,
    # so a failed sibling cannot poison an otherwise reviewable source batch.
    # Keep the diagnostic generator result and per-input receipt; never turn a
    # provider failure into a completed zero or an approved/rejected page.
    excluded: dict[int, dict[str, Any]] = {}
    for position, page in enumerate(candidates):
        mode = str(page.get("analysis_mode") or "").strip().lower()
        if page.get("skill") == "topic-research-compile" and mode and mode != "llm":
            rel = str(page.get("rel_path") or page.get("target") or "")
            excluded[position] = {
                "rel_path": rel, "chosen_target": None, "outcome": "blocked",
                "reason": f"non_llm_source: {mode} 仅保留诊断，未进入写入计划；请启用 LLM 或修复 provider 后重试。",
            }
    typed = prepare_typed_updates(
        index, cfg, [page for i, page in enumerate(candidates) if i not in excluded])
    accepted_outcomes = iter(typed["outcomes"])
    typed["outcomes"] = [excluded[i] if i in excluded else next(accepted_outcomes)
                         for i in range(len(candidates))]
    typed["issues"].extend(f"{item['rel_path']}: {item['reason']}" for item in excluded.values())
    result["typed_update_outcomes"] = typed["outcomes"]
    result["typed_update_issues"] = typed["issues"]
    result.setdefault("issues", []).extend(typed["issues"])
    target_choices: dict[str, list[str | None]] = {}
    by_source: dict[str, list[dict[str, Any]]] = {}
    for page, outcome in zip(candidates, typed["outcomes"]):
        rel = str(page.get("rel_path") or page.get("target") or "")
        target_choices.setdefault(rel, []).append(outcome.get("chosen_target"))
        sources = page.get("sources") or page.get("origin", {}).get("source_paths", [])
        for source in (str(src) for src in sources if src):
            by_source.setdefault(source, []).append(outcome)
    rank = {"noop": 1, "create": 2, "update": 3, "blocked": 4}
    for item in result.get("input_outcomes", []):
        if not isinstance(item, dict):
            continue
        matches = by_source.get(str(item.get("rel") or ""), [])
        item["generator_outcome"] = item.get("outcome")
        item["generator_complete"] = item.get("complete") is True
        if matches:
            dispositions = [str(o.get("outcome")) for o in matches]
            disposition = max(dispositions, key=lambda value: rank.get(value, 0))
            required = list(dict.fromkeys(
                str(o.get("chosen_target")) for o in matches
                if o.get("chosen_target")))
            item["updater_disposition"] = disposition
            item["required_targets"] = required
            noop_snapshots: dict[str, dict[str, Any]] = {}
            noop_targets: list[str] = []
            for update in matches:
                if update.get("outcome") != "noop":
                    continue
                target = str(update.get("chosen_target") or "")
                if target:
                    noop_targets.append(target)
                note = getattr(index, "by_rel", {}).get(target)
                if note is None:
                    continue
                try:
                    identity = identity_from_metadata(note.metadata)
                except (TypeError, ValueError):
                    identity = None
                if identity is None or type(identity[1]) is not int:
                    continue
                noop_snapshots[target] = {
                    "content_sha256": str(note.sha256),
                    "object_id": identity[0],
                    "revision": identity[1],
                    "canonical_path": target,
                    "verification": "updater_index",
                }
            item["updater_noop_targets"] = list(dict.fromkeys(noop_targets))
            item["updater_target_snapshots"] = noop_snapshots
            item["updater_reasons"] = [str(o.get("reason")) for o in matches
                                       if o.get("reason")]
            offsets: dict[str, int] = {}
            remapped: list[str] = []
            for target in item.get("targets", []):
                choices = target_choices.get(target)
                if choices:
                    offset = offsets.get(target, 0)
                    offsets[target] = offset + 1
                    target = choices[min(offset, len(choices) - 1)]
                if target and target not in remapped:
                    remapped.append(str(target))
            item["targets"] = remapped
            if disposition == "blocked":
                item["outcome"] = "blocked"
                item["complete"] = False
                item["reason"] = ((str(item.get("reason") or "") + "；")
                                   + "typed updater blocked："
                                   + "；".join(item["updater_reasons"]))
        else:
            item["updater_disposition"] = "not_run"
            item["required_targets"] = []
            item["updater_reasons"] = []
            if item.get("outcome") in {"ok", "partial"}:
                item["targets"] = []
    if result.get("input_outcomes"):
        result["processed"] = sum(
            1 for item in result["input_outcomes"]
            if item.get("complete") is True and item.get("outcome") == "ok"
            and item.get("updater_disposition") in {"create", "update", "noop"}
        )
    return typed["pages"]


def prepare_seed_receipt_outcomes(result: dict[str, Any], updater_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach atomic generator closure to the seed updater's exact outcomes.

    The atomic generator evaluates a batch, while ``prepare_seed_updates`` is
    the sole authority for create/update/noop/blocked dispositions.  Join them
    by source path so an uncited input can remain a completed evaluation and a
    failed sibling cannot receive the batch's success credit.
    """
    by_source: dict[str, list[dict[str, Any]]] = {}
    for update in updater_outcomes if isinstance(updater_outcomes, list) else []:
        if not isinstance(update, dict):
            continue
        for source in update.get("sources", []) if isinstance(update.get("sources"), list) else []:
            by_source.setdefault(str(source), []).append(update)
    rank = {"evaluated": 0, "noop": 1, "create": 2, "update": 3, "blocked": 4}
    outcomes = result.get("input_outcomes", []) if isinstance(result, dict) else []
    for item in outcomes:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("rel") or "")
        matches = by_source.get(rel, [])
        if not matches:
            if item.get("outcome") == "zero" and item.get("complete") is True:
                item["updater_disposition"] = "zero"
            elif item.get("complete") is True and item.get("outcome") == "ok":
                item["updater_disposition"] = "evaluated"
            else:
                item["updater_disposition"] = "not_run"
            item.setdefault("required_targets", [])
            item.setdefault("updater_target_snapshots", {})
            continue
        dispositions = [str(update.get("updater_disposition") or "blocked") for update in matches]
        disposition = max(dispositions, key=lambda value: rank.get(value, 4))
        required = list(dict.fromkeys(
            str(target) for update in matches
            for target in update.get("required_targets", [])
            if target))
        snapshots: dict[str, dict[str, Any]] = {}
        for update in matches:
            raw = update.get("updater_target_snapshots")
            if isinstance(raw, dict):
                snapshots.update({str(target): dict(snapshot) for target, snapshot in raw.items()
                                  if isinstance(snapshot, dict)})
        item["updater_disposition"] = disposition
        item["required_targets"] = required
        item["targets"] = required
        item["updater_target_snapshots"] = snapshots
        reasons = [str(update.get("reason") or "") for update in matches
                   if update.get("reason")]
        item["updater_reasons"] = reasons
        if disposition == "blocked":
            item["outcome"] = "blocked"
            item["complete"] = False
            item["reason"] = ((str(item.get("reason") or "") + "；")
                               + "；".join(reasons)).strip("；")
    if outcomes:
        result["processed"] = sum(
            1 for item in outcomes
            if isinstance(item, dict) and item.get("complete") is True
            and item.get("outcome") in {"ok", "zero"}
            and item.get("updater_disposition") in {"create", "update", "noop", "evaluated", "zero"}
        )
    return result


def make_seed_receipt_draft(index: Any, cfg: dict[str, Any], notes: list[Any],
                            use_llm: bool) -> dict[str, Any]:
    from .config import seed_generation_mode
    from .pipeline_history import make_generation_receipt_draft
    return make_generation_receipt_draft(
        index, cfg, skill="mindseed-grow", stage="seed_cluster", notes=notes,
        use_llm=use_llm, semantic={"kind": "seed", "skill": "mindseed-grow",
                                   "mode": seed_generation_mode(cfg),
                                   "question": None,
                                   "analysis_mode": "llm" if use_llm else "heuristic"})


def print_plan_summary(plan: dict[str, Any], path: Any, queued: int) -> None:
    """Plan summary printer, moved verbatim from the CLI to keep it thin."""
    print(f"计划文件：{path}")
    print(f"入口：{plan.get('entry')}")
    print(f"Primary skill：{plan.get('primary_skill')}")
    for retrieval in plan.get("retrieval", []):
        print(f"检索：{retrieval['engine']}，选中 {len(retrieval['hits'])} 页")
        if retrieval.get("fallback_reason"):
            print(retrieval["fallback_reason"])
        if retrieval.get("requires_review"):
            print("检索材料包含需复查的依据，详见计划 retrieval 字段。")
    print(f"扫描范围：{plan.get('scan_scope', 'changed')}")
    print(f"变更文件估计：{plan.get('changed_files')}")
    if plan.get("scan_scope") == "all":
        print(f"候选文件总数：{plan.get('candidate_files')}")
    batching = plan.get("batching") or {}
    if batching:
        print(
            "初始化批次："
            + f"raw {batching.get('raw_batches', 0)} 批，"
            + f"quicknote/inbox {batching.get('quicknote_batches', 0)} 批，"
            + f"本批后剩余 {batching.get('remaining_after_current', 0)} 个输入\n"
        )
    print(f"计划动作：{len(plan.get('actions', []))}")
    estimated = sum(int(action.get("estimated_inputs", 0)) for action in plan.get("actions", []))
    if estimated:
        print(f"预计处理输入：{estimated}")
    print(f"人工确认项：{len(plan.get('manual_review', []))}")
    quality = plan.get("plan_quality") or {}
    if quality.get("duplicate_targets"):
        print(f"重复目标路径：{len(quality.get('duplicate_targets', {}))}")
    blocked = quality.get("blocked_placeholder_pages") or []
    if blocked:
        print(f"mock/占位页面：{len(blocked)}")
    raw_cov = quality.get("raw_coverage") or {}
    if raw_cov.get("raw_total"):
        print(f"raw 覆盖：{raw_cov.get('covered', 0)}/{raw_cov.get('raw_total', 0)}")
    if quality.get("pdf_needs_extraction"):
        print(f"PDF 待抽取：{len(quality.get('pdf_needs_extraction', []))}")
    llm = plan.get("llm_runtime")
    if llm:
        mode = "mock" if llm.get("mock") else "provider"
        print(f"LLM runtime：{mode}，items={len(llm.get('items', []))}，ok={llm.get('ok')}")
        for note in llm.get("contract_notes") or []:
            print(f"契约降级提示：{note}")
    planned = plan.get("planned_pages", [])
    if planned:
        print(f"计划落盘页面：{len(planned)}")
        print(f"应用命令：python scripts\\personal_kb_steward.py apply-plan {path}")
        # -- Plan Diff 预览 --
        for pp in planned[:5]:
            print()
            print("─" * 60)
            print(f"  skill: {pp.get('skill', '')}")
            print(f"  路径: {pp.get('target', '')}")
            content = pp.get('content', '')
            preview_lines = content.split('\n')[:20]
            print("  前 20 行:")
            for pline in preview_lines:
                print(f"    {pline}")
            print("─" * 60)
        if len(planned) > 5:
            print(f"  ... 还有 {len(planned) - 5} 个页面未展示")
    if queued:
        print(f"已写入人工确认队列：{queued}")
    print(f"当前为 dry-run；{plan.get('apply_instruction')}")
