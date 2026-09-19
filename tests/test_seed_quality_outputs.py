"""Issue #16: real seed plan/review/apply and configured auxiliary output regressions."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import derived_index
from core.clustering import ClusterInput
from core.knowledge_objects import ObjectIdentityError
from core.run_records import RunRecordConflict
from core.skill_executor import execute_skill
from core.vault import build_index, parse_frontmatter
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    instance = fixtures.ObjectPlanTests()
    instance.setUp()
    # Only generated fixtures are used, never a local config or an actual vault.
    for key, value in list(instance.cfg['write'].items()):
        if key.endswith('_dir'):
            instance.cfg['write'][key] = '_kb-steward/' + value.split('/')[-1]
    instance.cfg['write'].update(index_file='_kb-steward/导航.md', logs_dir='_kb-steward/logs',
                                 log_file='_kb-steward/运行.md', index_title='个人知识工作台')
    instance.cfg['scan']['include_dirs'] = ['raw', 'quicknote', 'inbox', '_kb-steward']
    yield instance
    instance.doCleanups()


def grouping(inputs, **kwargs):
    return ([{'title': '地方媒体服务转型', 'sources': [n.path for n in inputs],
              'reasoning': '地方媒体需要把技术能力落实为可持续的服务。',
              'confidence': 'high', 'terms': ['媒体', '服务'], 'llm_clustered': True}], [])


def execute_seed(notes, cluster):
    with patch('core.clustering.cluster_inputs', return_value=([cluster], [])):
        return execute_skill(ROOT, 'mindseed-grow', {'notes': notes, 'config': {}, 'use_llm': False})


def plan_for(case, rels, rid):
    index = build_index(case.cfg)
    with patch('core.clustering.cluster_inputs', side_effect=grouping):
        result = steward.mvp_executor_plan(index, case.cfg, '整理知识库', 'mindseed-grow',
                                          [index.by_rel[p] for p in rels], {}, rid, use_llm=False)
    return {'run_id': rid, 'entry': 'init_kb', 'primary_skill': 'mindseed-grow', 'task': '整理知识库',
            'planned_pages': result['planned_pages'], 'manual_review': [
                {'type': 'planned_pages_require_review', 'risk': 'medium', 'reason': 'Review seed proposal'}]}


def reviewed_apply(case, plan):
    path = case.persist(plan)
    steward.write_manual_review_queue(case.cfg, plan)
    items = [x for x in steward.load_queue(steward.review_queue_path(case.cfg)) if x['run_id'] == plan['run_id']]
    assert items
    for item in items:
        assert steward.command_review(case.cfg, SimpleNamespace(review_command='approve', id=item['id'], reason='test review')) == 0
    assert steward.command_review(case.cfg, SimpleNamespace(review_command='apply-approved')) == 0
    manifest = case.root / '.openclaw/runs' / (plan['run_id'] + '.json')
    assert json.loads(manifest.read_text(encoding='utf-8'))['status'] == 'applied'
    return path, manifest


def test_signals_read_past_diary_template_and_keep_actual_sentences():
    observation = '本周读者咨询集中在办事流程，编辑部应先测试人工答疑再选择技术方案。'
    body = '# 晨间日记\n## 每日例程\n' + '- [x] 阅读课程与整理笔记\n' * 35 + '\n## 观察\n' + observation
    notes = [{'rel': 'quicknote/day.md', 'title': '日记', 'body': body, 'summary': body[:240]}]
    cluster, _ = grouping([ClusterInput('quicknote/day.md', '日记', body)])
    page = execute_seed(notes, cluster[0])['pages'][0]
    signals = page['item']['signals']
    assert any(observation in signal for signal in signals)
    assert all('[x]' not in signal and '每日例程' not in signal and not signal.endswith('...') for signal in signals)
    assert '[[quicknote/day.md]]' in ''.join(signals)


def test_empty_high_confidence_cluster_does_not_become_high_confidence_knowledge():
    notes = [{'rel': 'quicknote/a.md', 'title': '日记', 'body': '# 晨间日记\n- [x] 整理笔记', 'summary': '模板'}]
    cluster = {'title': '晨间日记例行打卡', 'sources': ['quicknote/a.md'], 'confidence': 'high',
               'reasoning': '仅包含每日例程的打卡记录，无额外实质内容。', 'terms': ['晨间日记']}
    page = execute_seed(notes, cluster)['pages'][0]
    meta, _ = parse_frontmatter(page['content'])
    assert page['item']['review_required'] is True
    assert meta['review_required'] == 'true' and meta['status'] == 'manual_review'
    assert meta['confidence'] == 'low' and meta['cluster_confidence'] == 'high'
    assert page['item']['signals'] == []
    assert page['item']['pending_links'] == []
    assert '主题关键词（不是待建链接）' in page['content']


def test_substantive_single_source_and_unresolved_links_have_independent_review_reasons():
    from core.seed_quality import seed_item
    notes = [{'rel': 'quicknote/a.md', 'body': '- 实际观察表明咨询内容集中在流程解释而非信息数量。'}]
    cluster = {'title': '服务观察', 'sources': ['quicknote/a.md'], 'confidence': 'high',
               'terms': ['服务'], 'pending_links': ['尚未创建的主题']}
    item = seed_item(cluster, notes, {})
    assert item['signals'] and item['pending_links'] == ['尚未创建的主题']
    assert any('低于 seed' in reason for reason in item['manual_review'])
    assert any('尚未解析' in reason for reason in item['manual_review'])
    cfg = {'quality_gate': {'min_sources_for_seed': 1, 'manual_review_on_unresolved_link': False}}
    item = seed_item(cluster, notes, cfg)
    assert item['confidence'] == 'medium' and item['review_required'] is True
    assert not any('低于 seed' in reason for reason in item['manual_review'])


def test_no_llm_seed_mode_never_calls_provider():
    notes = [{'rel': 'quicknote/a.md', 'title': '服务观察', 'body': '实际咨询需要由编辑提供事实依据和具体的办理程序。'}]
    with patch('core.llm.call_chat_completion', side_effect=AssertionError('no network')) as provider:
        result = execute_skill(ROOT, 'mindseed-grow', {'notes': notes, 'config': {}, 'use_llm': False})
    assert result['pages']
    provider.assert_not_called()


def test_init_pause_preserves_plan_then_existing_review_cli_applies_it(case, capsys):
    (case.root / 'raw/a.md').unlink()
    case.install_note('quicknote/a.md', '# 日记\n- [x] 阅读课程\n\n需求应来自用户反馈，不能先写技术蓝图。')
    before = (case.root / 'quicknote/a.md').read_bytes()
    with patch('core.clustering.cluster_inputs', side_effect=grouping):
        assert steward.command_init_kb(case.cfg, no_llm=True, apply=True, max_batches=1) == 1
    assert '计划已保存' in capsys.readouterr().out
    path, = (case.root / '.openclaw/plans').glob('*.json')
    plan = json.loads(path.read_text(encoding='utf-8'))
    assert len(plan['planned_pages']) == 1
    assert not (case.root / plan['planned_pages'][0]['rel_path']).exists()
    reviewed_apply(case, plan)
    assert (case.root / 'quicknote/a.md').read_bytes() == before
    assert (case.root / plan['planned_pages'][0]['rel_path']).exists()


def test_cross_batch_seed_updates_keep_identity_body_and_audit_then_noop(case, capsys):
    case.install_note('quicknote/a.md', '# 服务\n用户更需要可核对的服务过程，而非不落地的技术口号。')
    first = plan_for(case, ['quicknote/a.md'], 'seed-first')
    reviewed_apply(case, first)
    p1 = first['planned_pages'][0]
    target = case.root / p1['rel_path']
    original = target.read_text(encoding='utf-8')
    target.write_bytes(original.replace('type: seed-card', 'personal_field: 保留\ntype: seed-card').encode('utf-8') + '\n我的手写判断：先访谈十名读者。\n'.encode('utf-8'))
    original = target.read_text(encoding='utf-8')
    case.install_note('quicknote/b.md', '# 新观察\n咨询反馈表明服务需要持续答复，而不是建设另一个信息入口。')
    second = plan_for(case, ['quicknote/b.md'], 'seed-second')
    p2, = second['planned_pages']
    assert p2['operation'] == 'update' and p2['rel_path'] == p1['rel_path']
    assert '我的手写判断' in p2['content'] and 'personal_field: 保留' in p2['content']
    path, manifest = reviewed_apply(case, second)
    p2 = second['planned_pages'][0]
    assert p2['object_id'] == p1['object_id'] and p2['revision'] == p1['revision'] + 1
    assert set(p2['sources']) == {'quicknote/a.md', 'quicknote/b.md'}
    assert len(list((case.root / '_kb-steward/seeds').glob('*.md'))) == 2  # seed + managed README
    assert '我的手写判断' in target.read_text(encoding='utf-8')
    before = manifest.read_bytes()
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(case.cfg, str(path), allow_reviewed=True)
    assert manifest.read_bytes() == before
    with pytest.raises((SystemExit, ValueError)):
        steward.command_rollback(case.cfg, 'seed-second')
    assert target.exists() and manifest.read_bytes() == before
    assert plan_for(case, ['quicknote/b.md'], 'seed-third')['planned_pages'] == []
    derived_index.rebuild(case.cfg)
    assert derived_index.show(case.cfg, p2['object_id'])


def test_seed_update_generation_and_apply_refuse_stale_target_or_source(case, capsys):
    case.install_note('quicknote/a.md', '# 服务\n用户需求应先核实，再推进项目方案和技术选型。')
    first = plan_for(case, ['quicknote/a.md'], 'seed-base')
    reviewed_apply(case, first)
    case.install_note('quicknote/b.md', '# 服务观察\n持续服务需要记录每次反馈并确认是否真正解决问题。')
    proposed = plan_for(case, ['quicknote/b.md'], 'seed-stale')
    target = case.root / first['planned_pages'][0]['rel_path']
    target.write_bytes(target.read_bytes() + '\n人工修改必须保留。'.encode('utf-8'))
    before = target.read_bytes()
    with pytest.raises(ObjectIdentityError):
        case.persist(proposed)
    assert target.read_bytes() == before
    new = plan_for(case, ['quicknote/b.md'], 'seed-source-stale')
    path = case.persist(new)
    source = case.root / 'quicknote/b.md'
    source.write_bytes(source.read_bytes() + '\n新证据。'.encode('utf-8'))
    with pytest.raises((ObjectIdentityError, ValueError)):
        steward.command_apply_plan(case.cfg, str(path), allow_reviewed=True)
    assert target.read_bytes() == before


def test_similar_titles_are_review_suggestions_not_auto_merges(case, capsys):
    case.install_note('quicknote/a.md', '# 观察\n媒体服务需要收集真实需求并按反馈推进实施。')
    first = plan_for(case, ['quicknote/a.md'], 'seed-known')
    reviewed_apply(case, first)
    title = first['planned_pages'][0]['rel_path']
    original = (case.root / title).read_bytes()
    index = build_index(case.cfg)
    def different(inputs, **kwargs):
        clusters, issues = grouping(inputs, **kwargs)
        clusters[0]['title'] = '地方媒体服务转型实践'
        return clusters, issues
    with patch('core.clustering.cluster_inputs', side_effect=different):
        result = steward.mvp_executor_plan(index, case.cfg, '整理知识库', 'mindseed-grow',
                                          [index.by_rel['quicknote/a.md']], {}, 'similar', use_llm=False)
    p, = result['planned_pages']
    assert p['operation'] == 'create' and p['review_required']
    assert p['rel_path'] != title and '疑似重复' in p['content']
    assert result['issues']
    assert (case.root / title).read_bytes() == original


def test_existing_duplicate_seed_titles_do_not_choose_a_winner(case, capsys):
    case.install_note('quicknote/a.md', '# 服务\n读者反馈必须形成明确的处理步骤并建立后续记录。')
    first = plan_for(case, ['quicknote/a.md'], 'seed-duplicate-base')
    reviewed_apply(case, first)
    target = case.root / first['planned_pages'][0]['rel_path']
    meta, body = parse_frontmatter(target.read_text(encoding='utf-8'))
    # A legacy page with the same title, but no ID, is independently valid.
    case.install_note('_kb-steward/seeds/历史卡.md', '---\ntitle: 地方媒体服务转型\ntype: seed-card\nsources: ["quicknote/a.md"]\n---\n历史正文。')
    case.install_note('quicknote/b.md', '# 服务\n追加资料必须明确归属，不能随机选中一份历史主题。')
    assert plan_for(case, ['quicknote/b.md'], 'ambiguous')['planned_pages'] == []
    assert target.exists()


def test_custom_auxiliary_paths_apply_without_root_pollution_or_feedback_into_search(case, capsys):
    page = case.page('_kb-steward/topics/事实记录.md')
    plan = case.plan(page)
    path = case.persist(plan)
    assert steward.command_apply_plan(case.cfg, str(path)) == 0
    assert all(not (case.root / name).exists() for name in ('index.md', 'logs', 'log.md', 'outputs'))
    assert (case.root / '_kb-steward/导航.md').is_file()
    assert '个人知识工作台' in (case.root / '_kb-steward/导航.md').read_text(encoding='utf-8')
    assert (case.root / '_kb-steward/运行.md').is_file()
    logs = list((case.root / '_kb-steward/logs').rglob('*.md'))
    assert logs
    index = build_index(case.cfg)
    assert '_kb-steward/导航.md' not in index.by_rel and '_kb-steward/运行.md' not in index.by_rel
    assert all('/logs/' not in n.rel for n in index.notes)
    derived_index.rebuild(case.cfg)
    from core.derived_index import _open
    with _open(case.cfg) as conn:
        paths = [r[0] for r in conn.execute('SELECT path FROM notes')]
    assert '_kb-steward/导航.md' not in paths and all('/logs/' not in p for p in paths)


def test_two_runs_same_minute_have_distinct_operation_logs(case):
    from core.log_manager import write_run_log
    from datetime import datetime, timezone
    index = build_index(case.cfg)
    operations = [{'skill': 'mindseed-grow', 'created': [], 'inputs': ['quicknote/a.md']}]
    with patch('core.log_manager.datetime') as clock:
        clock.now.return_value = datetime(2026, 9, 19, 10, 15, 0, tzinfo=timezone.utc)
        one = write_run_log(index, {**case.cfg, '_run_id': 'one'}, operations, 'first')
        first = (case.root / one[0]).read_bytes()
        two = write_run_log(index, {**case.cfg, '_run_id': 'two'}, operations, 'second')
    assert one != two and (case.root / one[0]).read_bytes() == first
    aggregate = (case.root / '_kb-steward/运行.md').read_text(encoding='utf-8')
    assert all(f'[[{rel}]]' in aggregate for rel in (one[0], two[0]))


@pytest.mark.parametrize('key,value', [('index_file', '../escape.md'), ('log_file', 'raw/notes.md'),
                                      ('logs_dir', 'C:/outside'), ('logs_dir', '/tmp/outside')])
def test_invalid_auxiliary_paths_fail_before_any_knowledge_write(case, key, value, capsys):
    plan = case.plan(case.page('_kb-steward/topics/untouched.md'))
    path = case.persist(plan)
    case.cfg['write'][key] = value
    with pytest.raises((ValueError, SystemExit)):
        steward.command_apply_plan(case.cfg, str(path))
    assert not (case.root / '_kb-steward/topics/untouched.md').exists()


def test_configured_auxiliary_directory_symlink_is_rejected_before_apply(case, capsys):
    alias = case.root / 'link'
    try:
        alias.symlink_to(case.root / 'raw', target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create directory symlinks')
    case.cfg['write']['logs_dir'] = 'link/logs'
    plan = case.plan(case.page('_kb-steward/topics/untouched.md'))
    path = case.persist(plan)
    with pytest.raises((ValueError, SystemExit)):
        steward.command_apply_plan(case.cfg, str(path))
    assert not (case.root / 'raw/logs').exists()
    assert not (case.root / '_kb-steward/topics/untouched.md').exists()


def test_existing_user_index_and_log_are_not_overwritten(case, capsys):
    from core.index_builder import update_index
    from core.log_manager import write_run_log
    first = case.install_note('_kb-steward/导航.md', '# 我的手写导航\n保持原样。')
    second = case.install_note('_kb-steward/运行.md', '# 我的日志\n保持原样。')
    before = (first.read_bytes(), second.read_bytes())
    index = build_index(case.cfg)
    update_index(index, case.cfg)
    write_run_log(index, case.cfg, [{'skill': 'test', 'created': [], 'inputs': []}], 'test')
    assert (first.read_bytes(), second.read_bytes()) == before
    assert (case.root / '.openclaw/generated-index.md').exists()
    assert (case.root / '.openclaw/generated-log.md').exists()


def test_partial_seed_update_failure_preserves_real_writes_on_retry(case, capsys):
    case.install_note('quicknote/a.md', '# 服务\n先理解读者的真实需求，再决定需要建设哪些能力。')
    first = plan_for(case, ['quicknote/a.md'], 'partial-base')
    reviewed_apply(case, first)
    case.install_note('quicknote/b.md', '# 服务\n服务是否有效需要持续记录问题解决情况，而不是只数访问量。')
    plan = plan_for(case, ['quicknote/b.md'], 'partial-update')
    plan['planned_pages'].append(case.page('_kb-steward/topics/second.md'))
    path = case.persist(plan)
    original_writer = steward.safe_write_text
    def fail_second(cfg, target, content, **kwargs):
        if target.name == 'second.md':
            raise OSError('fixture second write failed')
        return original_writer(cfg, target, content, **kwargs)
    with patch.object(steward, 'safe_write_text', side_effect=fail_second):
        with pytest.raises(OSError):
            steward.command_apply_plan(case.cfg, str(path), allow_reviewed=True)
    manifest_path = case.root / '.openclaw/runs/partial-update.json'
    original = manifest_path.read_bytes()
    manifest = json.loads(original)
    assert manifest['status'] == 'failed' and len(manifest['created']) == 1
    record = manifest['created'][0]
    assert record['operation'] == 'update' and record['revision'] == 2
    assert record['object_id'] == first['planned_pages'][0]['object_id']
    assert record['content_verified'] is True and Path(record['backup_path']).is_file()
    assert not (case.root / '_kb-steward/topics/second.md').exists()
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(case.cfg, str(path), allow_reviewed=True)
    with pytest.raises((ValueError, SystemExit)):
        steward.command_rollback(case.cfg, 'partial-update')
    assert manifest_path.read_bytes() == original


def test_log_directory_cannot_hide_all_knowledge_from_scan(case):
    from core.output_paths import auxiliary_layout
    case.cfg['write']['logs_dir'] = '_kb-steward'
    with pytest.raises(ValueError, match='knowledge directory'):
        auxiliary_layout(case.cfg)
