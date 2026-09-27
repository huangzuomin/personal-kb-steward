"""Agent-CLI transport backend (Patch L): subprocess behavior, prompt build,
args template expansion, and failure mapping — subprocess is mocked."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import agent_backend  # noqa: E402
from core.agent_backend import build_prompt, call_agent_cli  # noqa: E402
from core.llm import LLMError  # noqa: E402


def _cfg(tmp: Path, **agent_extra) -> dict:
    agent = {"command": "fake-agent", "args": ["{stdin}"], "timeout_seconds": 5}
    agent.update(agent_extra)
    return {
        "llm": {"backend": "agent", "agent": agent},
        "knowledge_base": str(tmp),
    }


class BuildPromptTests(unittest.TestCase):
    def test_prompt_contains_contract_payload_and_workspace(self):
        prompt = build_prompt("SYSTEM", {"task": "t", "output_contract": {"a": 1}}, "W:\\kb")
        self.assertIn("SYSTEM", prompt)
        self.assertIn('"output_contract"', prompt)
        self.assertIn("W:\\kb", prompt)
        self.assertIn("abs_path", prompt)
        self.assertIn("只输出一个 JSON 对象", prompt)

    def test_payload_is_valid_json_block(self):
        prompt = build_prompt("S", {"task": "t"}, "W")
        payload_part = prompt.split("== 用户载荷（JSON）==\n", 1)[1].split("\n\n==", 1)[0]
        self.assertEqual(json.loads(payload_part), {"task": "t"})


class ArgvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_stdin_marker_expands_to_stdin_mode(self):
        with mock.patch.object(agent_backend, "_resolve_command", return_value="fake"), \
             mock.patch.object(agent_backend, "_write_prompt_file") as wf:
            wf.return_value = self.tmp / "p.txt"
            argv, stdin_mode = agent_backend._build_argv(
                {"command": "fake", "args": ["-p", "{stdin}"]}, "W", wf.return_value)
        self.assertEqual(argv, ["fake", "-p"])
        self.assertTrue(stdin_mode)

    def test_cwd_and_prompt_file_placeholders(self):
        pf = self.tmp / "p.txt"
        with mock.patch.object(agent_backend, "_resolve_command", return_value="fake"):
            argv, stdin_mode = agent_backend._build_argv(
                {"command": "fake", "args": ["--dir", "{cwd}", "--prompt-file", "{prompt_file}"]},
                "W", pf)
        self.assertEqual(argv, ["fake", "--dir", "W", "--prompt-file", str(pf)])
        self.assertFalse(stdin_mode)

    def test_prompt_file_and_stdin_marker_conflict(self):
        with mock.patch.object(agent_backend, "_resolve_command", return_value="fake"):
            with self.assertRaises(LLMError):
                agent_backend._build_argv(
                    {"command": "fake", "args": ["{prompt_file}", "{stdin}"]}, "W", self.tmp / "p.txt")

    def test_unknown_placeholder_rejected(self):
        with mock.patch.object(agent_backend, "_resolve_command", return_value="fake"):
            with self.assertRaises(LLMError):
                agent_backend._build_argv(
                    {"command": "fake", "args": ["{explode}"]}, "W", self.tmp / "p.txt")


class CallAgentCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp)
        # Isolate the shared prompt dir: a real llm-check run leaves
        # agent-prompt-*.txt files behind until its finally fires, and the
        # cleanup assertion below must not trip over those.
        self.prompt_dir = self.tmp / "prompts"
        patcher = mock.patch.object(agent_backend, "PROMPT_TMP_DIR", self.prompt_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, *, returncode=0, stdout=b'{"items": []}', stderr=b"",
             side_effect=None):
        proc = mock.Mock(returncode=returncode,
                         stdout=stdout, stderr=stderr)
        with mock.patch.object(agent_backend.subprocess, "run",
                               side_effect=side_effect or
                               (lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")) if False else proc)) as run, \
             mock.patch.object(agent_backend.shutil, "which", return_value="C:/bin/fake-agent.exe"):
            result = call_agent_cli(self.cfg, "SYS", {"task": "t"})
        return result, run

    def test_success_returns_stdout_and_cleans_prompt_file(self):
        result, run = self._run(stdout=b'{"items": []}')
        self.assertEqual(result, '{"items": []}')
        args, kwargs = run.call_args
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(Path(kwargs["cwd"]).resolve(), self.tmp.resolve())
        self.assertTrue(kwargs.get("input"))  # prompt via stdin
        tmp_files = list(agent_backend.PROMPT_TMP_DIR.glob("agent-prompt-*.txt"))
        self.assertEqual(tmp_files, [])

    def test_nonzero_exit_raises_with_stderr_tail(self):
        with self.assertRaises(LLMError) as ctx:
            self._run(returncode=2, stderr=b"boom detail")
        self.assertIn("退出码 2", str(ctx.exception))
        self.assertIn("boom detail", str(ctx.exception))

    def test_timeout_maps_to_llm_error(self):
        with self.assertRaises(LLMError) as ctx:
            self._run(side_effect=agent_backend.subprocess.TimeoutExpired(cmd="x", timeout=5))
        self.assertIn("超时", str(ctx.exception))

    def test_missing_binary_maps_to_llm_error(self):
        with mock.patch.object(agent_backend.subprocess, "run",
                               side_effect=FileNotFoundError()), \
             mock.patch.object(agent_backend.shutil, "which", return_value=None):
            with self.assertRaises(LLMError) as ctx:
                call_agent_cli(self.cfg, "SYS", {"task": "t"})
        self.assertIn("未找到", str(ctx.exception))

    def test_empty_stdout_raises(self):
        with self.assertRaises(LLMError):
            self._run(stdout=b"   \n")

    def test_unresolvable_command_raises(self):
        with mock.patch.object(agent_backend.shutil, "which", return_value=None):
            with self.assertRaises(LLMError) as ctx:
                call_agent_cli(self.cfg, "SYS", {"task": "t"})
        self.assertIn("未找到", str(ctx.exception))

    def test_prompt_file_mode_passes_no_stdin(self):
        cfg = _cfg(self.tmp, args=["--prompt-file", "{prompt_file}"])
        proc = mock.Mock(returncode=0, stdout=b'{"ok": 1}', stderr=b"")
        with mock.patch.object(agent_backend.subprocess, "run", return_value=proc) as run, \
             mock.patch.object(agent_backend.shutil, "which", return_value="fake"):
            result = call_agent_cli(cfg, "SYS", {"task": "t"})
        self.assertEqual(result, '{"ok": 1}')
        self.assertIsNone(run.call_args.kwargs.get("input"))


if __name__ == "__main__":
    unittest.main()
