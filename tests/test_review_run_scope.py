"""Issue #20 unit tests: real queue IO and run selection; apply callback is isolated."""
import json
from pathlib import Path

import pytest

from core.review_queue import load_queue, save_queue
from core.review_runs import apply_review_runs, review_blockers, select_review_runs, ReviewScopeError


def setup_runs(tmp_path, runs=('run-a', 'run-b', 'run-c')):
    queue = tmp_path / 'queue.jsonl'
    plans = tmp_path / 'plans'
    plans.mkdir()
    items = [{'id': rid + '-review', 'run_id': rid, 'type': 'planned_pages_require_review', 'status': 'approved'} for rid in runs]
    save_queue(queue, items)
    for rid in runs:
        (plans / f'{rid}-init-kb.json').write_text(json.dumps({'run_id': rid}), encoding='utf-8')
    return queue, plans


def run(queue, plans, apply, run_id=None, all_runs=False):
    return apply_review_runs(queue, plans, run_id=run_id, all_runs=all_runs, apply_plan=apply)


def test_only_requested_run_is_applied_and_other_records_unchanged(tmp_path):
    queue, plans = setup_runs(tmp_path)
    before = load_queue(queue)
    called = []
    assert run(queue, plans, lambda p, rid: called.append((p.name, rid)) or 0, run_id='run-a') == 0
    after = load_queue(queue)
    assert called == [('run-a-init-kb.json', 'run-a')]
    assert after[0]['status'] == 'applied'
    assert after[1:] == before[1:]


def test_multiple_runs_without_scope_refuse_before_any_apply(tmp_path):
    queue, plans = setup_runs(tmp_path)
    before = queue.read_bytes()
    def forbidden(*args):
        pytest.fail('must not apply without explicit multi-run scope')
    assert run(queue, plans, forbidden) == 1
    assert queue.read_bytes() == before


@pytest.mark.parametrize('status', ['pending', 'rejected', 'unexpected'])
def test_all_blocker_types_and_ids_are_reported(tmp_path, capsys, status):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    items = load_queue(queue)
    items.append({'id': 'quality-item', 'type': 'seed_quality_issues', 'status': status, 'run_id': 'run-a'})
    save_queue(queue, items)
    assert run(queue, plans, lambda *a: pytest.fail('blocked run applied'), run_id='run-a') == 1
    output = capsys.readouterr().out
    assert 'quality-item' in output and 'seed_quality_issues' in output and status in output
    assert review_blockers(items, 'run-a') == [items[-1]]


def test_success_is_persisted_before_later_failure(tmp_path, capsys):
    queue, plans = setup_runs(tmp_path)
    def apply(path, rid):
        if rid == 'run-b':
            assert load_queue(queue)[0]['status'] == 'applied'
            raise OSError('synthetic second-run failure')
        return 0
    assert run(queue, plans, apply, all_runs=True) == 1
    assert [i['status'] for i in load_queue(queue)] == ['applied', 'approved', 'approved']
    out = capsys.readouterr().out
    assert 'run-a-init-kb.json' in out and 'run-b-init-kb.json' in out
    assert 'not_attempted' in out and 'run-c' in out


def test_all_runs_report_their_plan_and_completion(tmp_path, capsys):
    queue, plans = setup_runs(tmp_path)
    assert run(queue, plans, lambda *a: 0, all_runs=True) == 0
    out = capsys.readouterr().out
    for rid in ('run-a', 'run-b', 'run-c'):
        assert f'{rid}-init-kb.json' in out
    assert all(i['status'] == 'applied' for i in load_queue(queue))


def test_legacy_single_run_default_remains_scoped(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    assert run(queue, plans, lambda *a: 0) == 0
    assert run(queue, plans, lambda *a: pytest.fail('completed run replayed'), run_id='run-a') == 0


def test_id_prefix_never_selects_another_run(tmp_path):
    queue, plans = setup_runs(tmp_path)
    before = queue.read_bytes()
    assert run(queue, plans, lambda *a: pytest.fail('prefix applied'), run_id='run') == 1
    assert queue.read_bytes() == before


def test_stored_plan_id_must_match_even_if_filename_matches(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    (plans / 'run-a-init-kb.json').write_text('{"run_id":"run-other"}', encoding='utf-8')
    assert run(queue, plans, lambda *a: pytest.fail('wrong plan applied'), run_id='run-a') == 1
    assert load_queue(queue)[0]['status'] == 'approved'


def test_duplicate_exact_plan_ids_refuse_to_choose(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    (plans / 'another.json').write_text('{"run_id":"run-a"}', encoding='utf-8')
    assert run(queue, plans, lambda *a: pytest.fail('ambiguous plan applied'), run_id='run-a') == 1


def test_unrelated_queue_append_is_not_lost(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    appended = {'id': 'new', 'run_id': 'new-run', 'status': 'pending', 'type': 'quality'}
    def apply(*args):
        save_queue(queue, [*load_queue(queue), appended])
        return 0
    assert run(queue, plans, apply, run_id='run-a') == 0
    assert load_queue(queue)[-1] == appended


def test_changed_approval_is_not_overwritten_after_write(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    def apply(*args):
        changed = load_queue(queue)
        changed[0]['status'] = 'rejected'
        save_queue(queue, changed)
        return 0
    assert run(queue, plans, apply, run_id='run-a') == 1
    assert load_queue(queue)[0]['status'] == 'rejected'


@pytest.mark.parametrize('bad', ['{broken', '[]', 'null'])
def test_corrupt_queue_is_not_silently_dropped(tmp_path, bad):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    queue.write_text(queue.read_text(encoding='utf-8') + bad + '\n', encoding='utf-8')
    before = queue.read_bytes()
    assert run(queue, plans, lambda *a: pytest.fail('corrupt gate bypassed'), run_id='run-a') == 1
    assert queue.read_bytes() == before


def test_interrupt_propagates_and_never_marks_current_run_applied(tmp_path):
    queue, plans = setup_runs(tmp_path, ('run-a',))
    def interrupt(*args):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(queue, plans, interrupt, run_id='run-a')
    assert load_queue(queue)[0]['status'] == 'approved'
