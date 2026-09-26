"""Focused T10 C3 checks for freeze completeness and output confinement."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from core.public_evaluation import PublicClaudeAdapter, PublicContextBundle, RunRecorder


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "evaluate_public_baseline.py"
_spec = importlib.util.spec_from_file_location("public_baseline_runner_c3", RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(runner)


def test_freeze_covers_production_inputs_and_manifest_fixture_bytes():
    frozen = runner.freeze_versions()
    required = {
        "config.example.json",
        "router.json",
        "workflows.json",
        "scripts/personal_kb_steward.py",
        "scripts/evaluate_public_baseline.py",
        "tests/public_round_support.py",
        "tests/fixtures/card-baseline/manifest.json",
        "core/schemas/source-note.schema.json",
        "core/templates/source_note.j2",
        "skills/mindseed-grow/SKILL.md",
        "skills/mindseed-grow/schema.json",
        "skills/topic-research-compile/executor.py",
        "skills/topic-research-compile/renderer.py",
    }
    assert required <= frozen.keys()
    assert not any(".execution" in rel or "__pycache__" in rel
                   for rel in frozen)

    manifest_path = ROOT / "tests" / "fixtures" / "card-baseline" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        path = ROOT / entry["path"]
        rel = path.relative_to(ROOT).as_posix()
        assert frozen[rel] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_versions_detects_new_untracked_input():
    frozen = runner.freeze_versions()
    tampered = dict(frozen)
    tampered["core/new-production-module.py"] = "0" * 64
    with pytest.raises(runner.RunnerError, match="blocking"):
        runner.verify_versions(tampered)


def test_verify_versions_detects_fixture_drift():
    frozen = runner.freeze_versions()
    tampered = dict(frozen)
    tampered["tests/fixtures/card-baseline/project_case_01.md"] = "1" * 64
    with pytest.raises(runner.RunnerError, match="blocking"):
        runner.verify_versions(tampered)


def test_main_refuses_even_empty_existing_artifact_root(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()

    assert runner.main(["--smoke", "--output-dir", str(output), "--rounds", "1"]) == 2
    assert list(output.iterdir()) == []


def test_main_refuses_symlink_artifact_root(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    output = tmp_path / "link"
    try:
        output.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    assert runner.main(["--smoke", "--output-dir", str(output), "--rounds", "1"]) == 2
    assert list(target.iterdir()) == []


def test_prepare_vault_rejects_prepopulated_or_escaped_target(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    existing = artifact / "rounds" / "round-00" / "vault"
    existing.mkdir(parents=True)
    (existing / "keep.md").write_text("keep", encoding="utf-8")
    with pytest.raises(runner.RunnerError, match="reuse synthetic vault"):
        runner.prepare_vault(existing, artifact)

    outside = tmp_path / "outside"
    outside.mkdir()
    escaped = artifact / "rounds" / "round-01" / "vault"
    escaped.parent.mkdir(parents=True)
    try:
        escaped.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")
    with pytest.raises(runner.RunnerError, match="symlink|junction|reparse"):
        runner.prepare_vault(escaped, artifact)
    assert list(outside.iterdir()) == []


def test_prepare_vault_rejects_native_junction_without_symlink_privilege(tmp_path):
    """Junctions are reparse points even when directory symlinks are blocked."""
    if __import__("os").name != "nt":
        pytest.skip("native junction is Windows-only")
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = artifact / "rounds" / "round-00" / "vault"
    junction.parent.mkdir(parents=True)
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True, check=False,
    )
    if completed.returncode != 0 or not junction.is_dir():
        pytest.skip("native junction creation unavailable")
    with pytest.raises(runner.RunnerError, match="symlink|junction|reparse"):
        runner.prepare_vault(junction, artifact)
    assert list(outside.iterdir()) == []


class _LiveCompleted:
    returncode = 0
    stdout = b'{"is_error": false, "result": "{}"}'
    stderr = b""


def _live_fixture_payloads():
    text = lambda fid: runner.load_fixture_manifest()[fid].text
    return [
        *[{"text": f"Title: {fid}\n\n{text(fid)}"}
          for fid in runner.ROUND_SOURCES],
        {"task": "atomic_seed", "units": [],
         "source": "quicknote/dialogue_user_ai_01.md"},
        {"task": "concept_extraction", "documents": [
            {"path": "raw/project_case_01.md", "content": text("project_case_01")},
        ]},
        {"task": "case_extraction", "documents": [
            {"path": "raw/project_case_01.md", "content": text("project_case_01")},
        ]},
        {"task": "question_led_topic_synthesis", "question": runner.TOPIC_QUESTION,
         "documents": [{"path": "raw/project_case_01.md",
                        "content": text("project_case_01")}],
         "upstream_source_analysis": []},
    ]


def test_live_fake_round_records_full_stage_split_and_adapter_attempts(tmp_path, monkeypatch):
    """The runner's live branch accounts source/seed/concept/case/topic calls."""
    import core.llm as llm_module

    calls: list[dict] = []
    payloads = _live_fixture_payloads()

    def fake_run(*args, **kwargs):
        del args, kwargs
        return _LiveCompleted()

    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True, "max_total_calls": 30,
                               "max_round_calls": 10}},
        RunRecorder(tmp_path / "adapter-artifacts", "run"),
        run_subprocess=fake_run,
    )

    class FakeSteward:
        def stamp(self):
            return "stamp"

        def __getattr__(self, name):
            del name
            return lambda *args, **kwargs: None

        def build_initialization_plan(self, *args, **kwargs):
            del args, kwargs
            for payload in payloads[:5]:
                llm_module.call_chat_completion({}, "source-or-seed", payload)
            return {"run_id": "live-fake-init", "planned_pages": []}

        def make_finalize_plan(self, *args, **kwargs):
            del args
            providers = kwargs["providers"]
            for stage, payload in zip(("concept", "case", "topic"), payloads[5:]):
                providers[stage]({}, f"{stage}-prompt", payload)
            return {"run_id": "live-fake-finalize", "planned_pages": []}

    monkeypatch.setattr(runner, "verify_versions", lambda frozen: None)
    monkeypatch.setattr(runner, "_load_steward", lambda: FakeSteward())
    monkeypatch.setattr(runner, "_register_applied_source_cards",
                        lambda vault, plan, bundle: ({}, {
                            "ok": True, "registered": [], "errors": [],
                        }))
    monkeypatch.setattr(runner, "_save_review_apply", lambda *args: {
        "applied": True, "blocked": None,
    })

    # run_round itself owns the live provider factory and records its calls;
    # no mock answer provider is imported in this path.  There are no writer
    # manifests in this deliberately narrow accounting fixture, so the result
    # is incomplete for the explicit missing-proof reason.
    result = runner.run_round(0, tmp_path / "artifacts", "live", adapter, {},
                              intake_only=False)

    assert result["provider_calls"] == 8
    assert result["provider_calls_logged"] == 8
    assert result["stage_split"] == {
        "source": 4, "seed": 1, "concept": 1, "case": 1, "topic": 1,
        "unknown": 0,
    }
    assert result["outcome"] == "incomplete"
    assert "missing_apply_manifest" in result["incomplete_reasons"]
    assert adapter.round_attempts[0] == 8
    assert adapter.total_attempts == 8
    assert not result["call_errors"]


def test_live_fake_timeout_consumes_attempt_and_refuses_after_cap(tmp_path):
    """Timeouts count toward the adapter cap; a third launch is refused."""
    attempts = {"subprocess": 0}

    def timeout_run(*args, **kwargs):
        del args, kwargs
        attempts["subprocess"] += 1
        raise subprocess.TimeoutExpired(cmd="fake-claude", timeout=1)

    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True, "max_total_calls": 2,
                               "max_round_calls": 2, "timeout_seconds": 1}},
        RunRecorder(tmp_path / "adapter-artifacts", "run"),
        run_subprocess=timeout_run,
    )
    bundle = PublicContextBundle()
    for fid, rel in {**runner.ROUND_SOURCES,
                     runner.ROUND_DIALOGUE[0]: runner.ROUND_DIALOGUE[1]}.items():
        bundle.register_fixture(fid, fid)
    calls: list[dict] = []
    provider = runner.make_live_provider(adapter, 0, bundle, calls)
    payload = {"text": "Title: source\n\n" +
               runner.load_fixture_manifest()["project_case_01"].text}

    for _ in range(2):
        with pytest.raises(Exception, match="timeout"):
            provider({}, "prompt", payload)
    with pytest.raises(Exception, match="budget exhausted"):
        provider({}, "prompt", payload)

    assert attempts["subprocess"] == 2
    assert adapter.total_attempts == 2
    assert adapter.round_attempts[0] == 2
    assert len(calls) == 3
    assert [call["adapter_attempted"] for call in calls] == [True, True, False]
    assert runner._stage_split(calls)["source"] == 2
    evidence = (tmp_path / "adapter-artifacts" / "run" / "evidence.jsonl")
    assert len(evidence.read_text(encoding="utf-8").splitlines()) == 2


def test_observed_manifest_counts_applied_typed_outputs_only(tmp_path):
    vault = tmp_path / "vault"
    target = vault / "wiki" / "concepts" / "good.md"
    bad = vault / "wiki" / "concepts" / "replacement.md"
    missing_proof = vault / "wiki" / "concepts" / "missing-proof.md"
    body_type_only = vault / "wiki" / "concepts" / "body-type-only.md"
    readme = vault / "wiki" / "concepts" / "README.md"
    backup = vault / "wiki" / ".openclaw" / "backups" / "run" / "old.md"
    for path in (target, bad, missing_proof, body_type_only, readme, backup):
        path.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nobject_id: kb:good\nrevision: 1\ntype: concept-page\n---\nvalid\n",
        encoding="utf-8")
    bad.write_text(
        "---\nobject_id: kb:bad\nrevision: 1\ntype: concept-page\n---\n\ufffd\n",
        encoding="utf-8")
    missing_proof.write_text(
        "---\nobject_id: kb:missing\nrevision: 1\ntype: concept-page\n---\nvalid\n",
        encoding="utf-8")
    body_type_only.write_text("body text\ntype: concept-page\n", encoding="utf-8")
    readme.write_text("---\ntype: concept-page\n---\nREADME\n", encoding="utf-8")
    backup.write_text("---\ntype: concept-page\n---\nbackup\n", encoding="utf-8")

    manifest = vault / ".openclaw" / "runs" / "run.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    target_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    bad_hash = hashlib.sha256(bad.read_bytes()).hexdigest()
    manifest.write_text(json.dumps({
        "run_id": "run",
        "status": "applied",
        "reconcile": {"ok": True, "missing": [], "hash_mismatch": [],
                       "duplicate_created": {}},
        "created": [
            {"rel_path": "wiki/concepts/good.md",
             "canonical_path": "wiki/concepts/good.md",
             "object_id": "kb:good", "revision": 1,
             "sha256": target_hash, "expected_sha256": target_hash,
             "content_verified": True},
            {"rel_path": "wiki/concepts/replacement.md",
             "canonical_path": "wiki/concepts/replacement.md",
             "object_id": "kb:bad", "revision": 1,
             "sha256": bad_hash, "expected_sha256": bad_hash,
             "content_verified": True},
            {"rel_path": "wiki/concepts/missing-proof.md",
             "canonical_path": "wiki/concepts/missing-proof.md",
             "object_id": "kb:missing", "revision": 1,
             "sha256": hashlib.sha256(missing_proof.read_bytes()).hexdigest(),
             "content_verified": True},
            {"rel_path": "wiki/concepts/body-type-only.md",
             "canonical_path": "wiki/concepts/body-type-only.md",
             "object_id": "kb:body", "revision": 1,
             "sha256": hashlib.sha256(body_type_only.read_bytes()).hexdigest(),
             "expected_sha256": hashlib.sha256(body_type_only.read_bytes()).hexdigest(),
             "content_verified": True},
            {"rel_path": "wiki/concepts/README.md",
             "canonical_path": "wiki/concepts/README.md",
             "object_id": "kb:readme", "revision": 1,
             "sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
             "expected_sha256": hashlib.sha256(readme.read_bytes()).hexdigest(),
             "content_verified": True},
            {"rel_path": "wiki/.openclaw/backups/run/old.md",
             "canonical_path": "wiki/.openclaw/backups/run/old.md",
             "object_id": "kb:backup", "revision": 1,
             "sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
             "expected_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
             "content_verified": True},
        ],
    }), encoding="utf-8")
    failed = vault / ".openclaw" / "runs" / "failed.json"
    failed.write_text(json.dumps({
        "run_id": "failed-after-write", "status": "failed",
        "reconcile": {"ok": False, "missing": ["wiki/concepts/good.md"],
                       "hash_mismatch": [], "duplicate_created": {}},
        "created": [{"rel_path": "wiki/concepts/good.md",
                     "canonical_path": "wiki/concepts/good.md",
                     "object_id": "kb:good", "revision": 1,
                     "sha256": target_hash, "expected_sha256": target_hash,
                     "content_verified": False}],
    }), encoding="utf-8")

    observed = runner._collect_observed_outputs(vault)

    assert observed["card_type_counts"]["concept-page"] == 1
    assert len(observed["observed"]) == 7
    assert any(item["rel_path"] == "wiki/concepts/replacement.md"
               for item in observed["failures"])
    assert any(item["rel_path"] == "wiki/concepts/README.md"
               and "excluded" in item["error"]
               for item in observed["failures"])
    assert any(item["rel_path"] == "wiki/.openclaw/backups/run/old.md"
               and "excluded" in item["error"]
               for item in observed["failures"])
    assert any(item["rel_path"] == "wiki/concepts/missing-proof.md"
               for item in observed["failures"])
    assert any(item["rel_path"] == "wiki/concepts/body-type-only.md"
               for item in observed["failures"])
    assert len(observed["verified_rel_paths"]) == 1
