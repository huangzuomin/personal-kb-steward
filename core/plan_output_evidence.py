"""Read-only evidence for outputs of one saved plan.

This module is deliberately a reader, not another apply path.  It binds the
caller supplied target catalog to the bytes of the saved parent plan, then
looks for immutable run/attempt records which are linked to that exact plan.
Every returned target is re-read from the current vault and its content and
knowledge-object identity are checked again before it is reported.

Callers should pass the full target catalog bound to the saved parent plan.
Subset callers then use the manifest's ``selected_targets`` to identify the
required subset; passing a sibling-only catalog makes that sibling visibly
unbound instead of weakening the parent linkage check.

The subset hash is intentionally small and deterministic.  It binds the
parent run and plan hash to sorted exact target tuples.  A future subset
writer and this reader can therefore share the function without sharing a
writer or trusting a target-name prefix.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .config import plan_dir, runs_dir
from .knowledge_objects import ObjectIdentityError, identity_from_metadata
from .vault import parse_frontmatter


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OPERATIONS = frozenset({"create", "update"})


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _strict_revision(value: Any) -> bool:
    return type(value) is int and value >= 1


def _strict_object_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _canonical_rel(value: Any) -> str | None:
    """Return a safe canonical relative path, without touching the filesystem."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    try:
        path = PurePosixPath(value)
    except (TypeError, ValueError):
        return None
    if (path.is_absolute() or value.startswith("/") or value.startswith("~")
            or value.startswith(".") or ":" in path.parts[0]
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != value):
        return None
    return value


def _safe_resolved(root: Path, rel: str) -> Path | None:
    """Resolve a target and reject links/traversal that change its rel path."""
    try:
        base = Path(root).resolve()
        lexical = base.joinpath(*PurePosixPath(rel).parts)
        resolved = lexical.resolve(strict=False)
        if not resolved.is_relative_to(base):
            return None
        if resolved.relative_to(base).as_posix() != rel:
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _same_resolved_path(value: Any, expected: Path, *, bases: tuple[Path, ...]) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    try:
        candidate = Path(value)
        if "\x00" in str(candidate) or any(part in {".", ".."} for part in candidate.parts):
            return False
        if not candidate.is_absolute():
            # Manifests written by the current writer use absolute paths.  A
            # relative value is accepted only against known public roots so a
            # filename cannot accidentally bind an unrelated private file.
            candidates = [(base / candidate).resolve() for base in bases]
        else:
            candidates = [candidate.resolve()]
        return any(item == expected for item in candidates)
    except (OSError, RuntimeError, ValueError):
        return False


def subset_evidence_hash(
    parent_run_id: str,
    parent_plan_sha256: str,
    selected_targets: Mapping[str, Mapping[str, Any]],
) -> str:
    """Hash ``parent run/hash + sorted exact target tuples``.

    The canonical payload is JSON with sorted keys and no insignificant
    whitespace.  Only the authority tuple is hashed, so evidence references,
    queue IDs, timestamps and execution run IDs cannot change the binding.
    Invalid input raises ``ValueError`` for writer-side callers; the reader
    converts malformed manifest input into a visible conflict instead.
    """
    if not isinstance(parent_run_id, str) or not parent_run_id:
        raise ValueError("parent_run_id must be a non-empty string")
    if not _is_sha256(parent_plan_sha256):
        raise ValueError("parent_plan_sha256 must be a lowercase SHA-256")
    if not isinstance(selected_targets, Mapping) or not selected_targets:
        raise ValueError("selected_targets must be a non-empty mapping")
    tuples: list[list[Any]] = []
    for target, expected in selected_targets.items():
        canonical = _canonical_rel(target)
        if canonical is None or not isinstance(expected, Mapping):
            raise ValueError("selected target tuple is malformed")
        if expected.get("canonical_path") != canonical:
            raise ValueError(f"selected target canonical_path mismatch: {canonical}")
        content_sha256 = expected.get("content_sha256")
        object_id = expected.get("object_id")
        revision = expected.get("revision")
        if not _is_sha256(content_sha256):
            raise ValueError(f"selected target hash is malformed: {canonical}")
        if not _strict_object_id(object_id) or not _strict_revision(revision):
            raise ValueError(f"selected target identity is malformed: {canonical}")
        tuples.append([canonical, content_sha256, object_id, revision])
    tuples.sort(key=lambda item: item[0])
    payload = {
        "parent_plan_sha256": parent_plan_sha256,
        "parent_run_id": parent_run_id,
        "selected_targets": tuples,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _conflict(
    conflicts: list[dict[str, Any]],
    code: str,
    detail: str,
    *,
    manifest_path: Path | None = None,
    target: str | None = None,
    **extra: Any,
) -> None:
    # ``kind`` follows the repository's existing conflict records; ``code``
    # is retained as a readable alias for callers that prefer error-code
    # terminology.
    item: dict[str, Any] = {"kind": code, "code": code, "detail": detail}
    if manifest_path is not None:
        item["manifest_path"] = str(manifest_path)
    if target is not None:
        item["target"] = target
    item.update(extra)
    if item not in conflicts:
        conflicts.append(item)


def _result() -> dict[str, Any]:
    return {
        "verified": {},
        "observed_failed": {},
        "conflicts": [],
        "manifest_paths": [],
    }


def _load_plan(
    index: Any,
    cfg: Mapping[str, Any],
    plan_path: Path,
    supplied_hash: Any,
    target_catalog: Any,
    conflicts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Load and bind the parent plan; all failures become conflicts."""
    if not _is_sha256(supplied_hash):
        _conflict(conflicts, "plan_hash_malformed", "supplied plan_sha256 is not a lowercase SHA-256")
        return None
    try:
        root = Path(getattr(index, "root"))
        root = root.resolve()
        path = Path(plan_path).resolve()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _conflict(conflicts, "plan_path_invalid", f"cannot resolve parent plan: {exc}")
        return None
    # A normal deployment may keep plans in the configured agent-level plan
    # directory rather than inside the vault.  The explicit configured plan
    # root is part of this reader's boundary; arbitrary paths remain refused.
    allowed_plan_roots = [root]
    try:
        allowed_plan_roots.append(plan_dir(dict(cfg)).resolve())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if not path.is_file() or not any(path.is_relative_to(base) for base in allowed_plan_roots):
        _conflict(conflicts, "plan_path_invalid", "parent plan is missing or outside the indexed/configured plan roots")
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _conflict(conflicts, "plan_unreadable", f"cannot read parent plan: {exc}")
        return None
    actual_hash = _sha256(raw)
    if actual_hash != supplied_hash:
        _conflict(conflicts, "plan_hash_mismatch", "saved parent plan bytes do not match supplied plan_sha256", expected=supplied_hash, actual=actual_hash)
    try:
        plan = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _conflict(conflicts, "plan_invalid_json", f"saved parent plan is not valid UTF-8 JSON: {exc}")
        return None
    if not isinstance(plan, dict):
        _conflict(conflicts, "plan_shape_invalid", "saved parent plan must be a JSON object")
        return None
    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        _conflict(conflicts, "plan_run_id_invalid", "saved parent plan has no valid run_id")
        return None
    pages = plan.get("planned_pages")
    if not isinstance(pages, list):
        _conflict(conflicts, "plan_pages_invalid", "saved parent plan planned_pages must be a list")
        return None
    page_by_target: dict[str, dict[str, Any]] = {}
    for page in pages:
        if not isinstance(page, dict):
            _conflict(conflicts, "plan_page_invalid", "saved parent plan contains a non-object page")
            continue
        rel = page.get("rel_path", page.get("canonical_path", page.get("target")))
        canonical = _canonical_rel(rel)
        aliases = [page[key] for key in ("rel_path", "canonical_path", "target") if key in page]
        if canonical is None or any(value != canonical for value in aliases):
            _conflict(conflicts, "plan_target_invalid", "saved page target is not canonical", target=str(rel))
            continue
        if canonical in page_by_target:
            _conflict(conflicts, "plan_duplicate_target", "saved parent plan contains duplicate target", target=canonical)
            continue
        operation = page.get("operation", "create")
        if operation not in _OPERATIONS:
            _conflict(conflicts, "plan_operation_invalid", "saved page operation is not create/update", target=canonical)
            continue
        content = page.get("content")
        content_hash = page.get("content_sha256")
        object_id = page.get("object_id")
        revision = page.get("revision")
        if not isinstance(content, str) or not _is_sha256(content_hash) or _sha256(content.encode("utf-8")) != content_hash:
            _conflict(conflicts, "plan_content_invalid", "saved page content/hash is missing or mismatched", target=canonical)
            continue
        if not _strict_object_id(object_id) or not _strict_revision(revision):
            _conflict(conflicts, "plan_identity_invalid", "saved page object identity/revision is malformed", target=canonical)
            continue
        page_by_target[canonical] = {
            "canonical_path": canonical,
            "content_sha256": content_hash,
            "object_id": object_id,
            "revision": revision,
            "operation": operation,
        }

    if not isinstance(target_catalog, Mapping) or not target_catalog:
        _conflict(conflicts, "target_catalog_invalid", "target_catalog must be a non-empty mapping")
        catalog: dict[str, dict[str, Any]] = {}
    else:
        catalog = {}
        for raw_target, expected in target_catalog.items():
            target = _canonical_rel(raw_target)
            if target is None or not isinstance(expected, Mapping):
                _conflict(conflicts, "target_catalog_entry_invalid", "target catalog target/tuple is malformed", target=str(raw_target))
                continue
            canonical_path = expected.get("canonical_path")
            content_sha256 = expected.get("content_sha256")
            object_id = expected.get("object_id")
            revision = expected.get("revision")
            if canonical_path != target:
                _conflict(conflicts, "target_catalog_path_mismatch", "target catalog canonical_path does not match key", target=target)
                continue
            if not _is_sha256(content_sha256) or not _strict_object_id(object_id) or not _strict_revision(revision):
                _conflict(conflicts, "target_catalog_identity_invalid", "target catalog hash/identity/revision is malformed", target=target)
                continue
            page = page_by_target.get(target)
            if page is None:
                _conflict(conflicts, "target_not_bound", "target catalog target is absent from saved parent plan", target=target)
                continue
            if any(page[key] != expected[key] for key in ("canonical_path", "content_sha256", "object_id", "revision")):
                _conflict(conflicts, "target_catalog_plan_mismatch", "target catalog tuple differs from saved bound page", target=target)
                continue
            if "operation" in expected and expected["operation"] != page["operation"]:
                _conflict(conflicts, "target_catalog_operation_mismatch", "target catalog operation differs from saved bound page", target=target)
                continue
            catalog[target] = {
                "canonical_path": target,
                "content_sha256": content_sha256,
                "object_id": object_id,
                "revision": revision,
                **({"operation": expected["operation"]} if "operation" in expected else {}),
            }
    if actual_hash != supplied_hash:
        # Continue collecting file evidence for auditability, but no output can
        # be authorized while this conflict remains visible.
        pass
    return {
        "root": root,
        "plan_path": path,
        "plan_sha256": supplied_hash,
        "run_id": run_id,
        "pages": page_by_target,
        "catalog": catalog,
        "cfg": cfg,
        "plan_roots": tuple(allowed_plan_roots),
    }


def _manifest_paths(runs_root: Path, parent_run_id: str) -> list[Path]:
    try:
        base = runs_root.resolve()
    except (OSError, RuntimeError):
        return []
    if not base.is_dir():
        return []
    paths: list[Path] = []
    for candidate in sorted(base.rglob("*.json"), key=lambda p: p.as_posix()):
        try:
            resolved = candidate.resolve()
            if not resolved.is_file() or not resolved.is_relative_to(base):
                continue
            relative = resolved.relative_to(base)
            # The canonical run and immutable attempts are the only records in
            # the contract.  Do not read arbitrary JSON under the vault.
            if relative.parts and relative.parts[0] not in {"attempts"} and len(relative.parts) != 1:
                continue
            if relative.name == f"{parent_run_id}.json" or (relative.parts and relative.parts[0] == "attempts") or len(relative.parts) == 1:
                paths.append(resolved)
        except (OSError, RuntimeError, ValueError):
            continue
    return list(dict.fromkeys(paths))


def _manifest_relevant(data: Any, path: Path, context: Mapping[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    parent_path = context["plan_path"]
    parent_run = context["run_id"]
    refs: list[Any] = [data.get("plan_path"), data.get("parent_plan_path")]
    bases = (context["root"], parent_path.parent, path.parent, *context.get("plan_roots", ()))
    path_match = any(_same_resolved_path(ref, parent_path, bases=bases) for ref in refs)
    run_match = data.get("run_id") == parent_run or data.get("parent_run_id") == parent_run
    canonical_name = path.name == f"{parent_run}.json"
    attempt_name = "attempts" in path.parts and parent_run in path.parts
    return path_match or run_match or canonical_name or attempt_name


def _link_kind(
    data: Mapping[str, Any],
    path: Path,
    context: Mapping[str, Any],
    conflicts: list[dict[str, Any]],
) -> str | None:
    bases = (context["root"], context["plan_path"].parent, path.parent, *context.get("plan_roots", ()))
    has_subset = any(key in data for key in ("parent_plan_path", "parent_plan_sha256", "parent_run_id", "subset_hash", "selected_targets"))
    if has_subset:
        required = ("parent_plan_path", "parent_plan_sha256", "parent_run_id", "subset_hash", "selected_targets")
        if any(key not in data for key in required):
            _conflict(conflicts, "subset_linkage_missing", "relevant subset manifest is missing parent linkage", manifest_path=path)
            return None
        if not _same_resolved_path(data.get("parent_plan_path"), context["plan_path"], bases=bases):
            _conflict(conflicts, "subset_parent_path_mismatch", "subset manifest parent_plan_path does not match saved plan", manifest_path=path)
            return None
        if data.get("parent_plan_sha256") != context["plan_sha256"]:
            _conflict(conflicts, "subset_parent_hash_mismatch", "subset manifest parent_plan_sha256 does not match saved plan", manifest_path=path)
            return None
        if data.get("parent_run_id") != context["run_id"]:
            _conflict(conflicts, "subset_parent_run_mismatch", "subset manifest parent_run_id does not match saved plan", manifest_path=path)
            return None
        if not isinstance(data.get("run_id"), str) or not data.get("run_id"):
            _conflict(conflicts, "subset_run_id_invalid", "subset manifest run_id is missing", manifest_path=path)
            return None
        selected = data.get("selected_targets")
        if not isinstance(selected, Mapping) or not selected:
            _conflict(conflicts, "subset_targets_invalid", "subset manifest selected_targets is not a non-empty mapping", manifest_path=path)
            return None
        selected_normalized: dict[str, dict[str, Any]] = {}
        for raw_target, expected in selected.items():
            target = _canonical_rel(raw_target)
            if target is None or not isinstance(expected, Mapping):
                _conflict(conflicts, "subset_target_invalid", "subset selected target tuple is malformed", manifest_path=path, target=str(raw_target))
                continue
            bound = context["catalog"].get(target)
            if bound is None:
                _conflict(conflicts, "subset_target_not_cataloged", "subset selected target is not in requested bound catalog", manifest_path=path, target=target)
                continue
            tuple_types_valid = (
                isinstance(expected.get("canonical_path"), str)
                and _is_sha256(expected.get("content_sha256"))
                and _strict_object_id(expected.get("object_id"))
                and _strict_revision(expected.get("revision"))
            )
            if (not tuple_types_valid or expected.get("canonical_path") != target
                    or any(expected.get(key) != bound.get(key) for key in ("canonical_path", "content_sha256", "object_id"))
                    or expected.get("revision") != bound.get("revision")):
                _conflict(conflicts, "subset_target_tuple_mismatch", "subset selected target does not match bound catalog", manifest_path=path, target=target)
                continue
            selected_normalized[target] = dict(bound)
        try:
            expected_subset_hash = subset_evidence_hash(context["run_id"], context["plan_sha256"], selected_normalized)
        except ValueError as exc:
            _conflict(conflicts, "subset_hash_input_invalid", str(exc), manifest_path=path)
            return None
        if data.get("subset_hash") != expected_subset_hash:
            _conflict(conflicts, "subset_hash_mismatch", "subset_hash does not match parent and selected target tuples", manifest_path=path, expected=expected_subset_hash, actual=data.get("subset_hash"))
            return None
        if not selected_normalized:
            return None
        return "subset"
    required = ("plan_path", "plan_sha256", "run_id")
    if any(key not in data for key in required):
        _conflict(conflicts, "manifest_linkage_missing", "relevant ordinary manifest is missing exact plan linkage", manifest_path=path)
        return None
    if not _same_resolved_path(data.get("plan_path"), context["plan_path"], bases=bases):
        _conflict(conflicts, "manifest_plan_path_mismatch", "ordinary manifest plan_path does not match saved plan", manifest_path=path)
        return None
    if data.get("plan_sha256") != context["plan_sha256"]:
        _conflict(conflicts, "manifest_plan_hash_mismatch", "ordinary manifest plan_sha256 does not match saved plan", manifest_path=path)
        return None
    if data.get("run_id") != context["run_id"]:
        _conflict(conflicts, "manifest_run_mismatch", "ordinary manifest run_id does not match saved plan", manifest_path=path)
        return None
    return "ordinary"


def _item_target(item: Mapping[str, Any]) -> str | None:
    values = [item[key] for key in ("rel_path", "canonical_path", "target") if key in item]
    if not values or any(not isinstance(value, str) for value in values) or len(set(values)) != 1:
        return None
    return _canonical_rel(values[0])


def _evidence_ref(path: Path, data: Mapping[str, Any], kind: str) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "manifest_path": str(path),
        "run_id": data.get("run_id"),
        "status": data.get("status"),
        "kind": kind,
    }
    for key in ("attempt_id", "event_id", "parent_run_id", "subset_hash"):
        if key in data:
            ref[key] = data[key]
    return ref


def _merge_fact(
    store: dict[str, dict[str, Any]],
    conflicts: list[dict[str, Any]],
    target: str,
    fact: dict[str, Any],
    *,
    category: str,
    manifest_path: Path,
) -> None:
    current = store.get(target)
    identity_keys = ("canonical_path", "content_sha256", "object_id", "revision")
    if current is not None and any(current.get(key) != fact.get(key) for key in identity_keys):
        _conflict(conflicts, "conflicting_target_facts", "matching evidence records disagree on target bytes or identity", manifest_path=manifest_path, target=target, category=category)
        # Preserve the first fact and report the later contradiction.  The
        # visible conflict prevents a caller from authorizing through it.
        return
    if current is None:
        store[target] = fact
        return
    evidence = current.setdefault("evidence", [])
    for ref in fact.get("evidence", []):
        if ref not in evidence:
            evidence.append(ref)
    for key, value in (("manifest_paths", fact.get("manifest_paths", [])), ("run_ids", fact.get("run_ids", []))):
        values = current.setdefault(key, [])
        for item in value:
            if item not in values:
                values.append(item)


def _verify_current(index: Any, target: str, expected: Mapping[str, Any]) -> tuple[bool, str]:
    root = Path(getattr(index, "root")).resolve()
    path = _safe_resolved(root, target)
    if path is None:
        return False, "target path escapes indexed root or uses a link"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, f"current target cannot be read: {exc}"
    if _sha256(raw) != expected.get("content_sha256"):
        return False, "current target content hash differs from bound target"
    try:
        text = raw.decode("utf-8-sig")
        metadata, _body = parse_frontmatter(text)
        identity = identity_from_metadata(metadata)
    except (UnicodeDecodeError, ObjectIdentityError, ValueError) as exc:
        return False, f"current target identity metadata is malformed: {exc}"
    if identity != (expected.get("object_id"), expected.get("revision")):
        return False, "current target object identity/revision differs from bound target"
    return True, "current target bytes and identity verified"


def _validate_created_item(
    item: Any,
    *,
    target: str,
    page: Mapping[str, Any],
    manifest_path: Path,
    conflicts: list[dict[str, Any]],
    require_verified: bool = True,
) -> bool:
    if not isinstance(item, Mapping):
        _conflict(conflicts, "manifest_item_invalid", "created output record is not an object", manifest_path=manifest_path, target=target)
        return False
    item_target = _item_target(item)
    if item_target != target:
        _conflict(conflicts, "manifest_item_target_invalid", "created output target is malformed or differs from its key", manifest_path=manifest_path, target=target)
        return False
    if item.get("content_verified") is not True:
        if require_verified:
            _conflict(conflicts, "manifest_item_unverified", "applied output record lacks content_verified=true", manifest_path=manifest_path, target=target)
        return False
    if not _is_sha256(item.get("expected_sha256")) or not _is_sha256(item.get("sha256")):
        _conflict(conflicts, "manifest_item_hash_invalid", "created output hash is missing or malformed", manifest_path=manifest_path, target=target)
        return False
    if item.get("expected_sha256") != page.get("content_sha256") or item.get("sha256") != page.get("content_sha256"):
        _conflict(conflicts, "manifest_item_hash_mismatch", "created output hash differs from bound plan page", manifest_path=manifest_path, target=target)
        return False
    if (not _strict_object_id(item.get("object_id")) or not _strict_revision(item.get("revision"))
            or item.get("object_id") != page.get("object_id")
            or item.get("revision") != page.get("revision")):
        _conflict(conflicts, "manifest_item_identity_mismatch", "created output identity differs from bound plan page", manifest_path=manifest_path, target=target)
        return False
    if "operation" in item and item.get("operation") != page.get("operation"):
        _conflict(conflicts, "manifest_item_operation_mismatch", "created output operation differs from bound plan page", manifest_path=manifest_path, target=target)
        return False
    return True


def _scan_manifest(
    result: dict[str, Any],
    path: Path,
    data: Any,
    context: Mapping[str, Any],
) -> None:
    conflicts = result["conflicts"]
    kind = _link_kind(data, path, context, conflicts) if isinstance(data, Mapping) else None
    if kind is None or not isinstance(data, Mapping):
        return
    status = data.get("status")
    if status not in {"applied", "failed"}:
        _conflict(conflicts, "manifest_status_invalid", "relevant manifest status is neither applied nor failed", manifest_path=path)
        return
    if not isinstance(data.get("created", []), list):
        _conflict(conflicts, "manifest_created_invalid", "relevant manifest created field is not a list", manifest_path=path)
        return
    if status == "applied":
        reconcile = data.get("reconcile")
        if not isinstance(reconcile, Mapping) or reconcile.get("ok") is not True:
            _conflict(conflicts, "applied_reconcile_missing", "applied manifest lacks real reconcile.ok=true", manifest_path=path)
            return
    if kind == "subset":
        selected = data.get("selected_targets")
        selected_targets = set(selected) if isinstance(selected, Mapping) else set()
    else:
        selected_targets = None
    by_target: dict[str, Mapping[str, Any]] = {}
    for item in data.get("created", []):
        if not isinstance(item, Mapping):
            _conflict(conflicts, "manifest_item_invalid", "created output record is not an object", manifest_path=path)
            continue
        target = _item_target(item)
        if target is None:
            _conflict(conflicts, "manifest_item_target_invalid", "created output has no safe canonical target", manifest_path=path)
            continue
        if target in by_target:
            _conflict(conflicts, "manifest_duplicate_target", "relevant manifest contains duplicate target records", manifest_path=path, target=target)
            continue
        by_target[target] = item
        page = context["pages"].get(target)
        if page is None:
            _conflict(conflicts, "manifest_target_not_in_plan", "relevant manifest output target is absent from saved parent plan", manifest_path=path, target=target)
            continue
        if selected_targets is not None and target not in selected_targets:
            _conflict(conflicts, "subset_output_not_selected", "subset manifest created an unselected target", manifest_path=path, target=target)
            continue
        _validate_created_item(item, target=target, page=page, manifest_path=path, conflicts=conflicts, require_verified=status == "applied")
    if status == "applied":
        required_targets = selected_targets if selected_targets is not None else set(context["catalog"])
        for target in required_targets:
            if target in context["catalog"] and target not in by_target:
                _conflict(conflicts, "manifest_target_missing", "applied manifest has no created evidence for requested target", manifest_path=path, target=target)
    if status == "failed" and "write_started" in data and not isinstance(data.get("write_started"), bool):
        _conflict(conflicts, "manifest_write_started_invalid", "failed manifest write_started must be a boolean", manifest_path=path)
        return
    if status == "failed" and data.get("write_started") is not True:
        # A preflight failure is a valid diagnostic, but it cannot establish a
        # mutation.  Do not turn the absence of write_started into a conflict.
        return
    for target, expected in context["catalog"].items():
        if selected_targets is not None and target not in selected_targets:
            continue
        item = by_target.get(target)
        if item is None:
            continue
        if not _validate_created_item(item, target=target, page=context["pages"][target], manifest_path=path, conflicts=conflicts, require_verified=status == "applied"):
            continue
        ok, reason = _verify_current(context["index"], target, expected)
        if not ok:
            _conflict(conflicts, "current_target_unverified", reason, manifest_path=path, target=target)
            continue
        ref = _evidence_ref(path, data, kind)
        fact = {
            "canonical_path": target,
            "content_sha256": expected["content_sha256"],
            "object_id": expected["object_id"],
            "revision": expected["revision"],
            "manifest_path": str(path),
            "run_id": data.get("run_id"),
            "evidence": [ref],
            "manifest_paths": [str(path)],
            "run_ids": [data.get("run_id")],
        }
        if status == "applied":
            _merge_fact(result["verified"], conflicts, target, fact, category="verified", manifest_path=path)
        else:
            _merge_fact(result["observed_failed"], conflicts, target, fact, category="observed_failed", manifest_path=path)


def verified_plan_outputs(
    index: Any,
    cfg: Mapping[str, Any],
    plan_path: Path,
    plan_sha256: str,
    target_catalog: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Read and verify outputs linked to one exact saved parent plan.

    The return value always has the four documented keys.  Malformed parent
    input, linkage, or evidence is represented in ``conflicts``; callers must
    fail closed whenever that list is non-empty.  This function never writes
    to the vault, queue, plan, run records, or receipts.  ``target_catalog``
    should contain every bound page in the saved parent plan, including pages
    outside a future subset; the subset manifest selects the per-target rows
    needed by its execution.
    """
    result = _result()
    try:
        root = Path(getattr(index, "root")).resolve()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _conflict(result["conflicts"], "index_invalid", f"index has no usable root: {exc}")
        return result
    context = _load_plan(index, cfg, Path(plan_path), plan_sha256, target_catalog, result["conflicts"])
    if context is None:
        return result
    context = {**context, "index": index, "root": root}
    try:
        run_root = Path(runs_dir(dict(cfg))).resolve()
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _conflict(result["conflicts"], "runs_path_invalid", f"cannot resolve run evidence root: {exc}")
        return result
    for path in _manifest_paths(run_root, context["run_id"]):
        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # Only canonical/attempt paths bearing this parent run are known
            # relevant when JSON itself cannot reveal its linkage.
            if path.name == f"{context['run_id']}.json" or context["run_id"] in path.parts:
                result["manifest_paths"].append(str(path))
                _conflict(result["conflicts"], "manifest_unreadable", f"relevant run evidence cannot be parsed: {exc}", manifest_path=path)
            continue
        if not _manifest_relevant(data, path, context):
            continue
        result["manifest_paths"].append(str(path))
        _scan_manifest(result, path, data, context)
    result["manifest_paths"] = list(dict.fromkeys(result["manifest_paths"]))
    return result


__all__ = ["subset_evidence_hash", "verified_plan_outputs"]
