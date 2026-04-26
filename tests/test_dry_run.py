import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DryRunTests(unittest.TestCase):
    def test_plan_command_is_dry_run(self):
        before = set((ROOT / "examples" / "mini-vault").rglob("*"))
        result = subprocess.run(
            ["python", "scripts/personal_kb_steward.py", "plan", "整理知识库"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run", result.stdout)
        after = set((ROOT / "examples" / "mini-vault").rglob("*"))
        self.assertEqual(before, after)

    def test_mock_llm_plan_is_dry_run(self):
        before = set((ROOT / "examples" / "mini-vault").rglob("*"))
        result = subprocess.run(
            ["python", "scripts/personal_kb_steward.py", "plan", "--mock-llm", "整理知识库"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LLM runtime", result.stdout)
        after = set((ROOT / "examples" / "mini-vault").rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
