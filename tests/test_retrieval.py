"""Actual Agent selection -> plan -> review -> apply; SQLite and files are real."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.derived_index import cache_path, rebuild, search
from core.knowledge_objects import ObjectIdentityError
from core.retrieval import Retriever, query_terms
from core.run_records import RunRecordConflict
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests.test_dependencies import publish, snapshot
from tests.test_reconcile import vault


def retrieve(vault, query, **kwargs):
    return Retriever(vault.cfg, build_index(vault.cfg)).select(query, **kwargs)


def make_task(vault, task='围绕大黄鱼生成材料包', **kwargs):
    result = steward.make_execution_plan(vault.cfg, task, **kwargs)
    assert result['primary_skill'] == 'writing-material-pack'
    assert result['planned_pages']
    return result


def apply_task(vault, proposal):
    path = steward.write_execution_plan(vault.cfg, proposal)
    steward.write_manual_review_queue(vault.cfg, proposal)
    queued = [q for q in steward.load_queue(steward.review_queue_path(vault.cfg))
              if q['run_id'] == proposal['run_id']]
    for q in queued:
        assert steward.command_review(vault.cfg, SimpleNamespace(
            review_command='approve', id=q['id'], reason='Test evidence reviewed')) == 0
    if queued:
        assert steward.command_review(vault.cfg, SimpleNamespace(review_command='apply-approved')) == 0
    else:
        assert steward.command_apply_plan(vault.cfg, str(path)) == 0
    record_path = steward.runs_dir(vault.cfg) / f"{proposal['run_id']}.json"
    return path, record_path


def test_real_material_task_uses_deep_fts_hits_and_records_inputs(vault):
    vault.install_note('raw/产业.md', '# 产业记录\n' + '背景描述。' * 1600 + '\n大黄鱼产业有一项可核对的调查记录。2026年9月19日，另一个错误日期是2026-02-30。')
    rebuild(vault.cfg)
    before = snapshot(vault.root)
    with patch.object(steward, 'select_notes', side_effect=AssertionError('Old selector used')):
        proposal = make_task(vault)
    report = proposal['retrieval'][0]
    assert report['terms'] == ['大黄鱼']
    assert report['engine'] == 'sqlite+live-delta'
    assert report['index_engines'] == ['fts5-trigram']
    assert [h['path'] for h in report['hits']] == ['raw/产业.md']
    assert '大黄鱼产业有一项可核对' in proposal['planned_pages'][0]['content']
    assert steward.extract_dates("2026年9月19日 2026-09-19 2026-02-30") == ["2026-09-19"]
    assert "2026-09-19" in proposal["planned_pages"][0]["content"]
    assert snapshot(vault.root) == before  # Planning/selection did not change the cache or notes.
    path, record = apply_task(vault, proposal)
    page = proposal['planned_pages'][0]
    saved = json.loads(record.read_text(encoding='utf-8'))
    assert saved['status'] == 'applied'
    assert saved['created'][0]['object_id'] == page['object_id']
    assert saved['created'][0]['sources'] == ['raw/产业.md']
    processed = steward.load_processed_index(vault.cfg)['processed']
    assert page['rel_path'] in processed['raw/产业.md']['skills']['writing-material-pack']['outputs']
    old_record = record.read_bytes()
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert record.read_bytes() == old_record
    assert steward.command_rollback(vault.cfg, proposal['run_id']) == 0
    assert not (vault.root / page['rel_path']).exists()
    assert (vault.root / 'raw/产业.md').read_bytes() == before['raw/产业.md']


def test_changed_deleted_and_new_files_never_supply_cached_content(vault):
    old = vault.install_note('raw/旧文.md', '# 原标题\n大黄鱼旧口径。')
    gone = vault.install_note('raw/删除.md', '# 删除\n大黄鱼已经废弃。')
    rebuild(vault.cfg)
    old.write_text('# 新标题\n只包含餐饮新口径。', encoding='utf-8')
    gone.unlink()
    vault.install_note('raw/新增.md', '# 新增\n大黄鱼新调查。')
    selected = retrieve(vault, '大黄鱼')
    assert [n.rel for n in selected.notes] == ['raw/新增.md']
    assert selected.report['hits'][0]['selected_by'] == 'live_scan'
    current = retrieve(vault, '餐饮').notes[0]
    assert current.title == '新标题' and '旧口径' not in current.body


@pytest.mark.parametrize('failure', ['missing', 'corrupt', 'scope'])
def test_cache_failure_falls_back_explicitly_without_writing(vault, failure):
    vault.install_note('raw/数据.md', '# 大黄鱼\n一条独立记录。')
    if failure != 'missing':
        rebuild(vault.cfg)
        if failure == 'corrupt':
            cache_path(vault.cfg).write_bytes(b'not sqlite')
        else:
            vault.cfg['scan']['exclude_dirs'].append('new-exclusion')
    before = snapshot(vault.root)
    selected = retrieve(vault, '大黄鱼')
    assert selected.notes[0].rel == 'raw/数据.md'
    assert selected.report['engine'] == 'live-scan'
    assert selected.report['fallback_reason']
    assert snapshot(vault.root) == before


def test_prefix_type_and_status_filter_before_limit_and_no_scope_expansion(vault):
    for i in range(55):
        vault.install_note(f'raw/{i}.md', '# 大黄鱼\n大黄鱼大黄鱼大黄鱼')
    vault.install_note('wiki/topics/wanted.md', vault.content('大黄鱼需要核对的专题。'))
    vault.install_note('wiki/topics/stale.md', vault.content('大黄鱼').replace('status: growing', 'status: archived'))
    rebuild(vault.cfg)
    assert search(vault.cfg, '大黄鱼', prefixes=('wiki/topics/',), note_status='growing', limit=1)['hits'][0]['path'] == 'wiki/topics/wanted.md'
    result = retrieve(vault, '大黄鱼', prefixes=('wiki/topics/',), note_type='topic-page', note_status='growing', limit=1)
    assert [n.rel for n in result.notes] == ['wiki/topics/wanted.md']
    # Its raw dependency is outside the request's allowed prefixes and is not appended.
    assert len(result.report['hits']) == 1


def test_dependency_expansion_and_transitive_stale_reach_plan_and_model(vault):
    upstream = publish(vault, 'Upstream')
    downstream = publish(vault, 'Downstream', upstream['rel_path'], 'Upstream observation.')
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nNew facts')
    selected = retrieve(vault, 'Downstream', limit=8)
    hit = next(h for h in selected.report['hits'] if h['path'] == downstream['rel_path'])
    assert hit['dependency_state'] == 'stale'
    assert hit['blocked_by'] == [upstream['rel_path']]
    assert hit['claim_ids']
    assert any(h['selected_by'] == 'dependency' and h['path'] == upstream['rel_path'] for h in selected.report['hits'])
    captured = {}
    def runtime(root, cfg, skill, task, documents, **kw):
        captured['docs'] = documents
        return {'items': [], 'issues': [], 'ok': True}
    with patch.object(steward, 'run_skill_runtime', side_effect=runtime):
        proposal = make_task(vault, '围绕 Downstream 生成材料包', use_llm=True)
    assert any(d['retrieval']['dependency_state'] == 'stale' for d in captured['docs'])
    page = proposal['planned_pages'][0]
    assert page['review_required'] is True
    assert '检索与来源复查' in page['content'] and 'stale' in page['content']
    path = steward.write_execution_plan(vault.cfg, proposal)
    with pytest.raises(SystemExit, match='人工审核'):
        steward.command_apply_plan(vault.cfg, str(path))


def test_same_version_consumer_and_legacy_unknown_are_distinguished(vault):
    old = publish(vault, 'Old')
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nNew version')
    fresh = publish(vault, 'Fresh')
    vault.install_note('wiki/topics/legacy.md', vault.content('A legacy observation.'))
    rebuild(vault.cfg)
    result = retrieve(vault, 'observation', limit=12)
    states = {h['path']: h['dependency_state'] for h in result.report['hits']}
    assert states[old['rel_path']] == 'stale'
    assert states[fresh['rel_path']] == 'no_signal'
    assert states['wiki/topics/legacy.md'] == 'unversioned'


def test_selected_source_changes_block_save_resave_and_apply(vault):
    source = vault.install_note('raw/记录.md', '# 大黄鱼\n这是一份有明确内容的产业记录。')
    rebuild(vault.cfg)
    proposal = make_task(vault)
    before = source.read_bytes()
    source.write_bytes(before + b'\nChanged before save')
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.write_execution_plan(vault.cfg, proposal)
    assert 'object_schema_version' not in proposal
    source.write_bytes(before)
    path = steward.write_execution_plan(vault.cfg, proposal)
    stored = path.read_bytes()
    source.write_bytes(before + b'\nChanged after save')
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.write_execution_plan(vault.cfg, proposal)
    assert path.read_bytes() == stored
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert not any((vault.root / p['rel_path']).exists() for p in proposal['planned_pages'])


def test_llm_selection_includes_current_deep_excerpt_not_just_introduction(vault):
    vault.install_note('raw/deep.md', '# 普通标题\n' + '无关前言。' * 1600 + '\n大黄鱼专题的关键段落就在这里。')
    rebuild(vault.cfg)
    retriever = Retriever(vault.cfg, build_index(vault.cfg))
    notes = steward.select_llm_input_notes(retriever.index, vault.cfg, '围绕大黄鱼生成材料包',
                                          'writing-material-pack', [], {}, retriever)
    docs = retriever.documents(notes, 200)
    assert len(docs[0]['content']) <= 200
    assert '大黄鱼专题的关键段落' in docs[0]['content']
    assert docs[0]['retrieval']['sha256'] == notes[0].sha256


def test_discover_topics_uses_retrieval_and_ingestion_does_not_load_cache(vault):
    vault.install_note('raw/发现.md', '# 大黄鱼\n一份可用于选题的产业记录。')
    rebuild(vault.cfg)
    with patch.object(steward, 'select_notes', side_effect=AssertionError('Old selector used')):
        proposal = steward.make_execution_plan(vault.cfg, '发现选题 大黄鱼')
    assert proposal['primary_skill'] == 'topic-insight-miner'
    assert proposal['retrieval'][0]['engine'] == 'sqlite+live-delta'
    assert 'raw/发现.md' in proposal['planned_pages'][0]['sources']
    with patch('core.retrieval._open', side_effect=AssertionError('Ingestion should not query cache')):
        assert steward.make_execution_plan(vault.cfg, '整理知识库')['retrieval'] == []


def test_fallback_does_not_follow_links_or_internal_notes(vault, tmp_path):
    private = tmp_path / 'private.md'
    private.write_text('# 大黄鱼\nNot part of vault', encoding='utf-8')
    try:
        (vault.root / 'raw/alias.md').symlink_to(private)
    except OSError:
        pytest.skip('Host does not allow symlink creation')
    assert retrieve(vault, '大黄鱼').notes == []
    assert not cache_path(vault.cfg).exists()


def test_task_terms_remove_only_known_boilerplate():
    assert query_terms('围绕新闻智能体准备写作素材') == ['新闻智能体']
    assert query_terms('温州 AI 材料包') == ['温州', 'ai']
