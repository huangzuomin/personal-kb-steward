"""Concrete retrieval/cache regressions using real Markdown, SQLite and apply."""
from contextlib import closing
import sqlite3
from unittest.mock import patch

import pytest

from core.vault import build_index
from core.derived_index import DerivedIndexError, cache_path, rebuild, search, show, status
from core.knowledge_objects import ObjectIdentityError, new_object_id
from scripts import kb_index as cli
from tests.test_reconcile import plan, provider, review_apply, vault


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file() and '.kb' not in p.relative_to(root).parts}


def data_rows(cfg):
    with closing(sqlite3.connect(cache_path(cfg))) as conn:
        return {table: conn.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
                for table in ('notes', 'claims', 'evidence')}


def test_real_claims_are_rebuildable_searchable_and_queries_are_readonly(vault, capsys):
    first = plan(vault)
    review_apply(vault, first)
    page = first['planned_pages'][0]
    before = files(vault.root)
    built = rebuild(vault.cfg)
    assert built['counts'] == {'notes': len(build_index(vault.cfg).by_rel), 'objects': 1, 'claims': 1, 'evidence': 1}
    for kind, query in [('note', 'Source'), ('claim', 'measured'), ('evidence', 'record')]:
        hit = search(vault.cfg, query, kind=kind)['hits'][0]
        assert hit['item_kind'] == kind
        assert hit['current_status'] == 'matched'
        if kind != 'note':
            assert hit['object_id'] == page['object_id']
            assert hit['evidence'][0]['current_match_status'] == 'matched'
            assert hit['evidence'][0]['start_line'] == 3
    detail = show(vault.cfg, page['object_id'])
    assert detail['note']['revision'] == 1
    assert detail['claims'][0]['evidence'][0]['quote'] == 'An evidence record.'
    saved = data_rows(vault.cfg)
    cache_path(vault.cfg).unlink()
    rebuild(vault.cfg)
    assert data_rows(vault.cfg) == saved
    db_before = cache_path(vault.cfg).read_bytes()
    capsys.readouterr()
    with patch.object(cli, 'config', return_value=vault.cfg), patch('core.reconcile.call_chat_completion') as model:
        for args in [['status'], ['show', page['object_id']], ['search', 'measured', '--kind', 'claim']]:
            assert cli.main(args) == 0
        model.assert_not_called()
    assert '"item_kind": "claim"' in capsys.readouterr().out
    assert cache_path(vault.cfg).read_bytes() == db_before
    assert files(vault.root) == before
    assert list(cache_path(vault.cfg).parent.iterdir()) == [cache_path(vault.cfg)]


def test_chinese_short_words_mixed_english_and_metadata_filters(vault):
    vault.install_note('wiki/topics/中文.md', vault.content('前言 ' * 100 + '温州大黄鱼产业发展。AI agent knows evidence.', new_object_id()))
    vault.install_note('wiki/topics/other.md', vault.content('温州餐饮消费观察。', new_object_id()))
    rebuild(vault.cfg)
    result = search(vault.cfg, '大黄鱼 温州 AI', note_type='topic-page', note_status='growing')
    assert result['engine'] == 'fts5-trigram'
    assert [hit['path'] for hit in result['hits']] == ['wiki/topics/中文.md']
    assert '大黄鱼' in result['hits'][0]['snippet']
    assert len(search(vault.cfg, '温州')['hits']) == 2
    assert search(vault.cfg, '温州')['engine'] == 'short-substring-scan'
    assert all('温州' in hit['snippet'] for hit in search(vault.cfg, '温州')['hits'])
    assert search(vault.cfg, 'EVIDENCE')['hits']
    assert not search(vault.cfg, '温州', note_status='archived')['hits']
    assert not search(vault.cfg, '温州', note_type="topic-page' OR 1=1 --")['hits']


def test_special_characters_are_literals_not_query_operators(vault):
    vault.install_note('raw/punctuation.md', '# Literal\n100% literal * value "quoted" C++')
    rebuild(vault.cfg)
    for query in ['%', '*', '"quoted"', 'C++']:
        hits = search(vault.cfg, query)['hits']
        assert [hit['path'] for hit in hits] == ['raw/punctuation.md']
    for query in ['NOT', "' OR 1=1 --", 'unfindable']:
        assert search(vault.cfg, query)['hits'] == []
    assert status(vault.cfg)['counts']['notes'] == 2


def test_title_weighting_and_limit_are_deterministic(vault):
    vault.install_note('raw/body.md', '# Ordinary\nEvidence appears here.')
    vault.install_note('raw/title.md', '# Evidence\nIt appears in a title.')
    rebuild(vault.cfg)
    hits = search(vault.cfg, 'Evidence', limit=1)['hits']
    assert hits[0]['path'] == 'raw/title.md'
    assert search(vault.cfg, 'Evidence', limit=1)['hits'] == hits


def test_update_rename_delete_rebuild_reflects_current_identity(vault):
    first = plan(vault)
    review_apply(vault, first)
    original = first['planned_pages'][0]
    rebuild(vault.cfg)
    vault.install_note('raw/b.md', '# Second\n\nA second observation.')
    updated = plan(vault, ['raw/b.md'], target=original['object_id'], rid='updated', model=provider(
        'update', 'New synthesized observation. [[raw/a.md]] [[raw/b.md]]'))
    review_apply(vault, updated)
    assert show(vault.cfg, original['object_id'])['current_status'] == 'changed'
    renamed = vault.root / 'wiki/topics/改名.md'
    (vault.root / original['rel_path']).rename(renamed)
    assert show(vault.cfg, original['object_id'])['current_status'] == 'unavailable'
    rebuild(vault.cfg)
    note = show(vault.cfg, original['object_id'])['note']
    assert (note['path'], note['revision']) == ('wiki/topics/改名.md', 2)
    assert original['rel_path'] not in [h['path'] for h in search(vault.cfg, 'Evidence')['hits']]
    renamed.unlink()
    assert search(vault.cfg, 'synthesized')['hits'][0]['current_status'] == 'unavailable'
    rebuild(vault.cfg)
    assert search(vault.cfg, 'synthesized')['hits'] == []
    assert status(vault.cfg)['counts']['claims'] == 0


def test_stale_evidence_is_reported_without_rebinding_or_note_mutation(vault):
    first = plan(vault)
    review_apply(vault, first)
    target = first['planned_pages'][0]['object_id']
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nChanged source')
    item = show(vault.cfg, target)
    evidence = item['claims'][0]['evidence'][0]
    assert evidence['match_status_at_build'] == 'matched'
    assert evidence['current_match_status'] == 'source_changed'
    before = files(vault.root)
    rebuild(vault.cfg)
    item = show(vault.cfg, target)
    assert item['claims'][0]['evidence'][0]['match_status_at_build'] == 'source_changed'
    assert item['claims'][0]['evidence'][0]['source_sha256'] == evidence['source_sha256']
    source.unlink()
    assert show(vault.cfg, target)['claims'][0]['evidence'][0]['current_match_status'] == 'unavailable'
    assert all(p == 'raw/a.md' or (vault.root / p).read_bytes() == raw for p, raw in before.items())


def test_bom_crlf_quotes_keep_original_file_hash(vault):
    import hashlib
    raw = b'\xef\xbb\xbf# Source\r\n\r\nAn evidence record.\r\n'
    (vault.root / 'raw/a.md').write_bytes(raw)
    first = plan(vault)
    review_apply(vault, first)
    rebuild(vault.cfg)
    item = show(vault.cfg, first['planned_pages'][0]['object_id'])
    evidence = item['claims'][0]['evidence'][0]
    assert evidence['source_sha256'] == hashlib.sha256(raw).hexdigest()
    assert evidence['current_match_status'] == 'matched'
    assert evidence['start_line'] == 3


def test_failed_rebuild_keeps_previous_complete_index_and_cleans_temp(vault):
    rebuild(vault.cfg)
    old = cache_path(vault.cfg).read_bytes()
    vault.install_note('wiki/topics/new.md', vault.content('Fresh material'))
    from core.derived_index import _records
    def fail_on_new(note, text):
        if note.rel.endswith('new.md'):
            raise OSError('injected mid-build failure')
        return _records(note, text)
    with patch('core.derived_index._records', side_effect=fail_on_new):
        with pytest.raises(OSError, match='mid-build'):
            rebuild(vault.cfg)
    assert cache_path(vault.cfg).read_bytes() == old
    assert not search(vault.cfg, 'Fresh')['hits']
    assert list(cache_path(vault.cfg).parent.iterdir()) == [cache_path(vault.cfg)]
    rebuild(vault.cfg)
    assert search(vault.cfg, 'Fresh')['hits']
    old = cache_path(vault.cfg).read_bytes()
    with patch('core.derived_index.os.replace', side_effect=PermissionError('reader busy')):
        with pytest.raises(PermissionError):
            rebuild(vault.cfg)
    assert cache_path(vault.cfg).read_bytes() == old


def test_duplicate_identity_or_invalid_claim_never_replaces_cache(vault):
    first = plan(vault)
    review_apply(vault, first)
    target = vault.root / first['planned_pages'][0]['rel_path']
    rebuild(vault.cfg)
    before = cache_path(vault.cfg).read_bytes()
    duplicate = vault.root / 'wiki/topics/duplicate.md'
    duplicate.write_bytes(target.read_bytes())
    with pytest.raises(ObjectIdentityError):
        rebuild(vault.cfg)
    duplicate.unlink()
    assert cache_path(vault.cfg).read_bytes() == before
    target.write_bytes(target.read_bytes().replace(b'claim:', b'wrong:', 1))
    with pytest.raises(ValueError):
        rebuild(vault.cfg)
    assert cache_path(vault.cfg).read_bytes() == before


def test_scope_deduplicates_includes_and_excludes_internal_data(vault):
    for path in ['raw/archive/hidden.md', 'wiki/.kb/hidden.md', 'wiki/.openclaw/hidden.md', '.kb/hidden.md']:
        vault.install_note(path, 'Private internal words')
    vault.cfg['scan']['include_dirs'] += ['raw', 'wiki/topics', '.kb']
    rebuild(vault.cfg)
    assert status(vault.cfg)['counts']['notes'] == 1
    assert not search(vault.cfg, 'Private')['hits']
    vault.cfg['scan']['exclude_dirs'].append('raw')
    with pytest.raises(DerivedIndexError, match='扫描范围'):
        search(vault.cfg, 'evidence')
    rebuild(vault.cfg)
    assert status(vault.cfg)['counts']['notes'] == 0


def test_missing_index_read_queries_do_not_create_anything(vault, capsys):
    before = files(vault.root)
    with patch.object(cli, 'config', return_value=vault.cfg):
        assert cli.main(['search', 'evidence']) == 1
    assert '索引不存在' in capsys.readouterr().err
    assert not cache_path(vault.cfg).parent.exists()
    assert files(vault.root) == before


def test_foreign_database_and_changed_root_are_not_silently_used(vault, tmp_path):
    path = cache_path(vault.cfg)
    path.parent.mkdir()
    path.write_bytes(b'not a database')
    before = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        rebuild(vault.cfg)
    assert path.read_bytes() == before
    path.unlink()
    rebuild(vault.cfg)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("UPDATE metadata SET value=? WHERE key='root'", (str(tmp_path),))
    with pytest.raises(DerivedIndexError, match='位置'):
        search(vault.cfg, 'evidence')
    rebuild(vault.cfg)
    assert search(vault.cfg, 'evidence')['hits']


def test_links_do_not_export_external_notes_or_redirect_cache(vault, tmp_path):
    outside = tmp_path / 'external'
    outside.mkdir()
    (outside / 'secret.md').write_text('external confidential sentinel', encoding='utf-8')
    link = vault.root / 'raw/linked'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('OS does not permit creating symlinks')
    rebuild(vault.cfg)
    assert status(vault.cfg)['warnings']
    assert not search(vault.cfg, 'confidential')['hits']
    cache_path(vault.cfg).unlink()
    cache_path(vault.cfg).parent.rmdir()
    (vault.root / '.kb').symlink_to(outside, target_is_directory=True)
    with pytest.raises(DerivedIndexError, match='链接'):
        rebuild(vault.cfg)
    assert not (outside / 'index.sqlite').exists()


@pytest.mark.parametrize('query,limit', [('', 10), (' ', 10), ('x' * 201, 10), ('ok', 0), ('ok', 101)])
def test_invalid_queries_fail_without_side_effects(vault, query, limit):
    with pytest.raises(DerivedIndexError):
        search(vault.cfg, query, limit=limit)
    assert not (vault.root / '.kb').exists()
