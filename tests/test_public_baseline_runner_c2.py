"""Focused T10 C2 checks for the public baseline runner.

These tests use the accepted public adapter seam with a fake subprocess.  No
native Claude process, network, or answer corpus is used here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from core.public_evaluation import PublicClaudeAdapter, PublicContextBundle, RunRecorder


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "evaluate_public_baseline.py"
_spec = importlib.util.spec_from_file_location("public_baseline_runner_c2", RUNNER_PATH)
runner = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(runner)


class _Completed:
    def __init__(self, result: str = "ok", returncode: int = 0,
                 stdout: bytes | None = None):
        self.stdout = stdout or json.dumps(
            {"is_error": False, "result": result}, ensure_ascii=False
        ).encode("utf-8")
        self.stderr = b""
        self.returncode = returncode


def _fixture_text(fid: str) -> str:
    return runner.load_fixture_manifest()[fid].text


def _payloads() -> list[dict]:
    return [
        # source-research-compile: actual source payload has text only
        {"text": "Title: 合成对话\n[片段 1]\n\n" +
         _fixture_text("dialogue_user_ai_01")},
        # atomic_seed
        {"task": "atomic_seed", "coverage_note": "", "units": [{
            "id": 0,
            "source": "tests/fixtures/card-baseline/dialogue_user_ai_01.md",
            "quote": "我收藏了很多文章，但从不删东西。",
            "kind": "assertion", "speaker": "林舟（用户）", "body_line": 3,
        }]},
        # concept_generation
        {"task": "concept_extraction", "documents": [
            {"path": "dialogue_user_ai_01.md", "title": "合成对话",
             "text": _fixture_text("dialogue_user_ai_01")},
            {"path": "research_summary_uncited_01.md", "title": "研究综述",
             "text": _fixture_text("research_summary_uncited_01")},
        ], "known_paths": [], "upstream": [],
         "output_contract": {"concept_found": "boolean"}},
        # case_generation
        {"task": "case_extraction", "documents": [
            {"path": "project_case_01.md", "title": "青梧书店案例",
             "text": _fixture_text("project_case_01")},
            {"path": "project_case_01_followup.md", "title": "回访观察",
             "text": _fixture_text("project_case_01_followup")},
            {"path": "project_case_01_counterexample.md", "title": "反例",
             "text": _fixture_text("project_case_01_counterexample")},
        ], "known_paths": [], "upstream": [],
         "output_contract": {"case_found": "boolean"}},
        # topic_generation
        {"task": "question_led_topic_synthesis",
         "question": "三段转化链在什么条件下有效、在什么条件下失效？",
         "documents": [{"path": "project_case_01.md", "title": "青梧书店案例",
                        "text": _fixture_text("project_case_01")}],
         "known_paths": [], "output_contract": {"topic_viable": "boolean"}},
    ]


def _provider(tmp_path: Path, seen: dict) -> tuple[object, PublicContextBundle]:
    def fake_run(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["input"] = kwargs["input"]
        return _Completed()

    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True, "max_total_calls": 10,
                               "max_round_calls": 10}},
        RunRecorder(tmp_path / "adapter-artifacts", "run"),
        run_subprocess=fake_run,
    )
    bundle = PublicContextBundle()
    for fid in {**runner.ROUND_SOURCES,
                runner.ROUND_DIALOGUE[0]: runner.ROUND_DIALOGUE[1]}:
        bundle.register_fixture(fid, fid)
    return runner.make_live_provider(adapter, 0, bundle), bundle


@pytest.mark.parametrize("payload", _payloads(), ids=[
    "source", "seed", "concept", "case", "topic",
])
def test_live_provider_preserves_all_five_generator_payload_shapes(tmp_path, payload):
    seen: dict = {}
    provider, _ = _provider(tmp_path, seen)

    assert provider({}, "public system prompt", payload) == "ok"
    # The adapter receives the exact generator argument.  Provenance is
    # recorded beside it and never injected into the model payload.
    assert json.loads(seen["input"].decode("utf-8")) == payload
    evidence = json.loads(
        (tmp_path / "adapter-artifacts" / "run" / "evidence.jsonl")
        .read_text(encoding="utf-8").splitlines()[0]
    )
    assert evidence["source_hashes"]
    assert not any(name.startswith("generated:")
                   for name in evidence["source_hashes"])


def test_live_provider_registers_generated_source_card_without_rewriting_payload(tmp_path):
    seen: dict = {}
    provider, _ = _provider(tmp_path, seen)
    text = "公开生成的 source-card 快照"
    payload = {"task": "concept_extraction", "documents": [{
        "path": "cards/source-card-01.md", "content": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }]}

    provider({}, "public system prompt", payload)
    assert json.loads(seen["input"].decode("utf-8")) == payload
    evidence = json.loads(
        (tmp_path / "adapter-artifacts" / "run" / "evidence.jsonl")
        .read_text(encoding="utf-8").splitlines()[0]
    )
    assert evidence["source_hashes"]["generated:cards/source-card-01.md"] == payload["documents"][0]["sha256"]


def test_applied_source_card_registration_reads_written_bytes_and_maps_source(tmp_path):
    vault = tmp_path / "vault"
    target = vault / "wiki" / "sources" / "source-case.md"
    target.parent.mkdir(parents=True)
    raw = "# applied source card\n\nexact bytes\n".encode("utf-8")
    target.write_bytes(raw)
    plan = {
        "planned_pages": [{
            "rel_path": "wiki/sources/source-case.md",
            "sources": ["raw/project_case_01.md"],
            "content_sha256": hashlib.sha256(raw).hexdigest(),
        }],
    }
    bundle = PublicContextBundle()
    source_map, result = runner._register_applied_source_cards(vault, plan, bundle)
    assert result["ok"] is True
    name = source_map["raw/project_case_01.md"]
    assert name == "generated:wiki/sources/source-case.md"
    assert bundle.source_hashes()[name] == hashlib.sha256(raw).hexdigest()


def test_source_chunk_requires_declared_exact_offset_for_partial_fixture(tmp_path):
    seen: dict = {}
    provider, _ = _provider(tmp_path, seen)
    text = _fixture_text("dialogue_user_ai_01")
    end = min(40, len(text))
    payload = {"text": (
        "Title: 合成对话\n[片段 1，字符偏移 0-{}，全文 {} 字符]\n\n{}"
    ).format(end, len(text), text[:end])}
    provider({}, "public system prompt", payload)
    assert json.loads(seen["input"].decode("utf-8")) == payload

    with pytest.raises(Exception):
        provider({}, "public system prompt", {"text": text[:end]})


def test_provider_failure_retains_raw_prompt_payload_and_error(tmp_path):
    seen: dict = {}
    provider, _ = _provider(tmp_path, seen)
    calls: list[dict] = []
    # A non-canonical source text fails before subprocess launch, but the raw
    # attempted call still remains inspectable in runner evidence.
    live = runner.make_live_provider(
        # Reuse the fake adapter construction, while adding the caller log.
        PublicClaudeAdapter(
            {"public_evaluation": {"enabled": True}},
            RunRecorder(tmp_path / "failure-artifacts", "run"),
            run_subprocess=lambda *a, **k: _Completed(),
        ),
        0, PublicContextBundle(), calls,
    )
    with pytest.raises(Exception):
        live({}, "raw prompt", {"text": "not a canonical public snapshot"})
    assert calls[0]["system_prompt"] == "raw prompt"
    assert calls[0]["payload"] == {"text": "not a canonical public snapshot"}
    assert calls[0]["error"]["type"]
    path = Path(runner._write_provider_evidence(tmp_path, 0, calls))
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["system_prompt"] == "raw prompt"
    assert record["payload"]["text"] == "not a canonical public snapshot"
    assert record["error"]["message"]


def test_apply_failure_after_partial_write_cannot_be_complete(tmp_path):
    from core.config import review_queue_path
    from core.review_queue import append_item

    vault = tmp_path / "vault"
    safety = vault / ".openclaw"
    cfg = {
        "knowledge_base": str(vault),
        "state_file": str(safety / "state.json"),
        "safety": {
            "plans_dir": str(safety / "plans"),
            "manual_review_queue": str(safety / "manual-review" / "queue.jsonl"),
        },
    }
    target = vault / "raw" / "written-before-apply-error.md"
    plan = {"run_id": "c2-write-after-failure", "planned_pages": []}

    class FakeSteward:
        def __init__(self):
            self.review_commands = []

        def write_execution_plan(self, cfg_, value):
            del cfg_
            path = safety / "plans" / "c2-write-after-failure.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
            return path

        def write_manual_review_queue(self, cfg_, value):
            del value
            append_item(review_queue_path(cfg_), {
                "run_id": plan["run_id"], "type": "page", "status": "pending",
            })
            return 1

        def command_review(self, cfg_, args):
            self.review_commands.append(args.review_command)
            if args.review_command == "batch-approve":
                return 0
            if args.review_command == "apply-approved":
                del cfg_
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("partial write", encoding="utf-8")
                return 1
            raise AssertionError(args.review_command)

    steward = FakeSteward()
    result = runner._save_review_apply(steward, cfg, plan)
    assert target.is_file()
    assert result["applied"] is False
    assert result["blocked"] == "apply_failed"
    assert result["apply_code"] == 1
    assert steward.review_commands == ["batch-approve", "apply-approved"]


def test_partial_producer_with_applyable_page_is_not_applied(tmp_path, monkeypatch):
    plan_path = tmp_path / "partial-plan.json"
    plan_path.write_text(json.dumps({
        "run_id": "partial-producer",
        "actions": [{
            "stage": "source_compile", "state": "partial",
            "planned_items": 1,
            "input_outcomes": [{"outcome": "partial", "complete": False,
                                 "targets": ["wiki/sources/source.md"]}],
        }],
        "planned_pages": [{"rel_path": "wiki/sources/source.md"}],
    }), encoding="utf-8")

    class FakeSteward:
        def build_initialization_plan(self, *args, **kwargs):
            del args, kwargs
            return {"run_id": "partial-producer", "planned_pages": []}

        def stamp(self):
            return "stamp"

        def __getattr__(self, name):
            del name
            return lambda *args, **kwargs: None

    monkeypatch.setattr(runner, "verify_versions", lambda frozen: None)
    monkeypatch.setattr(runner, "_load_steward", lambda: FakeSteward())
    monkeypatch.setattr(runner, "_save_review_apply", lambda *args: {
        "plan_path": str(plan_path), "applied": True, "blocked": None,
    })
    monkeypatch.setattr(runner, "make_smoke_provider",
                        lambda round_index, call_log: lambda *args: "unused")

    result = runner.run_round(0, tmp_path / "artifacts", "smoke", None, {},
                              intake_only=True)
    assert result["stages"]["initialization"]["applied"] is False
    assert result["stages"]["initialization"]["blocked"] == "producer_output_incomplete"
    assert result["outcome"] == "incomplete"
    assert any("producer state=partial" in p
               for p in result["stages"]["initialization"]["plan_validation"]["problems"])


@pytest.mark.parametrize("status", ["partial_input", "blocked", "model_error"])
def test_required_seed_outcome_or_state_cannot_hide_planned_page(tmp_path, status):
    """Executor status is authoritative even when a page is still planned."""
    for field in ("outcome", "state"):
        plan_path = tmp_path / f"seed-{field}-{status}.json"
        action = {
            "stage": "seed_cluster",
            "planned_pages": 1,
            field: status,
        }
        plan_path.write_text(json.dumps({
            "entry": "init_kb",
            "actions": [action],
            "planned_pages": [{"rel_path": "wiki/seeds/partial.md"}],
        }), encoding="utf-8")

        result = runner._validate_saved_plan(plan_path)

        assert result["ok"] is False
        assert any(status in problem for problem in result["problems"])


@pytest.mark.parametrize("reason", [
    "no_eligible_sources", "no_inputs", "no_relevant_sources",
])
def test_init_downstream_short_circuit_without_plans_remains_valid(tmp_path, reason):
    plan_path = tmp_path / f"short-circuit-{reason}.json"
    plan_path.write_text(json.dumps({
        "entry": "init_kb",
        "actions": [{
            "stage": "concept_generation",
            "outcome": "blocked",
            "state": "blocked",
            "reason": reason,
            "planned_items": 0,
        }],
        "planned_pages": [],
    }), encoding="utf-8")

    result = runner._validate_saved_plan(plan_path)

    assert result["ok"] is True
    assert result["problems"] == []


def test_provider_call_error_is_incomplete_even_if_apply_succeeds(tmp_path, monkeypatch):
    import core.llm as llm_module

    class FakeSteward:
        def build_initialization_plan(self, *args, **kwargs):
            del args, kwargs
            # The patched production seam invokes the provider and records a
            # real call error before this fake producer returns an applyable
            # plan.
            try:
                llm_module.call_chat_completion({}, "raw prompt", {"text": "x"})
            except RuntimeError:
                pass
            return {"run_id": "call-error", "planned_pages": []}

        def stamp(self):
            return "stamp"

        def __getattr__(self, name):
            del name
            return lambda *args, **kwargs: None

    def make_failing_provider(round_index, call_log):
        def failing_provider(*args):
            del args
            call_log.append({
                "round": round_index, "stage": "source:producer",
                "system_prompt": "raw prompt", "payload": {"text": "x"},
                "response": None,
                "error": {"type": "RuntimeError", "message": "producer provider failed"},
            })
            raise RuntimeError("producer provider failed")
        return failing_provider

    monkeypatch.setattr(runner, "verify_versions", lambda frozen: None)
    monkeypatch.setattr(runner, "_load_steward", lambda: FakeSteward())
    monkeypatch.setattr(runner, "_save_review_apply", lambda *args: {
        "applied": True, "blocked": None,
    })
    monkeypatch.setattr(runner, "make_smoke_provider", make_failing_provider)

    result = runner.run_round(0, tmp_path / "artifacts", "smoke", None, {},
                              intake_only=True)
    assert result["call_errors"]
    assert result["outcome"] == "incomplete"
    assert "provider_call_errors:1" in result["incomplete_reasons"]


def test_round_stage_failure_stays_incomplete_even_with_required_files(tmp_path, monkeypatch):
    class FakeSteward:
        def build_initialization_plan(self, *args, **kwargs):
            del args, kwargs
            return {"run_id": "round-failure", "planned_pages": []}

        def stamp(self):
            return "stamp"

        def __getattr__(self, name):
            # The plan call receives these normal steward hooks; their
            # behavior is irrelevant because _save_review_apply is replaced
            # by the controlled failed-apply result below.
            del name
            return lambda *args, **kwargs: None

    monkeypatch.setattr(runner, "verify_versions", lambda frozen: None)
    monkeypatch.setattr(runner, "_load_steward", lambda: FakeSteward())
    monkeypatch.setattr(runner, "_save_review_apply", lambda *args: {
        "applied": False, "blocked": "apply_failed", "apply_code": 1,
    })
    monkeypatch.setattr(runner, "make_smoke_provider",
                        lambda round_index, call_log: lambda *args: "unused")

    result = runner.run_round(0, tmp_path / "artifacts", "smoke", None, {},
                              intake_only=True)
    assert result["card_type_counts"]["source-note"] == 0
    assert "missing_apply_manifest" in result["incomplete_reasons"]
    assert result["stages"]["initialization"]["applied"] is False
    assert result["outcome"] == "incomplete"
    assert "initialization:apply_failed" in result["incomplete_reasons"]
