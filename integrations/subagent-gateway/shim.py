#!/usr/bin/env python3
"""Subagent gateway shim: serve as ``llm.agent.command`` for personal-kb-steward.

The steward's agent transport spawns this script as a headless "agent CLI".
Instead of calling a model itself, the shim drops the prompt into a queue
directory and blocks until the supervisor (Muse, the human-side operator)
writes the matching response file. The response text is printed to stdout,
exactly as a real agent CLI would.

Protocol (all files UTF-8 JSON):
  requests/<req_id>.json   {"id": ..., "prompt": ...}      written by shim
  responses/<req_id>.json  {"response": "<raw stdout>"}     written by supervisor

Queue dir: $SUBAGENT_GW_QUEUE (default: <repo>/.openclaw/tmp/subagent-gw).
Wait timeout: $SUBAGENT_GW_TIMEOUT seconds (default 600; keep below the
program-side ``llm.agent.timeout_seconds`` so this error surfaces first).

Security notes:
  - The shim never interprets the prompt; it is opaque bytes in transit.
  - Response files are only read from the supervisor-owned queue dir.
  - Exit code != 0 makes the steward raise LLMError (fail-closed).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

DEFAULT_TIMEOUT = 600.0
POLL_INTERVAL = 2.0


def queue_dir() -> Path:
    raw = os.environ.get("SUBAGENT_GW_QUEUE", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    root = Path(__file__).resolve().parents[2]
    return root / ".openclaw" / "tmp" / "subagent-gw"


def read_prompt() -> str:
    # Program passes "{stdin}" (prompt on stdin) or "{prompt_file}" (path).
    if len(sys.argv) > 1 and not sys.argv[1].startswith("{"):
        return Path(sys.argv[1]).read_text(encoding="utf-8")
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("subagent-gw shim: empty prompt on stdin")
    return data


def main() -> int:
    qdir = queue_dir()
    req_dir = qdir / "requests"
    resp_dir = qdir / "responses"
    req_dir.mkdir(parents=True, exist_ok=True)
    resp_dir.mkdir(parents=True, exist_ok=True)

    try:
        timeout = float(os.environ.get("SUBAGENT_GW_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    prompt = read_prompt()
    req_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    (req_dir / f"{req_id}.json").write_text(
        json.dumps({"id": req_id, "prompt": prompt}, ensure_ascii=False),
        encoding="utf-8",
    )
    # Best-effort: tell the supervisor where to look.
    print(f"[subagent-gw] request {req_id} queued in {req_dir}", file=sys.stderr)

    resp_file = resp_dir / f"{req_id}.json"
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if resp_file.exists():
            try:
                payload = json.loads(resp_file.read_text(encoding="utf-8"))
                response = payload["response"]
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
                print(f"[subagent-gw] bad response file {resp_file}: {exc}",
                      file=sys.stderr)
                return 1
            if not isinstance(response, str) or not response.strip():
                print(f"[subagent-gw] empty response in {resp_file}",
                      file=sys.stderr)
                return 1
            sys.stdout.write(response)
            return 0
        time.sleep(POLL_INTERVAL)

    print(f"[subagent-gw] timeout after {timeout:g}s waiting for {resp_file}",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
