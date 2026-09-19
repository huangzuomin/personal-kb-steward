from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import kb_root
from .knowledge_objects import ObjectRegistry, identity_from_metadata, is_knowledge_path


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

    @property
    def object_id(self) -> str | None:
        identity = identity_from_metadata(self.metadata) if is_knowledge_path(self.rel) else None
        return identity[0] if identity else None

    @property
    def revision(self) -> int | None:
        identity = identity_from_metadata(self.metadata) if is_knowledge_path(self.rel) else None
        return identity[1] if identity else None

    @property
    def canonical_path(self) -> str:
        return self.rel


@dataclass
class VaultIndex:
    root: Path
    notes: list[Note]
    by_rel: dict[str, Note]
    by_stem: dict[str, list[Note]]
    by_title: dict[str, list[Note]]
    by_attachment: dict[str, list[str]] = field(default_factory=dict)
    objects: ObjectRegistry = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.objects = ObjectRegistry.from_notes(self.notes)

    @property
    def by_object_id(self) -> dict[str, Note]:
        return {key: self.by_rel[obj.canonical_path] for key, obj in self.objects.by_id.items()}


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
        if current_key in {"object_id", "revision"} and current_key in meta:
            meta["_object_identity_error"] = f"Duplicate identity field: {current_key}"
        value = value.strip()
        if value == "":
            meta[current_key] = []
        elif (value.startswith("[") and value.endswith("]")) or (value.startswith("{") and value.endswith("}")):
            try:
                meta[current_key] = json.loads(value)
            except json.JSONDecodeError:
                if value.startswith("["):
                    meta[current_key] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
                else:
                    meta[current_key] = value
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


def excluded_note(cfg: dict[str, Any], path: Path) -> bool:
    """Generated index pages (0-MOC.md and friends) are navigation, not input.

    Feeding them to the LLM invites it to summarise a table of contents. The
    rule lives in config so a vault can name its own index pages instead of
    hardcoding the convention here. Empty by default: upstream vaults that
    never opted in keep indexing every file.
    """
    names = {str(n).strip().lower() for n in (cfg["scan"].get("exclude_files") or []) if str(n).strip()}
    if not names:
        return False
    return path.name.lower() in names or path.stem.lower() in names


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
            if excluded_note(cfg, path):
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
    return VaultIndex(
        root=root,
        notes=sorted(notes, key=lambda n: n.rel.lower()),
        by_rel=by_rel,
        by_stem=dict(by_stem),
        by_title=dict(by_title),
        by_attachment=build_attachment_index(root),
    )


def build_attachment_index(root: Path) -> dict[str, list[str]]:
    """索引全库非 .md 文件（附件），供双链解析使用。

    Obsidian 的链接解析认全文件类型，`![[报告.pdf]]` 与 `![[图片.png]]` 都是合法双链。
    若只索引 .md，所有附件嵌入都会被误报为断链——因此这里按相对路径扫描全库。
    键为小写 basename，值为库内相对路径列表。
    """
    index: dict[str, list[str]] = defaultdict(list)
    skip_tops = {".obsidian", ".git", ".kb", ".p0-quarantine", ".workbuddy-ai"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_tops]
        for name in filenames:
            if name.lower().endswith(".md"):
                continue
            rel = (Path(dirpath) / name).relative_to(root).as_posix()
            index[name.lower()].append(rel)
    return dict(index)


def extract_wikilinks(text: str) -> list[str]:
    r"""提取 Obsidian 双链目标。

    三处修正（本库实测踩到的坑）：
    1. `\#` 是**文件名的一部分**（本库既有约定，如 `[[\#我平常都看什麼書]]`），
       不能当作锚点分隔符截断。
    2. 不匹配 Markdown 链接文本里的 `[[PDF] xxx](https://…)`，那不是双链。
    3. 锚点 `#` 仅在未转义时才算分隔符。
    """
    targets: list[str] = []
    for raw in re.findall(r"\[\[(.+?)\]\]", text, re.S):
        if "\n" in raw or raw.startswith("["):
            continue
        target = raw.split("|")[0]
        target = re.split(r"(?<!\\)#", target)[0]
        target = target.strip().replace("\\#", "#")
        if target:
            targets.append(target)
    return targets


def wiki_stem(target: str) -> str:
    """Obsidian 口径的 stem：只在 target 真的以 .md 结尾时才剥离它。

    不能用 Path(...).stem —— 它会把文件名里的「.（数字）」当扩展名剥掉，
    例如 `方案（3.0）` 会被截成 `方案（3`，导致这类笔记永远解析不到。
    索引侧的键来自带 `.md` 的真实文件名，因此这里是「带 .md 才剥」的非对称修正。
    """
    clean = target.strip().replace("\\", "/")
    base = clean.rsplit("/", 1)[-1]
    if base.lower().endswith(".md"):
        return base[:-3]
    return base


def resolve_link(index: VaultIndex, target: str) -> str | None:
    """按 Obsidian 口径解析双链：相对路径 → 文件名 stem → 附件名 → 标题。"""
    clean = target.strip()
    if clean in index.by_rel:
        return clean
    as_path = clean.replace("\\", "/")
    if as_path in index.by_rel:
        return as_path
    matches = index.by_stem.get(wiki_stem(clean), [])
    if len(matches) == 1:
        return matches[0].rel
    attachment = index.by_attachment.get(as_path.lower(), [])
    if len(attachment) == 1:
        return attachment[0]
    title_matches = index.by_title.get(clean.lower(), [])
    if len(title_matches) == 1:
        return title_matches[0].rel
    return None
