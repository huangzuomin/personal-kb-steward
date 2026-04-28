import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import personal_kb_steward as steward  # noqa: E402


class ApplyPlanTests(unittest.TestCase):
    def make_cfg(self, kb: Path) -> dict:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
        cfg["knowledge_base"] = str(kb)
        cfg["state_file"] = str(kb / ".state.json")
        cfg["safety"]["plans_dir"] = str(kb / ".openclaw" / "plans")
        cfg["safety"]["runs_dir"] = str(kb / ".openclaw" / "runs")
        cfg["safety"]["processed_index"] = str(kb / ".openclaw" / "processed-index.json")
        cfg["safety"]["manual_review_queue"] = str(kb / ".openclaw" / "manual-review" / "queue.jsonl")
        cfg["safety"]["backup_dir"] = str(kb / ".openclaw" / "backups")
        cfg["safety"]["operation_log"] = str(kb / ".openclaw" / "operation-log.jsonl")
        return cfg

    def test_apply_plan_and_rollback_on_temp_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "quicknote" / "cursor.md").write_text(
                "# Cursor 课堂\nCursor AI 编程课堂 demo，需要展示重构、测试、运行报告。",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            plan = steward.make_execution_plan(cfg, "整理知识库")
            self.assertGreaterEqual(len(plan["planned_pages"]), 1)
            plan_path = steward.write_execution_plan(cfg, plan)

            self.assertEqual(steward.command_apply_plan(cfg, str(plan_path)), 0)
            created = [kb / page["rel_path"] for page in plan["planned_pages"]]
            self.assertTrue(all(path.exists() for path in created))
            self.assertTrue((kb / ".openclaw" / "operation-log.jsonl").exists())
            self.assertTrue((kb / ".openclaw" / "backups" / plan["run_id"]).exists())

            self.assertEqual(steward.command_rollback(cfg, plan["run_id"]), 0)
            self.assertTrue(all(not path.exists() for path in created))
            self.assertTrue((kb / ".openclaw" / "backups" / f"rollback-{plan['run_id']}").exists())

    def test_apply_plan_failure_reports_recovery_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            bad_plan = {
                "run_id": "bad-plan",
                "task": "bad input",
                "primary_skill": "mindseed-grow",
                "planned_pages": [{
                    "skill": "mindseed-grow",
                    "operation": "create",
                    "rel_path": "raw/blocked.md",
                    "sources": [],
                    "content": "blocked",
                    "content_sha256": steward.sha256_text("blocked"),
                }],
            }
            plan_path = kb / ".openclaw" / "plans" / "bad-plan.json"
            steward.write_json(plan_path, bad_plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            manifest = kb / ".openclaw" / "runs" / "bad-plan.json"
            self.assertTrue(manifest.exists())
            self.assertTrue((kb / ".openclaw" / "operation-log.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
