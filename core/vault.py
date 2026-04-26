from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import kb_root


@dataclass
class Note:
    path: Path
    rel: str
    title: str
    body: str
    metadata: dict[str, Any]
    sha256: str
    mtime: float
    size: int


@dataclass
class VaultIndex:
    root: Path
    notes: list[Note]
    by_rel: dict[str, Note]
    by_stem: dict[str, list[Note]]
    by_title: dict[str, list[Note]]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    current_key = ""
    for raw in match.group(1).splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("  - ") and current_key:
            meta.setdefault(current_key, []).append(line[4:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value == "":
            meta[current_key] = []
        elif value.startswith("[") and value.endswith("]"):
            try:
                meta[current_key] = json.loads(value)
            except json.JSONDecodeError:
                meta[current_key] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
        else:
            meta[current_key] = value.strip('"')
    return meta, match.group(2)


def first_heading(body: str) -> str | None:
    for line in body.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def read_note(path: Path, root: Path) -> Note:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    meta, body = parse_frontmatter(text)
    title = str(meta.get("title") or first_heading(body) or path.stem).strip()
    stat = path.stat()
    return Note(
        path=path,
        rel=path.relative_to(root).as_posix(),
        title=title,
        body=body,
        metadata=meta,
        sha256=hashlib.sha256(raw).hexdigest(),
        mtime=stat.st_mtime,
        size=stat.st_size,
    )


def build_index(cfg: dict[str, Any]) -> VaultIndex:
    root = kb_root(cfg)
    scan_cfg = cfg["scan"]
    include_dirs = scan_cfg["include_dirs"]
    exclude_dirs = set(scan_cfg["exclude_dirs"])
    extensions = set(scan_cfg["extensions"])
    notes: list[Note] = []
    for dirname in include_dirs:
        base = root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            if set(path.relative_to(root).parts) & exclude_dirs:
                continue
            notes.append(read_note(path, root))
    for path in root.glob("*.md"):
        if path.name != cfg["write"]["log_file"]:
            notes.append(read_note(path, root))
    by_rel = {note.rel: note for note in notes}
    by_stem: dict[str, list[Note]] = defaultdict(list)
    by_title: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        by_stem[note.path.stem].append(note)
        by_title[note.title.strip().lower()].append(note)
    return VaultIndex(root=root, notes=sorted(notes, key=lambda n: n.rel.lower()), by_rel=by_rel, by_stem=dict(by_stem), by_title=dict(by_title))
