"""Pure page-scoped review preparation for already-bound plans.

This module deliberately stops before queue mutation or apply.  It turns a
saved, object-bound plan into exact page review records and selects only pages
whose queue record matches the current plan's run, target, identity, operation
and content hash.  Queue UUIDs and statuses remain owned by the review queue;
this helper never creates IDs, changes records, reads the vault, or writes a
plan.

The optional ``applied_outputs`` argument to :func:`select_page_review` is a
caller-validated mapping of canonical target to::

    {
        "canonical_path": target,
        "content_sha256": <actual persisted output hash>,
        "object_id": <actual persisted object id>,
        "revision": <actual persisted revision>,
    }

The outer integrator is responsible for obtaining and validating those actual
output facts.  This helper only compares the supplied values with the planned
page record; it performs no filesystem lookup.  Without a matching entry an
``applied`` sibling is untrusted and cannot satisfy a selected page's link.
"""
from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .vault import extract_wikilinks, parse_frontmatter, wiki_stem


PAGE_REVIEW_SCHEMA_VERSION = 1
PAGE_REVIEW_TYPE = "planned_page_review"
PAGE_REVIEW_SCOPE = "page"
PAGE_REVIEW_SELECTION_TYPE = "page_review_selection"
_OPERATIONS = frozenset({"create", "update"})
_TERMINAL_STATUSES = frozenset({"approved", "applied"})
_STATUSES = frozenset({"pending", "approved", "rejected", "applied"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class PageReviewScopeError(ValueError):
    """The saved plan is not safe to turn into page review records."""


def _error(message: str) -> None:
    raise PageReviewScopeError(message)


def _run_id(plan: Mapping[str, Any]) -> str:
    value = plan.get("run_id")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _error("plan.run_id 必须是非空、精确的字符串")
    return value


def _target(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _error(f"{where} 必须是非空、无首尾空白的相对路径")
    path = PurePosixPath(value)
    if ("\\" in value or path.is_absolute() or path.as_posix() != value
            or value.endswith("/") or ".." in path.parts
            or ":" in value or "\x00" in value):
        _error(f"{where} 不是规范的 vault 相对路径：{value!r}")
    return value


def _hash(value: Any, where: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _error(f"{where} 必须是 64 位小写 SHA-256")
    return value


def _positive_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        _error(f"{where} 必须是正整数")
    return value


def _nonnegative_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        _error(f"{where} 必须是非负精确整数")
    return value


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _review_key(run_id: str, target: str, content_sha256: str) -> str:
    """Stable key formula; queue ``id`` remains a separate UUID authority."""
    value = f"{run_id}\x00{target}\x00{content_sha256}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _page_records_input(plan: Mapping[str, Any]) -> tuple[str, list[Any]]:
    if not isinstance(plan, Mapping):
        _error("plan 必须是对象")
    run_id = _run_id(plan)
    pages = plan.get("planned_pages")
    if not isinstance(pages, list):
        _error("plan.planned_pages 必须是数组")
    return run_id, pages


def _record_for_page(run_id: str, page: Mapping[str, Any], index: int) -> dict[str, Any]:
    where = f"planned_pages[{index}]"
    if not isinstance(page, Mapping):
        _error(f"{where} 必须是对象")

    rel_path = _target(page.get("rel_path"), f"{where}.rel_path")
    canonical = _target(page.get("canonical_path"), f"{where}.canonical_path")
    if canonical != rel_path:
        _error(f"{where} 的 canonical_path 与 rel_path 不一致")
    if "target" in page and _target(page.get("target"), f"{where}.target") != canonical:
        _error(f"{where} 的 target 与 canonical_path 不一致")

    operation = page.get("operation")
    if not isinstance(operation, str) or operation not in _OPERATIONS:
        _error(f"{where}.operation 未知或缺失：{operation!r}")
    content = page.get("content")
    if not isinstance(content, str):
        _error(f"{where}.content 必须是字符串")
    actual_hash = _content_hash(content)
    declared_hash = _hash(page.get("content_sha256"), f"{where}.content_sha256")
    if declared_hash != actual_hash:
        _error(f"{where}.content_sha256 与内容不一致：拒绝生成审核范围")

    object_id = page.get("object_id")
    if not isinstance(object_id, str) or not object_id.strip() or object_id != object_id.strip():
        _error(f"{where}.object_id 必须存在；B3a 不为未绑定页面发明身份")
    revision = _positive_int(page.get("revision"), f"{where}.revision")

    base_revision = page.get("base_revision")
    base_sha256 = page.get("base_sha256")
    base_object_id = page.get("base_object_id")
    if operation == "update":
        base_revision = _nonnegative_int(base_revision, f"{where}.base_revision")
        if base_revision >= revision:
            _error(f"{where}.base_revision 必须小于 revision")
        if base_sha256 is not None:
            base_sha256 = _hash(base_sha256, f"{where}.base_sha256")
        if base_object_id is not None and (
                not isinstance(base_object_id, str)
                or not base_object_id.strip()
                or base_object_id != base_object_id.strip()):
            _error(f"{where}.base_object_id 必须是非空字符串")
    else:
        if (base_revision is not None or base_sha256 is not None
                or base_object_id is not None):
            _error(f"{where}.create 不得携带 update base 字段")

    key = _review_key(run_id, canonical, actual_hash)
    return {
        "schema_version": PAGE_REVIEW_SCHEMA_VERSION,
        "type": PAGE_REVIEW_TYPE,
        "scope": PAGE_REVIEW_SCOPE,
        "run_id": run_id,
        "review_key": key,
        "target": canonical,
        "rel_path": canonical,
        "canonical_path": canonical,
        "operation": operation,
        "object_id": object_id,
        "revision": revision,
        "base_revision": base_revision,
        "base_sha256": base_sha256,
        "base_object_id": base_object_id,
        "content_sha256": actual_hash,
    }


def page_review_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Build exact page review records from an object-bound saved plan.

    The function is pure and raises :class:`PageReviewScopeError` for any
    malformed or ambiguous plan.  It does not add queue IDs or statuses.
    """
    run_id, pages = _page_records_input(plan)
    records: list[dict[str, Any]] = []
    by_target: dict[str, str] = {}
    by_object: dict[str, str] = {}
    for index, page in enumerate(pages):
        record = _record_for_page(run_id, page, index)
        target = record["target"]
        object_id = record["object_id"]
        if target in by_target:
            _error(f"重复或冲突的 page target：{target}")
        if object_id in by_object:
            _error(f"object_id 被多个 page target 使用：{object_id}")
        by_target[target] = object_id
        by_object[object_id] = target
        records.append(record)
    return records


def _status(item: Mapping[str, Any]) -> str:
    value = item.get("status", "pending")
    return value if isinstance(value, str) else "__invalid__"


_AUTHORITY_FIELDS = (
    "schema_version", "type", "scope", "run_id", "review_key", "target",
    "rel_path", "canonical_path", "operation", "object_id", "revision",
    "base_revision", "base_sha256", "base_object_id", "content_sha256",
)


def _record_matches(item: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for field in _AUTHORITY_FIELDS:
        expected_value = expected.get(field)
        actual_value = item.get(field)
        # Python considers True equal to 1; review authority fields cannot.
        # JSON scalar type is part of the saved identity contract.
        if type(actual_value) is not type(expected_value) or actual_value != expected_value:
            return False
    return True


def _conflict(kind: str, **details: Any) -> dict[str, Any]:
    return {"kind": kind, **details}


def _queue_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("id")
    return value if isinstance(value, str) and value.strip() else None


def _applied_output_validation(
    applied_outputs: Any,
    records_by_target: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if applied_outputs is None:
        return {}, []
    if not isinstance(applied_outputs, Mapping):
        return {}, [_conflict("invalid_applied_outputs", reason="必须是 target -> output 对象映射")]
    verified: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for raw_target, value in applied_outputs.items():
        try:
            target = _target(raw_target, "applied_outputs target")
        except PageReviewScopeError as exc:
            conflicts.append(_conflict("invalid_applied_output_target",
                                       target=raw_target, reason=str(exc)))
            continue
        expected = records_by_target.get(target)
        if expected is None:
            conflicts.append(_conflict("unknown_applied_output", target=target))
            continue
        if not isinstance(value, Mapping):
            conflicts.append(_conflict("invalid_applied_output", target=target,
                                       reason="output 必须是对象"))
            continue
        try:
            actual_path = _target(value.get("canonical_path"),
                                  f"applied_outputs[{target}].canonical_path")
            actual_hash = _hash(value.get("content_sha256"),
                                f"applied_outputs[{target}].content_sha256")
            actual_object = value.get("object_id")
            actual_revision = _positive_int(value.get("revision"),
                                            f"applied_outputs[{target}].revision")
        except PageReviewScopeError as exc:
            conflicts.append(_conflict("invalid_applied_output", target=target,
                                       reason=str(exc)))
            continue
        if (actual_path != target or actual_hash != expected["content_sha256"]
                or actual_object != expected["object_id"]
                or actual_revision != expected["revision"]):
            conflicts.append(_conflict(
                "applied_output_mismatch", target=target,
                expected={key: expected[key] for key in
                          ("canonical_path", "content_sha256", "object_id", "revision")},
                actual={"canonical_path": actual_path,
                        "content_sha256": actual_hash,
                        "object_id": actual_object,
                        "revision": actual_revision}))
            continue
        verified[target] = {
            "canonical_path": actual_path,
            "content_sha256": actual_hash,
            "object_id": actual_object,
            "revision": actual_revision,
        }
    return verified, conflicts


def _link_maps(records: list[dict[str, Any]], pages: list[Mapping[str, Any]]) -> tuple[
        dict[str, str], dict[str, str], dict[str, str], set[str], set[str]]:
    exact = {record["target"]: record["target"] for record in records}
    stems: dict[str, list[str]] = {}
    titles: dict[str, list[str]] = {}
    for record, page in zip(records, pages):
        stems.setdefault(wiki_stem(record["target"]).lower(), []).append(record["target"])
        content = page.get("content") if isinstance(page, Mapping) else None
        if isinstance(content, str):
            metadata, _ = parse_frontmatter(content)
            title = metadata.get("title")
            if isinstance(title, str) and title.strip():
                titles.setdefault(title.strip().lower(), []).append(record["target"])
    ambiguous_stems = {key for key, values in stems.items() if len(set(values)) > 1}
    ambiguous_titles = {key for key, values in titles.items() if len(set(values)) > 1}
    unique_stems = {key: values[0] for key, values in stems.items() if key not in ambiguous_stems}
    unique_titles = {key: values[0] for key, values in titles.items() if key not in ambiguous_titles}
    return exact, unique_stems, unique_titles, ambiguous_stems, ambiguous_titles


def _resolve_planned_link(
    raw: str,
    exact: Mapping[str, str],
    stems: Mapping[str, str],
    titles: Mapping[str, str],
    ambiguous_stems: set[str],
    ambiguous_titles: set[str],
) -> tuple[str | None, str | None]:
    clean = raw.strip().replace("\\", "/")
    if clean in exact:
        return exact[clean], None
    if clean.startswith("/") or ".." in clean.split("/") or ":" in clean:
        return None, None
    stem = wiki_stem(clean).lower()
    if stem in ambiguous_stems:
        return None, "ambiguous_stem"
    if stem in stems:
        return stems[stem], None
    title = clean.lower()
    if title in ambiguous_titles:
        return None, "ambiguous_title"
    return titles.get(title), None


def _dependency_blockers(
    selected_targets: list[str],
    pages_by_target: Mapping[str, Mapping[str, Any]],
    records_by_target: Mapping[str, Mapping[str, Any]],
    target_states: Mapping[str, str],
    verified_applied: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records = list(records_by_target.values())
    pages = [pages_by_target[record["target"]] for record in records]
    exact, stems, titles, ambiguous_stems, ambiguous_titles = _link_maps(records, pages)
    blockers: list[dict[str, Any]] = []
    for source_target in selected_targets:
        page = pages_by_target[source_target]
        content = page.get("content")
        if not isinstance(content, str):
            continue
        for raw_link in extract_wikilinks(content):
            linked, ambiguity = _resolve_planned_link(
                raw_link, exact, stems, titles, ambiguous_stems, ambiguous_titles)
            if linked is None:
                if ambiguity is not None:
                    blockers.append(_conflict(
                        "ambiguous_planned_sibling_link", source_target=source_target,
                        link=raw_link, ambiguity=ambiguity,
                        reason="planned sibling link has multiple stem/title targets"))
                continue
            if linked == source_target:
                continue
            state = target_states.get(linked, "pending")
            if state in {"pending", "rejected", "conflict"}:
                blockers.append(_conflict(
                    "future_or_rejected_sibling_link", source_target=source_target,
                    linked_target=linked, linked_state=state, link=raw_link,
                    reason="selected page links to a pending/rejected/conflicting sibling"))
            elif state == "applied" and linked not in verified_applied:
                blockers.append(_conflict(
                    "unverified_applied_sibling_link", source_target=source_target,
                    linked_target=linked, link=raw_link,
                    reason="queue status alone cannot verify an applied sibling output"))
    return blockers


def select_page_review(
    plan: dict[str, Any],
    queue_items: list[dict[str, Any]],
    applied_outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Select exact page approvals without mutating the plan or queue.

    ``applied_outputs`` is optional and defaults to trusting nothing.  A
    supplied entry must contain the canonical target, actual content hash,
    object ID and revision, all equal to the plan record.  The result includes
    selected pages and hashes for the integrator, while pending/rejected/
    applied targets, blockers and conflicts remain visible to the caller.
    """
    records = page_review_records(plan)
    run_id = _run_id(plan)
    if not isinstance(queue_items, list):
        _error("queue_items 必须是数组")
    pages = plan["planned_pages"]
    records_by_target = {record["target"]: record for record in records}
    pages_by_target = {record["target"]: page for record, page in zip(records, pages)}
    conflicts: list[dict[str, Any]] = []
    run_blockers: list[dict[str, Any]] = []
    legacy_aggregate: list[dict[str, Any]] = []
    scoped: dict[str, list[dict[str, Any]]] = {target: [] for target in records_by_target}
    valid_scoped_records = 0
    queue_id_indexes: dict[str, list[int]] = {}
    for index, raw_item in enumerate(queue_items):
        if isinstance(raw_item, Mapping):
            item_id = _queue_id(raw_item)
            if item_id is not None:
                queue_id_indexes.setdefault(item_id, []).append(index)
    duplicate_queue_ids = {
        item_id: indexes for item_id, indexes in queue_id_indexes.items()
        if len(indexes) > 1
    }

    for index, raw_item in enumerate(queue_items):
        if not isinstance(raw_item, Mapping):
            conflicts.append(_conflict("malformed_queue_record", index=index,
                                       reason="queue record 必须是对象"))
            continue
        item = dict(raw_item)
        item_run = item.get("run_id")
        item_type = item.get("type")
        item_target = item.get("target")
        known_target = item_target if isinstance(item_target, str) and item_target in records_by_target else None

        # Queue history belongs to its own run. A foreign record, even when it
        # names the same target, cannot authorize or block this run. Duplicate
        # queue IDs are checked below because a caller updating by ID must not
        # accidentally touch a foreign-run item.
        if item_run != run_id:
            continue

        status = _status(item)
        if item_type != PAGE_REVIEW_TYPE or item.get("scope") != PAGE_REVIEW_SCOPE:
            if item_type == "planned_pages_require_review":
                legacy_aggregate.append(item)
            if status not in _TERMINAL_STATUSES:
                run_blockers.append(_conflict(
                    "non_page_run_blocker", index=index, id=_queue_id(item),
                    record_type=item_type, status=status))
            continue

        if known_target is None:
            conflicts.append(_conflict("unknown_page_target", index=index,
                                       target=item_target, run_id=run_id))
            if status not in _TERMINAL_STATUSES:
                run_blockers.append(_conflict("unknown_page_scope_record", index=index,
                                              target=item_target, status=status))
            continue

        expected = records_by_target[known_target]
        if not _record_matches(item, expected):
            conflicts.append(_conflict("stale_or_forged_page_record", index=index,
                                       target=known_target,
                                       reason="record does not exactly match run/target/identity/hash",
                                       expected=dict(expected)))
            continue
        if _queue_id(item) is None:
            conflicts.append(_conflict("page_record_missing_queue_id", index=index,
                                       target=known_target))
            continue
        if status not in _STATUSES:
            conflicts.append(_conflict("invalid_page_record_status", index=index,
                                       target=known_target, status=status))
            continue
        item_id = _queue_id(item)
        if item_id in duplicate_queue_ids:
            conflicts.append(_conflict(
                "duplicate_queue_id", index=index, target=known_target,
                queue_id=item_id, indexes=duplicate_queue_ids[item_id],
                reason="queue UUID must identify one scoped record across all runs"))
            continue
        valid_scoped_records += 1
        scoped[known_target].append(item)

    verified_applied, applied_conflicts = _applied_output_validation(
        applied_outputs, records_by_target)
    conflicts.extend(applied_conflicts)

    target_states: dict[str, str] = {}
    selected_targets: list[str] = []
    pending_targets: list[str] = []
    rejected_targets: list[str] = []
    applied_targets: list[str] = []
    selected_review_ids: list[str] = []
    for record in records:
        target = record["target"]
        matches = scoped[target]
        if len(matches) != 1:
            if len(matches) > 1:
                conflicts.append(_conflict("duplicate_page_scope_records",
                                           target=target,
                                           record_ids=[_queue_id(item) for item in matches]))
            target_states[target] = "conflict" if len(matches) > 1 else "pending"
            if not matches:
                pending_targets.append(target)
            continue
        item = matches[0]
        status = _status(item)
        target_states[target] = status if status in _STATUSES else "conflict"
        if status == "approved":
            selected_targets.append(target)
            selected_review_ids.append(_queue_id(item) or "")
        elif status == "pending":
            pending_targets.append(target)
        elif status == "rejected":
            rejected_targets.append(target)
        elif status == "applied":
            applied_targets.append(target)

    # A target with a conflicting record is never silently treated as pending
    # or approved, even if another duplicate happens to be approved.
    conflict_targets = {entry.get("target") for entry in conflicts
                        if isinstance(entry.get("target"), str)}
    for target in conflict_targets:
        if target in records_by_target:
            target_states[target] = "conflict"
            if target in selected_targets:
                selected_targets.remove(target)
            if target not in pending_targets and target not in rejected_targets and target not in applied_targets:
                pending_targets.append(target)
            selected_review_ids = [
                item_id for item_id in selected_review_ids
                if item_id not in {_queue_id(item) for item in scoped[target]}
            ]

    # Legacy aggregate records can block an entire run while never becoming
    # page authority. An all-terminal aggregate is reported but does not
    # authorize any page.
    legacy_run_only = bool(legacy_aggregate) and valid_scoped_records == 0
    verified_applied_targets = set(verified_applied)
    dependency_blockers = _dependency_blockers(
        selected_targets, pages_by_target, records_by_target, target_states,
        verified_applied)

    selected_pages = [copy.deepcopy(pages_by_target[target]) for target in selected_targets]
    candidate_authorized_targets = {
        target: {
            "target": target,
            "content_sha256": records_by_target[target]["content_sha256"],
            "object_id": records_by_target[target]["object_id"],
            "revision": records_by_target[target]["revision"],
        }
        for target in selected_targets
    }
    all_page_targets = set(records_by_target)
    all_authorized = bool(all_page_targets) and all(
        target_states.get(target) == "approved"
        or (target_states.get(target) == "applied" and target in verified_applied_targets)
        for target in all_page_targets
    ) and not run_blockers and not conflicts and not dependency_blockers
    all_approved = bool(all_page_targets) and all(
        target_states.get(target) == "approved" for target in all_page_targets
    )
    blocking_conflicts = bool(conflicts)
    can_apply_subset = bool(selected_targets) and not run_blockers \
        and not blocking_conflicts and not dependency_blockers
    can_apply_all = all_approved and can_apply_subset
    authorized_targets = candidate_authorized_targets if can_apply_subset else {}

    return {
        "schema_version": PAGE_REVIEW_SCHEMA_VERSION,
        "type": PAGE_REVIEW_SELECTION_TYPE,
        "scope": PAGE_REVIEW_SCOPE,
        "run_id": run_id,
        "mode": "legacy_run" if legacy_run_only else "page_subset",
        "records": copy.deepcopy(records),
        "selected_pages": selected_pages,
        "selected_targets": list(selected_targets),
        "authorized_targets": authorized_targets,
        "authorized_target_hashes": {
            target: details["content_sha256"]
            for target, details in authorized_targets.items()
        },
        "selected_review_ids": selected_review_ids,
        "pending_targets": pending_targets,
        "rejected_targets": rejected_targets,
        "applied_targets": applied_targets,
        "verified_applied_targets": sorted(verified_applied_targets),
        "target_states": target_states,
        "run_blockers": run_blockers,
        "conflicts": conflicts,
        "dependency_blockers": dependency_blockers,
        "legacy_aggregate_records": [copy.deepcopy(item) for item in legacy_aggregate],
        "legacy_run_only": legacy_run_only,
        "all_pages_authorized": all_authorized,
        "can_apply_subset": can_apply_subset,
        "can_apply_all": can_apply_all,
    }


__all__ = [
    "PAGE_REVIEW_SCHEMA_VERSION",
    "PAGE_REVIEW_SCOPE",
    "PAGE_REVIEW_SELECTION_TYPE",
    "PAGE_REVIEW_TYPE",
    "PageReviewScopeError",
    "page_review_records",
    "select_page_review",
]
