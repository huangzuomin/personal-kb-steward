"""Stable, path-independent identities and a rebuildable in-memory object index.

Reading a vault never allocates an ID or writes a migration. The Markdown fields
are authoritative; canonical_path is always derived from the actual file path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable, TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from .vault import Note


class ObjectIdentityError(ValueError):
    """An identity is invalid, ambiguous, or would change during an update."""


def new_object_id() -> str:
    return f"kb:{uuid4()}"


# Knowledge objects live under this top-level dir. `config.write.*` may point
# somewhere else (e.g. `_kb-steward/`), so the root is settable rather than a
# literal. Callers that never set it keep the upstream `wiki/` behaviour.
_DEFAULT_KNOWLEDGE_ROOT = "wiki"
_KNOWLEDGE_ROOTS: tuple[str, ...] = (_DEFAULT_KNOWLEDGE_ROOT,)


def roots_from_write(cfg: dict[str, Any] | None) -> list[str]:
    """Top-level dirs named by `config.write`; files (e.g. log_file) are skipped."""
    write = cfg.get("write") if isinstance(cfg, dict) else None
    roots: list[str] = []
    for value in (write if isinstance(write, dict) else {}).values():
        text = str(value or "").replace("\\", "/").strip("/")
        if not text or "." in text.split("/")[-1]:
            continue  # a file (e.g. log_file), not a directory
        head = text.split("/")[0]
        if head and head not in roots:
            roots.append(head)
    return roots


def bind_knowledge_roots(cfg: dict[str, Any] | None) -> tuple[str, ...]:
    """Derive the knowledge-object roots from `config.write` and cache them."""
    global _KNOWLEDGE_ROOTS
    _KNOWLEDGE_ROOTS = tuple(roots_from_write(cfg)) or (_DEFAULT_KNOWLEDGE_ROOT,)
    return _KNOWLEDGE_ROOTS


def knowledge_root_prefixes(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    """The same roots as `bind_knowledge_roots`, in prefix form (`wiki/`).

    `is_knowledge_path` needs a whole path; a caller that only holds a relative
    path has to ask the coarser question "is this note inside the knowledge tree
    at all", which is a `startswith` against the root. Exposed separately so the
    health report can be config-driven without touching module state.
    """
    return tuple(f"{r}/" for r in roots_from_write(cfg)) or (f"{_DEFAULT_KNOWLEDGE_ROOT}/",)


def knowledge_root() -> str:
    return _KNOWLEDGE_ROOTS[0]


def is_knowledge_path(path: str) -> bool:
    p = PurePosixPath(path.replace("\\", "/"))
    return (
        len(p.parts) >= 2 and p.parts[0].lower() in _KNOWLEDGE_ROOTS
        and p.suffix.lower() == ".md" and p.name.lower() != "readme.md"
    )


def identity_from_metadata(meta: dict[str, Any]) -> tuple[str, int] | None:
    """Return None only for a genuinely legacy page, not a malformed identity.

    The existing frontmatter reader returns scalar numbers as strings. Accept a
    canonical positive decimal string as well as an integer, but never bool/float.
    Generic user-defined `id` fields are deliberately not interpreted as object_id.
    """
    if meta.get("_object_identity_error"):
        raise ObjectIdentityError(str(meta["_object_identity_error"]))
    if "object_id" not in meta and "revision" not in meta:
        return None
    object_id = meta.get("object_id")
    if not isinstance(object_id, str) or not object_id.startswith("kb:"):
        raise ObjectIdentityError("object_id must be a canonical kb:<UUID> value")
    try:
        parsed = UUID(object_id[3:])
    except (ValueError, AttributeError) as exc:
        raise ObjectIdentityError("object_id must be a canonical kb:<UUID> value") from exc
    if str(parsed) != object_id[3:] or parsed.int == 0:
        raise ObjectIdentityError("object_id must be a non-nil, lowercase canonical UUID")
    value = meta.get("revision")
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        try:
            value = int(value)
        except ValueError as exc:
            raise ObjectIdentityError("revision is outside the supported integer range") from exc
    if type(value) is not int or value < 1:
        raise ObjectIdentityError("revision must be a positive integer")
    return object_id, value


@dataclass(frozen=True)
class KnowledgeObject:
    object_id: str
    canonical_path: str
    object_type: str
    revision: int
    content_sha256: str

    def __post_init__(self) -> None:
        if type(self.revision) is not int:
            raise ObjectIdentityError("KnowledgeObject.revision must be an integer")
        identity_from_metadata({"object_id": self.object_id, "revision": self.revision})
        path = PurePosixPath(self.canonical_path)
        if not is_knowledge_path(self.canonical_path) or "\\" in self.canonical_path or ".." in path.parts or path.as_posix() != self.canonical_path:
            raise ObjectIdentityError("canonical_path must be a vault-relative knowledge page path")
        if not isinstance(self.object_type, str) or not self.object_type.strip():
            raise ObjectIdentityError("identified knowledge pages require a type")
        if not isinstance(self.content_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
            raise ObjectIdentityError("content_sha256 must be a SHA-256 hex digest")

    @classmethod
    def from_note(cls, note: Note) -> KnowledgeObject | None:
        if not is_knowledge_path(note.rel):
            return None
        identity = identity_from_metadata(note.metadata)
        if identity is None:
            return None
        object_type = note.metadata.get("type")
        if not isinstance(object_type, str) or not object_type.strip():
            raise ObjectIdentityError("identified knowledge pages require a type")
        return cls(identity[0], note.rel, object_type, identity[1], note.sha256)


@dataclass
class ObjectRegistry:
    """A disposable view over indexed Markdown, not a second source of truth."""
    by_id: dict[str, KnowledgeObject] = field(default_factory=dict)
    legacy_paths: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    duplicates: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_notes(cls, notes: Iterable[Note]) -> ObjectRegistry:
        registry = cls()
        groups: dict[str, list[KnowledgeObject]] = {}
        # Overlapping configured scan directories must not manufacture collisions.
        unique = {note.rel: note for note in notes}
        for rel, note in sorted(unique.items()):
            if not is_knowledge_path(rel):
                continue
            try:
                obj = KnowledgeObject.from_note(note)
            except ObjectIdentityError as exc:
                registry.issues.append({"kind": "invalid_object_identity", "file": rel, "reason": str(exc)})
                continue
            if obj is None:
                registry.legacy_paths.append(rel)
                continue
            groups.setdefault(obj.object_id, []).append(obj)
        for object_id, objects in sorted(groups.items()):
            if len(objects) == 1:
                registry.by_id[object_id] = objects[0]
            else:
                paths = sorted(obj.canonical_path for obj in objects)
                registry.duplicates[object_id] = paths
                registry.issues.append({"kind": "duplicate_object_id", "object_id": object_id, "files": paths})
        return registry

    def get(self, object_id: str) -> KnowledgeObject | None:
        if object_id in self.duplicates:
            raise ObjectIdentityError(f"Ambiguous object_id {object_id}: {self.duplicates[object_id]}")
        return self.by_id.get(object_id)

    def require_valid(self) -> None:
        if self.issues:
            raise ObjectIdentityError(f"Object index contains identity errors: {self.issues}")
