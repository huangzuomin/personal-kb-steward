"""Per-command --backend override (core.config.override_llm_backend + CLI wiring)."""
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.config import llm_backend, override_llm_backend  # noqa: E402


def _load_cli():
    path = ROOT / "scripts" / "personal_kb_steward.py"
    spec = importlib.util.spec_from_file_location("pks_cli", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pks_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


class OverrideHelperTests(unittest.TestCase):
    def test_sets_backend_on_copy(self):
        cfg = {"llm": {"backend": "api", "model": "m"}}
        new = override_llm_backend(cfg, "agent")
        self.assertEqual(new["llm"]["backend"], "agent")
        self.assertEqual(new["llm"]["model"], "m")

    def test_original_never_mutated(self):
        cfg = {"llm": {"backend": "api"}}
        override_llm_backend(cfg, "agent")
        self.assertEqual(cfg["llm"]["backend"], "api")

    def test_missing_llm_section(self):
        new = override_llm_backend({}, "agent")
        self.assertEqual(new["llm"]["backend"], "agent")

    def test_non_dict_llm_section_replaced(self):
        new = override_llm_backend({"llm": "junk"}, "api")
        self.assertEqual(llm_backend(new), "api")

    def test_invalid_value_rejected_not_coerced(self):
        for bad in ("claude", "AGENT", "", True, 3, None):
            with self.assertRaises(ValueError, msg=f"backend={bad!r}"):
                override_llm_backend({"llm": {"backend": "api"}}, bad)


class CliWiringTests(unittest.TestCase):
    def _run(self, argv, command_attr):
        mod = _load_cli()
        captured = {}
        fake_cfg = {"llm": {"backend": "api"}, "knowledge_base": "/tmp/kb"}
        mod.config = lambda: fake_cfg

        def fake_command(cfg, *args, **kwargs):
            captured["cfg"] = cfg
            captured["args"] = args
            captured["kwargs"] = kwargs
            return 0

        setattr(mod, command_attr, fake_command)
        rc = mod.main(argv)
        return rc, captured, fake_cfg

    def test_init_kb_backend_override_reaches_command(self):
        rc, captured, fake_cfg = self._run(
            ["init-kb", "--backend", "agent"], "command_init_kb")
        self.assertEqual(rc, 0)
        self.assertEqual(captured["cfg"]["llm"]["backend"], "agent")
        self.assertEqual(fake_cfg["llm"]["backend"], "api")  # original intact

    def test_task_backend_override_reaches_command(self):
        rc, captured, _ = self._run(
            ["task", "--backend", "agent", "整理", "笔记"], "command_task")
        self.assertEqual(rc, 0)
        self.assertEqual(captured["cfg"]["llm"]["backend"], "agent")

    def test_plan_backend_override_reaches_command(self):
        rc, captured, _ = self._run(
            ["plan", "--backend", "api", "整理", "笔记"], "command_plan")
        self.assertEqual(rc, 0)
        self.assertEqual(captured["cfg"]["llm"]["backend"], "api")

    def test_no_flag_passes_config_through(self):
        rc, captured, fake_cfg = self._run(["init-kb"], "command_init_kb")
        self.assertEqual(rc, 0)
        self.assertIs(captured["cfg"], fake_cfg)

    def test_invalid_backend_rejected_by_argparse(self):
        mod = _load_cli()
        mod.config = lambda: {}
        with self.assertRaises(SystemExit) as ctx:
            mod.main(["init-kb", "--backend", "claude"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
