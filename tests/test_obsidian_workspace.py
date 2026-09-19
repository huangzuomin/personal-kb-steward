"""Workspace pilot: real dependency/report/review paths, not a mocked Obsidian UI."""
import json
from pathlib import Path
import re
from unittest.mock import patch

import pytest

from core.dependencies import stale
from core.derived_index import rebuild
from core.vault import build_index
from scripts import workspace_report as cli
from tests.test_dependencies import publish, snapshot
from tests.test_reconcile import review_apply, vault
from tests.test_synthesis import model, synth

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'integrations/obsidian/vault'


def test_base_and_home_share_valid_view_and_path_contract():
    # JSON is the deliberately restricted YAML representation here. This is not
    # an Obsidian expression interpreter or a claim of native UI verification.
    base = json.loads((TEMPLATES / 'Steward/专题.base').read_text(encoding='utf-8'))
    assert base['filters'] == {'and': ['file.ext == "md"', 'file.inFolder("wiki")',
                                      'note.type == "topic-page"']}
    views = {v['name']: v for v in base['views']}
    assert set(views) == {'全部专题', '最近7天修改', '页面审核标记'}
    assert base['formulas']['stage'] == 'note.stage'
    assert base['formulas']['lifecycle'] == 'note.status'
    assert views['最近7天修改']['filters'] == 'file.mtime >= now() - "7d"'
    assert 'note.review_required == true' in views['页面审核标记']['filters']['or']
    assert 'note.review_required == "true"' in views['页面审核标记']['filters']['or']
    for view in views.values():
        assert view['type'] == 'table'
        for column in view['order']:
            assert column.startswith('formula.')  # No editable identity/status columns.
            assert column.removeprefix('formula.') in base['formulas']
    for path in TEMPLATES.rglob('*.md'):
        for link in re.findall(r'\[\[([^]]+)\]\]', path.read_text(encoding='utf-8')):
            target, _, fragment = link.split('|')[0].partition('#')
            assert (TEMPLATES / target).is_file(), target
            if fragment:
                assert fragment in views
    placeholder = (TEMPLATES / 'Steward/依赖复查.md').read_text(encoding='utf-8')
    assert '尚未生成' in placeholder and '不代表' in placeholder


def test_report_keeps_real_upstream_order_claims_and_does_not_write(vault):
    first = publish(vault, 'Upstream')
    second = publish(vault, 'Downstream', first['rel_path'], 'Upstream observation.')
    rebuild(vault.cfg)
    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nChanged source')
    expected = stale(vault.cfg)
    before = snapshot(vault.root)
    report = cli.render_report(vault.cfg)
    assert report.index('1. Upstream') < report.index('2. Downstream')
    assert '直接影响' in report and '间接影响' in report and '先复查上游' in report
    assert f"[[{first['rel_path']}]]" in report
    assert expected['pending_updates'][0]['claims'][0]['claim_id'] in report
    assert cli.text(expected['built_at']) in report and '检查时间（UTC）' in report
    assert '来源版本改变' in report and '不是实时待办' in report
    assert snapshot(vault.root) == before  # Includes SQLite, queue, plans and run manifests.
    assert all(n.metadata.get('status') != 'stale' for n in build_index(vault.cfg).notes)
    rebuild(vault.cfg)
    assert '待复查页面：2' in cli.render_report(vault.cfg)


def test_missing_source_is_reported_as_plain_text_not_a_new_wikilink(vault):
    publish(vault, 'Missing')
    rebuild(vault.cfg)
    (vault.root / 'raw/a.md').unlink()
    before = snapshot(vault.root)
    report = cli.render_report(vault.cfg)
    assert '不可用，未链接' in report
    assert '[[raw/a.md]]' not in report
    assert '人工核对来源或页面' in report
    assert snapshot(vault.root) == before


def test_missing_cache_is_not_a_successful_empty_report(vault, capsys):
    before = snapshot(vault.root)
    with patch.object(cli, 'config', return_value=vault.cfg):
        assert cli.main([]) == 1
    output = capsys.readouterr()
    assert output.out == '' and '报告未生成' in output.err
    assert snapshot(vault.root) == before


def test_unversioned_page_remains_unknown_even_when_no_changes_found(vault):
    vault.install_note('wiki/topics/legacy.md', vault.content())
    rebuild(vault.cfg)
    before = snapshot(vault.root)
    report = cli.render_report(vault.cfg)
    assert '无写作时版本依赖：1' in report
    assert '待复查页面：0' in report and '零条结果不代表全库已核实' in report
    assert build_index(vault.cfg).by_rel['wiki/topics/legacy.md'].object_id is None
    assert snapshot(vault.root) == before


def test_synthesis_review_apply_then_report_is_consistent(vault, capsys):
    rebuild(vault.cfg)
    proposal = synth(vault, topic='Workspace', completion=model())
    review_apply(vault, proposal)  # Asserts direct unreviewed apply is rejected first.
    page = proposal['planned_pages'][0]
    note = build_index(vault.cfg).by_rel[page['rel_path']]
    assert str(note.metadata['review_required']).lower() == 'true'
    assert note.object_id == page['object_id'] and note.revision == 1
    capsys.readouterr()
    rebuild(vault.cfg)
    before = snapshot(vault.root)
    with patch.object(cli, 'config', return_value=vault.cfg):
        assert cli.main([]) == 0
    report = capsys.readouterr().out
    assert '待复查页面：0' in report
    assert '不等于当前待审批任务' in report
    assert snapshot(vault.root) == before
    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nChanged')
    assert '待复查页面：1' in cli.render_report(vault.cfg)


def test_report_escapes_untrusted_text_and_refuses_ambiguous_links(vault):
    assert '[[' not in cli.text('![[not-real.md]]')
    assert '<script>' not in cli.text('<script>not code</script>')
    assert '[[raw/a.md]]' == cli.note_link(vault.root, 'raw/a.md')
    assert '[[' not in cli.note_link(vault.root, '../outside.md')
    assert '[[' not in cli.note_link(vault.root, 'raw/[alias].md')
    publish(vault, 'Safe')
    rebuild(vault.cfg)
    raw = vault.root / 'raw/a.md'
    raw.write_bytes(raw.read_bytes() + b'\nChanged')
    report = stale(vault.cfg)
    report['pending_updates'][0]['title'] = '![[injected.md]] <script>x</script>'
    report['warnings'] = ['![[more-injection.md]]']
    with patch.object(cli, 'stale', return_value=report):
        rendered = cli.render_report(vault.cfg)
    assert '[[injected.md]]' not in rendered and '<script>' not in rendered
    assert '覆盖警告' in rendered


def test_workspace_cli_has_no_apply_or_install_write_mode(vault):
    before = snapshot(vault.root)
    with patch.object(cli, 'config', return_value=vault.cfg):
        for flag in ('--apply', '--install', '--save'):
            with pytest.raises(SystemExit) as exc:
                cli.main([flag])
            assert exc.value.code == 2
    assert snapshot(vault.root) == before
    skill = ROOT / 'integrations/obsidian/skills/steward-workspace/SKILL.md'
    content = skill.read_text(encoding='utf-8')
    assert 'review apply-approved' in content and 'ALL approved items' in content
    assert not (ROOT / 'skills/steward-workspace').exists()
