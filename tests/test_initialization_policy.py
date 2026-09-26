"""B12 contracts for the fixed initialization pipeline policy."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.initialization_policy import (
    InitializationPipelineError,
    load_initialization_pipeline,
    validate_initialization_config,
    validate_initialization_pipeline,
)
from core.initializer import make_initialization_plan


ROOT = Path(__file__).resolve().parents[1]


def _cfg(root: Path) -> dict:
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    cfg["knowledge_base"] = str(root)
    cfg["state_file"] = str(root / ".state.json")
    for key, value in {
        "plans_dir": root / ".openclaw" / "plans",
        "runs_dir": root / ".openclaw" / "runs",
        "processed_index": root / ".openclaw" / "processed-index.json",
        "manual_review_queue": root / ".openclaw" / "manual-review" / "queue.jsonl",
        "backup_dir": root / ".openclaw" / "backups",
        "operation_log": root / ".openclaw" / "operation-log.jsonl",
    }.items():
        cfg["safety"][key] = str(value)
    return cfg


def _plan(cfg: dict, *, run_id: str = "policy-test", executor=None,
          batch_size: int = 6) -> dict:
    def no_pages(*args, **kwargs):
        del args, kwargs
        return {"inputs": [], "planned_pages": [], "issues": [], "provider_calls": 0}

    return make_initialization_plan(
        cfg,
        plan_run_id=run_id,
        stamp="2026-09-22T00:00:00Z",
        executor_plan_fn=executor or no_pages,
        page_requires_manual_review=lambda page: False,
        duplicate_page_targets=lambda pages: {},
        page_has_blocked_placeholder=lambda page: False,
        planned_raw_coverage=lambda raw, pages: {
            "total": len(raw), "planned": len(raw), "missing": [],
        },
        batch_size=batch_size,
        use_llm=False,
        include_all=True,
    )


class InitializationPipelinePolicyTests(unittest.TestCase):
    def test_default_pipeline_is_loaded_from_workflow_declaration(self):
        workflows = json.loads(
            (ROOT / "workflows.json").read_text(encoding="utf-8-sig")
        )
        expected = tuple(workflows["entries"]["init_kb"]["pipeline"])
        self.assertEqual(load_initialization_pipeline(), expected)

        with tempfile.TemporaryDirectory(prefix="init-policy-") as tmp:
            root = Path(tmp)
            for name in ("quicknote", "inbox", "raw", "wiki"):
                (root / name).mkdir()
            plan = _plan(_cfg(root))
            self.assertEqual(tuple(plan["pipeline_declared"]), expected)

    def test_fixed_policy_rejects_missing_required_unknown_duplicate_and_bad_order(self):
        valid = ["intake", "source_compile", "seed_cluster", "promote_candidates", "quality_gate"]
        cases = [
            ([], "required"),
            (["intake", "quality_gate"], "required"),
            (["intake", "source_compile", "quality_gate", "mystery"], "unknown"),
            (["intake", "source_compile", "seed_cluster", "seed_cluster", "quality_gate"], "duplicate"),
            (["intake", "seed_cluster", "source_compile", "quality_gate"], "order"),
        ]
        for pipeline, marker in cases:
            with self.subTest(pipeline=pipeline):
                with self.assertRaisesRegex(InitializationPipelineError, marker):
                    validate_initialization_pipeline(pipeline)
        self.assertEqual(tuple(validate_initialization_pipeline(valid)), tuple(valid))
        self.assertEqual(
            tuple(validate_initialization_pipeline(["intake", "source_compile", "quality_gate"])),
            ("intake", "source_compile", "quality_gate"),
        )

    def test_seed_override_is_strict_and_defaults_to_enabled(self):
        self.assertTrue(validate_initialization_config({}))
        self.assertTrue(validate_initialization_config({"initialize": {}}))
        self.assertFalse(validate_initialization_config({"initialize": {"seed_stage": False}}))
        for value in (None, 0, 1, "false", []):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InitializationPipelineError, "seed_stage"):
                    validate_initialization_config({"initialize": {"seed_stage": value}})

    def test_invalid_workflow_fails_before_executor_provider(self):
        calls = []

        def should_not_run(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("executor/provider was reached before pipeline validation")

        with tempfile.TemporaryDirectory(prefix="init-policy-") as tmp:
            root = Path(tmp)
            for name in ("quicknote", "inbox", "raw", "wiki"):
                (root / name).mkdir()
            with patch(
                "core.initialization_policy.workflow_for_entry",
                return_value={"pipeline": ["intake", "quality_gate"]},
            ):
                with self.assertRaises(InitializationPipelineError):
                    _plan(_cfg(root), executor=should_not_run)
        self.assertEqual(calls, [])

    def test_disabled_seed_is_explicit_even_with_historical_pending_or_rejected(self):
        with tempfile.TemporaryDirectory(prefix="init-policy-") as tmp:
            root = Path(tmp)
            for name in ("quicknote", "inbox", "raw", "wiki"):
                (root / name).mkdir()
            (root / "quicknote" / "old.md").write_text(
                "# 历史碎片\n\n等待人工审核的旧输入。", encoding="utf-8"
            )
            cfg = _cfg(root)
            cfg["initialize"] = {"seed_stage": False}
            selection_calls = []

            def historical_selection(index, cfg, skill, **kwargs):
                selection_calls.append(skill)
                if skill == "mindseed-grow":
                    note = index.notes[0]
                    return {
                        "generate": [], "pending": [{"note": note, "decision": "pending_review"}],
                        "rejected": [{"note": note, "decision": "review_rejected"}],
                        "unchanged": [], "retryable": [],
                    }
                return {"generate": [], "pending": [], "rejected": [], "unchanged": [], "retryable": []}

            with patch("core.initializer.select_generation_inputs", historical_selection):
                plan = _plan(cfg)

            seed_actions = [a for a in plan["actions"] if a.get("stage") == "seed_cluster"]
            self.assertEqual(len(seed_actions), 1)
            self.assertEqual(seed_actions[0]["reason"], "seed_stage_disabled")
            self.assertEqual(seed_actions[0]["provider_calls"], 0)
            self.assertEqual(
                seed_actions[0].get("seed_stage_disabled"), True,
            )
            self.assertFalse(any(page.get("skill") == "mindseed-grow" for page in plan["planned_pages"]))

    def test_optional_stages_omitted_are_not_executed(self):
        with tempfile.TemporaryDirectory(prefix="init-policy-") as tmp:
            root = Path(tmp)
            for name in ("quicknote", "inbox", "raw", "wiki"):
                (root / name).mkdir()
            (root / "quicknote" / "note.md").write_text(
                "# 碎片\n\n仍应保留在索引中，但本轮不进入 seed。", encoding="utf-8"
            )
            cfg = _cfg(root)
            provider_calls = []

            def should_not_run(*args, **kwargs):
                provider_calls.append((args, kwargs))
                raise AssertionError("optional stage executor was called")

            with patch(
                "core.initialization_policy.workflow_for_entry",
                return_value={"pipeline": ["intake", "source_compile", "quality_gate"]},
            ):
                plan = _plan(cfg, executor=should_not_run)

            self.assertEqual(plan["pipeline_declared"], ["intake", "source_compile", "quality_gate"])
            self.assertNotIn("seed_cluster", plan["pipeline_executed_now"])
            self.assertNotIn("promote_candidates", plan["pipeline_executed_now"])
            self.assertEqual(
                next(a for a in plan["actions"] if a.get("stage") == "promote_candidates")["reason"],
                "promote_stage_disabled",
            )
            self.assertEqual(provider_calls, [])
            self.assertFalse((root / "wiki" / "seeds").exists())

    def test_new_raw_precedes_retryable_receipt_in_small_batch(self):
        with tempfile.TemporaryDirectory(prefix="init-policy-") as tmp:
            root = Path(tmp)
            for name in ("quicknote", "inbox", "raw", "wiki"):
                (root / name).mkdir()
            failed = root / "raw" / "a-failed.md"
            fresh = root / "raw" / "b-new.md"
            failed.write_text("# 历史失败\n\n需要重试的来源。", encoding="utf-8")
            fresh.write_text("# 新来源\n\n首次进入编译批次的来源。", encoding="utf-8")
            cfg = _cfg(root)
            seen: list[list[str]] = []

            def executor(index, cfg, task, skill, notes, processed, run_id, **kwargs):
                del index, cfg, task, processed, run_id, kwargs
                if skill == "topic-research-compile":
                    seen.append([note.rel for note in notes])
                return {"inputs": [note.rel for note in notes], "planned_pages": [],
                        "issues": [], "provider_calls": 0}

            def receipt_lookup(cfg, stage, fingerprint=None, *, source_rel=None,
                               source_sha256=None, source_bytes=None, use_llm=True):
                del cfg, fingerprint, source_sha256, use_llm
                if stage in {"source_compile", "topic-research-compile"} and source_rel == "raw/a-failed.md":
                    return {"decision": "retryable", "reason": "历史失败 receipt"}
                return None

            with patch("core.pipeline_history.lookup_generation_receipt", receipt_lookup):
                plan = _plan(cfg, run_id="retry-order", executor=executor, batch_size=1)

            self.assertEqual(seen, [["raw/b-new.md"]])
            self.assertEqual(plan["batch_queue"]["raw"][0]["items"], ["raw/b-new.md"])
            self.assertIn("raw/a-failed.md", plan["batch_queue"]["raw"][1]["items"])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
