"""Exercise the real CI checker against disposable Git repositories (no network)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_committed_diff.py"
ZERO_SHA = "0" * 40


class Repository:
    def __init__(self, root: Path):
        self.root = root
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, PYTHONUTF8="1")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci-test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.initial = self.commit("initial.txt", "initial\n")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.root, env=self.env, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

    def commit(self, name: str, content: str) -> str:
        (self.root / name).write_bytes(content.encode("utf-8"))
        self.git("add", "--", name)
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def run(self, name: str, event: dict, event_sha: str, *, cwd: Path | None = None):
        event_file = self.root.parent / (self.root.name + "-event.json")
        event_file.write_text(json.dumps(event), encoding="utf-8")
        env = dict(self.env, GITHUB_EVENT_NAME=name, GITHUB_EVENT_PATH=str(event_file), GITHUB_SHA=event_sha)
        return subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=cwd or self.root, env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def pr(self, base: str, head: str, *, merge: str | None = None, cwd: Path | None = None):
        return self.run("pull_request", {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}},
                        merge or self.git("rev-parse", "HEAD"), cwd=cwd)

    def push(self, before: str):
        after = self.git("rev-parse", "HEAD")
        return self.run("push", {"before": before, "after": after}, after)

    def merge(self, base: str):
        self.git("checkout", "main")
        assert self.git("rev-parse", "HEAD") == base
        self.git("merge", "--no-ff", "feature", "-m", "fixture merge")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return Repository(root)


def test_clean_pr_logs_both_committed_ranges(repo):
    repo.git("checkout", "-b", "feature")
    head = repo.commit("feature.txt", "feature\n")
    repo.merge(repo.initial)
    merge = repo.git("rev-parse", "HEAD")
    result = repo.pr(repo.initial, head)
    assert result.returncode == 0, result.stderr
    assert f"DIFF_RANGE[pr-head]={repo.initial}..{head}" in result.stdout
    assert f"DIFF_RANGE[pr-merge]={repo.initial}..{merge}" in result.stdout


def test_pr_catches_earlier_committed_error_despite_clean_worktree_and_last_commit(repo):
    repo.git("checkout", "-b", "feature")
    repo.commit("bad.txt", "bad \n")
    head = repo.commit("good.txt", "good\n")
    repo.git("diff", "--check", "HEAD^", "HEAD")  # Last commit alone misses the error.
    repo.merge(repo.initial)
    assert repo.git("status", "--porcelain") == ""
    repo.git("diff", "--check")  # This was the old false-green check.
    result = repo.pr(repo.initial, head)
    assert result.returncode != 0
    assert "bad.txt" in result.stdout
    assert "COMMITTED_DIFF_CHECK=passed" not in result.stdout


def test_base_only_whitespace_is_not_charged_to_pr(repo):
    repo.git("checkout", "-b", "feature")
    head = repo.commit("feature.txt", "good\n")
    repo.git("checkout", "main")
    base = repo.commit("base-only.txt", "old base issue \n")
    repo.merge(base)
    result = repo.pr(base, head)
    assert result.returncode == 0, result.stderr
    assert f"PR_MERGE_BASE_SHA={repo.initial}" in result.stdout


def test_merge_result_is_checked_as_well_as_pr_head(repo):
    repo.git("checkout", "-b", "feature")
    head = repo.commit("feature.txt", "good\n")
    repo.merge(repo.initial)
    (repo.root / "merge-only.txt").write_bytes(b"bad resolution \n")
    repo.git("add", "merge-only.txt")
    repo.git("commit", "--amend", "--no-edit")
    result = repo.pr(repo.initial, head)
    assert result.returncode != 0
    assert "DIFF_RANGE[pr-merge]=" in result.stdout
    assert "merge-only.txt" in result.stdout


def test_push_checks_all_commits_in_event(repo):
    repo.commit("bad.txt", "bad \n")
    repo.commit("good.txt", "good\n")
    repo.git("diff", "--check", "HEAD^", "HEAD")
    result = repo.push(repo.initial)
    assert result.returncode != 0
    assert "bad.txt" in result.stdout


def test_valid_nonempty_push_passes(repo):
    after = repo.commit("good.txt", "good\n")
    result = repo.push(repo.initial)
    assert result.returncode == 0, result.stderr
    assert f"DIFF_RANGE[push]={repo.initial}..{after}" in result.stdout


@pytest.mark.parametrize("bad", [False, True])
def test_new_ref_checks_whole_tree_against_empty_tree(repo, bad):
    repo.commit("added.txt", "bad \n" if bad else "good\n")
    result = repo.push(ZERO_SHA)
    assert (result.returncode != 0) == bad
    assert f"PUSH_BEFORE_SHA={ZERO_SHA}" in result.stdout
    assert "DIFF_RANGE[push]=" in result.stdout


def test_missing_push_history_fails_closed(repo):
    result = repo.push("1" * 40)
    assert result.returncode != 0
    assert "COMMITTED_DIFF_CHECK=passed" not in result.stdout


def test_force_push_uses_event_before_even_when_not_an_ancestor(repo):
    before = repo.commit("old.txt", "old\n")
    repo.git("checkout", "-b", "replacement", repo.initial)
    after = repo.commit("new.txt", "new\n")
    result = repo.push(before)
    assert result.returncode == 0, result.stderr
    assert f"DIFF_RANGE[push]={before}..{after}" in result.stdout


def test_checkout_mismatch_fails(repo):
    result = repo.run("push", {"before": ZERO_SHA, "after": repo.initial}, "1" * 40)
    assert result.returncode != 0
    assert "Checkout does not match" in result.stderr


def test_push_after_mismatch_fails(repo):
    result = repo.run("push", {"before": ZERO_SHA, "after": "1" * 40}, repo.initial)
    assert result.returncode != 0
    assert "Push after SHA" in result.stderr


def test_pr_parent_mismatch_fails(repo):
    repo.git("checkout", "-b", "feature")
    head = repo.commit("feature.txt", "good\n")
    repo.merge(repo.initial)
    result = repo.pr(head, repo.initial)
    assert result.returncode != 0
    assert "not the merge candidate" in result.stderr


@pytest.mark.parametrize("value", ["--help", "bad-sha", ZERO_SHA])
def test_invalid_event_sha_fails_closed(repo, value):
    result = repo.run("push", {"before": ZERO_SHA, "after": repo.initial}, value)
    assert result.returncode != 0
    assert "DIFF_RANGE" not in result.stdout


def test_unknown_event_fails_closed(repo):
    result = repo.run("workflow_dispatch", {}, repo.initial)
    assert result.returncode != 0
    assert "Unsupported CI event" in result.stderr


def test_shallow_clone_does_not_silently_shrink_pr_range(repo):
    repo.git("checkout", "-b", "feature")
    for i in range(3):
        head = repo.commit(f"feature-{i}.txt", "good\n")
    repo.git("checkout", "main")
    for i in range(3):
        base = repo.commit(f"base-{i}.txt", "good\n")
    repo.merge(base)
    shallow = repo.root.parent / "shallow"
    repo.git("clone", "--depth=2", "--branch", "main", repo.root.as_uri(), str(shallow))
    result = repo.pr(base, head, cwd=shallow)
    assert result.returncode != 0
    assert "COMMITTED_DIFF_CHECK=passed" not in result.stdout
