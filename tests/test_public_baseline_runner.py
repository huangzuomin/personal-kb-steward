"""T10 C1 runner tests — offline only, ZERO native-Claude subprocess calls.

The smoke path runs the ACTUAL pipeline (initialization plan -> save ->
review -> apply; finalize plan) with the test-only mock provider. The live
path is never executed here; tests prove it cannot load test answers and
that adapter/CLI contracts hold.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_public_baseline as runner  # noqa: E402


# ---------------------------------------------------------------------------
# Smoke: actual pipeline, no native CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def blocked_subprocess(monkeypatch):
    """Any real subprocess attempt fails the test — smoke must not shell out."""

    def _boom(*args, **kwargs):
        raise AssertionError("native subprocess must not run in smoke mode")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


def test_smoke_round_runs_actual_pipeline_without_native_cli(tmp_path, blocked_subprocess):
    exit_code = runner.main(["--smoke", "--output-dir", str(tmp_path / "art"),
                             "--rounds", "1"])
    metrics = json.loads((tmp_path / "art" / "metrics.json").read_text(encoding="utf-8"))
    rnd = metrics["rounds"][0]

    # initialization: actual plan/save/review/apply produced the source + seed cards
    assert rnd["stages"]["initialization"]["applied"] is True
    counts = rnd["card_type_counts"]
    assert counts["source-note"] >= 4
    assert counts["seed-card"] >= 1

    # B1a is wired through the real production topic path; the runner does
    # not substitute a second writer.
    assert rnd["stages"]["finalize"]["applied"] is True
    assert counts["concept-page"] >= 1
    assert counts["case-story"] >= 1
    assert counts["topic-page"] >= 1
    assert rnd["outcome"] == "complete"
    assert metrics["semantic_pass"] is None
    assert exit_code == 0

    # All five source/seed/finalize generator stages used the same provider:
    # exactly eight offline calls happened, with no native CLI (fixture above).
    assert rnd["provider_calls"] == 8


def test_smoke_run_refuses_existing_artifact_root(tmp_path):
    out = tmp_path / "art"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    assert runner.main(["--smoke", "--output-dir", str(out), "--rounds", "1"]) == 2


def test_rounds_beyond_hard_max_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        runner.main(["--smoke", "--output-dir", str(tmp_path / "a"),
                     "--rounds", "4"])
    assert exc_info.value.code == 2
    with pytest.raises(SystemExit) as exc_info:
        runner.main(["--smoke", "--live", "--output-dir", str(tmp_path / "b")])
    assert exc_info.value.code == 2


def test_smoke_and_live_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        runner.main(["--smoke", "--live", "--output-dir", str(tmp_path / "c"),
                     "--rounds", "1"])


def test_live_requires_enabled_adapter_config(tmp_path):
    # live mode constructs the adapter with enabled=True; a malformed budget
    # is refused BEFORE any round/vault creation
    code = runner.main(["--live", "--output-dir", str(tmp_path / "art"),
                        "--rounds", "1", "--max-total-calls", "31"])
    assert code == 2
    assert not (tmp_path / "art" / "rounds").exists()


# ---------------------------------------------------------------------------
# Version freeze
# ---------------------------------------------------------------------------


def test_version_freeze_detects_changes(tmp_path):
    frozen = runner.freeze_versions()
    runner.verify_versions(frozen)  # unchanged passes
    tampered = dict(frozen)
    tampered["core/llm.py"] = "0" * 64
    with pytest.raises(runner.RunnerError, match="blocking"):
        runner.verify_versions(tampered)
    missing = dict(frozen)
    removed = next(iter(missing))
    del missing[removed]
    with pytest.raises(runner.RunnerError, match="blocking"):
        runner.verify_versions(missing)


def test_freeze_file_missing_raises(monkeypatch):
    """A missing explicit input blocks freeze construction."""
    missing_rel = "core/__c3_missing_input__.py"
    monkeypatch.setattr(
        runner, "FREEZE_EXPLICIT_FILES",
        (*runner.FREEZE_EXPLICIT_FILES, missing_rel),
    )
    with pytest.raises(runner.RunnerError, match="version-freeze file missing"):
        runner.freeze_versions()


# ---------------------------------------------------------------------------
# Live import guard: the live path must never load test answers
# ---------------------------------------------------------------------------


def test_live_path_never_imports_public_round_support():
    """AST guard: the only import of the test-only mock corpus is inside the
    smoke-only provider factory. Any live-path import fails this test."""
    source = (REPO_ROOT / "scripts" / "evaluate_public_baseline.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    allowed_function = "make_smoke_provider"
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def enclosing_function(node):
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
            current = parents.get(current)
        return None

    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "public_round_support" for alias in node.names):
                owner = enclosing_function(node)
                if owner != allowed_function:
                    offenders.append(owner or "module-level")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "public_round_support":
                owner = enclosing_function(node)
                if owner != allowed_function:
                    offenders.append(owner or "module-level")
    # the smoke function's lazy import must exist
    smoke_fn = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == allowed_function)
    lazy = any(isinstance(n, ast.Import) and
               any(a.name == "public_round_support" for a in n.names)
               for n in ast.walk(smoke_fn))
    assert lazy, "smoke provider must lazily import the mock corpus"
    assert offenders == [], offenders


def test_live_provider_factory_does_not_touch_mock_module(tmp_path, monkeypatch):
    """Runtime guard: constructing the LIVE provider with a blocking import
    hook succeeds — the live path provably never imports test answers."""

    class Blocker:
        def find_module(self, name, path=None):  # noqa: D401
            if name == "public_round_support" or name.startswith("public_round_support."):
                raise ImportError("test answers blocked in live mode")
            return None

        def find_spec(self, name, path=None, target=None):
            if name == "public_round_support" or name.startswith("public_round_support."):
                raise ImportError("test answers blocked in live mode")
            return None

    sys.meta_path.insert(0, Blocker())
    try:
        from core.public_evaluation import PublicContextBundle

        bundle = PublicContextBundle()
        for fid in runner.ROUND_SOURCES:
            bundle.register_fixture(fid, fid)
        adapter = _fake_adapter(tmp_path)
        provider = runner.make_live_provider(adapter, 0, bundle)
        assert callable(provider)
    finally:
        sys.meta_path.pop(0)


def _fake_adapter(tmp_path):
    """A live adapter whose subprocess seam records instead of launching."""
    from core.public_evaluation import (
        AdapterConfig, PublicClaudeAdapter, RunRecorder,
    )

    class FakeCompleted:
        stdout = b'{"is_error": false, "result": "ok"}'
        stderr = b""
        returncode = 0

    adapter = PublicClaudeAdapter(
        AdapterConfig.from_cfg({"public_evaluation": {"enabled": True}}),
        RunRecorder(tmp_path / "adapter-artifacts", "fake"),
        run_subprocess=lambda *a, **k: FakeCompleted())
    return adapter


# ---------------------------------------------------------------------------
# Budget: adapter bounds still enforced at runner level
# ---------------------------------------------------------------------------


def test_runner_reports_adapter_budget_refusal_as_block(tmp_path, monkeypatch):
    """If the adapter budget is exhausted mid-run, the round fails explicitly
    and is never presented as success."""
    calls = {"n": 0}

    def exhausting_provider(*args, **kwargs):
        calls["n"] += 1
        raise runner.RunnerError("budget exhausted; attempt refused before launch")

    monkeypatch.setattr(runner, "make_smoke_provider",
                        lambda round_index, call_log: exhausting_provider)
    code = runner.main(["--smoke", "--output-dir", str(tmp_path / "art"),
                        "--rounds", "1"])
    metrics = json.loads((tmp_path / "art" / "metrics.json").read_text(encoding="utf-8"))
    # the init stage could not apply → incomplete/blocked, never success
    rnd = metrics["rounds"][0]
    assert rnd["outcome"] == "incomplete"
    assert code == 1
