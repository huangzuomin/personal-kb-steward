"""Real plan/review/apply regressions for #20, #25, #27; isolated temporary vaults."""
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import jinja_renderer
from core.content_safety import SensitiveContentError
from core.vault import build_index, read_note
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


@pytest.fixture
def case():
    value = fixtures.ObjectPlanTests()
    value.setUp()
    yield value
    value.doCleanups()


def reviewed_plan(case, rid):
    page = case.page(f'wiki/topics/{rid}.md', content=case.content().replace('review_required: false', 'review_required: true'))
    page['review_required'] = True
    plan = case.plan(page)
    plan.update(run_id=rid, manual_review=[{'type': 'planned_pages_require_review', 'risk': 'medium', 'reason': 'fixture review'}])
    path = case.persist(plan)
    steward.write_manual_review_queue(case.cfg, plan)
    queue = steward.load_queue(steward.review_queue_path(case.cfg))
    for item in queue:
        if item['run_id'] == rid:
            assert steward.command_review(case.cfg, SimpleNamespace(review_command='approve', id=item['id'], reason='fixture')) == 0
    return path


def manifest_for_plan(case, plan_path, run_id):
    plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    linked = []
    for candidate in steward.runs_dir(case.cfg).glob(f'{run_id}*.json'):
        data = json.loads(candidate.read_text(encoding='utf-8'))
        if (data.get('parent_run_id') == run_id
                and data.get('parent_plan_path') == str(plan_path)
                and data.get('parent_plan_sha256') == plan_hash):
            linked.append(candidate)
    assert len(linked) == 1
    return json.loads(linked[0].read_text(encoding='utf-8'))


def test_real_apply_only_writes_requested_run(case):
    reviewed_plan(case, 'run-a')
    reviewed_plan(case, 'run-b')
    raw = (case.root / 'raw/a.md').read_bytes()
    assert steward.command_review(case.cfg, SimpleNamespace(review_command='apply-approved', run_id='run-a')) == 0
    assert (case.root / 'wiki/topics/run-a.md').exists()
    assert not (case.root / 'wiki/topics/run-b.md').exists()
    assert (case.root / 'raw/a.md').read_bytes() == raw
    items = steward.load_queue(steward.review_queue_path(case.cfg))
    assert {i['run_id']: i['status'] for i in items} == {'run-a': 'applied', 'run-b': 'approved'}
    assert any('计划提示：planned_pages_require_review' in p.read_text(encoding='utf-8')
               for p in (case.root / 'logs').rglob('*.md'))


def test_first_real_run_completion_survives_second_write_failure(case):
    plan_a = reviewed_plan(case, 'run-a')
    plan_b = reviewed_plan(case, 'run-b')
    writer = steward.safe_write_text
    def fail_b(cfg, target, content, **kwargs):
        if target.name == 'run-b.md':
            raise OSError('synthetic write failure')
        return writer(cfg, target, content, **kwargs)
    with patch.object(steward, 'safe_write_text', side_effect=fail_b):
        assert steward.command_review(case.cfg, SimpleNamespace(review_command='apply-approved', all=True)) == 1
    items = steward.load_queue(steward.review_queue_path(case.cfg))
    assert {i['run_id']: i['status'] for i in items} == {'run-a': 'applied', 'run-b': 'approved'}
    assert manifest_for_plan(case, plan_a, 'run-a')['status'] == 'applied'
    assert manifest_for_plan(case, plan_b, 'run-b')['status'] == 'failed'


def test_apply_rechecks_expected_id_after_plan_resolution(case):
    path = reviewed_plan(case, 'run-a')
    with pytest.raises(ValueError, match='run_id'):
        steward.command_apply_plan(case.cfg, str(path), allow_reviewed=True, expected_run_id='run-other')
    assert not (case.root / 'wiki/topics/run-a.md').exists()


def test_init_pause_lists_quality_and_page_review_ids(case, capsys):
    (case.root / 'raw/a.md').unlink()
    case.install_note('quicknote/a.md', '# 观察\n这条观察应先核实来源，再进入知识库。')
    assert steward.command_init_kb(case.cfg, no_llm=True, apply=True, max_batches=1) == 1
    out = capsys.readouterr().out
    queue = steward.load_queue(steward.review_queue_path(case.cfg))
    assert {'seed_quality_issues', 'planned_page_review'} <= {i['type'] for i in queue}
    for item in queue:
        assert item['id'] in out and item['type'] in out
    assert '--run-id' in out
    assert list((case.root / '.openclaw/plans').glob('*.json'))
    assert not steward.processed_index_path(case.cfg).exists()


def test_render_dependency_failure_never_advances_processed_state(case, monkeypatch):
    before = (case.root / 'raw/a.md').read_bytes()
    monkeypatch.setattr(jinja_renderer, '_JINJA2_AVAILABLE', False)
    with pytest.raises(jinja_renderer.RendererDependencyError):
        steward.command_init_kb(case.cfg, no_llm=True, apply=True, max_batches=1)
    assert not steward.processed_index_path(case.cfg).exists()
    assert not list((case.root / 'wiki/sources').glob('source-*.md'))
    assert (case.root / 'raw/a.md').read_bytes() == before


def test_structured_analysis_mode_blocks_even_without_body_marker():
    page = {'skill': 'topic-research-compile', 'analysis_mode': 'heuristic', 'content': '# 摘要\n正文不含分析模式。'}
    assert steward.page_has_blocked_placeholder(page)


def test_secret_in_generated_plan_is_refused_before_save(case):
    page = case.page(content=case.content('password=NotARealCredential9!Example'))
    with pytest.raises(SensitiveContentError):
        case.persist(case.plan(page))
    assert not list((case.root / '.openclaw/plans').glob('*.json'))
    assert not (case.root / 'wiki/topics/a.md').exists()


def test_real_read_note_and_seed_executor_share_filtered_input(case):
    rel = 'quicknote/safe.md'
    safe = '编辑部应核对每项信息来源，再形成候选议题。'
    path = case.install_note(rel, '# 观察\n````\n~~~\n内部哨兵不可进入信号。\n````\ncurl http://192.0.2.1\nnetwork=devnet\n' + safe)
    before = path.read_bytes()
    note = read_note(path, case.root)
    seen = []
    def cluster(inputs, **kwargs):
        seen.extend(inputs)
        return ([{'title': '来源核查', 'sources': [rel], 'reasoning': '信息来源需要核对。', 'confidence': 'high'}], [])
    cfg = {**case.cfg, 'seed_generation': {'mode': 'topic'}}
    with patch('core.clustering.cluster_inputs', side_effect=cluster):
        result = steward.mvp_executor_plan(build_index(cfg), cfg, '整理碎片', 'mindseed-grow', [note], {}, 'signal-test', use_llm=False)
    assert seen[0].content == safe
    page, = result['planned_pages']
    assert safe in page['content']
    assert '内部哨兵' not in page['content'] and '192.0.2.1' not in page['content']
    assert 'network=devnet' not in page['content']
    assert path.read_bytes() == before


def test_atomic_preview_also_filters_machine_lines_and_sents(case):
    rel = 'quicknote/atomic-safe.md'
    safe = '编辑部应核对每项信息来源，再形成候选议题。'
    path = case.install_note(rel, '# 观察\n````\n内部哨兵不可进入信号。\n````\ncurl http://192.0.2.1\nnetwork=devnet\n' + safe)
    before = path.read_bytes()
    result = steward.mvp_executor_plan(build_index(case.cfg), case.cfg, '整理碎片', 'mindseed-grow',
                                       [read_note(path, case.root)], {}, 'atomic-signal', use_llm=False)
    rendered = ''.join(p['content'] for p in result['planned_pages'])
    assert safe in rendered
    assert '内部哨兵' not in rendered and '192.0.2.1' not in rendered and 'network=devnet' not in rendered
    assert path.read_bytes() == before


def test_review_cli_never_drops_bad_queue_lines_during_id_backfill(case):
    path = steward.review_queue_path(case.cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"run_id":"run-a","type":"quality","status":"pending"}\n{broken\n', encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        steward.command_review(case.cfg, SimpleNamespace(review_command='list'))
    assert path.read_bytes() == before
