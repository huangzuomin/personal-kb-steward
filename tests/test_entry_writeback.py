"""Focused regressions for the two user-entry defects (B05/B06).

Work-memory: inputs must follow the ACTUAL configured scan locations, and a
valid model work-memory item must become a reviewable page in the configured
output dir. Writing-material-pack: a validated model result must reach the
saved page instead of the misleading heuristic template, and a failed/invalid
LLM response must never fall back to that template. All model I/O is mocked
with synthetic fixtures; no provider calls and no private data.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import personal_kb_steward as steward


PROJECT_NOTE = "# Alpha 项目计划\n\nAlpha 项目的目标与行动项：\n- 行动项：完成验收评审（计划，本周内）\n- 决策：采用方案 B\n"
DIARY_NOTE = "# 今日工作日记\n\n上午开项目例会，同步 Alpha 项目进度与待办。\n"


def make_cfg(kb: Path, *, include_dirs=None) -> dict:
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    cfg["knowledge_base"] = str(kb)
    cfg["state_file"] = str(kb / ".state.json")
    if include_dirs is not None:
        cfg["scan"]["include_dirs"] = include_dirs
    cfg["safety"]["plans_dir"] = str(kb / ".openclaw" / "plans")
    cfg["safety"]["runs_dir"] = str(kb / ".openclaw" / "runs")
    cfg["safety"]["processed_index"] = str(kb / ".openclaw" / "processed-index.json")
    cfg["safety"]["manual_review_queue"] = str(kb / ".openclaw" / "manual-review" / "queue.jsonl")
    cfg["safety"]["backup_dir"] = str(kb / ".openclaw" / "backups")
    cfg["safety"]["operation_log"] = str(kb / ".openclaw" / "operation-log.jsonl")
    return cfg


def work_memory_response(doc_paths):
    return json.dumps({"items": [{
        "title": "Alpha 项目工作记忆",
        "type": "work-memory",
        "status": "growing",
        "stage": "active",
        "sources": list(doc_paths),
        "summary": "Alpha 项目推进中：验收评审待完成，已决定采用方案 B。",
        "signals": ["验收评审为计划行动项，尚未发生。", "方案 B 决策已发生。"],
        "risks": ["验收评审可能延期。"],
        "gaps": [],
        "manual_review": ["行动项状态需人工确认。"],
        "related": [],
        "pending_links": [],
        "confidence": "medium",
        "review_required": True,
    }]}, ensure_ascii=False)


def material_pack_response(doc_paths):
    return json.dumps({"items": [{
        "title": "写作材料包：Alpha 验收评审",
        "type": "material-pack",
        "status": "growing",
        "stage": "assembling",
        "sources": list(doc_paths),
        "summary": "围绕 Alpha 验收评审的可用与不可用材料。",
        "topic": "Alpha 验收评审",
        "tension": "验收结果是否达到立项承诺仍缺少独立证据。",
        "facts": [
            "报告：验收报告结论为通过（正式文件）。",
            "访谈自述：负责人口述进度符合预期（未经独立核实）。",
            "AI 分析：模型认为风险下降（AI 生成，仅供参考）。",
            "数字 87% 为未经核实的转述口径。",
        ],
        "cases": [],
        "risks": ["访谈自述不能当正式结论引用。"],
        "gaps": ["缺少验收原始数据的独立来源。"],
        "not_recommended": ["不得把访谈自述写成已证实结论。"],
        "related": [],
        "pending_links": [],
        "confidence": "medium",
        "review_required": True,
    }]}, ensure_ascii=False)


def generic_material_pack_response(doc_paths):
    """The generic skill-runtime item shape: no facts/cases/not_recommended
    keys at all — substantive content lives in signals/angles/why_now/review."""
    return json.dumps({"items": [{
        "title": "写作材料包：Alpha 验收评审",
        "type": "material-pack",
        "status": "growing",
        "stage": "assembling",
        "sources": list(doc_paths),
        "summary": "围绕 Alpha 验收评审的可用与不可用材料。",
        "one_sentence_topic": "Alpha 验收评审的证据是否独立。",
        "tension": "验收结果是否达到立项承诺仍缺少独立证据。",
        "why_now": ["验收报告刚归档，等待独立核对。"],
        "signals": [
            "报告：验收报告结论为通过（正式文件）。",
            "访谈自述：负责人口述进度符合预期（未经独立核实）。",
            "AI 分析：模型认为风险下降（AI 生成，仅供参考）。",
            "数字 87% 为未经核实的转述口径。",
        ],
        "angles": ["核对口径：独立来源 vs 口述结论。"],
        "risks": ["访谈自述不能当正式结论引用。"],
        "gaps": ["缺少验收原始数据的独立来源。"],
        "manual_review": ["未核实数字需人工回原文复核。"],
        "related": [],
        "pending_links": [],
        "confidence": "medium",
        "review_required": True,
    }]}, ensure_ascii=False)


class WorkMemoryEntryTests(unittest.TestCase):
    def seed(self, kb: Path) -> None:
        (kb / "quicknote").mkdir(parents=True)
        (kb / "4-项目").mkdir()
        (kb / "4-项目" / "alpha-plan.md").write_text(PROJECT_NOTE, encoding="utf-8")
        (kb / "quicknote" / "diary.md").write_text(DIARY_NOTE, encoding="utf-8")

    def test_input_selection_follows_configured_scan_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb, include_dirs=["quicknote", "inbox", "raw", "wiki", "4-项目"])
            index = steward.build_index(cfg)
            selected = steward.select_llm_input_notes(
                index, cfg, "沉淀工作记忆 Alpha 项目", "work-memory-weave",
                index.notes, {}, None)
            rels = {n.rel for n in selected}
            self.assertIn("4-项目/alpha-plan.md", rels, "configured project note must be an LLM input")
            self.assertIn("quicknote/diary.md", rels)

    def test_processed_inputs_are_not_selected_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb, include_dirs=["quicknote", "4-项目"])
            index = steward.build_index(cfg)
            processed = {"processed": {"quicknote/diary.md": {"skills": {"work-memory-weave": {
                "sha256": index.by_rel["quicknote/diary.md"].sha256,
                "operation_status": "created"}}}}}
            selected = steward.select_llm_input_notes(
                index, cfg, "沉淀工作记忆", "work-memory-weave", index.notes, processed, None)
            self.assertEqual([n.rel for n in selected], ["4-项目/alpha-plan.md"])

    def test_model_item_becomes_reviewable_page_and_applies(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb, include_dirs=["quicknote", "4-项目"])
            captured = {}

            def model(_cfg, _prompt, payload):
                paths = [d["path"] for d in payload["documents"]]
                captured["paths"] = paths
                return work_memory_response(paths)

            with patch("core.skill_runtime.call_chat_completion", side_effect=model):
                plan = steward.make_execution_plan(
                    cfg, "整理 Alpha 项目工作记忆", use_llm=True, include_all=True)

            self.assertIn("4-项目/alpha-plan.md", captured["paths"], "project plan fixture must reach the model")
            self.assertIn("quicknote/diary.md", captured["paths"], "diary must be sent alongside the project plan")
            self.assertTrue(plan["llm_runtime"]["writeback_used"])
            self.assertEqual(len(plan["planned_pages"]), 1)
            page = plan["planned_pages"][0]
            self.assertTrue(page["rel_path"].startswith("wiki/work-memory/"))
            self.assertTrue(page["review_required"])
            self.assertEqual(set(page["retrieval_source_hashes"]),
                             {"4-项目/alpha-plan.md", "quicknote/diary.md"})
            self.assertIn('"producer": "llm_skill_runtime"', page["content"])
            self.assertIn("验收评审为计划行动项", page["content"], "planned-vs-occurred content preserved")
            self.assertIn("4-项目/alpha-plan.md", page["sources"])
            self.assertIn("planned_pages_require_review", {x["type"] for x in plan["manual_review"]})

            # Save -> approve -> apply-approved writes the real page.
            plan["run_id"] = "wm-fix-1"
            path = steward.write_execution_plan(cfg, plan)
            steward.write_manual_review_queue(cfg, plan)
            for item in steward.load_queue(steward.review_queue_path(cfg)):
                if item.get("run_id") == "wm-fix-1":
                    self.assertEqual(steward.command_review(cfg, SimpleNamespace(
                        review_command="approve", id=item["id"], reason="synthetic fixture")), 0)
            self.assertEqual(steward.command_review(cfg, SimpleNamespace(
                review_command="apply-approved", run_id="wm-fix-1")), 0)
            saved = (kb / page["rel_path"]).read_text(encoding="utf-8")
            self.assertIn("Alpha 项目工作记忆", saved)
            self.assertIn("wiki/work-memory", page["rel_path"])

            # Applied inputs leave the candidate pool (processed semantics kept).
            index = steward.build_index(cfg)
            processed = steward.load_processed_index(cfg)
            self.assertEqual(steward.select_llm_input_notes(
                index, cfg, "整理 Alpha 项目工作记忆", "work-memory-weave",
                index.notes, processed, None), [])

    def test_generated_output_dirs_are_never_reingested(self):
        """Configured knowledge OUTPUT dirs (even relocated, e.g. _kb-steward)
        must not feed back as work-memory inputs, while configured original
        project/diary directories stay eligible."""
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir(parents=True)
            (kb / "4-项目").mkdir()
            (kb / "4-项目" / "alpha-plan.md").write_text(PROJECT_NOTE, encoding="utf-8")
            (kb / "quicknote" / "diary.md").write_text(DIARY_NOTE, encoding="utf-8")
            generated_dir = "_kb-steward/work-memory"
            (kb / generated_dir).mkdir(parents=True)
            (kb / generated_dir / "generated.md").write_text(
                "# Alpha 项目工作记忆\n\n项目例会与待办，内容与原始记录高度相似。\n",
                encoding="utf-8")
            cfg = make_cfg(kb, include_dirs=["quicknote", "4-项目", generated_dir])
            cfg["write"]["work_memory_dir"] = generated_dir

            index = steward.build_index(cfg)
            selected = steward.select_llm_input_notes(
                index, cfg, "整理 Alpha 项目工作记忆", "work-memory-weave",
                index.notes, {}, None)

            rels = [n.rel for n in selected]
            self.assertEqual(rels, ["4-项目/alpha-plan.md", "quicknote/diary.md"])
            self.assertNotIn(f"{generated_dir}/generated.md", rels)

    def test_llm_failure_never_fabricates_a_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb, include_dirs=["quicknote", "4-项目"])
            failure = {"enabled": True, "mock": False, "skill": "work-memory-weave",
                       "skill_path": "skills/work-memory-weave/SKILL.md", "ok": False,
                       "issues": ["provider timeout"], "items": [], "previews": []}
            with patch.object(steward, "run_skill_runtime", return_value=failure):
                plan = steward.make_execution_plan(
                    cfg, "整理 Alpha 项目工作记忆", use_llm=True, include_all=True)
            self.assertEqual(plan["planned_pages"], [])
            self.assertFalse(plan["llm_runtime"]["writeback_used"])
            self.assertIn("llm_runtime_issues", {x["type"] for x in plan["manual_review"]})


class WritingMaterialPackEntryTests(unittest.TestCase):
    def seed(self, kb: Path) -> None:
        (kb / "raw").mkdir(parents=True)
        (kb / "raw" / "acceptance-report.md").write_text(
            "# 验收评审记录\n\nAlpha 项目验收评审的会议记录与结论。\n", encoding="utf-8")

    def test_model_result_replaces_heuristic_template_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)

            def model(_cfg, _prompt, payload):
                paths = [d["path"] for d in payload["documents"]]
                return material_pack_response(paths)

            with patch("core.skill_runtime.call_chat_completion", side_effect=model):
                plan = steward.make_execution_plan(
                    cfg, "围绕 Alpha 验收评审 生成材料包", use_llm=True, include_all=True)

            self.assertTrue(plan["llm_runtime"]["writeback_used"])
            self.assertEqual(len(plan["planned_pages"]), 1)
            page = plan["planned_pages"][0]
            self.assertTrue(page["rel_path"].startswith("wiki/material-packs/"))
            self.assertTrue(page["review_required"])
            content = page["content"]
            # Model distinctions reach the page verbatim.
            self.assertIn("报告：验收报告结论为通过", content)
            self.assertIn("访谈自述", content)
            self.assertIn("AI 分析", content)
            self.assertIn("未经核实的转述口径", content)
            self.assertIn("缺少验收原始数据的独立来源", content)
            # The old misleading heuristic template must not leak.
            self.assertNotIn("[待人工填写]", content)
            self.assertNotIn("暂无明显复核项", content)
            self.assertNotIn("机制解释型", content)
            self.assertEqual(page["sources"], ["raw/acceptance-report.md"])
            self.assertEqual(set(page["retrieval_source_hashes"]), {"raw/acceptance-report.md"})
            self.assertIn('"producer": "llm_skill_runtime"', content)

            plan["run_id"] = "mp-fix-1"
            path = steward.write_execution_plan(cfg, plan)
            steward.write_manual_review_queue(cfg, plan)
            for item in steward.load_queue(steward.review_queue_path(cfg)):
                if item.get("run_id") == "mp-fix-1":
                    self.assertEqual(steward.command_review(cfg, SimpleNamespace(
                        review_command="approve", id=item["id"], reason="synthetic fixture")), 0)
            self.assertEqual(steward.command_review(cfg, SimpleNamespace(
                review_command="apply-approved", run_id="mp-fix-1")), 0)
            self.assertIn("访谈自述", (kb / page["rel_path"]).read_text(encoding="utf-8"))

    def test_generic_contract_response_without_facts_becomes_a_page(self):
        """Real recorded responses use the EXISTING generic runtime fields and
        have no facts/cases/not_recommended keys; replay must still produce a
        page that renders the substantive signals/angles/why_now/review text
        without fabricating fact/case sections."""
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)

            def model(_cfg, _prompt, payload):
                return generic_material_pack_response([d["path"] for d in payload["documents"]])

            with patch("core.skill_runtime.call_chat_completion", side_effect=model):
                plan = steward.make_execution_plan(
                    cfg, "围绕 Alpha 验收评审 生成材料包", use_llm=True, include_all=True)

            self.assertTrue(plan["llm_runtime"]["writeback_used"])
            page = plan["planned_pages"][0]
            self.assertTrue(page["rel_path"].startswith("wiki/material-packs/"))
            content = page["content"]
            self.assertIn("报告：验收报告结论为通过", content)
            self.assertIn("访谈自述", content)
            self.assertIn("未经核实的转述口径", content)
            self.assertIn("核对口径：独立来源 vs 口述结论。", content)
            self.assertIn("验收报告刚归档", content)
            self.assertIn("未核实数字需人工回原文复核。", content)
            self.assertIn("缺少验收原始数据的独立来源", content)
            self.assertNotIn("[待人工填写]", content)
            self.assertNotIn("暂无明显复核项", content)

    def test_no_llm_behavior_keeps_honest_heuristic_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)
            plan = steward.make_execution_plan(cfg, "围绕 Alpha 验收评审 生成材料包", include_all=True)
            self.assertEqual(len(plan["planned_pages"]), 1)
            page = plan["planned_pages"][0]
            self.assertEqual(page["skill"], "writing-material-pack")
            self.assertTrue(page["review_required"], "no-LLM page stays review-gated, not model-labeled")

    def test_invalid_model_response_blocked_without_template_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)
            invalid = json.dumps({"items": [{
                "title": "坏响应", "type": "material-pack", "status": "growing",
                "stage": "assembling", "sources": ["raw/acceptance-report.md"],
                "summary": "facts 字段不是字符串列表。", "tension": "x",
                "facts": "不是列表", "cases": [], "risks": [], "gaps": [],
                "not_recommended": [], "confidence": "medium", "review_required": True,
            }]}, ensure_ascii=False)
            with patch("core.skill_runtime.call_chat_completion", return_value=invalid):
                plan = steward.make_execution_plan(
                    cfg, "围绕 Alpha 验收评审 生成材料包", use_llm=True, include_all=True)
            self.assertEqual([p for p in plan["planned_pages"]
                              if p.get("skill") == "writing-material-pack"], [])
            self.assertFalse(plan["llm_runtime"]["writeback_used"])
            blocked = {x["type"] for x in plan["manual_review"]}
            self.assertIn("llm_writeback_blocked", blocked)
            for page in plan["planned_pages"]:
                self.assertNotIn("[待人工填写]", page.get("content", ""))

    def test_unknown_source_in_model_response_blocked_in_integration(self):
        """Integration-level: an ok model response citing a source that was NOT
        provided must produce zero pages and a writeback blocker."""
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)
            phantom = {"enabled": True, "mock": False, "skill": "writing-material-pack",
                       "skill_path": "skills/writing-material-pack/SKILL.md", "ok": True,
                       "items": [{
                           "title": "幻影来源材料包", "type": "material-pack",
                           "status": "growing", "stage": "assembling",
                           "sources": ["raw/not-provided.md"],
                           "summary": "引用了未提供的来源。", "tension": "t",
                           "facts": ["f"], "cases": [], "risks": [], "gaps": [],
                           "not_recommended": [], "confidence": "medium",
                           "review_required": True}],
                       "previews": []}
            with patch.object(steward, "run_skill_runtime", return_value=phantom):
                plan = steward.make_execution_plan(
                    cfg, "围绕 Alpha 验收评审 生成材料包", use_llm=True, include_all=True)
            self.assertEqual([p for p in plan["planned_pages"]
                              if p.get("skill") == "writing-material-pack"], [])
            self.assertFalse(plan["llm_runtime"]["writeback_used"])
            self.assertIn("llm_writeback_blocked", {x["type"] for x in plan["manual_review"]})

    def test_pending_links_render_plain_and_body_links_stay_blocked(self):
        """pending_links is explicitly for not-yet-existing targets: wiki-link
        markup inside it is stripped to plain text so the page passes
        validate_markdown; an actual invalid link elsewhere (related) still
        blocks the page."""
        from core.llm_plan import entry_pages_from_llm, integrate_entry_llm_writeback
        cfg = {"write": {"materials_dir": "wiki/material-packs"}}
        item = {
            "title": "待创建链接材料包", "type": "material-pack", "status": "growing",
            "stage": "assembling", "sources": ["raw/a.md"], "summary": "s",
            "tension": "t", "facts": ["f"], "cases": [], "risks": [], "gaps": [],
            "not_recommended": [], "confidence": "medium", "review_required": True,
            "pending_links": ["[[Missing report]]", "[[待写|Alias 页面]]"],
        }
        result = {"ok": True, "skill": "writing-material-pack", "items": [item]}
        pages = entry_pages_from_llm(cfg, result, "run-pending")
        self.assertEqual(len(pages), 1)
        self.assertIn("待创建链接", pages[0]["content"])
        pending_section = pages[0]["content"].split("## 待创建链接", 1)[1]
        self.assertIn("Missing report", pending_section)
        self.assertIn("待写", pending_section)
        self.assertNotIn("[[", pending_section)
        # Integration: page survives real markdown/link validation.
        class FakeNote:
            rel = "raw/a.md"
            sha256 = "0" * 64
        merged, issue = integrate_entry_llm_writeback(
            cfg, [], result, [FakeNote()], "run-pending",
            lambda content, sources: [], skill="writing-material-pack")
        self.assertIsNone(issue)
        self.assertEqual(len(merged), 1)
        # An actual invalid link in a validated field (related) stays blocked:
        # validate_page flags the dangling wikilink and the writeback fails closed.
        bad = {"ok": True, "skill": "writing-material-pack", "items": [dict(item, related=["[[Missing report]]"])]}
        _, bad_issue = integrate_entry_llm_writeback(
            cfg, [], bad, [FakeNote()], "run-bad",
            lambda content, sources: ["双链无法解析：Missing report"],
            skill="writing-material-pack")
        self.assertIsNotNone(bad_issue)

    def test_provider_failure_leaves_no_template_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            self.seed(kb)
            cfg = make_cfg(kb)
            failure = {"enabled": True, "mock": False, "skill": "writing-material-pack",
                       "skill_path": "skills/writing-material-pack/SKILL.md", "ok": False,
                       "issues": ["missing api key"], "items": [], "previews": []}
            with patch.object(steward, "run_skill_runtime", return_value=failure):
                plan = steward.make_execution_plan(
                    cfg, "围绕 Alpha 验收评审 生成材料包", use_llm=True, include_all=True)
            self.assertEqual(plan["planned_pages"], [])
            self.assertIn("llm_runtime_issues", {x["type"] for x in plan["manual_review"]})

    def test_converter_rejects_wrong_type_and_unknown_sources(self):
        from core.llm_plan import LLMPlanError, entry_pages_from_llm
        cfg = {"write": {"materials_dir": "wiki/material-packs"}}
        bad_type = {"ok": True, "skill": "writing-material-pack", "items": [{
            "title": "t", "type": "research-plan", "status": "growing", "stage": "assembling",
            "sources": ["raw/a.md"], "summary": "s", "tension": "t", "facts": [], "cases": [],
            "risks": [], "gaps": [], "not_recommended": [], "confidence": "low",
            "review_required": True}]}
        with self.assertRaises(LLMPlanError):
            entry_pages_from_llm(cfg, bad_type, "run-x")
        ok_item = {"ok": True, "skill": "writing-material-pack", "items": [{
            "title": "材料包", "type": "material-pack", "status": "compiled", "stage": "draft_ready",
            "sources": ["raw/a.md"], "summary": "s", "tension": "t", "facts": ["f"],
            "cases": [], "risks": [], "gaps": [], "not_recommended": [],
            "confidence": "high", "review_required": False, "path": "wiki/material-packs/phantom.md"}]}
        page = entry_pages_from_llm(cfg, ok_item, "run-x")[0]
        self.assertTrue(page["rel_path"].startswith("wiki/material-packs/"))
        self.assertNotIn("phantom", page["rel_path"])
        # Unverifiable compiled/draft_ready claims are downgraded to
        # manual_review/needs_review behind explicit human approval.
        self.assertIn("status: manual_review", page["content"])
        self.assertIn("stage: needs_review", page["content"])
        self.assertIn("review_required: true", page["content"])


if __name__ == "__main__":
    unittest.main()
