import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import personal_kb_steward as steward  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_config_json_loads(self):
        data = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(data["safety"]["default_mode"], "dry-run")
        self.assertTrue(data["safety"]["require_apply_flag_for_writes"])

    def test_frontmatter_requires_stage_and_sources(self):
        data = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
        required = set(data["knowledge_model"]["required_frontmatter"])
        self.assertIn("stage", required)
        self.assertIn("sources", required)

    def test_agent_home_path_expansion(self):
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
        self.assertNotIn("C:\\Users\\zooma", cfg["knowledge_base"])
        resolved = steward.resolve_path("${AGENT_HOME}\\kb-template")
        self.assertEqual(resolved, (ROOT / "kb-template").resolve())


if __name__ == "__main__":
    unittest.main()
