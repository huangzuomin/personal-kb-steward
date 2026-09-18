import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import personal_kb_steward as steward  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_example_config_loads(self):
        data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(data["safety"]["default_mode"], "dry-run")
        self.assertTrue(data["safety"]["require_apply_flag_for_writes"])

    def test_frontmatter_requires_stage_and_sources(self):
        data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        required = set(data["knowledge_model"]["required_frontmatter"])
        self.assertIn("stage", required)
        self.assertIn("sources", required)

    def test_agent_home_path_expansion(self):
        cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        self.assertNotIn("C:\\Users", cfg["knowledge_base"])
        resolved = steward.resolve_path("${AGENT_HOME}\\kb-template")
        self.assertEqual(resolved, (ROOT / "kb-template").resolve())

    def test_active_is_a_stage_not_a_status(self):
        data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        statuses = set(data["knowledge_model"]["statuses"])
        stages = set(data["knowledge_model"]["workflow_stages"])
        self.assertNotIn("active", statuses)
        self.assertIn("active", stages)


if __name__ == "__main__":
    unittest.main()
