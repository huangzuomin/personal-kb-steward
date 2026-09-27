"""Shim protocol tests for the subagent gateway (no live subagent needed)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "integrations" / "subagent-gateway" / "shim.py"


def run_shim(prompt: str, queue: Path, timeout_env: str = "600",
             overall: int = 60) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["SUBAGENT_GW_QUEUE"] = str(queue)
    env["SUBAGENT_GW_TIMEOUT"] = timeout_env
    return subprocess.run(
        [sys.executable, str(SHIM)],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=overall,
        env=env,
    )


class ShimProtocolTests(unittest.TestCase):
    def test_request_response_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp)
            holder: dict = {}

            def fake_supervisor():
                # Wait for the request file, then answer it.
                req_dir = queue / "requests"
                for _ in range(100):
                    files = list(req_dir.glob("*.json"))
                    if files:
                        break
                    time.sleep(0.1)
                self.assertTrue(files, "shim never wrote a request file")
                req = json.loads(files[0].read_text(encoding="utf-8"))
                self.assertIn("只输出一个 JSON", req["prompt"])
                resp_dir = queue / "responses"
                resp_dir.mkdir(parents=True, exist_ok=True)
                (resp_dir / files[0].name).write_text(
                    json.dumps({"response": '{"ok": true}'}),
                    encoding="utf-8")

            t = threading.Thread(target=fake_supervisor, daemon=True)
            t.start()
            proc = run_shim("只输出一个 JSON 对象", queue)
            t.join(timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode())
            self.assertEqual(proc.stdout.decode().strip(), '{"ok": true}')

    def test_timeout_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_shim("hello", Path(tmp), timeout_env="2", overall=30)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("timeout", proc.stderr.decode().lower())

    def test_empty_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_shim("   ", Path(tmp), overall=30)
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
