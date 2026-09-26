"""Relation candidates for atomic seeds via the request-scoped Retriever.

Only the configured known documents/index are searched — never a parallel
vault scan. `related` targets are verified, actually matched index objects with
their concrete matching reasons; a suspicion is recorded as a suspicion, not as
a confirmed relation. A search that never ran is reported as not_attempted;
candidates_found is reported only when usable candidates exist.
"""
from __future__ import annotations

import re
import unicodedata

NOT_ATTEMPTED = "not_attempted"
NO_MATCH = "no_match"
CANDIDATES_FOUND = "candidates_found"


def _key(title: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", str(title)).casefold())


def neutralize_links(text: str) -> str:
    """Free-text pending entries must not render as fresh wikilinks."""
    return str(text).replace("[[", "［［").replace("]]", "］］")


def relation_candidates(item: dict, cfg: dict, index=None, retriever=None) -> dict:
    """Return relation report for one seed item: {related, pending_links,
    link_search, relation_explanations, suspected_duplicates}."""
    report = {"related": [], "pending_links": [], "link_search": NOT_ATTEMPTED,
              "relation_explanations": [], "suspected_duplicates": []}
    proposed = [neutralize_links(p) for p in item.get("pending_links", [])
                if isinstance(p, str) and p.strip()]
    if retriever is None or index is None:
        report["relation_explanations"].append("未提供检索索引，未尝试关系检索；不虚构关联。")
        report["pending_links"] = list(dict.fromkeys(proposed))
        return report
    query = " ".join([str(item.get("title", "")), str(item.get("summary", ""))])
    selection = retriever.select(query, limit=6)
    terms = [str(t) for t in selection.report.get("terms", [])]
    hits = {h["path"]: h for h in selection.report.get("hits", [])}  # key by path, not order
    own_sources = set(item.get("sources", []))
    for note in selection.notes:
        rel = note.rel
        if rel in own_sources:
            continue
        meta = note.metadata
        if meta.get("type") == "seed-card":
            same_units = set(item.get("thought_units", [])) & set(
                (meta.get("seed_state", {}) or {}).get("thought_units", []) or [])
            if _key(note.title) == _key(item.get("title", "")) or same_units:
                reason = f"[[{rel}]]：疑似重复（同名或同源信息单元），需人工判断；这是怀疑，不是已确认关系。"
                report["suspected_duplicates"].append(reason)
                report["relation_explanations"].append(reason)
                continue
        matched = [t for t in terms if t and t in (note.title + "\n" + note.body).lower()]
        hit = hits.get(rel, {})
        explanation = (f"[[{rel}]]：关键词命中（{', '.join(matched[:4]) or '查询词'}）；"
                       f"选取方式：{hit.get('selected_by', 'live_scan')}；"
                       f"关系类型：相关知识（待人工确认，检索不等于事实核实）。")
        report["related"].append(rel)
        report["relation_explanations"].append(explanation)
    # usable candidates only; suspicions do not make a "found" status
    report["link_search"] = CANDIDATES_FOUND if report["related"] else NO_MATCH
    # Anything proposed but not verifiable in the index stays pending, never related.
    report["pending_links"] = list(dict.fromkeys(
        p for p in proposed if p not in index.by_rel or p in {n.rel for n in selection.notes}))
    return report
