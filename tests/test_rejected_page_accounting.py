"""被人拒绝的页面必须被记成终态，否则整轮不记账、源文件被无限重复消费。

Regression（2026-09-22 生产库实测）：page-scoped subset apply 只批准部分页面时，
`processed_completion_operations` 的保守分支曾要求 plan 里**每一页**的产物都有事实。
被拒页按设计不落盘 ⇒ 没有事实 ⇒ 返回 [] ⇒ `processed_index_advanced=False` ⇒
`is_processed()` 永为 False ⇒ 下一轮原样重选同一批源文件，等于无限重复烧预算。

修复后：判据收缩到本次**选中**的页面；被拒页的源文件补一条空目标的终态记录
（`operation_status: skipped`），人工拒绝因此被记住。
"""
from __future__ import annotations

import contextlib
import io
import json
from types import SimpleNamespace
from unittest import TestCase

from core.apply_execution import processed_completion_operations
from core.review_queue import is_page_review_item
from core.state import is_processed, load_processed_index, unprocessed_notes
from core.vault import build_index
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


class RejectedPageAccountingTests(TestCase):
    def setUp(self):
        self.case = fixtures.ObjectPlanTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root, self.cfg = self.case.root, self.case.cfg
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def _queue(self, run_id: str) -> list[dict]:
        return [
            item for item in steward.load_queue(steward.review_queue_path(self.cfg))
            if item.get("run_id") == run_id
        ]

    def _review(self, command: str, **kwargs) -> int:
        return steward.command_review(
            self.cfg, SimpleNamespace(review_command=command, **kwargs)
        )

    def _persist_and_queue(self, plan: dict):
        """落 plan 并入队，走生产的 write_execution_plan + write_manual_review_queue。

        `write_execution_plan` 只写 plan 文件；页面审核行由
        `write_manual_review_queue` 依据 `manual_review` 里的
        `planned_pages_require_review` 条目展开，且该条目同时把 review_contract
        置为 page-scoped-v1。
        """
        plan.setdefault("manual_review", []).append(
            {
                "type": "planned_pages_require_review",
                "risk": "medium",
                "reason": "fixture page review",
            }
        )
        path = self.case.persist(plan)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["review_contract"], "page-scoped-v1")
        self.assertEqual(steward.write_manual_review_queue(self.cfg, saved), len(saved["planned_pages"]))
        return path, saved

    def _partial_approval_fixture(self):
        """两页 plan：批准第一页、拒绝第二页，然后 apply-approved。

        返回 (plan_path, plan, subset_manifest, kept_target, declined_target)。
        """
        kept = self.case.page(
            "wiki/topics/kept.md", content=self.case.content("Kept synthesis")
        )
        declined = self.case.page(
            "wiki/topics/declined.md", content=self.case.content("Declined synthesis")
        )
        # 第二页绑定另一个源文件，便于分别断言两个源的终态。
        self.case.install_note("raw/b.md", "# Second source\n\nAnother evidence record.")
        declined["sources"] = ["raw/b.md"]

        path, plan = self._persist_and_queue(self.case.plan(kept, declined))
        run_id = plan["run_id"]

        queued = self._queue(run_id)
        page_rows = [item for item in queued if is_page_review_item(item)]
        self.assertEqual(len(page_rows), 2, page_rows)
        # 非页面项（若有）必须先清空，否则该 run 的 pending 不为零会阻塞 apply。
        for item in queued:
            if not is_page_review_item(item):
                self.assertEqual(
                    self._review("approve", id=item["id"], reason="fixture"), 0
                )

        by_target = {row["target"]: row for row in page_rows}
        kept_target = kept["rel_path"]
        declined_target = declined["rel_path"]
        self.assertIn(kept_target, by_target)
        self.assertIn(declined_target, by_target)
        self.assertEqual(
            self._review("approve", id=by_target[kept_target]["id"], reason="keep"), 0
        )
        self.assertEqual(
            self._review("reject", id=by_target[declined_target]["id"], reason="declined"),
            0,
        )
        self.assertEqual(self._review("apply-approved"), 0)

        subset_paths = sorted(
            (self.root / ".openclaw/runs").glob(f"{run_id}.subset-*.json")
        )
        self.assertEqual(len(subset_paths), 1, subset_paths)
        subset = json.loads(subset_paths[0].read_text(encoding="utf-8"))
        return path, plan, subset, kept_target, declined_target

    def test_partial_approval_advances_processed_index_and_records_rejection(self):
        path, plan, subset, kept_target, declined_target = self._partial_approval_fixture()
        skill = plan["primary_skill"]

        # ① 修复的核心：部分批准不再让整轮记账停摆。
        self.assertTrue(
            subset["processed_index_advanced"],
            f"processed_index_advanced={subset.get('processed_index_advanced')!r}",
        )
        # ② 拒绝被带进 subset 上下文。
        self.assertEqual(subset["rejected_targets"], [declined_target])

        # ③ 被拒页按设计没有落盘，批准页已落盘。
        self.assertFalse((self.root / declined_target).exists())
        self.assertTrue((self.root / kept_target).exists())

        # ④ 两个源文件各得其所：批准页源 created 且带产出；被拒页源 skipped 且无产出。
        index = build_index(self.cfg)
        processed = load_processed_index(self.cfg)
        kept_record = processed["processed"]["raw/a.md"]["skills"][skill]
        declined_record = processed["processed"]["raw/b.md"]["skills"][skill]
        self.assertEqual(kept_record["operation_status"], "created")
        self.assertEqual(kept_record["outputs"], [kept_target])
        self.assertEqual(declined_record["operation_status"], "skipped")
        self.assertEqual(declined_record["outputs"], [])

        # ⑤ 两个源都算「已处理」，下一轮不会再被选出来。
        self.assertTrue(is_processed(processed, index.by_rel["raw/a.md"], skill))
        self.assertTrue(is_processed(processed, index.by_rel["raw/b.md"], skill))
        still = unprocessed_notes(
            processed,
            [index.by_rel["raw/a.md"], index.by_rel["raw/b.md"]],
            skill,
        )
        self.assertEqual([note.rel for note in still], [])

    def test_without_rejected_targets_the_declined_source_is_left_unrecorded(self):
        """对照：不传 rejected_targets 时，被拒页的源会被永久重复消费。"""
        path, plan, subset, kept_target, declined_target = self._partial_approval_fixture()
        index = build_index(self.cfg)

        old_ops = processed_completion_operations(
            self.cfg, plan, path, subset["created"], index,
            selected_targets=[kept_target],
        )
        old_sources = {rel for op in old_ops for rel in op.get("inputs", [])}
        self.assertEqual(old_sources, {"raw/a.md"})

        new_ops = processed_completion_operations(
            self.cfg, plan, path, subset["created"], index,
            selected_targets=[kept_target],
            rejected_targets=[declined_target],
        )
        new_sources = {rel for op in new_ops for rel in op.get("inputs", [])}
        self.assertEqual(new_sources, {"raw/a.md", "raw/b.md"})

    def test_all_pages_rejected_does_not_fabricate_completion(self):
        """全部拒绝时不该凭空记账——没有选中页就没有可证明的产物。"""
        declined = self.case.page(
            "wiki/topics/only.md", content=self.case.content("Only synthesis")
        )
        path, plan = self._persist_and_queue(self.case.plan(declined))
        run_id = plan["run_id"]

        queued = self._queue(run_id)
        page_rows = [item for item in queued if is_page_review_item(item)]
        self.assertEqual(len(page_rows), 1)
        self.assertEqual(
            self._review("reject", id=page_rows[0]["id"], reason="declined"), 0
        )
        self.assertEqual(self._review("apply-approved"), 0)

        # 没有任何页面被批准 → 不写库、也不推进记账。
        self.assertFalse((self.root / declined["rel_path"]).exists())
        subset_paths = sorted(
            (self.root / ".openclaw/runs").glob(f"{run_id}.subset-*.json")
        )
        for subset_path in subset_paths:
            subset = json.loads(subset_path.read_text(encoding="utf-8"))
            self.assertFalse(subset.get("processed_index_advanced"))
