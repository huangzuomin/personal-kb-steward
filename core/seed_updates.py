"""Conservative seed reuse: exact topic updates, similar titles only flag review.

No semantic auto-merge, no source rewrites. Updates append candidate material to
an existing seed; handwritten body/custom YAML survive. Plan/apply owns revisions.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from difflib import SequenceMatcher

from .config import sha256_text
from .knowledge_objects import identity_from_metadata
from .layout import knowledge_dirs
from .plan_objects import update_base
from .reconcile import _patch_header, _text
from .vault import parse_frontmatter


def _key(title: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize('NFKC', title).casefold())


def _recorded_units(state) -> set[str] | None:
    """Thought units already incorporated into an existing seed; None = legacy record."""
    if not isinstance(state, dict):
        return None
    recorded = state.get('thought_units')
    if not isinstance(recorded, list) or not all(isinstance(u, str) for u in recorded):
        return None
    return set(recorded)


def _page_identity(meta: dict) -> dict:
    """Atomic page identity: thought id + claim digest + exact source-information units.
    card_state (versioned) is preferred; bare thought_units is a fallback."""
    state = meta.get('card_state') if isinstance(meta.get('card_state'), dict) else {}
    raw_units = state.get('thought_units') or meta.get('thought_units')
    if isinstance(raw_units, str):
        try:
            raw_units = json.loads(raw_units)
        except ValueError:
            raw_units = []
    units = {str(u) for u in raw_units} if isinstance(raw_units, list) else set()
    kind = state.get('thought', {}).get('kind') if isinstance(state.get('thought'), dict) else None
    return {"units": units,
            "thought_id": state.get('thought_id') if isinstance(state.get('thought_id'), str) else None,
            "statement_sha256": state.get('statement_sha256') if isinstance(state.get('statement_sha256'), str) else None,
            "kind": kind if kind in ("question", "assertion") else None}


def _recorded_identity(state) -> dict | None:
    """Confirmed identity of an existing atomic seed; None = legacy record.

    thought_id is the EVIDENCE-VERSION fingerprint at last merge; object reuse
    for repeats relies on (kind, statement_sha256) + contained evidence, not on
    the stored fingerprint alone."""
    if not isinstance(state, dict) or not isinstance(state.get('thought_id'), str):
        return None
    units = _recorded_units(state)
    return {"thought_id": state['thought_id'], "units": units or set(),
            "statement_sha256": state.get('statement_sha256')
            if isinstance(state.get('statement_sha256'), str) else None,
            "kind": state.get('kind') if state.get('kind') in ("question", "assertion") else None,
            "source_hashes": state.get('source_hashes')
            if isinstance(state.get('source_hashes'), dict) else {}}


def _verified_hashes(sources, recorded_hashes, generation_hashes, index, issues, context: str,
                     *, atomic: bool):
    """Pin provenance WITHOUT rebinding or version mixing. Atomic records: a
    source path whose recorded verified hash differs from the proposal's
    generation hash is a VERSION CONFLICT and fails closed even if the
    generation hash matches the current index — old and new versions of one
    path are never mixed or relabeled. Legacy records (no stored verified
    hashes) keep their historical index-pinning semantics for retained sources."""
    merged = {}
    for rel in sources:
        recorded = recorded_hashes.get(rel)
        generated = generation_hashes.get(rel)
        if atomic and recorded and generated and recorded != generated:
            issues.append(f"{context}来源 {rel} 的新生成 hash 与既有已验证 hash 冲突"
                          f"（同一路径不允许混用新旧版本），需重新提取并人工复核。")
            return None
        expected = generated or recorded
        if expected is None:
            if not atomic and rel in index.by_rel:
                expected = index.by_rel[rel].sha256  # legacy semantics: pin current scan
            else:
                issues.append(f"{context}来源 {rel} 缺少已验证的生成/记录 hash，拒绝写入。")
                return None
        if rel not in index.by_rel or index.by_rel[rel].sha256 != expected:
            issues.append(f"{context}来源 {rel} 的快照与当前索引不一致（来源已变化或提案被篡改），拒绝写入而非重绑。")
            return None
        merged[rel] = expected
    return merged


def prepare_seed_updates(index, cfg: dict, pages: list[dict], *, return_outcomes: bool = False):
    prefix = knowledge_dirs(cfg)['seed_dir'] + '/'
    existing = [n for n in index.notes if n.rel.startswith(prefix) and n.metadata.get('type') == 'seed-card']
    result, issues = [], []
    receipt_outcomes: dict[int, dict] = {}
    targets = set()
    batch_units: dict[str, dict] = {}
    def mark(candidate: int, page: dict, disposition: str, targets_: list[str] | None = None,
             reason: str = '', note=None) -> None:
        snapshots = {}
        if disposition == 'noop' and note is not None:
            try:
                identity = identity_from_metadata(note.metadata)
            except (TypeError, ValueError):
                identity = None
            if identity is not None and type(identity[1]) is int:
                snapshots[str(note.rel)] = {
                    'content_sha256': str(note.sha256), 'object_id': identity[0],
                    'revision': identity[1], 'canonical_path': str(note.rel),
                    'verification': 'updater_index',
                }
        receipt_outcomes[candidate] = {
            'sources': list(dict.fromkeys(str(rel) for rel in page.get('sources', []) if rel)),
            'updater_disposition': disposition,
            'required_targets': list(dict.fromkeys(str(target) for target in (targets_ or []) if target)),
            'updater_target_snapshots': snapshots,
            'reason': str(reason or ''),
        }
    for candidate, page in enumerate(pages):
        meta, body = parse_frontmatter(page['content'])
        key = _key(str(meta.get('title', '')))
        page_id = _page_identity(meta)
        new_units = page_id['units']
        exact = [n for n in existing if _key(n.title) == key]
        # Stable identity lookup is NOT limited to exact title: a confirmed
        # thought keeps its id even if its title was later edited by hand.
        if page_id['thought_id']:
            same_id = [n for n in existing
                       if (_recorded_identity(n.metadata.get('seed_state')) or {}).get('thought_id')
                       == page_id['thought_id']]
            if same_id:
                exact = same_id
            elif not exact:
                # Same claim (statement/kind) with overlapping evidence targets
                # the confirmed object regardless of the stored title.
                claim_match = []
                for n in existing:
                    rec = _recorded_identity(n.metadata.get('seed_state'))
                    if (rec and rec['statement_sha256'] == page_id['statement_sha256']
                            and (rec['kind'] is None or page_id['kind'] is None
                                 or rec['kind'] == page_id['kind'])
                            and (page_id['units'] & rec['units'])):
                        claim_match.append(n)
                if claim_match:
                    exact = claim_match
        similar = [n for n in existing if key and SequenceMatcher(None, key, _key(n.title)).ratio() >= .78]
        # Similar names can describe distinct thoughts. Surface them for review,
        # never declare them the same object or change the target automatically.
        if not exact and similar:
            page['content'] = _patch_header(page['content'], {'related': [n.rel for n in similar],
                                                            'review_required': True})
            page['content'] += '\n## 疑似重复（先核对是否确为不同议题）\n\n' + ''.join(f'- [[{n.rel}]]\n' for n in similar)
            page['review_required'] = True
            issues.append('疑似同主题，不自动合并：' + ', '.join(n.rel for n in similar))
        if len(exact) > 1:
            reason = '同名 seed 不唯一，停止新建并保留原页：' + ', '.join(n.rel for n in exact)
            issues.append(reason)
            mark(candidate, page, 'blocked', [n.rel for n in exact], reason)
            continue
        sources = list(dict.fromkeys(page.get('sources', [])))
        hashes = {rel: index.by_rel[rel].sha256 for rel in sources if rel in index.by_rel}
        if len(hashes) != len(sources):
            reason = 'seed 引用不在扫描范围，保留原页且不生成更新：' + str(meta.get('title'))
            issues.append(reason)
            mark(candidate, page, 'blocked', [], reason)
            continue
        # The proposal's own verified generation hashes win over the current index.
        generation_hashes = meta.get('source_hashes') if isinstance(meta.get('source_hashes'), dict) else {}
        note = exact[0] if exact else None
        recorded = _recorded_identity(note.metadata.get('seed_state')) if note else None
        if note and recorded and page_id['thought_id']:
            # Provenance BEFORE any identity/containment NOOP: a proposal whose
            # generation hash conflicts with the recorded hash of the same path
            # must report a mismatch, never silently count as a harmless repeat.
            conflicts = [rel for rel in sources
                         if recorded['source_hashes'].get(rel)
                         and generation_hashes.get(rel)
                         and generation_hashes[rel] != recorded['source_hashes'][rel]]
            if conflicts:
                reason = ('atomic 更新拒绝：来源 ' + ', '.join(conflicts)
                          + ' 的新生成 hash 与既有已验证 hash 冲突（同一路径不允许混用新旧版本），需重新提取并人工复核。')
                issues.append(reason)
                mark(candidate, page, 'blocked', [note.rel], reason)
                continue
            stale = [rel for rel in sources
                     if generation_hashes.get(rel)
                     and (rel not in index.by_rel or index.by_rel[rel].sha256 != generation_hashes[rel])]
            if stale:
                reason = ('atomic 提案过期：来源 ' + ', '.join(stale)
                          + ' 在生成后已发生变化，需重新提取；不作为无害重复跳过。')
                issues.append(reason)
                mark(candidate, page, 'blocked', [note.rel], reason)
                continue
            # Atomic identity: same title is NOT the same object. Object reuse
            # keys on (kind, exact statement) + evidence containment, not on the
            # stored evidence-version fingerprint alone.
            same_claim = (page_id['statement_sha256'] == recorded['statement_sha256']
                          and (recorded['kind'] is None or page_id['kind'] is None
                               or page_id['kind'] == recorded['kind']))
            if page_id['thought_id'] == recorded['thought_id']:
                mark(candidate, page, 'noop', [note.rel], '已确认的相同原子念头与证据版本已存在。', note)
                continue  # Identical evidence-version repeat: already incorporated.
            if same_claim and new_units and new_units <= recorded['units']:
                mark(candidate, page, 'noop', [note.rel], '新提案证据已包含在已确认 seed 中。', note)
                continue  # Proposed evidence already contained in the confirmed object.
            if same_claim and new_units and (new_units & recorded['units']):
                # Same claim, NEW evidence: reviewed update of the same object.
                # The stored fingerprint becomes the merged evidence-version id.
                page['unit_merge'] = sorted(recorded['units'] | new_units)
            elif same_claim and new_units:
                note = None
                page['_distinct'] = True
                page['_distinct_issue'] = '同判断但证据无交集，不自动合并，需人工确认是否同一念头'
            elif new_units and (new_units & recorded['units']):
                note = None
                page['_distinct'] = True
                page['_distinct_issue'] = '同源信息但判断表述变化，不自动合并，需人工确认后再合并'
            elif new_units and new_units <= recorded['units']:
                note = None
                page['_distinct'] = True
                page['_distinct_issue'] = '同源信息但表述不同，不自动合并，需人工确认是否同一念头'
            else:
                note = None  # Distinct thought: fall through to a disambiguated create.
                page['_distinct'] = True
        elif note and recorded is None and page_id['thought_id']:
            # An old seed WITHOUT the versioned atomic card_state: never adopt or
            # rewrite it because the title matches. Separate reviewed atomic card.
            note = None
            page['_distinct'] = True
            page['_distinct_issue'] = '同名旧卡缺少原子 card_state 版本状态，不自动改写，已另建新卡待复核'
        elif note and recorded is None:
            previous = note.metadata.get('seed_state', {})
            old_hashes = previous.get('source_hashes', {}) if isinstance(previous, dict) else {}
            if not isinstance(old_hashes, dict):
                old_hashes = {}
            if hashes and all(old_hashes.get(rel) == h for rel, h in hashes.items()):
                mark(candidate, page, 'noop', [note.rel], 'legacy seed 已包含当前来源版本。', note)
                continue  # The source versions have already been incorporated (legacy record).
        if note:
            old_sources = note.metadata.get('sources', [])
            if not isinstance(old_sources, list) or not all(isinstance(s, str) for s in old_sources):
                reason = '既有 seed 来源格式无效，请先修正：' + note.rel
                issues.append(reason)
                mark(candidate, page, 'blocked', [note.rel], reason)
                continue
            sources = list(dict.fromkeys(old_sources + sources))
            if any(rel not in index.by_rel for rel in sources):
                reason = '既有 seed 来源缺失，请先复核：' + note.rel
                issues.append(reason)
                mark(candidate, page, 'blocked', [note.rel], reason)
                continue
            original = _text(note)  # Checks snapshot hash; preserves BOM and line endings.
            newline = '\r\n' if '\r\n' in original else '\n'
            # Pin provenance WITHOUT rebinding: retained sources keep their
            # recorded verified hash, new ones the generation hash; every hash
            # must match the current index or the update fails closed here.
            recorded_hashes = recorded['source_hashes'] if recorded else {}
            merged_hashes = _verified_hashes(sources, recorded_hashes, generation_hashes,
                                             index, issues, 'seed 更新拒绝：',
                                             atomic=recorded is not None)
            if merged_hashes is None:
                mark(candidate, page, 'blocked', [note.rel], issues[-1] if issues else 'seed update blocked')
                continue  # stale or inconsistent evidence is never rebound
            pinned = merged_hashes
            state = {'version': 2, 'source_hashes': merged_hashes}
            merged = page.pop('unit_merge', None)
            if merged is not None:
                state['thought_units'] = merged
            elif new_units:
                state['thought_units'] = sorted(new_units)
            if page_id['thought_id']:
                # Coherent post-merge identity: the evidence-version digest of
                # the merged set, so a later identical repeat is a NOOP.
                state['thought_id'] = page_id['thought_id']
                state['statement_sha256'] = page_id['statement_sha256']
                state['kind'] = page_id['kind'] or (recorded['kind'] if recorded else None)
            content = _patch_header(original, {
                'sources': sources, 'updated': dt.date.today().isoformat(), 'review_required': True,
                'confidence': page.get('confidence', 'low'), 'status': meta.get('status', 'manual_review'),
                'stage': meta.get('stage', 'candidate'),
                'origin': {'source_paths': sources, 'operation': 'mindseed-grow'},
                'seed_state': state, 'source_hashes': merged_hashes,
            })
            # Persisted evidence state must include the same evidence the new
            # proposal renders: merge it into the versioned card_state.
            old_state = note.metadata.get('card_state') if isinstance(note.metadata.get('card_state'), dict) else {}
            new_state = meta.get('card_state') if isinstance(meta.get('card_state'), dict) else {}
            if old_state or new_state:
                merged_card = dict(old_state)
                merged_card.setdefault('version', 1)
                merged_card['type'] = 'seed-card'
                combined = list(old_state.get('evidence', [])) + list(new_state.get('evidence', []))
                seen_rows = set()
                deduped = []
                for row in combined:
                    key = (row.get('source'), row.get('quote_sha256') or row.get('quote'))
                    if key in seen_rows:
                        continue
                    seen_rows.add(key)
                    # Only evidence consistent with the pinned (verified) hashes
                    # is retained; stale same-path versions are never kept.
                    if (row.get('source') in merged_hashes
                            and row.get('source_sha256')
                            and merged_hashes[row['source']] != row['source_sha256']):
                        continue
                    deduped.append(row)
                merged_card['evidence'] = deduped
                if page_id['thought_id']:
                    # Synchronize the whole versioned state with the merged set.
                    merged_card['thought_units'] = sorted(set(old_state.get('thought_units', [])) | new_units)
                    merged_card['thought_id'] = page_id['thought_id']
                    merged_card['statement_sha256'] = page_id['statement_sha256']
                    merged_card['analysis'] = dict(new_state.get('analysis', old_state.get('analysis', {})))
                    merged_card['source_hashes'] = merged_hashes
                content = _patch_header(content, {'card_state': merged_card})
            addition = body.replace("\r\n", "\n")
            addition = re.sub(r"^#{1,2} ", "### ", addition, flags=re.M).replace("\n", newline)
            content += newline + '## 本轮补充提案（原有正文保留）' + newline + newline + addition
            page.update(operation='update', rel_path=note.rel, content=content,
                        review_required=True, sources=sources,
                        origin={'source_paths': sources, 'operation': 'mindseed-grow'}, **update_base(note))
            mark(candidate, page, 'update', [note.rel], 'atomic seed update proposal', note)
        else:
            # Stable create path: no timestamp duplicates for an identical title.
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#]', '-', str(meta['title'])).strip(' .-')[:70] or 'seed'
            page['rel_path'] = f'{prefix}{name}.md'
            assigned = batch_units.setdefault(page['rel_path'], {'units': set(), 'ids': set()})
            batch_repeat = bool(page_id['thought_id'] and page_id['thought_id'] in assigned['ids'])
            distinct_issue = page.pop('_distinct_issue', '') or '同名不同念头，不自动合并，已另建新卡待复核'
            distinct = page.pop('_distinct', False) or bool(
                assigned['ids'] and page_id['thought_id'] and page_id['thought_id'] not in assigned['ids'])
            taken = page['rel_path'] in targets or (index.root / page['rel_path']).exists()
            if batch_repeat or (taken and not distinct) or (assigned['ids'] and assigned['units'] and not distinct):
                reason = 'seed 目标已占用，停止新建：' + page['rel_path']
                issues.append(reason)
                mark(candidate, page, 'blocked', [page['rel_path']], reason)
                continue
            if taken and distinct:
                # Same-title distinct ideas get a deterministic disambiguated
                # card instead of being swallowed by the existing page.
                placed = False
                for suffix in range(2, 100):
                    candidate = f'{prefix}{name}-{suffix}.md'
                    if candidate not in targets and not (index.root / candidate).exists():
                        page['rel_path'] = candidate
                        batch_units[candidate] = {'units': set(new_units), 'ids': {page_id['thought_id']}}
                        issues.append(distinct_issue + '：' + candidate)
                        placed = True
                        break
                if not placed:
                    reason = 'seed 目标已占用，停止新建：' + page['rel_path']
                    issues.append(reason)
                    mark(candidate, page, 'blocked', [page['rel_path']], reason)
                    continue
            else:
                assigned['units'].update(new_units)
                if page_id['thought_id']:
                    assigned['ids'].add(page_id['thought_id'])
            state = {'version': 2, 'source_hashes': hashes}
            if new_units:
                state['thought_units'] = sorted(new_units)
            if page_id['thought_id']:
                state['thought_id'] = page_id['thought_id']
                state['statement_sha256'] = page_id['statement_sha256']
                state['kind'] = page_id['kind']
            # Create proposals whose claimed source SHA disagrees with the
            # actual index are rejected at this seam, never persisted.
            rejected = False
            for rel in sources:
                claimed = generation_hashes.get(rel)
                if claimed is not None and claimed != hashes[rel]:
                    issues.append('seed 新建提案的来源 SHA 与当前索引不一致，已拒绝：' + rel)
                    rejected = True
                    break
            if rejected:
                mark(candidate, page, 'blocked', [page['rel_path']], issues[-1] if issues else 'seed proposal rejected')
                continue
            page['content'] = _patch_header(page['content'], {
                'seed_state': state, 'source_hashes': hashes})
            pinned = hashes
            mark(candidate, page, 'create', [page['rel_path']], 'atomic seed create proposal')
        if page['rel_path'] in targets:
            reason = '本批同主题重复提案已拦截：' + page['rel_path']
            issues.append(reason)
            mark(candidate, page, 'blocked', [page['rel_path']], reason)
            continue
        targets.add(page['rel_path'])
        # The plan references both retained and new sources. Pin all of them at
        # this generation snapshot with VERIFIED hashes only; do not refresh
        # them when saving or applying.
        page['retrieval_source_hashes'] = dict(pinned)
        page['content_sha256'] = sha256_text(page['content'])
        result.append(page)
    if return_outcomes:
        outcomes = [receipt_outcomes.get(i, {
            'sources': list(dict.fromkeys(str(rel) for rel in page.get('sources', []) if rel)),
            'updater_disposition': 'blocked', 'required_targets': [],
            'updater_target_snapshots': {}, 'reason': 'seed updater produced no disposition',
        }) for i, page in enumerate(pages)]
        return result, issues, outcomes
    return result, issues
