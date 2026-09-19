"""Run actual producer -> review -> apply -> audit paths, with only LLM I/O stubbed."""
import contextlib
import io
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import patch

from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.run_records import RunRecordConflict
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


class ProducerRecoveryTests(TestCase):
    def setUp(self):
        self.case = fixtures.ObjectPlanTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root, self.cfg = self.case.root, self.case.cfg
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def apply_produced(self, producer):
        before = set((self.root / '.openclaw/plans').glob('*.json'))
        raw_before = {p: p.read_bytes() for p in (self.root / 'raw').rglob('*') if p.is_file()}
        self.assertEqual(producer(), 0)
        paths = set((self.root / '.openclaw/plans').glob('*.json')) - before
        self.assertEqual(len(paths), 1)
        path = paths.pop()
        plan = json.loads(path.read_text(encoding='utf-8'))
        self.assertTrue(plan['planned_pages'])
        queued = [x for x in steward.load_queue(steward.review_queue_path(self.cfg)) if x['run_id'] == plan['run_id']]
        for item in queued:
            self.assertEqual(steward.command_review(self.cfg, SimpleNamespace(review_command='approve', id=item['id'], reason='fixture evidence reviewed')), 0)
        if queued:
            self.assertEqual(steward.command_review(self.cfg, SimpleNamespace(review_command='apply-approved')), 0)
            self.assertTrue(all(x['status'] == 'applied' for x in steward.load_queue(steward.review_queue_path(self.cfg)) if x['run_id'] == plan['run_id']))
        else:
            self.assertEqual(steward.command_apply_plan(self.cfg, str(path)), 0)
        manifest = json.loads((self.root / '.openclaw/runs' / f"{plan['run_id']}.json").read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'], 'applied')
        by_path = {x['rel_path']: x for x in manifest['created']}
        self.assertEqual(len(by_path), len(plan['planned_pages']))
        index = build_index(self.cfg)
        processed = json.loads(steward.processed_index_path(self.cfg).read_text(encoding='utf-8'))['processed']
        for page in plan['planned_pages']:
            rel = page['rel_path']
            record = by_path[rel]
            note = index.by_rel[rel]
            self.assertEqual((record['object_id'], record['revision']), (page['object_id'], page['revision']))
            self.assertEqual((note.object_id, note.revision, note.sha256), (record['object_id'], record['revision'], record['sha256']))
            self.assertTrue(record['content_verified'])
            self.assertEqual((self.root / rel).read_bytes(), page['content'].encode('utf-8'))
            for source in record['sources']:
                self.assertIn(rel, processed[source]['skills'][record['skill']]['outputs'])
        self.assertEqual(raw_before, {p: p.read_bytes() for p in raw_before})
        return plan, manifest

    def test_real_task_review_apply_tracks_objects_and_processed_sources(self):
        (self.root / 'raw/a.md').unlink()
        self.case.install_note('quicknote/想法.md', '# Evidence first\nA small concrete observation about reusable knowledge.')
        self.apply_produced(lambda: steward.command_task(self.cfg, '整理知识库'))

    def test_real_init_review_apply_tracks_objects_and_processed_sources(self):
        answer = json.dumps({'source_summary': 'An evidence record about reusable knowledge.',
                             'key_facts': ['The source contains an evidence record.'], 'quality_flags': [],
                             'topics': [{'topic_title': 'Evidence records', 'topic_stub_content': 'Study reusable source records.'}]})
        with patch('core.llm.call_chat_completion', return_value=answer) as provider:
            self.apply_produced(lambda: steward.command_init_kb(self.cfg, use_llm=True))
        self.assertTrue(provider.called)

    def test_real_finalize_can_update_existing_objects_in_second_run(self):
        for name in ('a', 'b'):
            self.case.install_note(f'wiki/sources/{name}.md', self.case.content('## 关键事实\n- A measured observation.').replace('topic-page', 'source-note'))
        first, _ = self.apply_produced(lambda: steward.command_finalize_kb(self.cfg))
        original = {p['rel_path']: (p['object_id'], p['revision']) for p in first['planned_pages']}
        target = self.root / 'wiki/sources/a.md'
        target.write_bytes(target.read_bytes() + '\n- A second measured observation.\n'.encode('utf-8'))
        second, _ = self.apply_produced(lambda: steward.command_finalize_kb(self.cfg))
        updates = [p for p in second['planned_pages'] if p['operation'] == 'update']
        self.assertTrue(updates)
        for page in updates:
            before_id, before_rev = original[page['rel_path']]
            self.assertEqual((page['object_id'], page['revision']), (before_id, before_rev + 1))

    def test_crlf_bom_chinese_update_keeps_reviewed_bytes_and_identity(self):
        target = self.root / 'wiki/topics/中文主题.md'
        old = '\ufeff' + self.case.content('Before', new_object_id(), 3).replace('\n', '\r\n')
        target.write_bytes(old.encode('utf-8'))
        text = '\ufeff' + self.case.content('After').replace('\n', '\r\n')
        plan = self.case.plan(self.case.page('wiki/topics/中文主题.md', operation='update', content=text))
        path = self.case.persist(plan)
        self.assertEqual(steward.command_apply_plan(self.cfg, str(path)), 0)
        self.assertEqual(target.read_bytes(), plan['planned_pages'][0]['content'].encode('utf-8'))
        self.assertEqual(build_index(self.cfg).by_rel['wiki/topics/中文主题.md'].revision, 4)

    def test_corrupt_existing_manifest_is_preserved_on_failed_retry(self):
        path = self.case.persist(self.case.plan(self.case.page()))
        manifest = self.root / '.openclaw/runs/object-test.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes(b'{incomplete audit record')
        before = manifest.read_bytes()
        with self.assertRaises(RunRecordConflict):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(manifest.read_bytes(), before)
        self.assertFalse((self.root / 'wiki/topics/a.md').exists())
        self.assertEqual(len(list((manifest.parent / 'attempts/object-test').glob('*.json'))), 1)

    @skipUnless(os.name == 'nt', 'Native Windows object-junction write guard')
    def test_native_junction_cannot_alias_raw_into_knowledge_objects(self):
        alias = self.root / 'wiki/topics/raw-alias'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(self.root / 'raw')], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(alias.rmdir)
        before = (self.root / 'raw/a.md').read_bytes()
        page = self.case.page('wiki/topics/raw-alias/a.md', operation='update')
        with self.assertRaises(ObjectIdentityError):
            self.case.persist(self.case.plan(page))
        self.assertEqual((self.root / 'raw/a.md').read_bytes(), before)
