"""Dependency regressions: real source -> reconcile -> review -> apply -> SQLite."""
import json
from contextlib import closing
import sqlite3
from unittest.mock import Mock, patch

import pytest

from core.dependencies import impact, stale
from core.derived_index import DerivedIndexError, _document, cache_path, rebuild
from core.reconcile import _patch_header, make_reconcile_plan
from core.vault import parse_frontmatter
from scripts import kb_index as cli
from tests.test_reconcile import plan, review_apply, vault


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def publish(case, title, source='raw/a.md', quote='An evidence record.', *, target=None, rid=None):
    # Include a line hint because a derived source repeats its claim in frontmatter.
    text = (case.root / source).read_text(encoding='utf-8-sig')
    line = next(i for i, value in enumerate(text.splitlines(), 1) if value == quote)
    response = {'decision': 'update' if target else 'create', 'reason': 'Refresh source version', 'conflicts': [],
                'claims': [{'statement': f'{title} observation.', 'kind': 'fact', 'confidence': 'medium',
                            'evidence': [{'source': source, 'quote': quote, 'start_line': line, 'relation': 'supports'}]}]}
    result = make_reconcile_plan(case.cfg, title, [source], target=target, plan_run_id=rid or title,
                                completion=Mock(return_value=json.dumps(response)))
    assert result['reconcile']['decision'] == response['decision'], result
    review_apply(case, result)
    return result['planned_pages'][0]


def pending(cfg):
    return {row['path']: row for row in stale(cfg)['pending_updates']}


def test_transitive_stale_survives_rebuild_and_clears_only_after_upstream_refresh(vault):
    upstream = publish(vault, 'Upstream')
    downstream = publish(vault, 'Downstream', upstream['rel_path'], 'Upstream observation.')
    rebuild(vault.cfg)
    potential = impact(vault.cfg, 'raw/a.md')
    assert potential['mode'] == 'potential'
    dependents = {n['path']: n for n in potential['dependents']}
    assert dependents[downstream['rel_path']]['via'] == ['raw/a.md', upstream['rel_path'], downstream['rel_path']]
    assert dependents[upstream['rel_path']]['depth'] == 1
    assert impact(vault.cfg, upstream['object_id'])['dependents'][0]['object_id'] == downstream['object_id']
    assert pending(vault.cfg) == {}

    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nNew information.')
    before = snapshot(vault.root)
    affected = pending(vault.cfg)
    assert set(affected) == {upstream['rel_path'], downstream['rel_path']}
    first, second = affected[upstream['rel_path']], affected[downstream['rel_path']]
    assert first['action'] == 'reconcile'
    assert first['claim_ids'] and second['claim_ids']
    assert first['claims'][0]['dependency_state'] == 'stale'
    assert second['blocked_by'] == [upstream['rel_path']]
    assert second['action'] == 'review_upstream' and 'reconcile_args' not in second
    assert first['reconcile_args'] == ['python', 'scripts/reconcile.py', 'Upstream', '--target',
                                       upstream['object_id'], '--source', 'raw/a.md']
    assert snapshot(vault.root) == before
    rebuild(vault.cfg)
    assert set(pending(vault.cfg)) == set(affected)  # Rebuilding is NOT evidence refresh.

    new_upstream = publish(vault, 'Upstream', target=upstream['object_id'], rid='refresh-upstream')
    assert (new_upstream['object_id'], new_upstream['revision']) == (upstream['object_id'], 2)
    assert pending(vault.cfg)[upstream['rel_path']]['action'] == 'refresh_index'
    rebuild(vault.cfg)
    remaining = pending(vault.cfg)
    assert set(remaining) == {downstream['rel_path']}
    assert remaining[downstream['rel_path']]['action'] == 'reconcile'
    new_downstream = publish(vault, 'Downstream', upstream['rel_path'], 'Upstream observation.',
                             target=downstream['object_id'], rid='refresh-downstream')
    assert (new_downstream['object_id'], new_downstream['revision']) == (downstream['object_id'], 2)
    rebuild(vault.cfg)
    assert not pending(vault.cfg)


def test_same_source_current_consumer_is_not_marked_stale_with_old_consumer(vault):
    old = publish(vault, 'Old')
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nA new version.')
    fresh = publish(vault, 'Fresh')
    rebuild(vault.cfg)
    assert set(pending(vault.cfg)) == {old['rel_path']}
    assert fresh['rel_path'] in {n['path'] for n in impact(vault.cfg, 'raw/a.md')['dependents']}


def test_only_claims_dependent_on_changed_source_are_selected(vault):
    vault.install_note('raw/b.md', '# Another\nA second observation.')
    proposal = plan(vault, ['raw/a.md', 'raw/b.md'], topic='Split', model=Mock(return_value=json.dumps({
        'decision': 'create', 'reason': 'Two observations', 'conflicts': [],
        'claims': [{'statement': statement, 'kind': 'fact', 'confidence': 'medium',
                    'evidence': [{'source': source, 'quote': quote, 'relation': 'supports'}]}
                   for statement, source, quote in [('First fact.', 'raw/a.md', 'An evidence record.'),
                                                     ('Second fact.', 'raw/b.md', 'A second observation.')]]})))
    review_apply(vault, proposal)
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nChanged')
    item = stale(vault.cfg)['pending_updates'][0]
    assert [c['statement'] for c in item['claims']] == ['First fact.']


def test_plain_links_and_related_are_not_dependency_edges(vault):
    text = vault.content('See [[raw/a.md]].').replace('sources: ["raw/a.md"]', 'sources: []\nrelated: ["raw/a.md"]')
    vault.install_note('wiki/topics/linked.md', text)
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nChanged')
    assert not impact(vault.cfg, 'raw/a.md')['dependents']
    assert not pending(vault.cfg)


def test_unversioned_legacy_sources_are_explicitly_unknown_not_rebased(vault):
    vault.install_note('wiki/topics/legacy.md', vault.content())
    rebuild(vault.cfg)
    assert stale(vault.cfg)['coverage']['unversioned_dependencies'] == 1
    assert not pending(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nChanged since index')
    assert stale(vault.cfg)['signals'][0]['reason'] == 'changed_since_index'
    rebuild(vault.cfg)
    report = stale(vault.cfg)
    assert not report['signals']
    assert report['coverage']['unversioned_dependencies'] == 1
    assert impact(vault.cfg, 'raw/a.md')['direct_edges'][0]['expected_sha256'] is None


def test_missing_source_keeps_dependencies_and_requires_manual_review(vault):
    topic = publish(vault, 'Missing')
    rebuild(vault.cfg)
    (vault.root / 'raw/a.md').unlink()
    for _ in range(2):
        item = pending(vault.cfg)[topic['rel_path']]
        assert item['unavailable_sources'] == ['raw/a.md']
        assert item['action'] == 'manual_review'
        assert 'reconcile_args' not in item
        assert impact(vault.cfg, 'raw/a.md')['dependents']
        rebuild(vault.cfg)


def test_legacy_cycle_terminates_and_blocks_circular_update_order(vault):
    vault.install_note('wiki/topics/a.md', vault.content().replace(
        'sources: ["raw/a.md"]', 'sources: ["raw/a.md", "wiki/topics/b.md"]'))
    vault.install_note('wiki/topics/b.md', vault.content().replace(
        'sources: ["raw/a.md"]', 'sources: ["wiki/topics/a.md"]'))
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nChanged')
    affected = pending(vault.cfg)
    assert set(affected) == {'wiki/topics/a.md', 'wiki/topics/b.md'}
    assert all(n['action'] == 'review_upstream' for n in affected.values())
    assert affected['wiki/topics/a.md']['blocked_by'] == ['wiki/topics/b.md']
    assert len(impact(vault.cfg, 'wiki/topics/a.md')['dependents']) == 1


def test_changed_target_is_not_given_an_executable_refresh_suggestion(vault):
    topic = publish(vault, 'Edited')
    rebuild(vault.cfg)
    target = vault.root / topic['rel_path']
    target.write_bytes(target.read_bytes() + b'\nHuman addition')
    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nChanged source')
    before = snapshot(vault.root)
    item = pending(vault.cfg)[topic['rel_path']]
    assert item['current_status'] == 'changed'
    assert item['action'] == 'refresh_index' and 'reconcile_args' not in item
    assert snapshot(vault.root) == before


def test_references_never_expand_scope_or_read_external_files(vault, tmp_path):
    vault.install_note('private/secret.md', '# Not in scope')
    vault.install_note('wiki/topics/private.md', vault.content().replace(
        'sources: ["raw/a.md"]', 'sources: ["private/secret.md", "../external.md", "https://example.invalid/a.md"]'))
    rebuild(vault.cfg)
    with patch('core.dependencies._document', wraps=_document) as read:
        report = stale(vault.cfg)
    assert all(call.args[1] != 'private/secret.md' for call in read.call_args_list)
    assert report['signals'][0]['reason'] == 'unavailable_or_out_of_scope'
    assert len(report['warnings']) == 2
    assert report['pending_updates'][0]['action'] == 'manual_review'


def test_evidence_location_mismatch_is_not_hidden_by_matching_source_hash(vault):
    topic = publish(vault, 'Locator')
    target = vault.root / topic['rel_path']
    text = target.read_text(encoding='utf-8')
    state = parse_frontmatter(text)[0]['reconcile_state']
    evidence = state['claims'][0]['evidence'][0]
    evidence['start'] += 1
    evidence['end'] += 1
    target.write_bytes(_patch_header(text, {'reconcile_state': state}).encode('utf-8'))
    rebuild(vault.cfg)
    report = stale(vault.cfg)
    assert [s['reason'] for s in report['signals']] == ['evidence_mismatch']
    assert report['pending_updates'][0]['action'] == 'manual_review'
    assert report['pending_updates'][0]['claim_ids'] == [state['claims'][0]['claim_id']]


def test_cli_is_readonly_without_models_or_queue_entries(vault, capsys):
    publish(vault, 'CLI')
    rebuild(vault.cfg)
    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nChanged')
    before = snapshot(vault.root)
    with patch.object(cli, 'config', return_value=vault.cfg), patch('core.reconcile.call_chat_completion') as model:
        for args in [['stale'], ['impact', 'raw/a.md']]:
            assert cli.main(args) == 0
        model.assert_not_called()
    assert '"dependency_state": "stale"' in capsys.readouterr().out
    assert snapshot(vault.root) == before


def test_old_cache_requires_rebuild_and_missing_cache_is_not_created(vault):
    with pytest.raises(DerivedIndexError, match='索引不存在'):
        stale(vault.cfg)
    assert not cache_path(vault.cfg).exists()
    rebuild(vault.cfg)
    with closing(sqlite3.connect(cache_path(vault.cfg))) as conn, conn:
        conn.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
    with pytest.raises(DerivedIndexError, match='版本'):
        stale(vault.cfg)
    rebuild(vault.cfg)
    assert not pending(vault.cfg)
