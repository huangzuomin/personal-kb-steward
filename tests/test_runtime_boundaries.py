import unittest
from pathlib import Path

from core import config, markdown, router, state, vault


ROOT = Path(__file__).resolve().parents[1]


class RuntimeBoundaryTests(unittest.TestCase):
    def test_core_modules_expose_expected_boundaries(self):
        self.assertTrue(callable(config.kb_root))
        self.assertTrue(callable(vault.build_index))
        self.assertTrue(callable(state.changed_notes))
        self.assertTrue(callable(router.route))
        self.assertTrue(callable(markdown.frontmatter))

    def test_runner_is_smaller_after_phase_14(self):
        line_count = len((ROOT / "scripts" / "personal_kb_steward.py").read_text(encoding="utf-8").splitlines())
        # v0.3: review 子命令扩展后上限调整
        self.assertLess(line_count, 1700)

    def test_review_queue_module_exists(self):
        from core import review_queue
        self.assertTrue(callable(review_queue.load_queue))
        self.assertTrue(callable(review_queue.approve_item))
        self.assertTrue(callable(review_queue.reject_item))
        self.assertTrue(callable(review_queue.batch_approve))

if __name__ == "__main__":
    unittest.main()
