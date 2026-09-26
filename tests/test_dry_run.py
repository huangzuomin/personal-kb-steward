"""CLI tests own their config and vault in an isolated source copy."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        for name in ("core", "scripts", "skills"):
            shutil.copytree(ROOT / name, self.home / name, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("router.json", "workflows.json"):
            shutil.copyfile(ROOT / name, self.home / name)
        self.vault = self.home / "kb-template"
        (self.vault / "quicknote").mkdir(parents=True)
        (self.vault / "quicknote/想法.md").write_text("# A small idea\nEvidence before synthesis.\n", encoding="utf-8")
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        cfg["llm"]["api_key_env"] = "STEWARD_TEST_UNUSED_KEY"
        (self.home / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def run_plan(self, *args):
        before = {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        env = dict(os.environ)
        env.pop("STEWARD_TEST_UNUSED_KEY", None)
        # The vault here is a 7-file template: a healthy run takes about a
        # second. The allowance is generous because this test shells out, and
        # under a full-suite run the machine is busy enough that 30s is not a
        # reliable ceiling — the failure it produced was load, not a hang.
        result = subprocess.run(
            [sys.executable, "scripts/personal_kb_steward.py", "plan", *args, "整理知识库"],
            cwd=self.home, capture_output=True, text=True, encoding="utf-8", env=env, timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run", result.stdout)
        after = {p.relative_to(self.vault): p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(list((self.home / ".openclaw/plans").glob("*.json")))
        return result

    def test_plan_command_is_dry_run(self):
        self.run_plan()

    def test_mock_llm_plan_is_dry_run(self):
        output = self.run_plan("--mock-llm").stdout
        # The current mock plan follows the atomic seed-card contract; the
        # CLI summary does not promise an "LLM runtime" label.
        self.assertIn("skill: mindseed-grow", output)
        self.assertIn("type: seed-card", output)
        self.assertIn("schema_version: m0-1", output)
        self.assertNotIn("type: topic-card", output)


if __name__ == "__main__":
    unittest.main()
