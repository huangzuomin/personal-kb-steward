"""Read-only dependency impact and stale-review worklist over the derived cache.

No stale flag is written to Markdown or SQLite. A changed dependency calls for
review, not a claim that the old assertion is false. Only explicit provenance
edges propagate; repeated/cyclic paths are visited once per changed source.
"""
from __future__ import annotations

from collections import defaultdict, deque
import datetime as dt
import sqlite3
from typing import Any

from .claims import Evidence, evidence_status
from .config import kb_root
from .derived_index import DerivedIndexError, _document, _info, _open

NOTICE = ("依赖图来自索引快照，新增/改名/改动依赖后请重建。stale 仅表示需复查，不表示结论错误。"
          "无版本 sources 不能证明新鲜；清单不改页面、不写审核队列、不调用模型。")


class _Graph:
    def __init__(self, cfg: dict[str, Any], conn: sqlite3.Connection):
        self.root = kb_root(cfg)
        self.notes = {r['path']: dict(r) for r in conn.execute(
            'SELECT path,object_id,revision,title,type,status,sha256 FROM notes')}
        self.edges = [dict(r) for r in conn.execute(
            'SELECT * FROM dependencies ORDER BY source,dependent,claim_id,relation')]
        self.outgoing = defaultdict(list)
        self.incoming = defaultdict(list)
        for edge in self.edges:
            self.outgoing[edge['source']].append(edge)
            self.incoming[edge['dependent']].append(edge)
        self.claims = {(r['path'], r['claim_id']): dict(r) for r in conn.execute('SELECT * FROM claims')}
        self.evidence = defaultdict(list)
        for r in conn.execute('SELECT * FROM evidence'):
            e = Evidence(**{key: r[key] for key in Evidence.__dataclass_fields__})
            self.evidence[(r['path'], r['claim_id'], e.source, e.relation)].append(e)
        self.documents: dict[str, dict | None] = {}

    def document(self, source: str) -> dict | None:
        # References never expand the configured scan scope or follow links.
        if source not in self.documents:
            self.documents[source] = _document(self.root, source) if source in self.notes else None
        return self.documents[source]

    def current_status(self, path: str) -> str:
        doc = self.document(path)
        return 'unavailable' if doc is None else 'matched' if doc['sha256'] == self.notes[path]['sha256'] else 'changed'

    def reason(self, edge: dict) -> str | None:
        source = edge['source']
        if source not in self.notes:
            return 'unavailable_or_out_of_scope'
        doc = self.document(source)
        if doc is None:
            return 'unavailable'
        if edge['expected_sha256'] is not None:
            if doc['sha256'] != edge['expected_sha256']:
                return 'source_changed'
            key = (edge['dependent'], edge['claim_id'], source, edge['relation'])
            if any(evidence_status(e, doc) != 'matched' for e in self.evidence[key]):
                return 'evidence_mismatch'
        elif doc['sha256'] != self.notes[source]['sha256']:
            return 'changed_since_index'  # No author-time baseline for legacy references.
        return None


def _walk(graph: _Graph, source: str, seeds: list[dict]) -> dict[str, dict]:
    """Shortest witness per dependent plus all incoming affected claim IDs."""
    found: dict[str, dict] = {}
    visited = {source}
    queue = deque()

    def add(edge: dict, via: list[str]) -> None:
        target = edge['dependent']
        if target == source:
            return
        item = found.setdefault(target, {'path': target, 'via': via, 'claim_ids': set()})
        if edge['claim_id']:
            item['claim_ids'].add(edge['claim_id'])
        if target not in visited:
            visited.add(target)
            queue.append((target, via))

    for edge in seeds:
        add(edge, [source, edge['dependent']])
    while queue:
        parent, via = queue.popleft()
        for edge in graph.outgoing[parent]:
            add(edge, [*via, edge['dependent']])
    return found


def impact(cfg: dict[str, Any], source: str) -> dict:
    """Potential downstream impact, even for an unchanged source. Does not mark stale."""
    with _open(cfg) as conn:
        graph = _Graph(cfg, conn)
        if source.startswith('kb:'):
            matches = [n['path'] for n in graph.notes.values() if n['object_id'] == source]
            if not matches:
                raise DerivedIndexError('索引中没有该对象，请重建后检查')
            source = matches[0]
        if source not in graph.notes and source not in graph.outgoing:
            raise DerivedIndexError('索引中没有该来源或依赖，请重建后检查')
        affected = _walk(graph, source, graph.outgoing[source])
        dependents = [{**graph.notes[path], 'via': item['via'], 'depth': len(item['via']) - 1,
                       'claim_ids': sorted(item['claim_ids'])}
                      for path, item in sorted(affected.items())]
        return {**_info(conn), 'notice': NOTICE, 'mode': 'potential', 'source': source,
                'dependents': dependents, 'direct_edges': graph.outgoing[source]}


def stale(cfg: dict[str, Any]) -> dict:
    """Compare recorded source versions with current bytes, then propagate review.

    This explicitly scans indexed dependency sources; it is not a background watcher.
    The worklist is recomputed each run so a successful reconcile/rebuild clears it.
    """
    with _open(cfg) as conn:
        graph = _Graph(cfg, conn)
        seeds = defaultdict(list)
        signals = []
        for edge in graph.edges:
            reason = graph.reason(edge)
            if reason:
                doc = graph.document(edge['source'])
                signals.append({**edge, 'reason': reason,
                                'current_sha256': doc['sha256'] if doc else None})
                seeds[edge['source']].append(edge)
        affected: dict[str, dict] = {}
        for source, edges in sorted(seeds.items()):
            for path, found in _walk(graph, source, edges).items():
                item = affected.setdefault(path, {'path': path, 'claim_ids': set(), 'causes': []})
                item['claim_ids'].update(found['claim_ids'])
                item['causes'].append({'source': source, 'via': found['via'],
                                       'direct': len(found['via']) == 2})
        mismatched = {s['dependent'] for s in signals if s['reason'] == 'evidence_mismatch'}
        pending = []
        for path, item in sorted(affected.items()):
            note = graph.notes[path]
            sources = sorted({e['source'] for e in graph.incoming[path]})
            blocked = [s for s in sources if s in affected]
            missing = [s for s in sources if graph.document(s) is None]
            current = graph.current_status(path)
            action = ('refresh_index' if current != 'matched' else 'review_upstream' if blocked else
                      'manual_review' if missing or path in mismatched or note['type'] != 'topic-page' else 'reconcile')
            claims = [{**graph.claims[(path, cid)], 'dependency_state': 'stale'}
                      for cid in sorted(item['claim_ids'])]
            entry = {**note, 'dependency_state': 'stale', 'current_status': current,
                     'claim_ids': sorted(item['claim_ids']), 'claims': claims, 'causes': item['causes'],
                     'sources': sources, 'blocked_by': blocked, 'unavailable_sources': missing, 'action': action}
            if action == 'reconcile':
                # Arguments, not a shell string; never execute automatically.
                args = ['python', 'scripts/reconcile.py', note['title'], '--target', note['object_id'] or path]
                for source in sources:
                    args.extend(['--source', source])
                entry['reconcile_args'] = args
            pending.append(entry)
        pending.sort(key=lambda item: (item['action'] != 'reconcile', item['path']))
        return {**_info(conn), 'notice': NOTICE, 'mode': 'observed',
                'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'coverage': {'dependencies': len(graph.edges),
                             'unversioned_dependencies': sum(e['expected_sha256'] is None for e in graph.edges),
                             'checked_sources': len(graph.outgoing)},
                'signals': signals, 'pending_updates': pending}
