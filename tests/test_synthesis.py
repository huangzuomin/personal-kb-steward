"""Synthesis integration: real retrieval, evidence compilation, review and writes."""
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.dependencies import impact, stale
from core.derived_index import rebuild, search, show
from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.reconcile import ReconcileConflict, make_reconcile_plan
from core.retrieval import Retriever
from core.run_records import RunRecordConflict
from core.synthesis import make_synthesis_plan
from core.vault import build_index
from scripts import personal_kb_steward as steward
from scripts import synthesize as cli
from tests.test_dependencies import publish, snapshot
from tests.test_reconcile import review_apply, vault


def model(decision='create', statement='A combined inference.', evidence=None, **extra):
    return Mock(return_value=json.dumps({
        'decision': decision, 'reason': 'Compare supplied observations', 'conflicts': [],
        'claims': [{'statement': statement, 'kind': 'inference', 'confidence': 'medium',
                    'evidence': evidence or [{'source': 'raw/a.md', 'quote': 'An evidence record.',
                                             'relation': 'supports'}]}], **extra}))


def synth(case, *, question='evidence implications', topic='Evidence', rid='synthesis', **kw):
    return make_synthesis_plan(case.cfg, question, topic=topic, plan_run_id=rid, **kw)


def test_cross_source_synthesis_retrieval_review_apply_and_search(vault):
    vault.install_note('raw/b.md', '# Evidence B\nA second observation.')
    rebuild(vault.cfg)
    completion = model(evidence=[
        {'source': 'raw/a.md', 'quote': 'An evidence record.', 'relation': 'supports'},
        {'source': 'raw/b.md', 'quote': 'A second observation.', 'relation': 'supports'}])
    before = snapshot(vault.root)
    proposal = synth(vault, discussion='Consider whether both observations imply a shared trend.', completion=completion)
    assert proposal['reconcile']['decision'] == 'create', proposal
    assert completion.call_count == 1  # No preview/recompile second model call.
    payload = completion.call_args.args[2]
    assert payload['synthesis_request']['question'] == 'evidence implications'
    assert 'shared trend' in payload['synthesis_request']['discussion']
    assert {d['path'] for d in payload['sources']} == {'raw/a.md', 'raw/b.md'}
    assert len(payload['retrieval']['hits']) == 2
    assert snapshot(vault.root) == before
    saved = review_apply(vault, proposal)
    page = proposal['planned_pages'][0]
    note = build_index(vault.cfg).by_rel[page['rel_path']]
    assert note.revision == 1 and str(note.metadata['review_required']).lower() == 'true'
    assert note.metadata['reconcile_state']['synthesis_request'] == payload['synthesis_request']
    claim = note.metadata['reconcile_state']['claims'][0]
    assert claim['kind'] == 'inference' and len(claim['evidence']) == 2
    record = json.loads((steward.runs_dir(vault.cfg) / 'synthesis.json').read_text(encoding='utf-8'))
    assert record['status'] == 'applied'
    assert record['created'][0]['claim_ids'] == [claim['claim_id']]
    for source in ('raw/a.md', 'raw/b.md'):
        processed = steward.load_processed_index(vault.cfg)['processed'][source]['skills']['kb-reconcile']
        assert processed['outputs'] == [page['rel_path']]
        assert (vault.root / source).read_bytes() == before[source]
    rebuild(vault.cfg)
    assert search(vault.cfg, 'combined', kind='claim')['hits'][0]['path'] == page['rel_path']
    assert len(show(vault.cfg, note.object_id)['claims']) == 1
    assert impact(vault.cfg, 'raw/b.md')['dependents'][0]['object_id'] == note.object_id
    assert not stale(vault.cfg)['pending_updates']
    assert json.loads(saved.read_text(encoding='utf-8'))['retrieval'][0]['engine'] == 'sqlite+live-delta'


def test_same_topic_update_preserves_human_text_identity_and_prior_sources(vault):
    oid = new_object_id()
    original = '\ufeff' + vault.content('## 手写判断\n原有观察不能被覆盖。', oid, 3)
    target = vault.root / 'wiki/topics/existing.md'
    target.write_bytes(original.replace('\n', '\r\n').encode())
    vault.install_note('raw/b.md', '# New research\nA second observation.')
    rebuild(vault.cfg)
    completion = model('update')
    proposal = synth(vault, topic='Sample topic', question='new research', target=oid, limit=1, completion=completion)
    assert proposal['reconcile']['decision'] == 'update', proposal
    sources = {d['path'] for d in completion.call_args.args[2]['sources']}
    assert 'wiki/topics/existing.md' not in sources
    assert 'raw/a.md' in sources and 'raw/b.md' in sources
    assert 'existing_source' in {h['selected_by'] for h in proposal['retrieval'][0]['hits']}
    review_apply(vault, proposal)
    updated = build_index(vault.cfg).by_object_id[oid]
    assert updated.revision == 4 and updated.rel == 'wiki/topics/existing.md'
    assert 'custom: keep-me\r\n' in target.read_bytes().decode()
    assert '## 手写判断\r\n原有观察不能被覆盖。' in target.read_bytes().decode()
    assert target.read_bytes().startswith(b'\xef\xbb\xbf')
    assert len([n for n in build_index(vault.cfg).notes if n.metadata.get('type') == 'topic-page']) == 1
    with pytest.raises(SystemExit, match='包含更新页面'):
        steward.command_rollback(vault.cfg, 'synthesis')
    assert target.is_file()


def test_same_request_noops_but_new_question_on_same_sources_can_update(vault):
    first = synth(vault, completion=model())
    review_apply(vault, first)
    page = first['planned_pages'][0]
    before = snapshot(vault.root)
    unused = Mock(side_effect=AssertionError('Unchanged request must not call the model'))
    repeat = synth(vault, completion=unused, rid='repeat')
    assert repeat['reconcile']['decision'] == 'noop', repeat
    assert cli.present_plan(vault.cfg, repeat) == 0
    assert snapshot(vault.root) == before
    fresh_model = model('update', statement='A different, narrower inference.')
    updated = synth(vault, question='evidence limits', completion=fresh_model, rid='new-question')
    assert updated['reconcile']['decision'] == 'update', updated
    review_apply(vault, updated)
    assert updated['planned_pages'][0]['object_id'] == page['object_id']
    assert updated['planned_pages'][0]['revision'] == 2
    # The ordinary explicit-source command retains its source-based noop contract.
    explicit = make_reconcile_plan(vault.cfg, 'Evidence', ['raw/a.md'], plan_run_id='explicit', completion=unused)
    assert explicit['reconcile']['decision'] == 'noop'
    # A different question alone does not justify a revision if every claim/evidence is identical.
    identical = synth(vault, question='evidence again', completion=fresh_model, rid='identical')
    assert identical['reconcile']['decision'] == 'noop'


def test_changed_discussion_is_not_mistaken_for_an_already_compiled_request(vault):
    first = synth(vault, discussion='Initial thought', completion=model())
    review_apply(vault, first)
    revised = model('update', statement='A revised inference based on the same evidence.')
    next_plan = synth(vault, discussion='Narrow this thought', completion=revised, rid='discussion')
    assert revised.call_count == 1
    assert next_plan['reconcile']['decision'] == 'update'
    assert next_plan['reconcile']['synthesis_request']['discussion'] == 'Narrow this thought'


def test_discussion_does_not_become_citable_evidence(vault):
    completion = model(evidence=[{'source': 'raw/a.md', 'quote': 'Only in the draft.', 'relation': 'supports'}])
    proposal = synth(vault, discussion='Only in the draft.', completion=completion)
    assert proposal['reconcile']['decision'] == 'conflict'
    assert '原文片段不存在' in proposal['reconcile']['reason']
    assert not proposal['planned_pages']
    unused = Mock()
    no_sources = synth(vault, question='unmatchedword', topic='Another', discussion='A confident unsupported claim.', completion=unused)
    assert no_sources['reconcile']['decision'] == 'conflict'
    unused.assert_not_called()


def test_known_stale_upstream_cannot_be_laundered_into_new_synthesis(vault):
    upstream = publish(vault, 'Upstream')
    downstream = publish(vault, 'Downstream', upstream['rel_path'], 'Upstream observation.')
    rebuild(vault.cfg)
    source = vault.root / 'raw/a.md'
    source.write_bytes(source.read_bytes() + b'\nNew evidence')
    unused = Mock()
    before = snapshot(vault.root)
    proposal = synth(vault, question='Downstream', topic='New finding', completion=unused)
    assert proposal['reconcile']['decision'] == 'conflict'
    assert '先更新上游' in proposal['reconcile']['reason']
    assert any(h['path'] == downstream['rel_path'] and h['dependency_state'] == 'stale'
               for h in proposal['retrieval'][0]['hits'])
    assert snapshot(vault.root) == before
    unused.assert_not_called()


def test_change_between_retrieval_and_compilation_does_not_rebase_inputs(vault):
    select = Retriever.select
    def change_source(retriever, *args, **kw):
        selected = select(retriever, *args, **kw)
        raw = vault.root / 'raw/a.md'
        raw.write_bytes(raw.read_bytes() + b'\nConcurrent edit')
        return selected
    unused = Mock()
    with patch.object(Retriever, 'select', change_source):
        proposal = synth(vault, completion=unused)
    assert proposal['reconcile']['decision'] == 'conflict'
    assert '来源版本或范围已变化' in proposal['reconcile']['reason']
    assert not proposal['planned_pages']
    unused.assert_not_called()


def test_source_changes_block_first_save_resave_and_apply(vault):
    raw = vault.root / 'raw/a.md'
    before = raw.read_bytes()
    proposal = synth(vault, completion=model())
    raw.write_bytes(before + b'\nChange before first save')
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.write_execution_plan(vault.cfg, proposal)
    raw.write_bytes(before)
    path = steward.write_execution_plan(vault.cfg, proposal)
    serialized = path.read_bytes()
    raw.write_bytes(before + b'\nChange after save')
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.write_execution_plan(vault.cfg, proposal)
    assert path.read_bytes() == serialized
    with pytest.raises(ObjectIdentityError, match='Retrieval source changed'):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert not (vault.root / proposal['planned_pages'][0]['rel_path']).exists()


def test_human_edit_during_synthesis_blocks_update_without_losing_original(vault):
    oid = new_object_id()
    target = vault.install_note('wiki/topics/manual.md', vault.content(object_id=oid))
    def completing(*args):
        target.write_bytes(target.read_bytes() + '\n人工新增内容。'.encode())
        return model('update').return_value
    proposal = synth(vault, target=oid, completion=completing)
    assert proposal['reconcile']['decision'] == 'update'
    edited = target.read_bytes()
    with pytest.raises(ObjectIdentityError, match='Generation base'):
        steward.write_execution_plan(vault.cfg, proposal)
    assert target.read_bytes() == edited


def test_failed_replay_keeps_success_record_and_update_backup(vault):
    oid = new_object_id()
    target = vault.install_note('wiki/topics/original.md', vault.content(object_id=oid, revision=2))
    original = target.read_bytes()
    proposal = synth(vault, target=oid, completion=model('update'))
    path = review_apply(vault, proposal)
    record_path = steward.runs_dir(vault.cfg) / 'synthesis.json'
    record_bytes = record_path.read_bytes()
    record = json.loads(record_bytes)
    backup = Path(record['created'][0]['backup_path'])
    assert backup.read_bytes() == original
    assert record['created'][0]['revision'] == 3
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert record_path.read_bytes() == record_bytes
    assert backup.read_bytes() == original
    with pytest.raises(SystemExit, match='包含更新页面'):
        steward.command_rollback(vault.cfg, 'synthesis')
    assert target.read_bytes() == proposal['planned_pages'][0]['content'].encode()


def test_postwrite_failure_records_synthesis_actually_written_and_allows_safe_create_rollback(vault):
    proposal = synth(vault, completion=model())
    path = steward.write_execution_plan(vault.cfg, proposal)
    with patch.object(steward, 'update_processed_index', side_effect=OSError('injected index failure')):
        with pytest.raises(OSError, match='injected'):
            steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    record_path = steward.runs_dir(vault.cfg) / 'synthesis.json'
    before = record_path.read_bytes()
    record = json.loads(before)
    assert record['status'] == 'failed' and record['phase'] == 'update_processed_index'
    assert len(record['created']) == 1 and record['created'][0]['content_verified']
    assert record['created'][0]['claim_ids']
    assert (vault.root / proposal['planned_pages'][0]['rel_path']).is_file()
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert record_path.read_bytes() == before
    assert steward.command_rollback(vault.cfg, 'synthesis') == 0
    assert not (vault.root / proposal['planned_pages'][0]['rel_path']).exists()
    assert (vault.root / 'raw/a.md').is_file()


def test_request_tampering_is_detected_at_plan_and_page_boundaries(vault):
    proposal = synth(vault, completion=model())
    tampered = copy.deepcopy(proposal)
    tampered['reconcile']['synthesis_request'] = {'question': 'Other', 'discussion': ''}
    with pytest.raises(ReconcileConflict, match='综合问题'):
        steward.write_execution_plan(vault.cfg, tampered)
    saved = steward.write_execution_plan(vault.cfg, proposal)
    data = json.loads(saved.read_text(encoding='utf-8'))
    data['planned_pages'][0]['synthesis_request']['question'] = 'Other'
    saved.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ReconcileConflict, match='综合问题'):
        steward.command_apply_plan(vault.cfg, str(saved), allow_reviewed=True)
    assert not (vault.root / proposal['planned_pages'][0]['rel_path']).exists()


def test_model_conflict_noop_or_summary_only_never_create_writable_pages(vault):
    for decision, extra in [('conflict', {'conflicts': ['Sources disagree.']}),
                            ('noop', {'claims': []}),
                            ('create', {'claims': [], 'summary': 'Unsupported free text'})]:
        proposal = synth(vault, completion=model(decision, **extra))
        assert not proposal['planned_pages']
        assert proposal['reconcile']['decision'] in {'conflict', 'noop'}


def test_cli_preview_queues_review_without_writing_notes_or_calling_model_twice(vault, capsys):
    before = (vault.root / 'raw/a.md').read_bytes()
    completion = model()
    with patch.object(cli, 'config', return_value=vault.cfg), patch('core.synthesis.call_chat_completion', completion):
        assert cli.main(['evidence implications', '--topic', 'Evidence', '--discussion', 'Compare observations']) == 0
    assert completion.call_count == 1
    output = capsys.readouterr().out
    assert 'Synthesis: create' in output and '人工审核项：1' in output
    assert 'live-scan' in output and '+A combined inference.' in output
    assert not list((vault.root / 'wiki/topics').glob('*.md'))
    assert (vault.root / 'raw/a.md').read_bytes() == before
    queued = steward.load_queue(steward.review_queue_path(vault.cfg))
    assert len(queued) == 1
    assert not (vault.root / '.kb').exists()


def test_large_context_is_rejected_without_silent_truncation(vault):
    vault.cfg['reconcile'] = {'max_context_chars': 100}
    unused = Mock()
    proposal = synth(vault, discussion='context ' * 100, completion=unused)
    assert proposal['reconcile']['decision'] == 'conflict'
    assert '上下文超过' in proposal['reconcile']['reason']
    unused.assert_not_called()
