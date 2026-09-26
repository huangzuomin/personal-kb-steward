"""Narrow integration seam for reviewed page-subset execution.

This module prepares exact authorization and invokes the existing
``command_apply_plan`` writer.  It does not write pages, plans, queue rows, or
run records itself.  The caller owns queue mutation after re-reading the
authority, while this seam supplies evidence for successful and failed
observed writes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import review_queue_path, sha256_file
from .page_review_scope import page_review_records, select_page_review
from .plan_output_evidence import subset_evidence_hash, verified_plan_outputs
from .review_runs import load_checked_queue
from .vault import build_index


def _queue_snapshot(items: list[dict[str, Any]]) -> str:
    encoded = json.dumps(items, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


queue_snapshot_hash = _queue_snapshot


def _target_catalog(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records = page_review_records(dict(plan))
    return {
        record["target"]: {
            key: record[key]
            for key in ("canonical_path", "content_sha256", "object_id", "revision", "operation")
        }
        for record in records
    }


def selected_plan_pages(
    plan: Mapping[str, Any], authorization: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return only pages bound by the exact subset authorization."""
    selected = authorization.get("selected_targets")
    if not isinstance(selected, Mapping) or not selected:
        raise ValueError("subset authorization has no selected target map")
    pages = plan.get("planned_pages")
    if not isinstance(pages, list):
        raise ValueError("saved plan planned_pages is not a list")
    by_target = {
        page.get("rel_path"): page
        for page in pages
        if isinstance(page, Mapping) and isinstance(page.get("rel_path"), str)
    }
    chosen: list[dict[str, Any]] = []
    for target, expected in selected.items():
        page = by_target.get(target)
        if not isinstance(expected, Mapping) or not isinstance(page, Mapping):
            raise ValueError(f"subset target is absent from saved plan: {target}")
        for key in ("canonical_path", "content_sha256", "object_id", "revision"):
            if page.get(key, page.get("rel_path") if key == "canonical_path" else None) != expected.get(key):
                raise ValueError(f"subset target binding differs from saved plan: {target}")
        chosen.append(dict(page))
    return chosen


def _result(**values: Any) -> dict[str, Any]:
    return {
        "status": "blocked",
        "selected_review_ids": [],
        "selected_targets": {},
        "verified_targets": {},
        "execution_run_id": None,
        "subset_hash": None,
        "queue_snapshot_sha256": None,
        **values,
    }


def subset_context_fields(
    context: Mapping[str, Any], keys: tuple[str, ...]
) -> dict[str, Any]:
    return {key: context[key] for key in keys if key in context}


def apply_subset_with_writer(
    cfg: Mapping[str, Any],
    plan_path: Path,
    related_queue: list[dict[str, Any]],
    *,
    writer: Callable[..., int],
) -> dict[str, Any]:
    return apply_saved_subset(
        cfg,
        plan_path,
        related_queue,
        apply_plan=lambda parent, authorization: writer(
            cfg,
            str(parent),
            allow_reviewed=True,
            expected_run_id=authorization["parent_run_id"],
            subset_context=authorization,
        ),
    )


def apply_saved_subset(
    cfg: Mapping[str, Any],
    plan_path: Path,
    related_queue: list[dict[str, Any]],
    *,
    apply_plan: Callable[[Path, dict[str, Any]], int],
) -> dict[str, Any]:
    """Prepare, execute, and reconcile one exact reviewed page subset."""
    try:
        plan_raw = plan_path.read_bytes()
        plan = json.loads(plan_raw.decode("utf-8"))
        if not isinstance(plan, dict):
            return _result(error="saved plan must be an object")
        parent_run_id = plan.get("run_id")
        if not isinstance(parent_run_id, str) or not parent_run_id:
            return _result(error="saved plan has no valid parent run_id")
        parent_plan_sha256 = hashlib.sha256(plan_raw).hexdigest()
        catalog = _target_catalog(plan)
        index = build_index(dict(cfg))
        evidence_before = verified_plan_outputs(
            index, cfg, plan_path, parent_plan_sha256, catalog
        )
        if evidence_before["conflicts"]:
            return _result(
                status="blocked",
                error="existing output evidence has conflicts",
                conflicts=evidence_before["conflicts"],
            )
        prior_outputs = {
            **evidence_before["verified"],
            **evidence_before["observed_failed"],
        }
        selection = select_page_review(
            plan, related_queue, applied_outputs=prior_outputs
        )
        selected = {
            target: {
                **details,
                "canonical_path": target,
                "operation": catalog[target]["operation"],
            }
            for target, details in selection["authorized_targets"].items()
        }
        if not selected:
            states = list(selection.get("target_states", {}).values())
            terminal = bool(states) and all(
                state in {"applied", "rejected"}
                for state in states
            )
            rejected = terminal and all(state == "rejected" for state in states)
            return _result(
                status=("rejected" if rejected else "terminal_noop")
                if terminal and not selection["run_blockers"] else "blocked",
                error=None if terminal and not selection["run_blockers"] else "page review selection is blocked",
                selection=selection,
            )
        if not selection["can_apply_subset"]:
            return _result(
                status="blocked",
                error="page review selection is blocked",
                selection=selection,
            )
        subset_hash = subset_evidence_hash(
            parent_run_id, parent_plan_sha256, selected
        )
        execution_run_id = f"{parent_run_id}.subset-{subset_hash[:16]}"
        queue_snapshot_sha256 = _queue_snapshot(related_queue)
        auth = {
            "parent_run_id": parent_run_id,
            "parent_plan_path": str(plan_path),
            "parent_plan_sha256": parent_plan_sha256,
            "subset_hash": subset_hash,
            "execution_run_id": execution_run_id,
            "queue_snapshot_sha256": queue_snapshot_sha256,
            "selected_review_ids": selection["selected_review_ids"],
            "selected_targets": selected,
            # A human rejection is a decision, not a missing output.  Carrying it
            # into the subset context lets the processed-index writer record those
            # sources as terminal, instead of re-proposing them every run.
            "rejected_targets": [
                str(target) for target in (selection.get("rejected_targets") or [])
                if isinstance(target, str) and target
            ],
        }
        current = [
            item for item in load_checked_queue(review_queue_path(dict(cfg)))
            if item.get("run_id") == parent_run_id
        ]
        if current != related_queue:
            return _result(
                status="blocked",
                error="review queue changed before subset write",
                conflicts=[{"kind": "queue_changed_before_write"}],
                selection=selection,
            )
        code = 0
        error: str | None = None
        try:
            code = apply_plan(plan_path, auth)
        except (Exception, SystemExit) as exc:
            code = 1
            error = str(exc)
        if sha256_file(plan_path) != parent_plan_sha256:
            return _result(
                status="failed",
                error="saved parent plan changed during subset apply",
                conflicts=[{"kind": "parent_plan_changed"}],
                selection=selection,
                authorization=auth,
                **auth,
            )
        evidence_after = verified_plan_outputs(
            build_index(dict(cfg)), cfg, plan_path, parent_plan_sha256, catalog
        )
        if evidence_after["conflicts"]:
            return _result(
                status="failed",
                error=error or "output evidence has conflicts after subset apply",
                conflicts=evidence_after["conflicts"],
                selection=selection,
                authorization=auth,
                **auth,
            )
        verified_targets = {
            **evidence_after["verified"],
            **evidence_after["observed_failed"],
        }
        verified_selected = {
            target: verified_targets[target]
            for target in selected
            if target in verified_targets
        }
        complete = set(verified_selected) == set(selected)
        status = "applied" if code == 0 and complete and error is None else "failed"
        return _result(
            status=status,
            error=error or (None if status == "applied" else "subset writer did not verify all selected targets"),
            selection=selection,
            authorization=auth,
            evidence=evidence_after,
            verified_targets=verified_selected,
            **auth,
        )
    except (Exception, SystemExit) as exc:
        return _result(status="blocked", error=str(exc))


def _parent_target_catalog(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    pages = plan.get("planned_pages")
    if not isinstance(pages, list):
        return {}
    for page in pages:
        if not isinstance(page, Mapping):
            return {}
        target = str(page.get("canonical_path") or page.get("rel_path") or page.get("target") or "")
        if not target or target in catalog:
            return {}
        content_hash = page.get("content_sha256")
        object_id = page.get("object_id")
        revision = page.get("revision")
        if (not isinstance(content_hash, str) or not content_hash
                or not isinstance(object_id, str) or not object_id
                or type(revision) is not int):
            return {}
        catalog[target] = {
            "canonical_path": target,
            "content_sha256": content_hash,
            "object_id": object_id,
            "revision": revision,
            "operation": str(page.get("operation") or "create"),
        }
    return catalog


def _same_output_tuple(expected: Mapping[str, Any], fact: Mapping[str, Any]) -> bool:
    return all(
        type(fact.get(key)) is type(expected.get(key))
        and fact.get(key) == expected.get(key)
        for key in ("canonical_path", "content_sha256", "object_id", "revision")
    )


def _current_noop_fact(index: Any, target: str, expected: Mapping[str, Any]) -> dict[str, Any] | None:
    note = getattr(index, "by_rel", {}).get(target)
    if note is None:
        return None
    metadata = getattr(note, "metadata", {})
    object_id = metadata.get("object_id")
    revision = metadata.get("revision")
    if isinstance(revision, bool):
        return None
    try:
        revision = int(revision)
    except (TypeError, ValueError):
        return None
    if (note.sha256 != expected.get("content_sha256")
            or object_id != expected.get("object_id")
            or revision != expected.get("revision")):
        return None
    return {
        "canonical_path": target,
        "content_sha256": expected.get("content_sha256"),
        "object_id": expected.get("object_id"),
        "revision": expected.get("revision"),
        "verification": "updater_snapshot",
    }


def _reconciled_created_facts(
    index: Any, parent_catalog: Mapping[str, Mapping[str, Any]],
    created: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for item in created:
        target = str(item.get("rel_path") or "")
        expected = parent_catalog.get(target)
        note = getattr(index, "by_rel", {}).get(target)
        if not target or not isinstance(expected, Mapping) or note is None:
            continue
        fact = {
            "canonical_path": target,
            "content_sha256": item.get("expected_sha256"),
            "object_id": item.get("object_id"),
            "revision": item.get("revision"),
        }
        if (item.get("content_verified") is not True
                or item.get("sha256") != expected.get("content_sha256")
                or not _same_output_tuple(expected, fact)
                or note.sha256 != expected.get("content_sha256")):
            continue
        metadata = getattr(note, "metadata", {})
        if (metadata.get("object_id") != expected.get("object_id")
                or isinstance(metadata.get("revision"), bool)
                or str(metadata.get("revision")) != str(expected.get("revision"))):
            continue
        facts[target] = {**fact, "verification": "current_reconcile"}
    return facts


def _append_completion_operation(
    grouped: dict[str, dict[str, Any]], skill: str, rel: str,
    targets: list[str], target_catalog: Mapping[str, Mapping[str, Any]],
) -> None:
    operation = grouped.setdefault(skill, {
        "skill": skill,
        "operation": "apply-plan",
        "created": [],
        "inputs": [],
        "source_outputs": {},
        "issues": [],
    })
    if rel not in operation["inputs"]:
        operation["inputs"].append(rel)
    output_map = operation["source_outputs"].setdefault(rel, [])
    for target in targets:
        if target not in output_map:
            output_map.append(target)
        entry = target_catalog.get(target, {})
        if entry.get("operation") != "noop" and target not in operation["created"]:
            operation["created"].append(target)


def _page_target(page: Mapping[str, Any]) -> str:
    """The page target, resolved in the same order as ``_parent_target_catalog``."""
    return str(page.get("canonical_path") or page.get("rel_path") or page.get("target") or "")


def _page_sources(page: Mapping[str, Any]) -> list[str]:
    sources = page.get("sources") or []
    sources = [sources] if isinstance(sources, str) else sources
    return [rel for rel in sources if isinstance(rel, str) and rel]


def processed_completion_operations(
    cfg: Mapping[str, Any], plan: Mapping[str, Any], plan_path: Path,
    created: list[Mapping[str, Any]], index: Any, *,
    selected_targets: Iterable[str] | None = None,
    rejected_targets: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Build only operations whose exact parent outputs are currently proved.

    Subset apply reaches this after reconcile and before the existing processed
    index writer.  Successful and individually observed parent evidence is
    unioned with the current reconciled writes; receipt inputs then require all
    of their exact required targets.  Plans without receipts use the
    conservative all-required-target rule.

    ``selected_targets`` is the page subset this apply was authorized for.  The
    conservative rule must be scoped to it, not to the whole saved plan: a page
    the human rejected is a deliberate decision, and letting it block the rule
    would leave every approved source unrecorded and re-proposed forever.

    ``rejected_targets`` is emitted as a terminal (output-less) record for that
    page's sources, so a declined source is remembered instead of re-proposed.
    """
    parent_catalog = _parent_target_catalog(plan)
    if not parent_catalog:
        return []
    try:
        evidence = verified_plan_outputs(
            index, cfg, plan_path, sha256_file(plan_path), parent_catalog
        )
    except Exception:
        return []
    if evidence.get("conflicts"):
        return []
    facts: dict[str, dict[str, Any]] = {
        **(evidence.get("observed_failed") or {}),
        **(evidence.get("verified") or {}),
    }
    facts.update(_reconciled_created_facts(index, parent_catalog, created))
    grouped: dict[str, dict[str, Any]] = {}
    receipts = plan.get("generation_receipts")
    if receipts is None:
        selected = {
            str(target) for target in (selected_targets or []) if isinstance(target, str) and target
        }
        required = selected or set(parent_catalog)
        if not required.issubset(facts):
            return []
        rejected = {
            str(target) for target in (rejected_targets or []) if isinstance(target, str) and target
        }
        for page in plan.get("planned_pages", []):
            if not isinstance(page, Mapping):
                continue
            target = _page_target(page)
            if not target or target not in required:
                continue
            skill = str(page.get("skill") or plan.get("primary_skill") or "")
            for rel in _page_sources(page):
                _append_completion_operation(grouped, skill, rel, [target], parent_catalog)
        # Rejected pages carry no output on purpose.  Recording them with an
        # empty target list makes the source terminal ("skipped") rather than
        # permanently unprocessed.
        for page in plan.get("planned_pages", []):
            if not isinstance(page, Mapping):
                continue
            target = _page_target(page)
            if not target or target not in rejected:
                continue
            skill = str(page.get("skill") or plan.get("primary_skill") or "")
            for rel in _page_sources(page):
                _append_completion_operation(grouped, skill, rel, [], parent_catalog)
        return list(grouped.values())
    if (not isinstance(receipts, Mapping) or receipts.get("schema_version") != 1
            or not isinstance(receipts.get("stages"), list)):
        return []
    blocked: set[tuple[str, str]] = set()
    completed: dict[tuple[str, str], list[str]] = {}
    for stage in receipts["stages"]:
        if not isinstance(stage, Mapping):
            continue
        skill = str(stage.get("skill") or plan.get("primary_skill") or "")
        stage_catalog = stage.get("target_catalog")
        raw_outcomes = stage.get("input_outcomes")
        if not isinstance(stage_catalog, Mapping) or not isinstance(raw_outcomes, list):
            continue
        for outcome in raw_outcomes:
            if not isinstance(outcome, Mapping):
                continue
            rel = str(outcome.get("rel") or "")
            key = (skill, rel)
            note = getattr(index, "by_rel", {}).get(rel)
            raw_required = outcome.get("required_targets")
            if (not rel or note is None
                    or not outcome.get("complete") is True
                    or str(outcome.get("outcome") or "") not in {"ok", "zero"}
                    or not isinstance(outcome.get("source_sha256"), str)
                    or not outcome.get("source_sha256")
                    or note.sha256 != outcome.get("source_sha256")
                    or not isinstance(raw_required, list)
                    or any(not isinstance(target, str) or not target for target in raw_required)):
                blocked.add(key)
                continue
            required = list(dict.fromkeys(raw_required))
            for target in required:
                expected = stage_catalog.get(target)
                if not isinstance(expected, Mapping):
                    blocked.add(key)
                    break
                if expected.get("operation") == "noop":
                    fact = _current_noop_fact(index, target, expected)
                else:
                    parent_expected = parent_catalog.get(target)
                    fact = facts.get(target)
                    if (not isinstance(parent_expected, Mapping)
                            or not isinstance(fact, Mapping)
                            or not _same_output_tuple(parent_expected, fact)
                            or not _same_output_tuple(expected, fact)):
                        fact = None
                if fact is None:
                    blocked.add(key)
                    break
            else:
                completed.setdefault(key, []).extend(required)
    for key, targets in completed.items():
        if key in blocked:
            continue
        skill, rel = key
        stage_target_catalog = {
            target: next(
                (stage.get("target_catalog", {}).get(target, {})
                 for stage in receipts["stages"]
                 if isinstance(stage, Mapping)
                 and str(stage.get("skill") or plan.get("primary_skill") or "") == skill
                 and isinstance(stage.get("target_catalog"), Mapping)
                 and target in stage["target_catalog"]),
                {},
            )
            for target in targets
        }
        _append_completion_operation(
            grouped, skill, rel, list(dict.fromkeys(targets)), stage_target_catalog
        )
    return list(grouped.values())


def record_apply_completion(
    cfg: Mapping[str, Any],
    plan: Mapping[str, Any],
    plan_path: Path,
    created: list[Mapping[str, Any]],
    index: Any,
    operations: list[dict[str, Any]],
    subset_context: Mapping[str, Any] | None,
    *,
    writer: Callable[[Any, Mapping[str, Any], list[dict[str, Any]]], None],
) -> list[dict[str, Any]]:
    """Apply 的记账收尾：算出该写进 processed index 的操作，并交给 ``writer`` 落盘。

    非 subset 路径沿用调用方已算好的 ``operations``。subset 路径必须把授权范围
    透传给 :func:`processed_completion_operations`：保守判据若要求整份 plan 的
    产物齐全，一个被拒页就会让所有已批准源永远记不上账，下一轮重复选同一批输入。

    ``writer`` 由调用方注入（runner 传自己的 ``update_processed_index``），
    而不是在这里直接 import ``core.state``：那是测试注入 index 写失败的位置，
    也避免 core 之间的反向依赖。放在 core 而非 runner，是因为 runner 有行数上限。
    """
    if subset_context is None:
        completion: list[dict[str, Any]] = operations
    else:
        completion = processed_completion_operations(
            cfg, plan, plan_path, created, index,
            selected_targets=subset_context.get("selected_targets") or (),
            rejected_targets=subset_context.get("rejected_targets") or (),
        )
    if completion:
        writer(index, cfg, completion)
    return completion


__all__ = [
    "apply_saved_subset", "apply_subset_with_writer", "selected_plan_pages",
    "subset_context_fields", "queue_snapshot_hash", "processed_completion_operations",
    "record_apply_completion",
]
