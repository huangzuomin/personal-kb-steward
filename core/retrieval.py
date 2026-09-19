"""Request-scoped Agent retrieval. Cache ranks; current Markdown supplies content."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import sqlite3
from typing import Any

from .config import sha256_file, sha256_text
from .dependencies import stale
from .derived_index import DerivedIndexError, INTERNAL_DIRS, _info, _open, _path, search
from .knowledge_objects import ObjectIdentityError
from .layout import knowledge_dirs, knowledge_prefixes
from .vault import Note, VaultIndex

DEFAULT_PREFIXES = ("raw/", "quicknote/", "inbox/", "wiki/seeds/", "wiki/topics/", "wiki/sources/",
                    "wiki/evidence/", "wiki/gaps/", "wiki/claim-checks/")

INPUT_DIRS = ("raw", "quicknote", "inbox")


def retrieval_prefixes(cfg: dict[str, Any] | None = None,
                       knowledge: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Default recall scope: raw inputs first, then knowledge objects."""
    return tuple(f"{d}/" for d in INPUT_DIRS) + (knowledge if knowledge is not None else knowledge_prefixes(cfg))


def knowledge_prefixes_with_inputs(cfg: dict[str, Any] | None = None,
                                   knowledge: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Knowledge objects first, `raw/` last: for cross-source synthesis tasks."""
    return (knowledge if knowledge is not None else knowledge_prefixes(cfg)) + ("raw/",)


# --- Page predicates ------------------------------------------------------
# These live here, not in the runner, because the runner has a hard line cap
# and these are pure functions over config + a page dict.
def topic_prefixes(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    return (knowledge_dirs(cfg)["topics_dir"] + "/",)


def source_prefixes(cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    return (knowledge_dirs(cfg)["sources_dir"] + "/",)


def is_topic_page(page: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    return str(page.get("rel_path", "")).startswith(topic_prefixes(cfg))


def is_source_page(page: dict[str, Any], cfg: dict[str, Any] | None = None) -> bool:
    return str(page.get("rel_path", "")).startswith(source_prefixes(cfg))

# Strip only known task boilerplate, not arbitrary Chinese substrings or inferred concepts.
BOILERPLATE = re.compile(r"准备写作素材|生成写作材料包|生成材料包|发现选题|发现主题|写作素材|材料包|素材包|围绕|关于|material pack", re.I)
STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "about", "please",
             "一个", "如何", "什么", "生成", "整理", "资料", "内容", "来源", "请", "的"}
NOTICE = "检索不等于事实核实；旧依据需复查。内容来自当前扫描的 Markdown，不从缓存回写。"


# Words that mark a fact line as a case. Kept generic on purpose: upstream also
# listed a specific city name here, which labelled any line mentioning that city
# as a case regardless of what it described.
CASE_MARKERS = ("案例", "项目", "case study", "implementation")


def fallback_terms(query: str) -> list[str]:
    """Query's own words, for when stopword filtering leaves nothing.

    A hardcoded vocabulary here made every vault search as though it were the
    upstream demo corpus, so the fallback is derived from the query instead.
    """
    return [q.lower() for q in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,12}", query)]


def query_terms(query: str) -> list[str]:
    clean = BOILERPLATE.sub(" ", query)
    words = re.findall(r"[A-Za-z][A-Za-z0-9_+-]*|[\u4e00-\u9fff]+", clean)
    terms = [t.lower() for t in words]
    unique = list(dict.fromkeys(t for t in terms if t not in STOPWORDS))[:16]
    if unique:
        return unique
    # No extractable term (empty query, or boilerplate only). The old fallback
    # was a hardcoded demo vocabulary ("ai 新闻 媒体 温州 知识"), which made every
    # vault search as though it were the upstream demo corpus. Fall back to the
    # query's own words instead, so the behaviour stays vault-neutral.
    return list(dict.fromkeys(terms))[:16]


def excerpt(note: Note, terms: list[str], limit: int) -> str:
    """A contiguous current-body window, including a deep hit rather than only the introduction."""
    positions = [note.body.lower().find(t) for t in terms]
    first = min((p for p in positions if p >= 0), default=0)
    start = max(0, first - min(120, limit // 4)) if first >= limit else 0
    return note.body[start:start + limit]


@dataclass
class Selection:
    notes: list[Note]
    report: dict[str, Any]


class Retriever:
    """One instance per plan: bounded FTS recall plus live delta and one-hop sources.

    No index rebuild, model call or disk write. Missing/incompatible caches fall
    back to the existing live vault snapshot and explicitly lose dependency coverage.
    """
    def __init__(self, cfg: dict[str, Any], index: VaultIndex):
        self.cfg, self.index = cfg, index
        self.loaded = False
        self.cached: dict[str, str] = {}
        self.incoming: dict[str, list[dict]] = defaultdict(list)
        self.pending: dict[str, dict] = {}
        self.info: dict = {}
        self.fallback: str | None = None
        self.history: list[dict] = []
        self.hits: dict[str, dict] = {}
        self.terms: list[str] = []

    def _load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        try:
            with _open(self.cfg) as conn:
                self.info = _info(conn)
                self.cached = dict(conn.execute("SELECT path,sha256 FROM notes"))
                for row in conn.execute("SELECT * FROM dependencies ORDER BY dependent,source,claim_id"):
                    self.incoming[row["dependent"]].append(dict(row))
            report = stale(self.cfg)
            self.pending = {n["path"]: n for n in report["pending_updates"]}
        except (OSError, ValueError, sqlite3.Error, KeyError, TypeError) as exc:
            self.fallback = f"索引不可用，回退当前文件扫描；依赖状态未完整核对：{exc}"
            self.cached, self.pending = {}, {}
            self.incoming.clear()

    def select(self, query: str, *, limit: int = 12, prefixes: tuple[str, ...] | None = None,
               note_type: str | None = None, note_status: str | None = None) -> Selection:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("检索 limit 必须为 1 至 100")
        # None means "use the configured layout"; callers that pass an explicit
        # tuple still get exactly that scope.
        if prefixes is None:
            prefixes = retrieval_prefixes(self.cfg)
        self._load()
        terms = query_terms(query)
        eligible = {}
        for note in self.index.by_rel.values():
            if (not note.rel.startswith(prefixes) or set(note.path.relative_to(self.index.root).parts) & INTERNAL_DIRS
                    or note_type is not None and note.metadata.get("type") != note_type
                    or note_status is not None and note.metadata.get("status") != note_status):
                continue
            try:
                _path(self.index.root, note.rel)  # Never introduce a linked/out-of-scope source through fallback.
            except (OSError, ValueError):
                continue
            eligible[note.rel] = note

        ranks: dict[str, int] = {}
        engine = "live-scan"
        index_engines = set()
        if self.fallback is None:
            try:
                for term in terms:
                    found = search(self.cfg, term, prefixes=prefixes, note_type=note_type,
                                   note_status=note_status, limit=min(100, max(20, limit * 4)))
                    engine = "sqlite+live-delta"
                    index_engines.add(found["engine"])
                    for rank, hit in enumerate(found["hits"]):
                        ranks[hit["path"]] = min(rank, ranks.get(hit["path"], rank))
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.fallback = f"全文检索失败，回退当前文件扫描：{exc}"
                ranks.clear()
                engine = "live-scan"
        # Newly created/edited notes are not invisible just because rebuild is explicit.
        candidates = eligible if self.fallback else {
            path: note for path, note in eligible.items()
            if path in ranks or self.cached.get(path) != note.sha256}
        scored = []
        for path, note in candidates.items():
            hay = (note.title + "\n" + note.body).lower()
            matched = sum(t in hay for t in terms)
            if matched:
                scored.append(((-matched, -sum(t in note.title.lower() for t in terms),
                                ranks.get(path, 100), path), note))
        notes = [n for _, n in sorted(scored, key=lambda x: x[0])[:limit]]
        selected_by = {n.rel: "keyword" if n.rel in ranks else "live_scan" for n in notes}
        # Supplement, never displace keyword matches; no related/wikilink expansion.
        for parent in list(notes):
            if self.cached.get(parent.rel) != parent.sha256:
                continue  # Stale dependency metadata must not pick new inputs.
            for edge in self.incoming[parent.rel]:
                source = edge["source"]
                if len(notes) < limit and source in eligible and source not in selected_by:
                    notes.append(eligible[source])
                    selected_by[source] = "dependency"

        hits = self.describe(notes, selected_by=selected_by)
        require_review = any(h["dependency_state"] not in {"no_signal", "not_applicable"} for h in hits)
        require_review |= any(str(n.metadata.get("status")) in {"stale", "conflict", "manual_review"}
                              or str(n.metadata.get("review_required", "")).lower() == "true" for n in notes)
        report = {"query": query, "terms": terms, "engine": engine, "built_at": self.info.get("built_at"),
                  "fallback_reason": self.fallback, "notice": NOTICE, "hits": hits,
                  "requires_review": require_review, "warnings": self.info.get("warnings", []),
                  "index_engines": sorted(index_engines)}
        self.history.append(report)
        self.hits.update({h["path"]: h for h in hits})
        self.terms = terms
        return Selection(notes, report)

    def describe(self, notes: list[Note], *, selected_by: dict[str, str] | None = None) -> list[dict]:
        """Describe explicit as well as retrieved inputs using the same request snapshot."""
        self._load()
        hits = []
        for note in notes:
            same = self.cached.get(note.rel) == note.sha256
            pending = self.pending.get(note.rel) if same and not self.fallback else None
            edges = self.incoming[note.rel]
            state = ("not_applicable" if not note.is_knowledge else
                     "unchecked" if not same or self.fallback else "stale" if pending else
                     "unversioned" if not edges or any(e["expected_sha256"] is None for e in edges) else "no_signal")
            hit = {"path": note.rel, "sha256": note.sha256, "object_id": note.object_id, "revision": note.revision,
                   "selected_by": (selected_by or {}).get(note.rel, "explicit_source"), "dependency_state": state,
                   "cache_status": "matched" if same else "changed_or_new",
                   "causes": pending["causes"] if pending else [],
                   "blocked_by": pending["blocked_by"] if pending else [],
                   "claim_ids": pending["claim_ids"] if pending else []}
            hits.append(hit)
        return hits

    def documents(self, notes: list[Note], max_chars: int,
                  total_budget: int = 0) -> list[dict]:
        """Build LLM input documents under an optional whole-set character budget.

        `max_chars` caps each document; `total_budget` caps the sum. When a budget
        is set, every document still gets a fair share (budget / len(notes)) so that
        one long note cannot crowd out the rest, and later documents borrow whatever
        earlier ones left unused. Without a budget, behaviour is unchanged.
        """
        return budget_documents(notes, max_chars, total_budget,
                                render=lambda n, limit: {"path": n.rel, "title": n.title,
                                    "type": str(n.metadata.get("type", "")),
                                    "status": str(n.metadata.get("status", "")),
                                    "stage": str(n.metadata.get("stage", "")),
                                    "content": excerpt(n, self.terms, limit),
                                    "retrieval": self.hits.get(n.rel, {}), "usage_note": NOTICE})


def budget_documents(notes: list[Note], max_chars: int, total_budget: int = 0, *, render=None) -> list[dict]:
    """Fair sequential content budget; 0 means uncapped total, never negative slicing."""
    if type(max_chars) is not int or max_chars < 0 or type(total_budget) is not int or total_budget < 0:
        raise ValueError("Source character budgets must be nonnegative integers")
    remaining = total_budget
    docs = []
    for i, note in enumerate(notes):
        limit = min(max_chars, remaining // (len(notes) - i)) if total_budget else max_chars
        doc = render(note, limit) if render else {
            "path": note.rel, "title": note.title, "type": str(note.metadata.get("type") or ""),
            "status": str(note.metadata.get("status") or ""), "stage": str(note.metadata.get("stage") or ""),
            "content": note.body[:limit],
        }
        docs.append(doc)
        if total_budget:
            remaining -= len(doc["content"])
    return docs



def annotate_pages(pages: list[dict], selection: Selection) -> None:
    """Keep diagnostics in plan and rendered material, and preserve the existing review gate."""
    from .reconcile import _patch_header
    for page in pages:
        page["retrieval_source_hashes"] = {n.rel: n.sha256 for n in selection.notes}
        page["retrieval"] = selection.report
        if selection.report["requires_review"]:
            page["review_required"] = True
            rows = [f"- {h['path']}：{h['dependency_state']}" for h in selection.report["hits"]]
            page["content"] = (_patch_header(page["content"], {"review_required": True})
                               + "\n\n## 检索与来源复查\n\n" + NOTICE + "\n" + "\n".join(rows) + "\n")
            page["content_sha256"] = sha256_text(page["content"])


def validate_retrieval_page(index: VaultIndex, page: dict) -> None:
    """Pin selected current inputs at both save and apply; do not re-base a saved proposal."""
    if "retrieval_source_hashes" not in page:
        return  # Old saved plans and unrelated producers retain their contracts.
    hashes = page["retrieval_source_hashes"]
    if not isinstance(hashes, dict) or not all(isinstance(p, str) and isinstance(h, str)
            and re.fullmatch(r"[0-9a-f]{64}", h) for p, h in hashes.items()):
        raise ObjectIdentityError("Invalid retrieval source snapshots")
    if any(p not in hashes for p in page.get("sources", [])):
        raise ObjectIdentityError("Planned source is missing its retrieval snapshot")
    for rel, expected in hashes.items():
        try:
            if rel not in index.by_rel or sha256_file(_path(index.root, rel)) != expected:
                raise ObjectIdentityError(f"Retrieval source changed: {rel}; regenerate the proposal")
        except (OSError, DerivedIndexError) as exc:
            raise ObjectIdentityError(f"Retrieval source unavailable: {rel}") from exc
