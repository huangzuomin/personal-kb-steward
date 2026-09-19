"""Disposable SQLite/FTS5 snapshot. Markdown owns data; queries never write it."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import tempfile
from typing import Any, Iterator

from .claims import Evidence, evidence_status, normalized_text, read_claims, render_claims
from .config import kb_root
from .knowledge_objects import ObjectRegistry
from .reconcile import END, START, _managed
from .vault import Note, first_heading, parse_frontmatter

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4B425349  # KBSI: only replace our own cache.
INTERNAL_DIRS = {".kb", ".git", ".obsidian", ".openclaw"}
NOTICE = "索引是构建时快照；新增文件须重建后可搜。片段匹配不等于判断已证实。"
_SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE notes (
    path TEXT PRIMARY KEY, object_id TEXT UNIQUE, revision INTEGER,
    title TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL,
    body TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE claims (
    path TEXT NOT NULL REFERENCES notes(path), claim_id TEXT NOT NULL,
    statement TEXT NOT NULL, kind TEXT NOT NULL, confidence TEXT NOT NULL,
    PRIMARY KEY(path, claim_id)
);
CREATE TABLE evidence (
    path TEXT NOT NULL, claim_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    source TEXT NOT NULL, source_sha256 TEXT NOT NULL, quote TEXT NOT NULL,
    quote_sha256 TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, relation TEXT NOT NULL,
    match_status_at_build TEXT NOT NULL,
    PRIMARY KEY(path, claim_id, ordinal),
    FOREIGN KEY(path, claim_id) REFERENCES claims(path, claim_id)
);
CREATE INDEX evidence_source ON evidence(source);
CREATE VIRTUAL TABLE search_fts USING fts5(
    item_kind UNINDEXED, path UNINDEXED, claim_id UNINDEXED, ordinal UNINDEXED,
    title, body, tokenize='trigram'
);
"""


class DerivedIndexError(ValueError):
    """A cache is missing, incompatible or cannot be safely built."""


def _path(root: Path, rel: str) -> Path:
    p = PurePosixPath(rel)
    if (not rel or "\\" in rel or p.is_absolute() or ".." in p.parts
            or p.as_posix() != rel):
        raise DerivedIndexError(f"非规范的知识库相对路径：{rel}")
    path = root / rel
    if path.resolve() != path or not path.resolve().is_relative_to(root):
        raise DerivedIndexError(f"索引不跟随目录/文件链接：{rel}")
    return path


def cache_path(cfg: dict[str, Any]) -> Path:
    root = kb_root(cfg)
    if not root.is_dir():
        raise DerivedIndexError(f"知识库目录不存在：{root}")
    return _path(root, ".kb/index.sqlite")


def _scope(cfg: dict[str, Any]) -> str:
    scan = cfg["scan"]
    return json.dumps({k: sorted(set(scan[k])) for k in ("include_dirs", "exclude_dirs", "extensions")}
                      | {"log_file": cfg["write"]["log_file"]}, ensure_ascii=False, sort_keys=True)


def _paths(cfg: dict[str, Any], warnings: list[str]) -> list[Path]:
    """Same configured Markdown scope as the vault, excluding runtime/cache data."""
    root = kb_root(cfg)
    excluded = INTERNAL_DIRS | set(cfg["scan"]["exclude_dirs"])
    found: set[Path] = set()
    def allowed(path: Path) -> bool:
        return not (set(path.relative_to(root).parts) & excluded)
    def add(path: Path) -> None:
        if path.suffix.lower() == ".md" and allowed(path):
            try:
                _path(root, path.relative_to(root).as_posix())
            except DerivedIndexError as exc:
                warnings.append(str(exc))
                return
            if path.is_file():
                found.add(path)
    def walk_error(exc: OSError) -> None:
        raise exc  # Never publish an apparently complete but unreadable tree.
    if ".md" in cfg["scan"]["extensions"]:
        for name in sorted(set(cfg["scan"]["include_dirs"])):
            base = root if name == "." else _path(root, name)
            if not base.exists() or not allowed(base):
                continue
            for parent, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
                retained = []
                for name in dirs:
                    path = Path(parent) / name
                    if not allowed(path):
                        continue
                    try:
                        _path(root, path.relative_to(root).as_posix())
                        retained.append(name)
                    except DerivedIndexError as exc:
                        warnings.append(str(exc))
                dirs[:] = sorted(retained)
                for name in sorted(files):
                    add(Path(parent) / name)
    for path in root.glob("*.md"):
        if path.name != cfg["write"]["log_file"]:
            add(path)
    return sorted(found)


def _snapshot(cfg: dict[str, Any], warnings: list[str]) -> tuple[list[Note], dict[str, dict[str, str]]]:
    root = kb_root(cfg)
    notes, documents = [], {}
    for path in _paths(cfg, warnings):
        raw = path.read_bytes()
        text = raw.decode("utf-8")  # Invalid input must not silently become replacement characters.
        meta, body = parse_frontmatter(normalized_text(text))
        rel = path.relative_to(root).as_posix()
        sha = hashlib.sha256(raw).hexdigest()
        title = str(meta.get("title") or first_heading(body) or path.stem).strip()
        notes.append(Note(path, rel, title, body, meta, sha, path.stat().st_mtime, len(raw)))
        documents[rel] = {"path": rel, "content": text, "sha256": sha}
    ObjectRegistry.from_notes(notes).require_valid()
    return notes, documents


def _records(note: Note, text: str) -> list:
    state = note.metadata.get("reconcile_state")
    if not isinstance(state, dict) or state.get("version") != 2:
        return []  # Existing ordinary/v1 pages are searchable, never migrated.
    span, state = _managed(text, note.metadata)
    records = read_claims(state)
    expected = "\n".join([START, "## 资料综合", "", render_claims(records), END])
    if not note.object_id or not span or normalized_text(text[span[0]:span[1]]) != expected:
        raise DerivedIndexError(f"判断记录与页面身份/综合区块不一致：{note.rel}")
    for claim in records:
        if any(state["source_hashes"].get(e.source) != e.source_sha256 for e in claim.evidence):
            raise DerivedIndexError(f"判断来源版本与页面记录不一致：{note.rel}")
    return records


@contextmanager
def _open(cfg: dict[str, Any]) -> Iterator[sqlite3.Connection]:
    path = cache_path(cfg)
    if not path.is_file():
        raise DerivedIndexError("索引不存在；先运行 python scripts/kb_index.py rebuild")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise DerivedIndexError("不是本项目的派生索引，拒绝使用或覆盖")
        meta = dict(conn.execute("SELECT key,value FROM metadata"))
        if meta.get("schema_version") != str(SCHEMA_VERSION):
            raise DerivedIndexError("索引版本不同，请重建索引")
        if meta.get("root") != str(kb_root(cfg)) or meta.get("scope") != _scope(cfg):
            raise DerivedIndexError("知识库位置或扫描范围已改变，请重建索引")
        yield conn
    finally:
        conn.close()


def _populate(conn: sqlite3.Connection, notes: list[Note], documents: dict, metadata: dict) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA application_id={APPLICATION_ID}")
    conn.executescript(_SCHEMA)
    with conn:
        conn.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
        for note in notes:
            conn.execute("INSERT INTO notes VALUES (?,?,?,?,?,?,?,?)",
                         (note.rel, note.object_id, note.revision, note.title,
                          str(note.metadata.get("type", "")), str(note.metadata.get("status", "")),
                          note.body, note.sha256))
            conn.execute("INSERT INTO search_fts VALUES (?,?,?,?,?,?)",
                         ("note", note.rel, None, None, note.title, note.body))
            for claim in _records(note, documents[note.rel]["content"]):
                conn.execute("INSERT INTO claims VALUES (?,?,?,?,?)",
                             (note.rel, claim.claim_id, claim.statement, claim.kind, claim.confidence))
                conn.execute("INSERT INTO search_fts VALUES (?,?,?,?,?,?)",
                             ("claim", note.rel, claim.claim_id, None, note.title, claim.statement))
                for i, evidence in enumerate(claim.evidence):
                    conn.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                 (note.rel, claim.claim_id, i, *asdict(evidence).values(),
                                  evidence_status(evidence, documents.get(evidence.source))))
                    conn.execute("INSERT INTO search_fts VALUES (?,?,?,?,?,?)",
                                 ("evidence", note.rel, claim.claim_id, i, claim.statement, evidence.quote))


def rebuild(cfg: dict[str, Any]) -> dict:
    """Explicit full rebuild: replace only a complete cache, never modify notes."""
    path = cache_path(cfg)
    if path.exists():
        # Root/scope/schema may change on rebuild, but never replace someone else's DB.
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as old:
            if old.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise DerivedIndexError("目标不是派生索引，拒绝覆盖 .kb/index.sqlite")
    warnings: list[str] = []
    notes, documents = _snapshot(cfg, warnings)
    metadata = {"schema_version": str(SCHEMA_VERSION), "root": str(kb_root(cfg)), "scope": _scope(cfg),
                "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "warnings": json.dumps(warnings, ensure_ascii=False)}
    path.parent.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="index-", suffix=".sqlite", dir=path.parent)
    os.close(fd)
    temp = Path(name)
    conn = None
    try:
        conn = sqlite3.connect(temp)
        _populate(conn, notes, documents, metadata)
        conn.close()
        os.replace(temp, path)
    finally:
        if conn is not None:
            conn.close()
        temp.unlink(missing_ok=True)
    return status(cfg)


def _info(conn: sqlite3.Connection) -> dict:
    meta = dict(conn.execute("SELECT key,value FROM metadata"))
    return {"schema_version": SCHEMA_VERSION, "built_at": meta["built_at"],
            "warnings": json.loads(meta["warnings"]), "notice": NOTICE}


def status(cfg: dict[str, Any]) -> dict:
    with _open(cfg) as conn:
        counts = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("notes", "claims", "evidence")}
        counts["objects"] = conn.execute("SELECT count(*) FROM notes WHERE object_id IS NOT NULL").fetchone()[0]
        return {**_info(conn), "index": str(cache_path(cfg)), "counts": counts}


def _document(root: Path, rel: str) -> dict | None:
    try:
        raw = _path(root, rel).read_bytes()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "content": raw.decode("utf-8")}
    except (OSError, ValueError):
        return None


def _current(root: Path, note: dict) -> str:
    doc = _document(root, note["path"])
    return "unavailable" if doc is None else "matched" if doc["sha256"] == note["sha256"] else "changed"


def _evidence(conn: sqlite3.Connection, root: Path, path: str, identifier: str,
              ordinal: int | None = None) -> list[dict]:
    sql = "SELECT * FROM evidence WHERE path=? AND claim_id=?"
    params: list = [path, identifier]
    if ordinal is not None:
        sql += " AND ordinal=?"
        params.append(ordinal)
    result, documents = [], {}
    for row in conn.execute(sql + " ORDER BY ordinal", params):
        item = dict(row)
        e = Evidence(**{key: item[key] for key in Evidence.__dataclass_fields__})
        if e.source not in documents:
            indexed = conn.execute("SELECT 1 FROM notes WHERE path=?", (e.source,)).fetchone()
            documents[e.source] = _document(root, e.source) if indexed else None
        item["current_match_status"] = evidence_status(e, documents[e.source])
        result.append(item)
    return result


def show(cfg: dict[str, Any], target: str) -> dict:
    with _open(cfg) as conn:
        row = conn.execute("SELECT * FROM notes WHERE path=? OR object_id=?", (target, target)).fetchone()
        if row is None:
            raise DerivedIndexError(f"索引中没有该页面或对象：{target}；新增/改名后请重建")
        note = dict(row)
        claims = [dict(r) for r in conn.execute("SELECT * FROM claims WHERE path=? ORDER BY claim_id", (note["path"],))]
        for claim in claims:
            claim["evidence"] = _evidence(conn, kb_root(cfg), note["path"], claim["claim_id"])
        return {**_info(conn), "note": note, "current_status": _current(kb_root(cfg), note), "claims": claims}


def search(cfg: dict[str, Any], query: str, *, kind: str = "note", note_type: str | None = None,
           note_status: str | None = None, limit: int = 10) -> dict:
    """Plain whitespace-separated terms ANDed as literals, never raw SQL/FTS syntax."""
    if not isinstance(query, str) or not query.strip() or len(query) > 200 or "\x00" in query:
        raise DerivedIndexError("查询须为 1 至 200 字符的非空文本")
    if kind not in {"note", "claim", "evidence", "all"} or type(limit) is not int or not 1 <= limit <= 100:
        raise DerivedIndexError("非法检索类型或 limit（1 至 100）")
    terms = list(dict.fromkeys(query.split()))
    if len(terms) > 16:
        raise DerivedIndexError("一次最多查询 16 个词")
    long, short = [t for t in terms if len(t) >= 3], [t for t in terms if len(t) < 3]
    where, params = [], []
    if long:
        where.append("search_fts MATCH ?")
        params.append(" AND ".join('"' + t.replace('"', '""') + '"' for t in long))
    for term in short:
        where.append("(instr(lower(f.title), ?) > 0 OR instr(lower(f.body), ?) > 0)")
        params.extend((term.lower(), term.lower()))
    for column, value in (("f.item_kind", None if kind == "all" else kind),
                          ("n.type", note_type), ("n.status", note_status)):
        if value is not None:
            where.append(column + "=?")
            params.append(value)
    score = "bm25(search_fts,0,0,0,0,3,1)" if long else "0.0"
    snippet = ("snippet(search_fts,-1,'[',']',' … ',32)" if long else
               "substr(f.body,max(1,instr(lower(f.body),?)-60),200)")
    if not long:
        params.insert(0, terms[0].lower())
    sql = f"""SELECT f.item_kind, f.path, f.claim_id, f.ordinal, n.object_id, n.revision,
        n.title, n.type, n.status, n.sha256, {score} AS score, {snippet} AS snippet
        FROM search_fts f JOIN notes n ON n.path=f.path WHERE {' AND '.join(where)}
        ORDER BY score, f.path, f.item_kind, f.claim_id, f.ordinal LIMIT ?"""
    with _open(cfg) as conn:
        hits, freshness = [], {}
        for row in conn.execute(sql, [*params, limit]).fetchall():
            item = dict(row)
            if item["path"] not in freshness:
                freshness[item["path"]] = _current(kb_root(cfg), item)
            item["current_status"] = freshness[item["path"]]
            if item["claim_id"]:
                item["evidence"] = _evidence(conn, kb_root(cfg), item["path"], item["claim_id"], item["ordinal"])
            hits.append(item)
        return {**_info(conn), "query": query, "engine": "fts5-trigram" if long else "short-substring-scan",
                "hits": hits}
