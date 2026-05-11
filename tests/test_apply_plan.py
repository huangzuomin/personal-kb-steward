import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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

    def test_empty_directory_plan_logs_and_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)

            plan = steward.make_execution_plan(cfg, "整理知识库")
            plan_path = steward.write_execution_plan(cfg, plan)

            self.assertEqual(plan["changed_files"], 0)
            self.assertEqual(plan["planned_pages"], [])
            self.assertTrue(plan_path.exists())
            self.assertTrue((kb / ".openclaw" / "operation-log.jsonl").exists())

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
            generated_text = created[0].read_text(encoding="utf-8")
            self.assertIn("origin:", generated_text)
            self.assertIn("quicknote/cursor.md", generated_text)
            self.assertTrue((kb / ".openclaw" / "operation-log.jsonl").exists())
            self.assertTrue((kb / ".openclaw" / "backups" / plan["run_id"]).exists())
            run_logs = list((kb / "logs").rglob("*.md"))
            self.assertTrue(any("## Input Files" in p.read_text(encoding="utf-8") for p in run_logs))
            self.assertTrue(any("quicknote/cursor.md" in p.read_text(encoding="utf-8") for p in run_logs))
            self.assertTrue(any("## Output Files" in p.read_text(encoding="utf-8") for p in run_logs))

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

    def test_hash_mismatch_fails_before_any_page_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "wiki" / "seeds").mkdir(parents=True)
            cfg = self.make_cfg(kb)
            bad_plan = {
                "run_id": "hash-mismatch",
                "task": "bad hash",
                "primary_skill": "mindseed-grow",
                "planned_pages": [
                    {
                        "skill": "mindseed-grow",
                        "operation": "create",
                        "rel_path": "wiki/seeds/first.md",
                        "sources": [],
                        "content": "first",
                        "content_sha256": steward.sha256_text("first"),
                    },
                    {
                        "skill": "mindseed-grow",
                        "operation": "create",
                        "rel_path": "wiki/seeds/second.md",
                        "sources": [],
                        "content": "second",
                        "content_sha256": steward.sha256_text("tampered"),
                    },
                ],
            }
            plan_path = kb / ".openclaw" / "plans" / "hash-mismatch.json"
            steward.write_json(plan_path, bad_plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            self.assertFalse((kb / "wiki" / "seeds" / "first.md").exists())
            self.assertFalse((kb / "wiki" / "seeds" / "second.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "hash-mismatch.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["created"], [])
            self.assertIn("重新生成 plan", manifest["next_step"])

    def test_apply_plan_blocks_duplicate_targets_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            plan = {
                "run_id": "duplicate-targets",
                "task": "duplicate targets",
                "primary_skill": "topic-research-compile",
                "planned_pages": [
                    {
                        "skill": "topic-research-compile",
                        "operation": "create",
                        "rel_path": "wiki/sources/source-ai.md",
                        "sources": ["raw/a.md"],
                        "content": "first",
                        "content_sha256": steward.sha256_text("first"),
                    },
                    {
                        "skill": "topic-research-compile",
                        "operation": "create",
                        "rel_path": "wiki/sources/source-ai.md",
                        "sources": ["raw/b.md"],
                        "content": "second",
                        "content_sha256": steward.sha256_text("second"),
                    },
                ],
            }
            plan_path = kb / ".openclaw" / "plans" / "duplicate-targets.json"
            steward.write_json(plan_path, plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            self.assertFalse((kb / "wiki" / "sources" / "source-ai.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "duplicate-targets.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["created"], [])

    def test_apply_plan_blocks_mock_content_even_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            content = "# Source\n\nMock summary for dry-run.\n"
            plan = {
                "run_id": "mock-content",
                "task": "mock content",
                "primary_skill": "topic-research-compile",
                "planned_pages": [{
                    "skill": "topic-research-compile",
                    "operation": "create",
                    "rel_path": "wiki/sources/mock.md",
                    "sources": ["raw/a.md"],
                    "content": content,
                    "content_sha256": steward.sha256_text(content),
                    "review_required": True,
                    "confidence": "low",
                }],
            }
            plan_path = kb / ".openclaw" / "plans" / "mock-content.json"
            steward.write_json(plan_path, plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path), allow_reviewed=True)

            self.assertFalse((kb / "wiki" / "sources" / "mock.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "mock-content.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")

    def test_apply_plan_blocks_manual_review_pages_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "wiki" / "seeds").mkdir(parents=True)
            cfg = self.make_cfg(kb)
            plan = {
                "run_id": "manual-review-block",
                "task": "manual review",
                "primary_skill": "mindseed-grow",
                "planned_pages": [
                    {
                        "skill": "mindseed-grow",
                        "operation": "create",
                        "rel_path": "wiki/seeds/safe.md",
                        "sources": ["quicknote/a.md"],
                        "content": "safe",
                        "content_sha256": steward.sha256_text("safe"),
                        "review_required": False,
                        "confidence": "medium",
                    },
                    {
                        "skill": "mindseed-grow",
                        "operation": "create",
                        "rel_path": "wiki/seeds/review.md",
                        "sources": ["quicknote/b.md"],
                        "content": "review",
                        "content_sha256": steward.sha256_text("review"),
                        "review_required": True,
                        "confidence": "medium",
                    },
                ],
            }
            plan_path = kb / ".openclaw" / "plans" / "manual-review-block.json"
            steward.write_json(plan_path, plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            self.assertFalse((kb / "wiki" / "seeds" / "safe.md").exists())
            self.assertFalse((kb / "wiki" / "seeds" / "review.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "manual-review-block.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["created"], [])
            self.assertIn("manual review queue", manifest["next_step"])

    def test_apply_plan_blocks_low_confidence_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            plan = {
                "run_id": "low-confidence-block",
                "task": "low confidence",
                "primary_skill": "topic-insight-miner",
                "planned_pages": [{
                    "skill": "topic-insight-miner",
                    "operation": "create",
                    "rel_path": "wiki/topics/low.md",
                    "sources": ["raw/a.md"],
                    "content": "low",
                    "content_sha256": steward.sha256_text("low"),
                    "review_required": False,
                    "confidence": "low",
                }],
            }
            plan_path = kb / ".openclaw" / "plans" / "low-confidence-block.json"
            steward.write_json(plan_path, plan)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            self.assertFalse((kb / "wiki" / "topics" / "low.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "low-confidence-block.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("manual review queue", manifest["next_step"])

    def test_init_kb_apply_skips_existing_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "wiki" / "sources").mkdir(parents=True)
            (kb / "wiki" / "sources" / "existing.md").write_text("existing", encoding="utf-8")
            cfg = self.make_cfg(kb)
            content = "new"
            plan = {
                "run_id": "init-skip-existing",
                "task": "init skip existing",
                "entry": "init_kb",
                "primary_skill": "kb-initialize",
                "planned_pages": [
                    {
                        "skill": "topic-research-compile",
                        "operation": "create",
                        "rel_path": "wiki/sources/existing.md",
                        "sources": ["raw/a.md"],
                        "content": "replacement",
                        "content_sha256": steward.sha256_text("replacement"),
                        "review_required": False,
                        "confidence": "medium",
                    },
                    {
                        "skill": "topic-research-compile",
                        "operation": "create",
                        "rel_path": "wiki/sources/new.md",
                        "sources": ["raw/b.md"],
                        "content": content,
                        "content_sha256": steward.sha256_text(content),
                        "review_required": False,
                        "confidence": "medium",
                    },
                ],
            }
            plan_path = kb / ".openclaw" / "plans" / "init-skip-existing.json"
            steward.write_json(plan_path, plan)

            self.assertEqual(steward.command_apply_plan(cfg, str(plan_path)), 0)

            self.assertEqual((kb / "wiki" / "sources" / "existing.md").read_text(encoding="utf-8"), "existing")
            self.assertTrue((kb / "wiki" / "sources" / "new.md").exists())
            manifest = json.loads((kb / ".openclaw" / "runs" / "init-skip-existing.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "applied")
            self.assertEqual(manifest["skipped_existing_pages"], ["wiki/sources/existing.md"])

    def test_review_apply_approved_applies_reviewed_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            content = "reviewed page"
            plan = {
                "run_id": "approved-run",
                "task": "approved plan",
                "primary_skill": "mindseed-grow",
                "planned_pages": [{
                    "skill": "mindseed-grow",
                    "operation": "create",
                    "rel_path": "wiki/seeds/reviewed.md",
                    "sources": [],
                    "content": content,
                    "content_sha256": steward.sha256_text(content),
                    "review_required": True,
                    "confidence": "low",
                }],
            }
            plan_path = kb / ".openclaw" / "plans" / "approved-run.json"
            steward.write_json(plan_path, plan)
            steward.append_item(steward.review_queue_path(cfg), {
                "run_id": "approved-run",
                "entry": "organize_kb",
                "task": "approved plan",
                "type": "planned_executor_issues",
                "risk": "P2",
                "reason": "needs review",
                "status": "approved",
            })

            args = SimpleNamespace(review_command="apply-approved")
            self.assertEqual(steward.command_review(cfg, args), 0)
            self.assertTrue((kb / "wiki" / "seeds" / "reviewed.md").exists())
            queue = steward.load_queue(steward.review_queue_path(cfg))
            self.assertEqual(queue[0]["status"], "applied")
            self.assertIn("applied_at", queue[0])

    def test_review_apply_approved_refuses_pending_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            content = "reviewed page"
            plan = {
                "run_id": "pending-run",
                "task": "pending plan",
                "primary_skill": "mindseed-grow",
                "planned_pages": [{
                    "skill": "mindseed-grow",
                    "operation": "create",
                    "rel_path": "wiki/seeds/reviewed.md",
                    "sources": [],
                    "content": content,
                    "content_sha256": steward.sha256_text(content),
                    "review_required": True,
                    "confidence": "low",
                }],
            }
            plan_path = kb / ".openclaw" / "plans" / "pending-run.json"
            steward.write_json(plan_path, plan)
            steward.append_item(steward.review_queue_path(cfg), {
                "run_id": "pending-run",
                "type": "approved",
                "status": "approved",
            })
            steward.append_item(steward.review_queue_path(cfg), {
                "run_id": "pending-run",
                "type": "still_pending",
            })

            args = SimpleNamespace(review_command="apply-approved")
            self.assertEqual(steward.command_review(cfg, args), 1)
            self.assertFalse((kb / "wiki" / "seeds" / "reviewed.md").exists())

    def test_malformed_plan_json_reports_next_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            plan_path = kb / ".openclaw" / "plans" / "broken-json.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, str(plan_path))

            manifest = json.loads((kb / ".openclaw" / "runs" / "broken-json.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("重新生成 plan", manifest["next_step"])
            self.assertTrue((kb / ".openclaw" / "operation-log.jsonl").exists())

    def test_missing_plan_reference_reports_path_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)

            with self.assertRaises(SystemExit):
                steward.command_apply_plan(cfg, "missing-plan")

            manifest = json.loads((kb / ".openclaw" / "runs" / "missing-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("plan", manifest["next_step"])

    def test_topic_research_compile_created_pages_are_applied_and_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            raw = kb / "raw" / "article.md"
            raw.write_text(
                "# Long research article\n\nThis report studies durable knowledge base workflows, ingestion, summaries, and source tracking.",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            cfg["_run_id"] = "topic-compile-test"
            index = steward.build_index(cfg)

            result = steward.execute_skill(steward.ROOT, "topic-research-compile", {
                "config": cfg,
                "notes": steward.executor_notes([index.by_rel["raw/article.md"]]),
                "use_llm": False,
            })
            op = steward.apply_executor_pages(index, cfg, result)

            self.assertEqual(op["skill"], "topic-research-compile")
            self.assertIn("raw/article.md", op["inputs"])
            self.assertGreaterEqual(len(op["created"]), 1)
            self.assertTrue(any(rel.startswith("wiki/sources/") for rel in op["created"]))
            self.assertEqual(op["manual_reviews"], [])
            self.assertTrue(all((kb / rel).exists() for rel in op["created"]))

            steward.update_processed_index(index, cfg, [op])
            processed = json.loads((kb / ".openclaw" / "processed-index.json").read_text(encoding="utf-8"))
            record = processed["processed"]["raw/article.md"]["skills"]["topic-research-compile"]
            self.assertEqual(record["operation_status"], "needs_review")
            self.assertTrue(any(rel.startswith("wiki/sources/") for rel in record["outputs"]))
            self.assertEqual(
                [note.rel for note in steward.unprocessed_notes(processed, [index.by_rel["raw/article.md"]], "topic-research-compile")],
                ["raw/article.md"],
            )

    def test_processed_index_keeps_issue_records_unprocessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "quicknote" / "needs-review.md").write_text("# Needs Review\n\nuncertain", encoding="utf-8")
            cfg = self.make_cfg(kb)
            index = steward.build_index(cfg)
            op = {
                "skill": "mindseed-grow",
                "created": ["wiki/seeds/needs-review.md"],
                "inputs": ["quicknote/needs-review.md"],
                "issues": ["low confidence"],
            }

            steward.update_processed_index(index, cfg, [op])
            processed = json.loads((kb / ".openclaw" / "processed-index.json").read_text(encoding="utf-8"))
            record = processed["processed"]["quicknote/needs-review.md"]["skills"]["mindseed-grow"]

            self.assertEqual(record["operation_status"], "needs_review")
            self.assertEqual(
                [note.rel for note in steward.unprocessed_notes(processed, [index.by_rel["quicknote/needs-review.md"]], "mindseed-grow")],
                ["quicknote/needs-review.md"],
            )


if __name__ == "__main__":
    unittest.main()
