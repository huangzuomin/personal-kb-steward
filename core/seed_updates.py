"""Conservative seed reuse: exact topic updates, similar titles only flag review.

No semantic auto-merge, no source rewrites. Updates append candidate material to
an existing seed; handwritten body/custom YAML survive. Plan/apply owns revisions.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from difflib import SequenceMatcher

from .config import sha256_text
from .layout import knowledge_dirs
from .plan_objects import update_base
from .reconcile import _patch_header, _text
from .vault import parse_frontmatter


def _key(title: str) -> str:
    return re.sub(r"[^\w]", "", unicodedata.normalize('NFKC', title).casefold())


def prepare_seed_updates(index, cfg: dict, pages: list[dict]) -> tuple[list[dict], list[str]]:
    prefix = knowledge_dirs(cfg)['seed_dir'] + '/'
    existing = [n for n in index.notes if n.rel.startswith(prefix) and n.metadata.get('type') == 'seed-card']
    result, issues = [], []
    targets = set()
    for page in pages:
        meta, body = parse_frontmatter(page['content'])
        key = _key(str(meta.get('title', '')))
        exact = [n for n in existing if _key(n.title) == key]
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
            issues.append('同名 seed 不唯一，停止新建并保留原页：' + ', '.join(n.rel for n in exact))
            continue
        sources = list(dict.fromkeys(page.get('sources', [])))
        hashes = {rel: index.by_rel[rel].sha256 for rel in sources if rel in index.by_rel}
        if len(hashes) != len(sources):
            issues.append('seed 引用不在扫描范围，保留原页且不生成更新：' + str(meta.get('title')))
            continue
        if exact:
            note = exact[0]
            previous = note.metadata.get('seed_state', {})
            old_hashes = previous.get('source_hashes', {}) if isinstance(previous, dict) else {}
            if not isinstance(old_hashes, dict):
                old_hashes = {}
            if hashes and all(old_hashes.get(rel) == h for rel, h in hashes.items()):
                continue  # The source versions have already been incorporated.
            old_sources = note.metadata.get('sources', [])
            if not isinstance(old_sources, list) or not all(isinstance(s, str) for s in old_sources):
                issues.append('既有 seed 来源格式无效，请先修正：' + note.rel)
                continue
            sources = list(dict.fromkeys(old_sources + sources))
            if any(rel not in index.by_rel for rel in sources):
                issues.append('既有 seed 来源缺失，请先复核：' + note.rel)
                continue
            original = _text(note)  # Checks snapshot hash; preserves BOM and line endings.
            newline = '\r\n' if '\r\n' in original else '\n'
            content = _patch_header(original, {
                'sources': sources, 'updated': dt.date.today().isoformat(), 'review_required': True,
                'confidence': page.get('confidence', 'low'), 'status': meta.get('status', 'manual_review'),
                'stage': meta.get('stage', 'candidate'),
                'origin': {'source_paths': sources, 'operation': 'mindseed-grow'},
                'seed_state': {'version': 1, 'source_hashes': {**old_hashes, **hashes}},
            })
            addition = body.replace("\r\n", "\n")
            addition = re.sub(r"^#{1,2} ", "### ", addition, flags=re.M).replace("\n", newline)
            content += newline + '## 本轮补充提案（原有正文保留）' + newline + newline + addition
            page.update(operation='update', rel_path=note.rel, content=content,
                        review_required=True, sources=sources,
                        origin={'source_paths': sources, 'operation': 'mindseed-grow'}, **update_base(note))
        else:
            # Stable create path: no timestamp duplicates for an identical title.
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]#]', '-', str(meta['title'])).strip(' .-')[:70] or 'seed'
            page['rel_path'] = f'{prefix}{name}.md'
            if (index.root / page['rel_path']).exists():
                issues.append('seed 目标已占用，停止新建：' + page['rel_path'])
                continue
            page['content'] = _patch_header(page['content'], {'seed_state': {'version': 1, 'source_hashes': hashes}})
        if page['rel_path'] in targets:
            issues.append('本批同主题重复提案已拦截：' + page['rel_path'])
            continue
        targets.add(page['rel_path'])
        # The plan references both retained and new sources. Pin all of them at
        # this generation snapshot; do not refresh them when saving or applying.
        page['retrieval_source_hashes'] = {rel: index.by_rel[rel].sha256 for rel in sources}
        page['content_sha256'] = sha256_text(page['content'])
        result.append(page)
    return result, issues
