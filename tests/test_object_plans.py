import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.config import sha256_text
from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.plan_objects import bind_plan_objects, validate_object_writes, update_base
from core.run_records import RunRecordConflict
from core.vault import build_index, read_note
from scripts import personal_kb_steward as steward


ROOT = Path(__file__).resolve().parents[1]


class ObjectPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.cfg["knowledge_base"] = str(self.root)
        self.cfg["state_file"] = str(self.root / ".state.json")
        for key, filename in {
            "plans_dir": "plans", "runs_dir": "runs", "processed_index": "processed-index.json",
            "manual_review_queue": "manual-review/queue.jsonl", "backup_dir": "backups",
            "operation_log": "operation-log.jsonl",
        }.items():
            self.cfg["safety"][key] = str(self.root / ".openclaw" / filename)
        for folder in ("raw", "inbox", "quicknote", "wiki/topics"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "raw/a.md").write_text("# Source\n\nAn evidence record.", encoding="utf-8")

    def content(self, text="Current synthesis", object_id=None, revision=1):
        identity = f"object_id: {object_id}\nrevision: {revision}\n" if object_id else ""
        return (f"---\n{identity}title: Sample topic\ntype: topic-page\nstatus: growing\nstage: candidate\n"
                'sources: ["raw/a.md"]\nconfidence: medium\nreview_required: false\n'
                f"custom: keep-me\n---\n# Sample topic\n\n{text}\n")

    def page(self, path="wiki/topics/a.md", operation="create", content=None):
        text = self.content() if content is None else content
        base = update_base(read_note(self.root / path, self.root)) if operation == "update" and (self.root / path).is_file() else {}
        return {**base, "skill": "topic-research-compile", "operation": operation, "rel_path": path,
                "sources": ["raw/a.md"], "content": text, "content_sha256": sha256_text(text),
                "review_required": False, "confidence": "medium"}

    def plan(self, *pages):
        return {"run_id": "object-test", "task": "object identity test", "entry": "discover_topics",
                "primary_skill": "topic-research-compile", "planned_pages": list(pages), "manual_review": []}

    def persist(self, plan):
        return steward.write_execution_plan(self.cfg, plan)

    def install_note(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_plan_allocates_id_before_apply_and_keeps_raw_unchanged(self):
        raw = self.root / "raw/a.md"
        raw_bytes = raw.read_bytes()
        plan = self.plan(self.page())
        path = self.persist(plan)
        saved = json.loads(path.read_text(encoding="utf-8"))
        page = saved["planned_pages"][0]
        self.assertEqual(saved["object_schema_version"], 1)
        self.assertEqual(page["revision"], 1)
        self.assertEqual(page["canonical_path"], page["rel_path"])
        self.assertEqual(page["content_sha256"], sha256_text(page["content"]))
        self.assertFalse((self.root / page["rel_path"]).exists())
        self.assertEqual(raw.read_bytes(), raw_bytes)
        self.assertEqual(steward.command_apply_plan(self.cfg, str(path)), 0)
        index = build_index(self.cfg)
        self.assertEqual(index.by_object_id[page["object_id"]].revision, 1)
        manifest = json.loads((self.root / ".openclaw/runs/object-test.json").read_text())
        self.assertEqual(manifest["created"][0]["object_id"], page["object_id"])
        self.assertEqual(manifest["created"][0]["revision"], 1)
        self.assertEqual(raw.read_bytes(), raw_bytes)

    def test_resaving_plan_does_not_reallocate_or_rebase(self):
        plan = self.plan(self.page())
        path = self.persist(plan)
        before = path.read_bytes()
        self.persist(plan)
        self.assertEqual(path.read_bytes(), before)

    def test_update_preserves_identity_and_increments_revision(self):
        object_id = new_object_id()
        target = self.install_note("wiki/topics/a.md", self.content("Before", object_id, 3))
        before = target.read_bytes()
        # Simulate a renderer that dropped the identity fields entirely.
        plan = self.plan(self.page(operation="update", content=self.content("After")))
        path = self.persist(plan)
        page = plan["planned_pages"][0]
        self.assertEqual((page["object_id"], page["revision"], page["base_revision"]), (object_id, 4, 3))
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(steward.command_apply_plan(self.cfg, str(path)), 0)
        self.assertEqual(build_index(self.cfg).by_object_id[object_id].revision, 4)
        self.assertIn("After", target.read_text())
        self.assertIn("custom: keep-me", target.read_text())

    def test_human_edit_after_planning_blocks_entire_batch(self):
        target = self.install_note("wiki/topics/a.md", self.content("Before", new_object_id(), 2))
        plan = self.plan(self.page("wiki/topics/new.md"), self.page(operation="update"))
        path = self.persist(plan)
        target.write_text(target.read_text() + "Human edit\n", encoding="utf-8")
        edited = target.read_bytes()
        with self.assertRaises(ObjectIdentityError):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(target.read_bytes(), edited)
        self.assertFalse((self.root / "wiki/topics/new.md").exists())

    def test_bound_update_plan_cannot_be_replayed(self):
        self.install_note("wiki/topics/a.md", self.content("Before", new_object_id()))
        path = self.persist(self.plan(self.page(operation="update")))
        steward.command_apply_plan(self.cfg, str(path))
        before = (self.root / "wiki/topics/a.md").read_bytes()
        manifest = self.root / ".openclaw/runs/object-test.json"
        audit_before = manifest.read_bytes()
        backups = {p: p.read_bytes() for p in (self.root / ".openclaw/backups").rglob("*") if p.is_file()}
        with self.assertRaises(RunRecordConflict):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual((self.root / "wiki/topics/a.md").read_bytes(), before)
        self.assertEqual(manifest.read_bytes(), audit_before)
        self.assertEqual(backups, {p: p.read_bytes() for p in (self.root / ".openclaw/backups").rglob("*") if p.is_file()})
        with self.assertRaisesRegex(SystemExit, "包含更新页面"):
            steward.command_rollback(self.cfg, "object-test")

    def test_legacy_page_is_adopted_only_on_explicit_update(self):
        target = self.install_note("wiki/topics/a.md", self.content("Legacy"))
        before = target.read_bytes()
        self.assertIsNone(build_index(self.cfg).by_rel["wiki/topics/a.md"].object_id)
        plan = self.plan(self.page(operation="update"))
        path = self.persist(plan)
        self.assertEqual(target.read_bytes(), before)
        self.assertIsNone(plan["planned_pages"][0]["base_revision"])
        steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(build_index(self.cfg).by_rel["wiki/topics/a.md"].revision, 1)

    def test_legacy_plan_can_create_legacy_page_but_cannot_strip_existing_id(self):
        plan = self.plan(self.page())
        path = self.root / "old-plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        steward.command_apply_plan(self.cfg, str(path))
        self.assertIsNone(build_index(self.cfg).by_rel["wiki/topics/a.md"].object_id)
        self.install_note("wiki/topics/a.md", self.content("Identified", new_object_id()))
        before = (self.root / "wiki/topics/a.md").read_bytes()
        plan = self.plan(self.page(operation="update"))
        plan["run_id"] = "legacy-strip-attempt"
        path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaises(ObjectIdentityError):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual((self.root / "wiki/topics/a.md").read_bytes(), before)

    def test_duplicate_ids_inside_plan_block_all_writes(self):
        plan = self.plan(self.page(), self.page("wiki/topics/b.md"))
        path = self.persist(plan)
        first, second = plan["planned_pages"]
        second["content"] = second["content"].replace(second["object_id"], first["object_id"])
        second["object_id"] = first["object_id"]
        second["content_sha256"] = sha256_text(second["content"])
        path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaises(ObjectIdentityError):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertFalse((self.root / "wiki/topics/a.md").exists())
        self.assertFalse((self.root / "wiki/topics/b.md").exists())

    def test_collision_with_existing_object_is_rejected(self):
        object_id = new_object_id()
        self.install_note("wiki/topics/existing.md", self.content("Original", object_id))
        page = self.page(content=self.content("Copy", object_id))
        with self.assertRaises(ObjectIdentityError):
            validate_object_writes(build_index(self.cfg), [page])

    def test_renderer_cannot_choose_new_object_id(self):
        supplied = new_object_id()
        plan = self.plan(self.page(content=self.content("Text", supplied, 99)))
        self.persist(plan)
        self.assertNotEqual(plan["planned_pages"][0]["object_id"], supplied)
        self.assertEqual(plan["planned_pages"][0]["revision"], 1)

    def test_review_gate_is_not_relaxed(self):
        page = self.page()
        page["review_required"] = True
        plan = self.plan(page)
        path = self.persist(plan)
        with self.assertRaises(SystemExit):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertFalse((self.root / "wiki/topics/a.md").exists())
        self.assertTrue(plan["planned_pages"][0]["review_required"])

    def test_plan_metadata_must_match_markdown(self):
        plan = self.plan(self.page())
        self.persist(plan)
        for key, value in (("object_id", new_object_id()), ("revision", 8), ("revision", True), ("canonical_path", "wiki/topics/other.md")):
            bad = copy.deepcopy(plan)
            bad["planned_pages"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ObjectIdentityError):
                validate_object_writes(build_index(self.cfg), bad["planned_pages"], schema_version=1)

    def test_missing_or_partial_identity_in_bound_plan_is_not_legacy(self):
        for content in (self.content(), self.content().replace("type: topic-page", f"type: topic-page\nobject_id: {new_object_id()}")):
            with self.subTest(content=content), self.assertRaises(ObjectIdentityError):
                validate_object_writes(build_index(self.cfg), [self.page(content=content)], schema_version=1)

    def test_duplicate_frontmatter_identity_keys_are_rejected(self):
        text = self.content("Text", new_object_id()).replace("revision: 1", "revision: 1\nrevision: 2")
        with self.assertRaises(ObjectIdentityError):
            validate_object_writes(build_index(self.cfg), [self.page(content=text)])

    def test_unknown_schema_version_is_rejected(self):
        for version in (True, "1", 2):
            with self.subTest(version=version), self.assertRaises(ObjectIdentityError):
                validate_object_writes(build_index(self.cfg), [], schema_version=version)

    def test_symlink_into_raw_cannot_be_used_as_update_target(self):
        source = self.root / "raw/a.md"
        alias = self.root / "wiki/topics/alias.md"
        try:
            alias.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this platform")
        before = source.read_bytes()
        with self.assertRaises(ObjectIdentityError):
            self.persist(self.plan(self.page("wiki/topics/alias.md", operation="update")))
        self.assertEqual(source.read_bytes(), before)

    def test_reports_remain_available_when_registry_has_issues(self):
        object_id = new_object_id()
        for name in ("a", "b"):
            self.install_note(f"wiki/topics/{name}.md", self.content("Duplicate", object_id))
        lint = steward.healthcheck(build_index(self.cfg), self.cfg)
        self.assertEqual(lint["object_identity_issues"][0]["kind"], "duplicate_object_id")
        report_plan = self.plan(self.page("outputs/report.md", content="# Report\n"))
        path = self.persist(report_plan)
        self.assertNotIn("object_id", report_plan["planned_pages"][0])
        self.assertTrue(path.exists())

    def test_rollback_refuses_update_manifest_instead_of_deleting_object(self):
        target = self.install_note("wiki/topics/a.md", self.content("Before", new_object_id()))
        path = self.persist(self.plan(self.page(operation="update")))
        steward.command_apply_plan(self.cfg, str(path))
        after = target.read_bytes()
        with self.assertRaises(SystemExit):
            steward.command_rollback(self.cfg, "object-test")
        self.assertEqual(target.read_bytes(), after)

    def test_real_task_and_finalize_producers_use_same_identity_boundary(self):
        self.install_note("quicknote/idea.md", "# A small idea\nEvidence first, then synthesis.")
        task_plan = steward.make_execution_plan(self.cfg, "整理知识库")
        self.persist(task_plan)
        self.assertTrue(task_plan["planned_pages"])
        self.assertTrue(all(page.get("object_id") for page in task_plan["planned_pages"]))
        for name in ("a", "b"):
            self.install_note(f"wiki/sources/{name}.md", self.content("## 关键事实\n- A measured fact.").replace("topic-page", "source-note"))
        final_plan = steward.make_finalize_plan(self.cfg, plan_run_id="finalize-test", stamp="2026-09-19")
        self.persist(final_plan)
        self.assertTrue(final_plan["planned_pages"])
        self.assertTrue(all(page.get("object_id") for page in final_plan["planned_pages"]))


if __name__ == "__main__":
    unittest.main()
