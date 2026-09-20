"""Extract source sentences for seeds, not heading/task-template previews.

This is a deterministic excerpt filter, NOT a semantic truth/quality score.
Clustering confidence is kept separate from the review status of a knowledge page.
"""
from __future__ import annotations

import re

from .signal_extraction import signal_sentences

_EMPTY_REASON = re.compile(r"无(?:额外)?实质内容|无额外内容|仅[有含].{0,30}(?:打卡|例程)|no substantive content|only routine", re.I)


def seed_item(cluster: dict, notes: list[dict], cfg: dict) -> dict:
    by_rel = {n['rel']: n for n in notes}
    sources = list(dict.fromkeys(s for s in cluster.get('sources', []) if s in by_rel))
    signals = []
    for source in sources:
        for sentence in signal_sentences(by_rel[source].get('body', ''), limit=2):
            # Quoted source text is not a new link instruction; only the program's
            # provenance suffix becomes a wikilink in the generated page.
            display = sentence.replace('[[', '［［').replace(']]', '］］')
            signals.append(f'{display}（[[{source}]]）')
    cluster_confidence = cluster.get('confidence', 'low')
    pending = cluster.get('pending_links') or []
    if not isinstance(pending, list) or not all(isinstance(p, str) for p in pending):
        pending = []
    reasons = []
    if not signals or _EMPTY_REASON.search(str(cluster.get('reasoning', ''))):
        reasons.append('未抽取到足够的实质信息，或聚类说明自述无实质内容；仅保留待审核提案，不应直接入库。')
    minimum = int(cfg.get('quality_gate', {}).get('min_sources_for_seed', 2))
    if len(sources) < minimum:
        reasons.append(f'仅 {len(sources)} 个来源，低于 seed 复核阈值 {minimum}；单条有价值的想法仍可人工保留。')
    if pending and cfg.get('quality_gate', {}).get('manual_review_on_unresolved_link', True):
        reasons.append('存在尚未解析的待创建链接，需要人工确认。')
    if cluster_confidence not in {'medium', 'high'}:
        reasons.append('聚类置信度低或无效，需要确认主题边界。')
    # Even a confident cluster is only a proposed interpretation of its sources.
    # Empty/single-source content must never inherit high confidence from grouping.
    return {
        'title': cluster['title'], 'type': 'seed-card',
        'status': 'manual_review' if reasons else 'seed',
        'stage': 'needs_context' if reasons else 'candidate',
        'sources': sources,
        'summary': str(cluster.get('reasoning') or '根据来源摘句形成的候选议题，主题边界待确认。'),
        'signals': signals[:6], 'keywords': cluster.get('terms', [])[:4],
        'growth_directions': ['核对摘句能否支持核心议题，再收窄研究问题。', '来源充分后再生成选题或证据包。'],
        'related': [], 'pending_links': pending,
        'tags': cluster.get('tags', ['seed']),
        'cluster_confidence': cluster_confidence,
        'confidence': 'low' if reasons else 'medium', 'review_required': True,
        'origin': {'source_paths': sources, 'operation': 'mindseed-grow'},
        'manual_review': reasons or ['摘句确实存在不等于主题已获证明，请核对信息量和主题边界。'],
    }
