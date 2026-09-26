"""回归：`initialize.seed_stage` 开关。

需求背景（2026-09-22）：用户要求「先只跑 raw 源卡，不产种子」。
但 `mindseed-grow`（seed_cluster 阶段）**在构建 plan 时就会调用模型**，
所以「先生成再在 review 阶段 reject」并不能省下模型调用；
而收窄 `scan.include_dirs` 会让索引缺 quicknote、进而让 apply 时重写的
`index.md` 丢掉这些条目。**唯一干净的做法是一个默认不改行为的配置开关。**

本文件守三件事：
1. 不配置时行为**逐字不变**（种子照常产出）——与 B09 同一条纪律；
2. 显式关闭时**零种子页面、零模型调用**；
3. 关闭种子**不影响源卡**（raw 仍被沉淀）。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import personal_kb_steward as steward  # noqa: E402
from tests.test_card_pipeline_integration import (  # noqa: E402
    RAW_REL, source_answer, write_raw)
from tests.test_seed_receipt_acceptance import (  # noqa: E402
    DerivedZeroProvider, SeedProvider, build_seed_plan, make_seed_vault,
    seed_pages, seed_stage)


class RecordingSourceProvider:
    """答 raw 源卡；记录每次调用，用于证明关闭种子后模型一次都没被叫。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, cfg, system_prompt, payload):
        del cfg, system_prompt
        self.calls.append(payload)
        return source_answer()


def _with_flag(cfg: dict, value: bool | None) -> dict:
    out = copy.deepcopy(cfg)
    if value is not None:
        out["initialize"] = {"seed_stage": value}
    return out


class SeedStageDefaultTests(unittest.TestCase):
    def test_unset_flag_keeps_seed_stage_working(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="seed-switch-") as tmp:
            root, cfg = make_seed_vault(Path(tmp), 10)
            provider = SeedProvider()
            plan = build_seed_plan(_with_flag(cfg, None), "switch-default", provider)
            self.assertTrue(seed_pages(plan), "未配置时种子阶段必须照常产出")
            self.assertNotEqual(seed_stage(plan)["reason"], "seed_stage_disabled")
            self.assertTrue(provider.calls)


class SeedStageDisabledTests(unittest.TestCase):
    def test_disabled_plans_no_seed_pages_and_spends_no_model_call(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="seed-switch-") as tmp:
            root, cfg = make_seed_vault(Path(tmp), 10)
            provider = SeedProvider()
            plan = build_seed_plan(_with_flag(cfg, False), "switch-off", provider)
            self.assertEqual(seed_pages(plan), [])
            stage = seed_stage(plan)
            self.assertIs(stage.get("seed_stage_enabled"), False)
            self.assertEqual(stage["reason"], "seed_stage_disabled")
            self.assertIn("seed_stage=false", stage["reason_detail"])
            # 关键：不是「先生成再 reject」——模型一次都没被叫
            self.assertEqual(provider.calls, [])

    def test_disabled_seed_stage_still_compiles_raw_source_cards(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="seed-switch-") as tmp:
            root, cfg = make_seed_vault(Path(tmp), 10)
            write_raw(root)
            provider = RecordingSourceProvider()
            with patch("core.llm.call_chat_completion", provider):
                plan = steward.build_initialization_plan(
                    _with_flag(cfg, False),
                    plan_run_id="switch-off-raw",
                    stamp=steward.stamp(),
                    executor_plan_fn=steward.mvp_executor_plan,
                    page_requires_manual_review=steward.page_requires_manual_review,
                    duplicate_page_targets=steward.duplicate_page_targets,
                    page_has_blocked_placeholder=(
                        lambda page: steward.page_has_blocked_placeholder(page, cfg)),
                    planned_raw_coverage=steward.planned_raw_coverage,
                    batch_size=6, use_llm=True, include_all=False,
                    discover_providers={"concept": DerivedZeroProvider(),
                                        "case": DerivedZeroProvider()},
                )
            source = next(a for a in plan["actions"] if a.get("stage") == "source_compile")
            outcomes = {item.get("rel"): item for item in source.get("input_outcomes", [])}
            self.assertEqual(outcomes[RAW_REL]["outcome"], "ok")
            self.assertTrue(any(RAW_REL in (p.get("sources") or [])
                                for p in plan["planned_pages"]))
            self.assertEqual(seed_pages(plan), [])
            self.assertEqual(seed_stage(plan)["reason"], "seed_stage_disabled")


if __name__ == "__main__":
    unittest.main()
