"""Actual Agent selection -> plan -> review -> apply; SQLite and files are real."""
import hashlib
import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.retrieval as core_retrieval
from core.derived_index import cache_path, rebuild, search
from core.knowledge_objects import ObjectIdentityError
from core.retrieval import (Retriever, knowledge_prefixes_with_inputs, query_terms,
                            retrieval_input_dirs, retrieval_prefixes)
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
    plan_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    linked = []
    for candidate in steward.runs_dir(vault.cfg).glob(f"{proposal['run_id']}*.json"):
        data = json.loads(candidate.read_text(encoding='utf-8'))
        if (data.get('parent_run_id') == proposal['run_id']
                and data.get('parent_plan_path') == str(path)
                and data.get('parent_plan_sha256') == plan_hash):
            linked.append(candidate)
    if json.loads(path.read_text(encoding='utf-8')).get('review_contract') == 'page-scoped-v1':
        assert len(linked) == 1
    record_path = linked[0] if linked else steward.runs_dir(vault.cfg) / f"{proposal['run_id']}.json"
    assert len(linked) == 1 or record_path.is_file()
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
    with pytest.raises((RunRecordConflict, SystemExit)) as replay:
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    if isinstance(replay.value, SystemExit):
        assert str(replay.value) == f"目标已存在，拒绝覆盖：{page['rel_path']}"
    assert record.read_bytes() == old_record
    assert steward.command_rollback(vault.cfg, saved['run_id']) == 0
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
        # Model writeback contract: a usable material-pack item citing the
        # provided docs (entry writeback replaced the heuristic template page).
        return {'skill': skill, 'items': [{
            'title': 'Downstream 材料包', 'type': 'material-pack', 'status': 'growing',
            'stage': 'assembling', 'sources': [d['path'] for d in documents[:1]],
            'summary': '下游依赖待复查。', 'tension': '下游结论依赖上游旧版本。',
            'facts': ['下游页面引用的上游结论已过期。'], 'cases': [], 'risks': ['上游已变更。'],
            'gaps': [], 'not_recommended': [], 'confidence': 'medium',
            'review_required': True}], 'issues': [], 'ok': True}
    with patch.object(steward, 'run_skill_runtime', side_effect=runtime):
        proposal = make_task(vault, '围绕 Downstream 生成材料包', use_llm=True)
    assert any(d['retrieval']['dependency_state'] == 'stale' for d in captured['docs'])
    assert proposal['llm_runtime']['writeback_used'] is True
    page = proposal['planned_pages'][0]
    assert page['rel_path'].startswith('wiki/material-packs/')
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
    # 长中文段切成 3 字窗口（与索引侧 FTS5 trigram 同宽）；长度 <= 3 的段保持原样
    # —— 它本身就是一个 trigram，再切只会加噪声。
    assert query_terms('围绕新闻智能体准备写作素材') == ['新闻智', '闻智能', '智能体']
    assert query_terms('温州 AI 材料包') == ['温州', 'ai']
    assert query_terms('大黄鱼') == ['大黄鱼']


def test_long_chinese_query_slices_into_windows_across_every_clause():
    """回归：连续中文整段当一个 term，等于要求它逐字出现 → 长中文查询恒 0 命中。

    切成 3 字窗口后每段独立检索再取并集；额度还必须**跨子句轮转**，
    否则预算会被第一个子句吃光，后面的子句永不参与检索（同一个 bug 的下一层）。
    """
    terms = query_terms('整理一份家庭手冲咖啡参数调整的素材，区分自测记录与外部资料，列出待核实项')
    assert len(terms) == 16
    # 三个子句都要有代表，不能只剩第一个
    assert '整理一' in terms
    assert '区分自' in terms
    assert '列出待' in terms
    # 每个窗口都是 3 个汉字；整段长串不再出现
    assert all(len(t) == 3 for t in terms)
    assert '整理一份家庭手冲咖啡参数调整的素材' not in terms


def test_long_chinese_query_reaches_the_vault(vault):
    """端到端：长中文查询必须能在真实检索链路上命中（修复前恒 0）。"""
    vault.install_note('raw/专题.md', '# 大黄鱼产业观察\n温州沿海的大黄鱼养殖与加工记录。')
    rebuild(vault.cfg)
    selected = retrieve(vault, '大黄鱼产业观察记录')
    assert [n.rel for n in selected.notes] == ['raw/专题.md']
    # 对照：整段当一个 term 时，正文里没有这条逐字长串，命中为空。
    assert '大黄鱼产业观察记录' not in (vault.root / 'raw/专题.md').read_text(encoding='utf-8')


def test_legacy_whole_phrase_term_is_why_the_query_missed(vault):
    """对照：同一个库、同一条查询，旧口径（整段一个 term）必须 0 命中。

    没有这条对照，「长中文查询能命中」的测试就无法证明它测的是切词修复，
    而不是碰巧命中。
    """
    vault.install_note('raw/专题.md', '# 大黄鱼产业观察\n温州沿海的大黄鱼养殖与加工记录。')
    rebuild(vault.cfg)

    def legacy_query_terms(query):
        # 修复前的实现，逐字复刻。
        clean = core_retrieval.BOILERPLATE.sub(' ', query)
        words = re.findall(r'[A-Za-z][A-Za-z0-9_+-]*|[\u4e00-\u9fff]+', clean)
        terms = [t.lower() for t in words]
        unique = list(dict.fromkeys(t for t in terms if t not in core_retrieval.STOPWORDS))[:16]
        return unique or list(dict.fromkeys(terms))[:16]

    original = core_retrieval.query_terms
    core_retrieval.query_terms = legacy_query_terms
    try:
        legacy = core_retrieval.Retriever(vault.cfg, build_index(vault.cfg)).select('大黄鱼产业观察记录')
    finally:
        core_retrieval.query_terms = original
    assert legacy.notes == []
    # 同一条查询在新口径下必须命中 —— 有对照才说明测试真的在测修复。
    assert [n.rel for n in retrieve(vault, '大黄鱼产业观察记录').notes] == ['raw/专题.md']


def test_recall_scope_is_configurable_and_defaults_to_the_historical_three():
    """检索范围必须可配置：本库 70% 的内容在 raw/quicknote/inbox 之外。

    默认值保持不变（历史行为）；非法条目直接报错，不静默放宽或收窄范围。
    注意这与 ``layout.INPUT_DIRS`` **不是同一个东西** —— 那个是「知识输出不得与之
    重叠」的安全集合，放宽检索范围绝不能放宽写入守卫。
    """
    assert retrieval_input_dirs(None) == ('raw', 'quicknote', 'inbox')
    assert retrieval_input_dirs({'scan': {}}) == ('raw', 'quicknote', 'inbox')

    extended = retrieval_input_dirs({'scan': {'retrieval_include_dirs': ['raw', '2-领域', '3-资源']}})
    assert extended == ('raw', '2-领域', '3-资源')
    assert '2-领域/' in retrieval_prefixes({'scan': {'retrieval_include_dirs': ['2-领域']}})

    with pytest.raises(ValueError):
        retrieval_input_dirs({'scan': {'retrieval_include_dirs': 'raw'}})
    with pytest.raises(ValueError):
        retrieval_input_dirs({'scan': {'retrieval_include_dirs': ['../escape']}})

    # 显式空列表 = 只要知识对象，不回退默认值
    assert retrieval_input_dirs({'scan': {'retrieval_include_dirs': []}}) == ()


def test_writing_entry_recall_scope_is_configurable_too():
    """写作入口（跨源综合）也必须吃 scan.retrieval_include_dirs。

    实测：它原本把 ``raw/`` 写死，导致本库 `2-领域/` 下的料对写作入口永远不可见，
    而这在配置层面无解 —— 只能改代码。未配置时保持历史行为（只有 raw/），
    不制造惊喜。
    """
    # 未配置 → 与历史完全一致（知识对象 + 只有 raw/）
    assert knowledge_prefixes_with_inputs(None)[-1] == 'raw/'
    assert knowledge_prefixes_with_inputs({'scan': {}})[-1] == 'raw/'

    # 配置了 → 纳入配置里的目录
    cfg = {'scan': {'retrieval_include_dirs': ['raw', '2-领域', '4-项目']}}
    prefixes = knowledge_prefixes_with_inputs(cfg)
    assert '2-领域/' in prefixes
    assert '4-项目/' in prefixes
    assert 'raw/' in prefixes

    # 显式空列表 = 只要知识对象，不再回退到 raw/
    empty = knowledge_prefixes_with_inputs({'scan': {'retrieval_include_dirs': []}})
    assert 'raw/' not in empty
    assert '2-领域/' not in empty


def test_extended_recall_scope_reaches_topic_directories(vault):
    """端到端：顶层主题目录里的笔记，只有纳入范围后才可能被检索到。

    本库把大部分笔记放在 2-领域/ 这类顶层目录下，历史范围完全覆盖不到它们。
    """
    vault.cfg['scan']['include_dirs'].append('2-领域')  # 先让它进入索引
    vault.install_note('2-领域/领域笔记.md', '# 大黄鱼\n一条长期领域的记录。')
    rebuild(vault.cfg)

    assert retrieve(vault, '大黄鱼').notes == []  # 默认范围之外 → 检索不到

    vault.cfg['scan']['retrieval_include_dirs'] = ['raw', '2-领域']
    got = retrieve(vault, '大黄鱼')
    assert [n.rel for n in got.notes] == ['2-领域/领域笔记.md']
