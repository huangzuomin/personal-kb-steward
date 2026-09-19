"""Reproduce failed-retry audit loss and the pre-save stale-baseline window."""
import contextlib
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.run_records import RunRecordConflict
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


class RecoveryReviewTests(TestCase):
    def setUp(self):
        self.case = fixtures.ObjectPlanTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root, self.cfg = self.case.root, self.case.cfg
        self.manifest = self.root / ".openclaw/runs/object-test.json"
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def update_plan(self, mixed=False):
        self.case.install_note("wiki/topics/a.md", self.case.content("Old", new_object_id(), 3))
        pages = [self.case.page(operation="update", content=self.case.content("New"))]
        if mixed:
            pages.append(self.case.page("wiki/topics/b.md"))
        return self.case.plan(*pages)

    def test_create_replay_preserves_applied_manifest_and_remaining_recovery(self):
        path = self.case.persist(self.case.plan(self.case.page()))
        steward.command_apply_plan(self.cfg, str(path))
        before = self.manifest.read_bytes()
        with self.assertRaises(RunRecordConflict):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(self.manifest.read_bytes(), before)
        events = [json.loads(p.read_text(encoding="utf-8")) for p in (self.root / ".openclaw/runs/attempts/object-test").glob("*.json")]
        self.assertEqual(len({event["attempt_id"] for event in events}), 2)
        self.assertTrue(any(event["status"] == "failed" and event["preserved_existing_run"] for event in events))
        steward.command_rollback(self.cfg, "object-test")
        self.assertFalse((self.root / "wiki/topics/a.md").exists())

    def test_generation_to_first_save_edit_refused_for_identified_and_legacy(self):
        for object_id in (None, new_object_id()):
            with self.subTest(object_id=object_id):
                target = self.case.install_note("wiki/topics/a.md", self.case.content("Old", object_id, 3))
                plan = self.case.plan(self.case.page("wiki/topics/new.md"), self.case.page(operation="update"))
                original_base = plan["planned_pages"][1]["base_sha256"]
                target.write_text(target.read_text(encoding="utf-8") + "Human edit\n", encoding="utf-8")
                before = target.read_bytes()
                with self.assertRaisesRegex(ObjectIdentityError, "Generation base"):
                    self.case.persist(plan)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(plan["planned_pages"][1]["base_sha256"], original_base)
                self.assertNotIn("object_schema_version", plan)
                self.assertFalse((self.root / "wiki/topics/new.md").exists())

    def test_update_without_generation_snapshot_does_not_acquire_save_time_base(self):
        plan = self.update_plan()
        for key in ("base_sha256", "base_revision", "base_object_id"):
            del plan["planned_pages"][0][key]
        with self.assertRaisesRegex(ObjectIdentityError, "generation-time base"):
            self.case.persist(plan)

    def test_bound_update_resave_after_edit_preserves_exact_original_plan(self):
        plan = self.update_plan()
        path = self.case.persist(plan)
        before = path.read_bytes()
        target = self.root / "wiki/topics/a.md"
        target.write_text(target.read_text(encoding="utf-8") + "Human edit\n", encoding="utf-8")
        changed = target.read_bytes()
        self.case.persist(plan)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(ObjectIdentityError):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(target.read_bytes(), changed)

    def test_second_write_failure_preserves_partial_run_and_backup_on_retry(self):
        plan = self.update_plan(mixed=True)
        path = self.case.persist(plan)
        writer = steward.safe_write_text
        def fail_second(cfg, target, content, **kw):
            if kw["operation"] == "apply_plan_create_page" and target.name == "b.md":
                raise OSError("injected second write failure")
            return writer(cfg, target, content, **kw)
        with patch.object(steward, "safe_write_text", side_effect=fail_second), self.assertRaises(OSError):
            steward.command_apply_plan(self.cfg, str(path))
        before = self.manifest.read_bytes()
        record = json.loads(before)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["phase"], "writing_pages")
        self.assertEqual(len(record["created"]), 1)
        self.assertEqual(record["created"][0]["object_id"], plan["planned_pages"][0]["object_id"])
        self.assertEqual(record["created"][0]["revision"], 4)
        self.assertEqual(record["created"][0]["operation"], "update")
        backup = Path(record["created"][0]["backup_path"])
        old = backup.read_bytes()
        self.assertIn(b"Old", old)
        self.assertFalse((self.root / "wiki/topics/b.md").exists())
        with self.assertRaises(RunRecordConflict):
            steward.command_apply_plan(self.cfg, str(path))
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(backup.read_bytes(), old)
        with self.assertRaisesRegex(SystemExit, "包含更新页面"):
            steward.command_rollback(self.cfg, "object-test")

    def test_log_failure_after_page_write_keeps_actual_write_in_manifest(self):
        import core.safety as safety
        path = self.case.persist(self.update_plan())
        logger = safety.append_operation_log
        def fail_after_write(cfg, event):
            if event["operation"] == "apply_plan_update_page":
                raise OSError("post-write log failure")
            return logger(cfg, event)
        with patch.object(safety, "append_operation_log", side_effect=fail_after_write), self.assertRaises(OSError):
            steward.command_apply_plan(self.cfg, str(path))
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["created"]), 1)
        self.assertTrue(record["created"][0]["content_verified"])
        self.assertTrue(Path(record["created"][0]["backup_path"]).is_file())

    def test_metadata_stage_failures_never_report_success_or_lose_written_pages(self):
        for stage in ("write_run_log", "update_processed_index", "save_state", "update_index"):
            with self.subTest(stage=stage):
                plan = self.case.plan(self.case.page(f"wiki/topics/{stage}.md"))
                plan["run_id"] = stage
                path = self.case.persist(plan)
                with patch.object(steward, stage, side_effect=OSError(stage)), self.assertRaises(OSError):
                    steward.command_apply_plan(self.cfg, str(path))
                manifest = self.root / f".openclaw/runs/{stage}.json"
                before = manifest.read_bytes()
                record = json.loads(before)
                self.assertEqual((record["status"], record["phase"]), ("failed", stage))
                self.assertEqual(len(record["created"]), 1)
                self.assertTrue(record["created"][0]["content_verified"])
                with self.assertRaises(RunRecordConflict):
                    steward.command_apply_plan(self.cfg, str(path))
                self.assertEqual(manifest.read_bytes(), before)

    def test_corrupt_write_is_not_reported_as_success(self):
        path = self.case.persist(self.case.plan(self.case.page()))
        def corrupt(cfg, target, content, **kw):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"incomplete")
            return {"operation": kw["operation"]}
        with patch.object(steward, "safe_write_text", side_effect=corrupt), self.assertRaises(SystemExit):
            steward.command_apply_plan(self.cfg, str(path))
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertFalse(record["created"][0]["content_verified"])
        with self.assertRaises(SystemExit):
            steward.command_rollback(self.cfg, "object-test")

    def test_actual_finalizer_captures_base_before_first_save(self):
        for name in ("a", "b"):
            self.case.install_note(f"wiki/sources/{name}.md", self.case.content("## 关键事实\n- A measured fact.", new_object_id()).replace("topic-page", "source-note"))
        plan = steward.make_finalize_plan(self.cfg, plan_run_id="finalizer-base", stamp="2026-09-19")
        updates = [p for p in plan["planned_pages"] if p["operation"] == "update"]
        self.assertTrue(updates)
        self.assertTrue(all(p.get("base_sha256") for p in updates))
        target = self.root / updates[0]["rel_path"]
        target.write_text(target.read_text(encoding="utf-8") + "Human change", encoding="utf-8")
        before = target.read_bytes()
        with self.assertRaises(ObjectIdentityError):
            self.case.persist(plan)
        self.assertEqual(target.read_bytes(), before)

    def test_preflight_rejection_can_be_approved_and_retried_without_writes(self):
        page = self.case.page()
        page["review_required"] = True
        path = self.case.persist(self.case.plan(page))
        with self.assertRaises(SystemExit):
            steward.command_apply_plan(self.cfg, str(path))
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertFalse(record["write_started"])
        self.assertEqual(record["created"], [])
        steward.command_apply_plan(self.cfg, str(path), allow_reviewed=True)
        self.assertEqual(json.loads(self.manifest.read_text(encoding="utf-8"))["status"], "applied")
