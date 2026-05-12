import json
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import personal_kb_steward as steward
from core.finalizer import make_finalize_plan


class WorkflowDeclarationTests(unittest.TestCase):
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

    def test_workflow_pipeline_matches_current_automatic_execution(self):
        workflows = json.loads((ROOT / "workflows.json").read_text(encoding="utf-8-sig"))
        for entry, workflow in workflows["entries"].items():
            with self.subTest(entry=entry):
                if entry == "init_kb":
                    self.assertGreater(len(workflow["pipeline"]), 1)
                    self.assertEqual(workflow["primary_skill"], "kb-initialize")
                else:
                    self.assertEqual(workflow["pipeline"], [workflow["primary_skill"]])

    def test_plan_declared_pipeline_matches_executed_pipeline_for_user_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)

            scenarios = [
                ("topic idea", "discover_topics", ["topic-insight-miner"]),
                ("material pack", "prepare_writing", ["writing-material-pack"]),
                ("timeline review", "weave_work_memory", ["work-memory-weave"]),
            ]
            for task, entry, expected_pipeline in scenarios:
                with self.subTest(entry=entry):
                    plan = steward.make_execution_plan(cfg, task)
                    self.assertEqual(plan["entry"], entry)
                    self.assertEqual(plan["pipeline_declared"], expected_pipeline)
                    self.assertEqual(plan["pipeline_executed_now"], expected_pipeline)
                    self.assertEqual(plan["actions"][0]["pipeline_declared"], expected_pipeline)
                    self.assertEqual(plan["actions"][0]["pipeline_executed_now"], expected_pipeline)

    def test_initial_all_scan_processes_existing_unchanged_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "quicknote" / "old-note.md").write_text(
                "# 旧笔记\n\n这是一条已经存在的旧知识库碎片，需要初始整理。",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            index = steward.build_index(cfg)
            steward.save_state_core(cfg, index, [], steward.stamp())

            incremental_plan = steward.make_execution_plan(cfg, "整理知识库")
            all_scan_plan = steward.make_execution_plan(cfg, "整理知识库", include_all=True)

            self.assertEqual(incremental_plan["scan_scope"], "changed")
            self.assertEqual(incremental_plan["changed_files"], 0)
            self.assertEqual(incremental_plan["candidate_files"], 0)
            self.assertEqual(incremental_plan["planned_pages"], [])
            self.assertEqual(all_scan_plan["scan_scope"], "all")
            self.assertEqual(all_scan_plan["changed_files"], 0)
            self.assertGreaterEqual(all_scan_plan["candidate_files"], 1)
            self.assertGreaterEqual(len(all_scan_plan["planned_pages"]), 1)

    def test_organize_kb_routes_raw_notes_to_compile_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "raw" / "温州人工智能观察.md").write_text(
                "# 温州人工智能观察\n\n这是一篇长文材料，需要先沉淀为 source note 和 topic stub，而不是直接变成 seed。",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            index = steward.build_index(cfg)
            steward.save_state_core(cfg, index, [], steward.stamp())

            plan = steward.make_execution_plan(cfg, "整理知识库", include_all=True)

            follow_up_actions = [
                action for action in plan["actions"]
                if action.get("operation") == "run_follow_up_skill"
            ]
            review_types = {item.get("type") for item in plan["manual_review"]}

            self.assertEqual(follow_up_actions[0]["skill"], "topic-research-compile")
            self.assertGreaterEqual(follow_up_actions[0]["planned_pages"], 1)
            self.assertGreaterEqual(len(plan["planned_pages"]), 1)
            self.assertTrue(any(page["rel_path"].startswith("wiki/sources/source-") for page in plan["planned_pages"]))
            self.assertFalse(any("Mock summary for dry-run" in page["content"] for page in plan["planned_pages"]))
            self.assertNotIn("planned_pages_require_review", review_types)
            self.assertNotIn("raw_input_blocked", review_types)

    def test_organize_kb_blocks_raw_full_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            for idx in range(3):
                (kb / "raw" / f"article-{idx}.md").write_text(
                    "# Article\n\nlong raw article",
                    encoding="utf-8",
                )
            cfg = self.make_cfg(kb)

            plan = steward.make_execution_plan(cfg, "整理知识库", include_all=True)
            review_types = {item.get("type") for item in plan["manual_review"]}

            self.assertIn("wrong_entry_for_initialization", review_types)
            self.assertEqual(plan["planned_pages"], [])
            self.assertFalse(any(action.get("skill") == "topic-research-compile" for action in plan["actions"]))

    def test_init_kb_builds_batched_pipeline_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            for idx in range(7):
                (kb / "raw" / f"温州人工智能资料{idx}.md").write_text(
                    "# 温州人工智能资料\n\n温州人工智能局推动人工智能创新发展先行市建设，布局产业平台和应用场景。",
                    encoding="utf-8",
                )
            (kb / "quicknote" / "idea.md").write_text("# AI课程\n\nAI课程选题 #seed", encoding="utf-8")
            (kb / "raw" / "report.pdf").write_bytes(b"%PDF-1.4")
            cfg = self.make_cfg(kb)

            plan = steward.build_initialization_plan(
                cfg,
                plan_run_id="init-test",
                stamp=steward.stamp(),
                executor_plan_fn=steward.mvp_executor_plan,
                page_requires_manual_review=steward.page_requires_manual_review,
                duplicate_page_targets=steward.duplicate_page_targets,
                page_has_blocked_placeholder=steward.page_has_blocked_placeholder,
                planned_raw_coverage=steward.planned_raw_coverage,
                batch_size=3,
                use_llm=False,
            )

            self.assertEqual(plan["entry"], "init_kb")
            self.assertEqual(plan["batching"]["raw_batches"], 3)
            self.assertGreater(plan["batching"]["remaining_after_current"], 0)
            self.assertTrue(any(action["stage"] == "source_compile" for action in plan["actions"]))
            self.assertTrue(any(page["rel_path"].startswith("wiki/concepts/") for page in plan["planned_pages"]))
            self.assertFalse(any(page["rel_path"].startswith("wiki/topics/topic-") for page in plan["planned_pages"]))
            init_pages = [page for page in plan["planned_pages"] if page.get("skill") == "kb-initialize"]
            self.assertTrue(init_pages)
            self.assertFalse(any(steward.page_requires_manual_review(page) for page in init_pages))
            self.assertIn("raw/report.pdf", plan["batch_queue"]["pdf_needs_extraction"])

    def test_finalize_kb_updates_aggregation_pages_and_related_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "wiki" / "sources").mkdir(parents=True)
            for idx, title in enumerate(["温州人工智能局挂牌", "温州AI产业平台", "温州AI应用场景"]):
                (kb / "raw" / f"{idx}.md").write_text(f"# {title}\n\n原始资料", encoding="utf-8")
                (kb / "wiki" / "sources" / f"source-{idx}.md").write_text(
                    "\n".join([
                        "---",
                        f"title: Source {idx}",
                        "type: source-note",
                        "status: growing",
                        "stage: compiled",
                        "created: 2026-05-11",
                        "updated: 2026-05-11",
                        f"sources: [\"raw/{idx}.md\"]",
                        "related: []",
                        "tags: [\"source\"]",
                        "confidence: high",
                        "review_required: false",
                        "---",
                        f"# Source {idx}",
                        "",
                        "## 关键事实",
                        f"- {title}，推动政策、产业平台和应用场景建设。",
                        "",
                        "## 提取的专题",
                        "- 温州人工智能创新发展路径：围绕政策、机构和产业应用形成路径。",
                    ]),
                    encoding="utf-8",
                )
            cfg = self.make_cfg(kb)

            plan = make_finalize_plan(cfg, plan_run_id="finalize-test", stamp=steward.stamp())

            self.assertEqual(plan["entry"], "finalize_kb")
            self.assertTrue(any(page["rel_path"] == "wiki/topics/温州人工智能创新发展路径.md" for page in plan["planned_pages"]))
            source_updates = [page for page in plan["planned_pages"] if page["rel_path"].startswith("wiki/sources/")]
            self.assertGreaterEqual(len(source_updates), 3)
            self.assertTrue(all("wiki/topics/温州人工智能创新发展路径.md" in page["content"] for page in source_updates))
            material = next(page for page in plan["planned_pages"] if page["rel_path"] == "wiki/material-packs/温州AI政策与产业研究资料包.md")
            self.assertIn("[[wiki/topics/温州人工智能创新发展路径.md]]", material["content"])
            self.assertIn("反方证据与信息缺口", material["content"])
            self.assertEqual(material["content"].count("推动政策、产业平台和应用场景建设"), 1)


if __name__ == "__main__":
    unittest.main()
