"""Regression contracts from the pre-merge safety review; no real vaults."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import personal_kb_steward as steward
from scripts import validate_config as validator

ROOT = Path(__file__).resolve().parents[1]


def isolated_config(root):
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    cfg["knowledge_base"] = str(root)
    cfg["state_file"] = str(root / ".openclaw/state.json")
    for key, filename in {
        "plans_dir": "plans", "runs_dir": "runs", "processed_index": "processed-index.json",
        "manual_review_queue": "manual-review/queue.jsonl", "backup_dir": "backups",
        "operation_log": "operation-log.jsonl",
    }.items():
        cfg["safety"][key] = str(root / ".openclaw" / filename)
    cfg["llm"]["api_key_env"] = "STEWARD_TEST_UNUSED_KEY"
    return cfg


class RollbackReviewTests(unittest.TestCase):
    def test_update_and_mixed_runs_refuse_before_any_deletion(self):
        for operations in (("update",), ("create", "update"), ("update", "create")):
            with self.subTest(operations=operations), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                cfg = isolated_config(root)
                pages = []
                for i, operation in enumerate(operations):
                    target = root / f"wiki/topics/{i}.md"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if operation == "update":
                        target.write_text("Old version", encoding="utf-8")
                    text = f"New version {i}"
                    pages.append({"skill": "kb-finalize", "operation": operation,
                                  "rel_path": target.relative_to(root).as_posix(),
                                  "content": text, "content_sha256": steward.sha256_text(text), "sources": []})
                # Legacy serialized plan: this tests recovery, not LLM or identity binding.
                path = root / "review-plan.json"
                path.write_text(json.dumps({"run_id": "review-mixed", "planned_pages": pages}), encoding="utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    steward.command_apply_plan(cfg, str(path))
                manifest = root / ".openclaw/runs/review-mixed.json"
                before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
                with patch.object(steward, "safe_delete_file") as delete:
                    with self.assertRaisesRegex(SystemExit, "包含更新页面"):
                        steward.command_rollback(cfg, "review-mixed")
                    delete.assert_not_called()
                self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})
                self.assertEqual(json.loads(manifest.read_text())["status"], "applied")

    def test_pure_create_rollback_still_works(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = isolated_config(root)
            text = "# Generated page\n"
            page = {"skill": "mindseed-grow", "operation": "create", "rel_path": "wiki/seeds/new.md",
                    "content": text, "content_sha256": steward.sha256_text(text), "sources": []}
            path = root / "plan.json"
            path.write_text(json.dumps({"run_id": "create-only", "planned_pages": [page]}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                steward.command_apply_plan(cfg, str(path))
                steward.command_rollback(cfg, "create-only")
            self.assertFalse((root / page["rel_path"]).exists())
            self.assertTrue((root / ".openclaw/backups/rollback-create-only/wiki/seeds/new.md").exists())


class ConfigReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "agent"
        self.root.mkdir()
        self.cfg = isolated_config(self.root)
        self.router = json.loads((ROOT / "router.json").read_text(encoding="utf-8"))
        self.workflows = json.loads((ROOT / "workflows.json").read_text(encoding="utf-8"))

    def validate(self, cfg):
        values = {validator.CONFIG_PATH: cfg, validator.ROUTER_PATH: self.router,
                  validator.WORKFLOWS_PATH: self.workflows}
        with patch.object(validator, "ROOT", self.root), patch.object(validator, "read_json", side_effect=lambda p: values[p]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = validator.main()
        return result, output.getvalue()

    def test_public_contract_allows_internal_workflows_without_advertising_them(self):
        self.assertIn("init_kb", self.workflows["entries"])
        code, out = self.validate(self.cfg)
        self.assertEqual(code, 0, out)
        self.assertNotIn("init_kb", out)
        for entry in validator.PUBLIC_ENTRIES:
            self.assertIn(entry, out)

    def test_missing_unknown_empty_internal_only_and_duplicate_entries_rejected(self):
        public = list(self.cfg["routing"]["user_entries"])
        invalid = [public[:-1], public + ["unknown"], [], ["init_kb"], public + ["init_kb"], public + [public[0]], "organize_kb", [None]]
        for entries in invalid:
            with self.subTest(entries=entries):
                cfg = copy.deepcopy(self.cfg)
                cfg["routing"]["user_entries"] = entries
                self.assertEqual(self.validate(cfg)[0], 1)

    def test_missing_public_workflow_rejected(self):
        del self.workflows["entries"]["organize_kb"]
        self.assertEqual(self.validate(self.cfg)[0], 1)

    def test_sibling_prefix_escape_rejected_for_every_runtime_path(self):
        for key in ("plans_dir", "runs_dir", "processed_index", "manual_review_queue", "backup_dir", "operation_log"):
            with self.subTest(key=key):
                cfg = copy.deepcopy(self.cfg)
                cfg["safety"][key] = str(self.root.with_name("agent-other") / key)
                self.assertEqual(self.validate(cfg)[0], 1)

    def test_dotdot_escape_rejected_but_nested_directories_allowed(self):
        self.cfg["safety"]["backup_dir"] = str(self.root / "child" / ".." / ".." / "outside")
        self.assertEqual(self.validate(self.cfg)[0], 1)
        self.cfg["safety"]["backup_dir"] = str(self.root / "child" / ".." / "backups")
        self.assertEqual(self.validate(self.cfg)[0], 0)

    def test_symlink_escape_rejected(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Directory symlinks unavailable")
        self.cfg["safety"]["backup_dir"] = str(alias / "backups")
        self.assertEqual(self.validate(self.cfg)[0], 1)
