"""Config validation for the llm.backend selector (Patch L)."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.config import llm_backend  # noqa: E402


class LlmBackendTests(unittest.TestCase):
    def test_absent_llm_section_defaults_to_api(self):
        self.assertEqual(llm_backend(None), "api")
        self.assertEqual(llm_backend({}), "api")
        self.assertEqual(llm_backend({"scan": {}}), "api")

    def test_absent_backend_key_defaults_to_api(self):
        cfg = {"llm": {"provider": "openai-compatible", "base_url": "https://x/v1"}}
        self.assertEqual(llm_backend(cfg), "api")

    def test_non_dict_llm_section_rejected(self):
        with self.assertRaises(ValueError):
            llm_backend({"llm": "claude"})

    def test_unknown_backend_rejected_not_coerced(self):
        for bad in ("claude", "AGENT", "agent-cli", "", True, 3):
            with self.assertRaises(ValueError, msg=f"backend={bad!r}"):
                llm_backend({"llm": {"backend": bad}})

    def test_agent_backend_requires_agent_object(self):
        with self.assertRaises(ValueError):
            llm_backend({"llm": {"backend": "agent"}})
        with self.assertRaises(ValueError):
            llm_backend({"llm": {"backend": "agent", "agent": "claude"}})

    def test_agent_backend_requires_nonempty_command(self):
        with self.assertRaises(ValueError):
            llm_backend({"llm": {"backend": "agent", "agent": {"command": "  "}}})

    def test_agent_args_must_be_string_list(self):
        with self.assertRaises(ValueError):
            llm_backend({"llm": {"backend": "agent",
                                 "agent": {"command": "claude", "args": ["-p", 7]}}})

    def test_agent_env_must_be_str_str_map(self):
        with self.assertRaises(ValueError):
            llm_backend({"llm": {"backend": "agent",
                                 "agent": {"command": "claude", "env": {"K": 1}}}})

    def test_valid_agent_backend_accepted(self):
        cfg = {"llm": {"backend": "agent",
                       "agent": {"command": "claude", "args": ["-p", "{stdin}"],
                                 "env": {"ANTHROPIC_MODEL": "x"}}}}
        self.assertEqual(llm_backend(cfg), "agent")

    def test_live_config_parses(self):
        import json
        live = ROOT / "config.json"
        if not live.exists():
            # CI and fresh clones run without a local config; the value of
            # this check only exists when one is present.
            self.skipTest("no live config.json (expected on CI/fresh clones)")
        data = json.loads(live.read_text(encoding="utf-8-sig"))
        self.assertIn(llm_backend(data), {"api", "agent"})

    def test_example_config_defaults_to_api_and_documents_agent_template(self):
        import json
        data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(llm_backend(data), "api")
        agent = data["llm"]["agent"]
        self.assertIsInstance(agent["command"], str)
        self.assertIn("{stdin}", agent["args"])


if __name__ == "__main__":
    unittest.main()
