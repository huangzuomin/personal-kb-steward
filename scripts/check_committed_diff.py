#!/usr/bin/env python3
"""Check event-pinned, committed changes, not the clean Actions working tree."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ZERO_SHA = "0" * 40


def git_output(*args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], input=input_text, check=True,
        stdout=subprocess.PIPE, text=True, encoding="utf-8",
    ).stdout.strip()


def sha(value: Any, field: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError(f"{field} must be a full GitHub commit SHA")
    if value == ZERO_SHA and not allow_zero:
        raise ValueError(f"{field} cannot be the zero SHA")
    return value


def require_commit(value: str) -> None:
    # Missing history must fail closed. Never fall back to HEAD^ or an empty diff.
    git_output("cat-file", "-e", f"{value}^{{commit}}")


def check_committed_diff(event_name: str, event: dict[str, Any], event_sha: str) -> None:
    checked_out = git_output("rev-parse", "HEAD")
    expected = sha(event_sha, "GITHUB_SHA")
    print(f"CHECKED_OUT_SHA={checked_out}\nEVENT_SHA={expected}", flush=True)
    if checked_out != expected:
        raise ValueError("Checkout does not match the event SHA")

    ranges: list[tuple[str, str, str]] = []
    if event_name == "pull_request":
        pr = event["pull_request"]
        base = sha(pr["base"]["sha"], "pull_request.base.sha")
        head = sha(pr["head"]["sha"], "pull_request.head.sha")
        require_commit(base)
        require_commit(head)
        parents = git_output("show", "-s", "--format=%P", checked_out).split()
        print(f"BASE_HEAD_SHA={base}\nPR_HEAD_SHA={head}", flush=True)
        print("MERGE_PARENTS=" + " ".join(parents), flush=True)
        if parents != [base, head]:
            raise ValueError("Checkout is not the merge candidate for this PR event")
        ancestors = git_output("merge-base", "--all", base, head).split()
        if len(ancestors) != 1:
            raise ValueError("A unique PR merge base is required; fetch complete history")
        print(f"PR_MERGE_BASE_SHA={ancestors[0]}", flush=True)
        # Equivalent to base...head, plus what the merge would add to current base.
        ranges = [("pr-head", ancestors[0], head), ("pr-merge", base, checked_out)]
    elif event_name == "push":
        before = sha(event["before"], "push.before", allow_zero=True)
        after = sha(event["after"], "push.after")
        if event.get("deleted") or after != checked_out:
            raise ValueError("Push after SHA must match the checked-out commit")
        if before == ZERO_SHA:
            # A new ref has no before commit: explicitly audit the whole initial tree.
            start = git_output("hash-object", "-w", "-t", "tree", "--stdin", input_text="")
        else:
            require_commit(before)
            start = before
        print(f"PUSH_BEFORE_SHA={before}\nPUSH_AFTER_SHA={after}", flush=True)
        ranges = [("push", start, after)]
    else:
        raise ValueError(f"Unsupported CI event: {event_name}")

    for label, start, end in ranges:
        print(f"DIFF_RANGE[{label}]={start}..{end}", flush=True)
        # Do not use --exit-code: valid, nonempty changes should pass --check.
        subprocess.run(
            ["git", "diff", "--check", "--no-ext-diff", "--no-textconv", start, end, "--"],
            check=True,
        )
    print("COMMITTED_DIFF_CHECK=passed", flush=True)


def main() -> int:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        check_committed_diff(os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"])
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Committed-diff check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
