"""Bind stable identities at the plan boundary and validate before mutation.

No LLM/provider calls or filesystem writes are performed here. In particular,
apply never creates an ID or silently repairs the plan a human already reviewed.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from .config import sha256_file, sha256_text
from .knowledge_objects import ObjectIdentityError, identity_from_metadata, is_knowledge_path, new_object_id
from .vault import Note, VaultIndex, parse_frontmatter, read_note


OBJECT_SCHEMA_VERSION = 1
_HEADER = re.compile(r"\A(?:\ufeff)?---[^\S\r\n]*\r?\n(.*?)^---[^\S\r\n]*(?:\r?\n|\Z)", re.M | re.S)
_ID_FIELDS = re.compile(r"^(object_id|revision):[^\r\n]*(?:\r?\n|\Z)", re.M)


def _metadata(content: str) -> dict[str, Any]:
    """Validate our flat identity keys without rewriting unrelated YAML fields."""
    match = _HEADER.match(content)
    if match:
        counts = Counter(_ID_FIELDS.findall(match.group(1)))
        if any(count > 1 for count in counts.values()):
            raise ObjectIdentityError("Duplicate object_id/revision frontmatter keys")
    return parse_frontmatter(content.lstrip("\ufeff"))[0]


def _stamp(content: str, object_id: str, revision: int) -> str:
    match = _HEADER.match(content)
    if not match:
        raise ObjectIdentityError("Generated knowledge pages require a frontmatter block")
    # Change only the two owned top-level fields; preserve the body, custom keys,
    # ordering, comments and newline convention of the renderer's output.
    newline = "\r\n" if "\r\n" in match.group(0) else "\n"
    fields = f"object_id: {object_id}{newline}revision: {revision}{newline}"
    header = _ID_FIELDS.sub("", match.group(1))
    return content[:match.start(1)] + fields + header + content[match.end(1):]


def _current(index: VaultIndex, rel: str) -> Note | None:
    if "\\" in rel or ".." in PurePosixPath(rel).parts or PurePosixPath(rel).as_posix() != rel:
        raise ObjectIdentityError(f"Noncanonical object path: {rel}")
    target = (index.root / rel).resolve()
    if not target.is_relative_to(index.root.resolve()):
        raise ObjectIdentityError(f"Object target escapes the vault: {rel}")
    if target.relative_to(index.root.resolve()).as_posix() != rel:
        raise ObjectIdentityError(f"Object writes through symlinks are not supported: {rel}")
    return read_note(target, index.root.resolve()) if target.is_file() else None


def update_base(note: Note) -> dict[str, Any]:
    """Capture from the exact Note snapshot used to generate an update, not save-time IO."""
    identity = identity_from_metadata(note.metadata)
    return {"base_sha256": note.sha256, "base_revision": identity[1] if identity else None,
            "base_object_id": identity[0] if identity else None}


def _require_generation_base(page: dict[str, Any], current: Note) -> None:
    expected = update_base(current)
    if not all(key in page for key in expected):
        raise ObjectIdentityError(f"Update is missing its generation-time base: {current.rel}; regenerate the proposal")
    if (not isinstance(page["base_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", page["base_sha256"])
            or page["base_revision"] is not None and type(page["base_revision"]) is not int
            or any(page[key] != value for key, value in expected.items())):
        raise ObjectIdentityError(f"Generation base revision/hash conflict: {current.rel}; regenerate the proposal")


def bind_plan_objects(index: VaultIndex, plan: dict[str, Any]) -> None:
    """Finalize plan identities once, before serializing it for human review.

Legacy pages are adopted only when an explicit update is planned. Re-saving an
already bound plan never increments revisions, changes IDs, or re-bases hashes.
    """
    if plan.get("primary_skill") == "kb-reconcile" or "reconcile" in plan:
        from .reconcile import validate_reconcile_plan
        validate_reconcile_plan(index, plan)
    version = plan.get("object_schema_version")
    if version is not None:
        if type(version) is not int or version != OBJECT_SCHEMA_VERSION:
            raise ObjectIdentityError(f"Unsupported object_schema_version: {version}")
        return
    pages = copy.deepcopy(plan.get("planned_pages", []))
    if any(is_knowledge_path(str(page.get("rel_path") or "")) for page in pages):
        index.objects.require_valid()
    for page in pages:
        rel = str(page.get("rel_path") or "")
        if not is_knowledge_path(rel):
            continue
        content = page.get("content")
        if not isinstance(content, str):
            raise ObjectIdentityError(f"Missing content for {rel}")
        meta = _metadata(content)
        if not isinstance(meta.get("type"), str) or not meta["type"].strip():
            raise ObjectIdentityError(f"Missing knowledge object type: {rel}")
        operation = page.get("operation", "create")
        if operation not in {"create", "update"}:
            raise ObjectIdentityError(f"Unsupported object operation: {operation}")
        target_note = _current(index, rel)
        current = target_note if operation == "update" else None
        if operation == "update" and current is None:
            raise ObjectIdentityError(f"Missing update target: {rel}")
        if current:
            _require_generation_base(page, current)
        old = identity_from_metadata(current.metadata) if current else None
        object_id = old[0] if old else new_object_id()
        revision = old[1] + 1 if old else 1
        content = _stamp(content, object_id, revision)
        if identity_from_metadata(_metadata(content)) != (object_id, revision):
            raise ObjectIdentityError(f"Could not safely stamp identity fields: {rel}")
        page.update(object_id=object_id, revision=revision, canonical_path=rel,
                    content=content, content_sha256=sha256_text(content))
    plan["planned_pages"] = pages
    plan["object_schema_version"] = OBJECT_SCHEMA_VERSION


def validate_object_writes(index: VaultIndex, pages: list[dict[str, Any]], *, schema_version: Any = None) -> None:
    """Fail closed for collisions, identity loss, and stale bound update plans.

Unversioned legacy plans remain readable. They cannot strip/reassign an existing
object's ID. This is preflight validation, not a multi-file atomic transaction.
    """
    if schema_version is not None and (type(schema_version) is not int or schema_version != OBJECT_SCHEMA_VERSION):
        raise ObjectIdentityError(f"Unsupported object_schema_version: {schema_version}")
    if any(is_knowledge_path(str(page.get("rel_path") or "")) for page in pages):
        index.objects.require_valid()
    seen: dict[str, str] = {}
    for page in pages:
        if page.get("skill") == "kb-reconcile":
            from .reconcile import validate_reconcile_page
            validate_reconcile_page(index, page)
        rel = str(page.get("rel_path") or "")
        if not is_knowledge_path(rel):
            continue
        meta = _metadata(page["content"])
        proposed = identity_from_metadata(meta)
        current = _current(index, rel)
        old = identity_from_metadata(current.metadata) if current else None
        operation = page.get("operation", "create")
        if operation not in {"create", "update"}:
            raise ObjectIdentityError(f"Unsupported object operation: {operation}")
        if schema_version is not None and proposed is None:
            raise ObjectIdentityError(f"Bound plan has no object identity: {rel}")
        if old and proposed is None:
            raise ObjectIdentityError(f"Update would remove object identity: {rel}")
        if proposed is None:
            continue
        object_id, revision = proposed
        if not isinstance(meta.get("type"), str) or not meta["type"].strip():
            raise ObjectIdentityError(f"Missing knowledge object type: {rel}")
        if object_id in seen:
            raise ObjectIdentityError(f"Duplicate planned object_id {object_id}: {seen[object_id]}, {rel}")
        seen[object_id] = rel
        registered = index.objects.get(object_id)
        if registered and registered.canonical_path != rel:
            raise ObjectIdentityError(f"object_id {object_id} already belongs to {registered.canonical_path}")
        if old and (object_id != old[0] or revision != old[1] + 1):
            raise ObjectIdentityError(f"Identity/revision conflict for {rel}; regenerate the plan")
        if not old and revision != 1:
            raise ObjectIdentityError(f"New objects start at revision 1: {rel}")
        if schema_version is not None:
            if type(page.get("revision")) is not int or (page.get("object_id"), page.get("revision"), page.get("canonical_path")) != (object_id, revision, rel):
                raise ObjectIdentityError(f"Plan metadata disagrees with frontmatter: {rel}")
            if operation == "update":
                expected_revision = old[1] if old else None
                if current is None or page.get("base_sha256") != current.sha256 or page.get("base_revision") != expected_revision or (old and type(page.get("base_revision")) is not int):
                    raise ObjectIdentityError(f"Base revision/hash conflict for {rel}; regenerate the plan")


def object_manifest_fields(page: dict[str, Any]) -> dict[str, Any]:
    if not is_knowledge_path(str(page.get("rel_path") or "")):
        return {}
    identity = identity_from_metadata(_metadata(page["content"]))
    if identity is None:
        return {}
    result = {"object_id": identity[0], "revision": identity[1], "canonical_path": page["rel_path"]}
    state = _metadata(page["content"]).get("reconcile_state", {})
    if page.get("skill") == "kb-reconcile" and isinstance(state, dict) and state.get("version") == 2:
        result["claim_ids"] = [claim["claim_id"] for claim in state["claims"]]
    return result


def reconcile_created_pages(root: Path, created: list[dict[str, Any]]) -> dict[str, Any]:
    rels = [str(item.get("rel_path") or "") for item in created]
    unique_rels = sorted(set(rel for rel in rels if rel))
    missing = []
    hash_mismatch = []
    for item in created:
        rel = str(item.get("rel_path") or "")
        if not rel:
            continue
        target = root / rel
        if not target.exists():
            missing.append(rel)
        elif (item.get("sha256") and sha256_file(target) != item["sha256"]) or (item.get("expected_sha256") and sha256_file(target) != item["expected_sha256"]):
            hash_mismatch.append(rel)
    duplicate_created = {rel: count for rel, count in Counter(rels).items() if rel and count > 1}
    return {
        "created_count": len(created),
        "unique_created_count": len(unique_rels),
        "duplicate_created": duplicate_created,
        "missing": missing,
        "hash_mismatch": hash_mismatch,
        "ok": len(created) == len(unique_rels) and not missing and not hash_mismatch,
    }
