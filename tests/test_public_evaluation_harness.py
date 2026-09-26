"""Offline tests for the bounded public Claude provider adapter (T10 checkpoint A).

All tests patch subprocess; no real CLI or network is ever used. Provenance
accounting runs against the real tests/fixtures/card-baseline manifest,
which is public synthetic content. Payload shapes mirror the REAL accepted
generator contracts (source chunk dict, seed units list, concept/case/topic
documents payload) reconstructed from the public code, never private input.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.public_evaluation import (
    ABSOLUTE_MAX_ROUND_CALLS,
    ABSOLUTE_MAX_TOTAL_CALLS,
    AdapterConfig,
    PublicClaudeAdapter,
    PublicContextBundle,
    PublicEvaluationError,
    PublicPayload,
    RunRecorder,
    default_executable,
    fixture_annotation,
    load_fixture_manifest,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "tests" / "fixtures" / "card-baseline" / "manifest.json"
GOOD_SYSTEM_PROMPT = "你是卡片生成器。只输出 JSON。"


def make_envelope(result, is_error: bool = False, usage: dict | None = None) -> bytes:
    envelope = {"is_error": is_error, "result": result}
    if usage is not None:
        envelope["usage"] = usage
    return json.dumps(envelope).encode("utf-8")


class FakeCompleted:
    def __init__(self, stdout: bytes, returncode: int = 0, stderr: bytes = b""):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def make_recorder(tmp_path: Path, run_id: str = "run-test") -> RunRecorder:
    return RunRecorder(tmp_path / "artifacts", run_id)


def make_adapter(tmp_path: Path, run_subprocess, **cfg_overrides) -> PublicClaudeAdapter:
    cfg = {"public_evaluation": {"enabled": True, **cfg_overrides}}
    return PublicClaudeAdapter(cfg, make_recorder(tmp_path), run_subprocess=run_subprocess)


# ---------------------------------------------------------------------------
# Real generator payload shapes (public shapes from the accepted generators)
# ---------------------------------------------------------------------------


def fixture_text(fixture_id: str) -> str:
    return load_fixture_manifest(MANIFEST)[fixture_id].text


def make_bundle() -> PublicContextBundle:
    bundle = PublicContextBundle(MANIFEST)
    bundle.register_fixture("src_dialogue", "dialogue_user_ai_01")
    bundle.register_fixture("src_report", "research_summary_uncited_01")
    bundle.register_fixture("src_case", "project_case_01")
    bundle.register_fixture("src_followup", "project_case_01_followup")
    bundle.register_fixture("src_counter", "project_case_01_counterexample")
    return bundle


def source_chunk_payload() -> dict:
    """Source stage: chunk dict {text: header+chunk} (topic-research-compile)."""
    header = ("Title: 合成对话\n[片段 1，字符偏移 0-100，全文 100 字符]\n\n")
    return {"text": header + fixture_text("dialogue_user_ai_01")}


def seed_units_payload() -> dict:
    """Seed stage: atomic_seed units list payload (core.atomic_seed)."""
    return {"task": "atomic_seed", "coverage_note": "", "units": [
        {"id": 0, "source": "tests/fixtures/card-baseline/dialogue_user_ai_01.md",
         "quote": "我收藏了很多文章，但从不删东西。", "kind": "assertion",
         "speaker": "林舟（用户）", "body_line": 3},
    ]}


def concept_documents_payload() -> dict:
    """Concept stage: documents payload (core.concept_generation)."""
    return {
        "task": "concept_extraction",
        "documents": [
            {"path": "dialogue_user_ai_01.md", "title": "合成对话",
             "text": fixture_text("dialogue_user_ai_01")},
            {"path": "research_summary_uncited_01.md", "title": "未核实研究综述",
             "text": fixture_text("research_summary_uncited_01")},
        ],
        "known_paths": [],
        "upstream": [],
        "output_contract": {"concept_found": "boolean"},
    }


def case_documents_payload() -> dict:
    """Case stage: documents payload (core.case_generation)."""
    return {
        "task": "case_extraction",
        "documents": [
            {"path": "project_case_01.md", "title": "青梧书店案例",
             "text": fixture_text("project_case_01")},
            {"path": "project_case_01_followup.md", "title": "回访观察",
             "text": fixture_text("project_case_01_followup")},
            {"path": "project_case_01_counterexample.md", "title": "反例",
             "text": fixture_text("project_case_01_counterexample")},
        ],
        "known_paths": [],
        "upstream": [],
        "output_contract": {"case_found": "boolean"},
    }


def topic_documents_payload() -> dict:
    """Topic stage: question-led documents payload (core.topic_generation)."""
    return {
        "task": "question_led_topic_synthesis",
        "question": "三段转化链在什么条件下有效、在什么条件下失效？",
        "documents": [
            {"path": "project_case_01.md", "title": "青梧书店案例",
             "text": fixture_text("project_case_01")},
        ],
        "known_paths": [],
        "output_contract": {"topic_viable": "boolean"},
    }


def register_payload_for_shape(bundle: PublicContextBundle, payload) -> PublicPayload:
    built_from = {
        dict: ["src_dialogue"],
    }.get(type(payload), [])
    # provenance accounting: name the fixture documents actually used
    if payload.get("task") in ("case_extraction", "question_led_topic_synthesis") \
            if isinstance(payload, dict) else False:
        built_from = ["src_case", "src_followup", "src_counter"]
    if isinstance(payload, dict) and payload.get("task") == "concept_extraction":
        built_from = ["src_dialogue", "src_report"]
    return bundle.register_payload(payload, built_from=built_from or ["src_dialogue"])


# ---------------------------------------------------------------------------
# Real invocation: -p print mode, --restricted, tools disabled, no resume
# ---------------------------------------------------------------------------


def test_argv_print_mode_restricted_and_isolation_flags(tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    adapter.bind_for_round(1)(  # explicit round, both shapes accepted
        {"llm": {"model": "should-be-ignored"}}, GOOD_SYSTEM_PROMPT, payload
    )

    argv = seen["argv"]
    assert argv[0].lower().replace("/", "\\") == default_executable()[0].lower().replace("/", "\\")
    assert "-p" in argv  # print mode: unattended, never interactive
    assert "--restricted" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert "--disable-slash-commands" in argv
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--system-prompt") + 1] == GOOD_SYSTEM_PROMPT
    assert argv[argv.index("--model") + 1] == "claude-opus-5[1m]"
    assert argv[argv.index("--effort") + 1] == "medium"
    assert "--setting-sources" not in argv  # redundant under --restricted
    assert "--bare" not in argv  # OAuth path preserved

    kwargs = seen["kwargs"]
    assert kwargs["shell"] is False
    payload_text = kwargs["input"].decode("utf-8")
    assert payload_text not in " ".join(argv)  # content never in argv
    # model cwd is a fresh temp dir outside the checkout
    cwd = Path(kwargs["cwd"]).resolve()
    assert cwd != REPO_ROOT and REPO_ROOT not in cwd.parents


def test_bind_for_round_accepts_two_arg_generator_shape(tmp_path):
    def fake_run(argv, **kwargs):
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, source_chunk_payload())
    bound = adapter.bind_for_round(2)
    assert bound(GOOD_SYSTEM_PROMPT, payload) == "ok"
    record = json.loads(
        adapter.recorder.evidence_path.read_text(encoding="utf-8").splitlines()[0]
    )
    assert record["round"] == 2  # explicit, not implicit round 0


def test_wrong_arity_refused(tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError("must not launch")

    adapter = make_adapter(tmp_path, boom)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    with pytest.raises(PublicEvaluationError, match="accepts"):
        adapter.bind_for_round(0)(payload)


def test_live_disabled_by_default(tmp_path):
    def boom(*args, **kwargs):  # must never be reached
        raise AssertionError("subprocess must not run when live is disabled")

    cfg = {"public_evaluation": {}}  # enabled absent
    adapter = PublicClaudeAdapter(cfg, make_recorder(tmp_path), run_subprocess=boom)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    with pytest.raises(PublicEvaluationError, match="live mode is not enabled"):
        adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)


def test_live_requires_explicit_bool_not_truthy_string(tmp_path):
    with pytest.raises(PublicEvaluationError, match="boolean"):
        AdapterConfig.from_cfg({"public_evaluation": {"enabled": "false"}})
    with pytest.raises(PublicEvaluationError, match="boolean"):
        AdapterConfig.from_cfg({"public_evaluation": {"enabled": "true"}})
    with pytest.raises(PublicEvaluationError, match="boolean"):
        AdapterConfig.from_cfg({"public_evaluation": {"enabled": 1}})


def test_malformed_config_rejected_strict_types(tmp_path):
    with pytest.raises(PublicEvaluationError, match="positive integer"):
        AdapterConfig.from_cfg({"public_evaluation": {"max_total_calls": "30"}})
    with pytest.raises(PublicEvaluationError, match="positive integer"):
        AdapterConfig.from_cfg({"public_evaluation": {"max_round_calls": 0}})
    with pytest.raises(PublicEvaluationError, match="positive integer"):
        AdapterConfig.from_cfg({"public_evaluation": {"timeout_seconds": -5}})
    with pytest.raises(PublicEvaluationError, match="positive integer"):
        AdapterConfig.from_cfg({"public_evaluation": {"timeout_seconds": True}})
    with pytest.raises(PublicEvaluationError, match="non-empty string"):
        AdapterConfig.from_cfg({"public_evaluation": {"model": ""}})
    with pytest.raises(PublicEvaluationError, match="argv list"):
        AdapterConfig.from_cfg(
            {"public_evaluation": {"executable": "claude.exe -p"}}  # shell string
        )


def test_refuses_arbitrary_string_payload(tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError("must not launch")

    adapter = make_adapter(tmp_path, boom)
    with pytest.raises(PublicEvaluationError, match="PublicPayload"):
        adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, "raw text")


def test_generator_cfg_values_are_ignored(tmp_path):
    """A production cfg must never override adapter settings."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    hostile_cfg = {"public_evaluation": {
        "enabled": False, "model": "evil-model", "effort": "high",
        "max_total_calls": 999, "timeout_seconds": 1,
    }}
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    adapter.bind_for_round(0)(hostile_cfg, GOOD_SYSTEM_PROMPT, payload)
    argv = seen["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5[1m]"  # frozen config wins
    assert argv[argv.index("--effort") + 1] == "medium"
    assert adapter.config.max_total_calls == 30


# ---------------------------------------------------------------------------
# Budget accounting (at/beyond boundaries, failures count)
# ---------------------------------------------------------------------------


def test_budget_counts_failed_attempts_and_refuses_before_excess(tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return FakeCompleted(b"", returncode=1, stderr=b"boom")  # every attempt fails

    adapter = make_adapter(tmp_path, fake_run, max_total_calls=3, max_round_calls=3)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    bound = adapter.bind_for_round(1)
    for _ in range(3):
        with pytest.raises(PublicEvaluationError):
            bound(GOOD_SYSTEM_PROMPT, payload)
    assert len(calls) == 3  # three failed attempts all consumed budget
    with pytest.raises(PublicEvaluationError, match="refused before launch"):
        bound(GOOD_SYSTEM_PROMPT, payload)
    assert len(calls) == 3  # the 4th was refused BEFORE launching


def test_round_budget_refuses_before_excess(tmp_path):
    def fake_run(argv, **kwargs):
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run, max_total_calls=30, max_round_calls=2)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    bound1 = adapter.bind_for_round(1)
    bound1(GOOD_SYSTEM_PROMPT, payload)
    bound1(GOOD_SYSTEM_PROMPT, payload)
    with pytest.raises(PublicEvaluationError, match="round 1 budget exhausted"):
        bound1(GOOD_SYSTEM_PROMPT, payload)
    adapter.bind_for_round(2)(GOOD_SYSTEM_PROMPT, payload)  # other rounds unaffected


def test_config_bounds_cannot_exceed_hard_limits(tmp_path):
    with pytest.raises(PublicEvaluationError, match="hard bound"):
        AdapterConfig.from_cfg({"public_evaluation": {"max_total_calls": 31}})
    with pytest.raises(PublicEvaluationError, match="hard bound"):
        AdapterConfig.from_cfg({"public_evaluation": {"max_round_calls": 11}})
    assert ABSOLUTE_MAX_TOTAL_CALLS == 30
    assert ABSOLUTE_MAX_ROUND_CALLS == 10


def test_timeout_consumes_budget(tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.TimeoutExpired(cmd=argv, timeout=1, output=b"partial", stderr=b"")

    adapter = make_adapter(
        tmp_path, fake_run, max_total_calls=2, max_round_calls=2, timeout_seconds=1
    )
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    bound = adapter.bind_for_round(1)
    for _ in range(2):
        with pytest.raises(PublicEvaluationError, match="timeout"):
            bound(GOOD_SYSTEM_PROMPT, payload)
    assert len(calls) == 2
    with pytest.raises(PublicEvaluationError, match="refused before launch"):
        bound(GOOD_SYSTEM_PROMPT, payload)
    assert len(calls) == 2


def test_nonzero_and_is_error_count_against_budget(tmp_path):
    responses = [
        FakeCompleted(make_envelope("x", is_error=True)),
        FakeCompleted(b"not json", returncode=7),
    ]

    def fake_run(argv, **kwargs):
        return responses.pop(0)

    adapter = make_adapter(tmp_path, fake_run, max_total_calls=2, max_round_calls=2)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    bound = adapter.bind_for_round(1)
    with pytest.raises(PublicEvaluationError, match="is_error"):
        bound(GOOD_SYSTEM_PROMPT, payload)
    with pytest.raises(PublicEvaluationError, match="not a JSON envelope"):
        bound(GOOD_SYSTEM_PROMPT, payload)
    with pytest.raises(PublicEvaluationError, match="refused before launch"):
        bound(GOOD_SYSTEM_PROMPT, payload)  # budget exhausted by the 2 failures


# ---------------------------------------------------------------------------
# Error surfacing: is_error / nonzero / missing result / non-string result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "completed,match",
    [
        (FakeCompleted(make_envelope("x", is_error=True), returncode=0), "is_error"),
        (FakeCompleted(b'{"is_error": false, "other": 1}', returncode=0), "no result field"),
        (FakeCompleted(b"not json", returncode=0), "not a JSON envelope"),
        (FakeCompleted(make_envelope(None), returncode=0), "not a string"),
        (FakeCompleted(make_envelope({"nested": 1}), returncode=0), "not a string"),
        (FakeCompleted(make_envelope(["a"]), returncode=0), "not a string"),
        (FakeCompleted(make_envelope(42), returncode=0), "not a string"),
        (FakeCompleted(make_envelope("x"), returncode=3), "nonzero exit code"),
    ],
)
def test_failures_become_explicit_adapter_errors(tmp_path, completed, match):
    def fake_run(argv, **kwargs):
        return completed

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    with pytest.raises(PublicEvaluationError, match=match):
        adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)


def test_nonstring_result_rejected_with_raw_evidence_preserved(tmp_path):
    stdout = make_envelope(None)

    def fake_run(argv, **kwargs):
        return FakeCompleted(stdout)

    recorder = make_recorder(tmp_path)
    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True}}, recorder, run_subprocess=fake_run
    )
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    with pytest.raises(PublicEvaluationError, match="not a string"):
        adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)
    attempt_dir = recorder.run_dir / "attempts" / "round00" / "attempt001"
    assert (attempt_dir / "stdout.raw.txt").read_text(encoding="utf-8") == stdout.decode("utf-8")
    record = json.loads(recorder.evidence_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["result_text"] is None and record["failure"]
    assert record["result_sha256"] is None


def test_exact_result_string_returned_and_json_preserved_verbatim(tmp_path):
    # Malformed JSON *inside* the result must be passed through untouched —
    # the generator owns interpretation; the adapter never repairs.
    raw = '{"answer": broken,,,}'

    def fake_run(argv, **kwargs):
        return FakeCompleted(make_envelope(raw, usage={"input_tokens": 10, "output_tokens": 5}))

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    assert adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload) == raw


def test_failure_evidence_recorded(tmp_path):
    def fake_run(argv, **kwargs):
        return FakeCompleted(b"", returncode=1, stderr=b"boom")

    recorder = make_recorder(tmp_path)
    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True}}, recorder, run_subprocess=fake_run
    )
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    with pytest.raises(PublicEvaluationError):
        adapter.bind_for_round(3)(GOOD_SYSTEM_PROMPT, payload)
    lines = recorder.evidence_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["failure"] and record["return_code"] == 1
    assert record["result_text"] is None
    assert record["round"] == 3
    assert (recorder.run_dir / "attempts" / "round03" / "attempt001" / "stderr.raw.txt").read_text(
        encoding="utf-8"
    ) == "boom"
    assert record["system_prompt_sha256"] == sha256_text(GOOD_SYSTEM_PROMPT)
    assert record["user_payload_sha256"] == sha256_text(payload.to_json())


def test_successful_evidence_fields(tmp_path):
    def fake_run(argv, **kwargs):
        return FakeCompleted(make_envelope('{"ok": true}', usage={"total_cost_usd": 0.0}))

    recorder = make_recorder(tmp_path)
    adapter = PublicClaudeAdapter(
        {"public_evaluation": {"enabled": True}}, recorder, run_subprocess=fake_run
    )
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, case_documents_payload())
    out = adapter.bind_for_round(2)(GOOD_SYSTEM_PROMPT, payload)
    assert out == '{"ok": true}'
    record = json.loads(recorder.evidence_path.read_text(encoding="utf-8").splitlines()[0])
    for key in ("run", "round", "index", "model", "effort", "system_prompt_sha256",
                "source_hashes", "duration_seconds", "usage", "return_code",
                "timeout", "result_sha256", "failure"):
        assert key in record
    assert record["round"] == 2
    assert record["source_hashes"] == payload.provenance
    assert record["failure"] is None


# ---------------------------------------------------------------------------
# Run directory safety
# ---------------------------------------------------------------------------


def test_refuses_overwrite_of_existing_run(tmp_path):
    make_recorder(tmp_path, "run-x")
    with pytest.raises(PublicEvaluationError, match="refusing to overwrite"):
        make_recorder(tmp_path, "run-x")


def test_outputs_bounded_to_artifact_root(tmp_path):
    recorder = make_recorder(tmp_path)
    with pytest.raises(PublicEvaluationError, match="escapes artifact root"):
        recorder._write("../../outside.txt", "nope")


def test_attempt_files_never_overwritten(tmp_path):
    recorder = make_recorder(tmp_path)
    recorder._write("attempts/round00/attempt001/stdout.raw.txt", "first")
    with pytest.raises(PublicEvaluationError, match="refusing to overwrite"):
        recorder._write("attempts/round00/attempt001/stdout.raw.txt", "second")


# ---------------------------------------------------------------------------
# Fixture allowlist provenance
# ---------------------------------------------------------------------------


def test_manifest_loads_with_hashes_and_strips_annotations():
    snaps = load_fixture_manifest(MANIFEST)
    assert "project_case_01" in snaps
    assert all(s.sha256 for s in snaps.values())
    assert "expected_units" not in vars(snaps["project_case_01"])


def test_nonmanifest_or_escaping_manifest_rejected(tmp_path):
    forged = tmp_path / "manifest.json"
    forged.write_text(json.dumps({"fixtures": []}), encoding="utf-8")
    with pytest.raises(PublicEvaluationError, match="must live under"):
        load_fixture_manifest(forged)


def write_forged_manifest(tmp_path, mutate, monkeypatch):
    """Forge a manifest in a temp allowlist dir and point the module at it."""
    import core.public_evaluation as pe

    forged_dir = tmp_path / "card-baseline"
    forged_dir.mkdir(exist_ok=True)
    src = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutate(src)
    (forged_dir / "manifest.json").write_text(json.dumps(src), encoding="utf-8")
    monkeypatch.setattr(pe, "FIXTURE_DIR", forged_dir)
    return forged_dir / "manifest.json"


def test_nonsynthetic_entry_rejected(tmp_path, monkeypatch):
    path = write_forged_manifest(
        tmp_path, lambda s: s["fixtures"][0].__setitem__("synthetic", False), monkeypatch
    )
    with pytest.raises(PublicEvaluationError, match="synthetic"):
        load_fixture_manifest(path)


def test_missing_or_escaping_fixture_file_rejected(tmp_path, monkeypatch):
    path = write_forged_manifest(
        tmp_path, lambda s: s["fixtures"][0].__setitem__("path", "../../../core/llm.py"),
        monkeypatch,
    )
    with pytest.raises(PublicEvaluationError, match="escapes allowlist"):
        load_fixture_manifest(path)

    path = write_forged_manifest(
        tmp_path, lambda s: s["fixtures"][0].__setitem__("path", "does_not_exist.md"),
        monkeypatch,
    )
    with pytest.raises(PublicEvaluationError, match="missing"):
        load_fixture_manifest(path)


def test_bundle_refuses_unregistered_provenance_document():
    bundle = PublicContextBundle(MANIFEST)
    with pytest.raises(PublicEvaluationError, match="not registered"):
        bundle.register_payload({"text": "x"}, built_from=["ghost"])


def test_bundle_refuses_unknown_fixture(tmp_path):
    bundle = PublicContextBundle(MANIFEST)
    with pytest.raises(PublicEvaluationError, match="not in manifest"):
        bundle.register_fixture("x", "not_a_fixture")


def test_generated_registration_requires_exact_hash(tmp_path):
    bundle = PublicContextBundle(MANIFEST)
    with pytest.raises(PublicEvaluationError, match="hash mismatch"):
        bundle.register_generated("gen1", "seed_intermediate", "文本", "0" * 64)
    doc = bundle.register_generated(
        "gen1", "seed_intermediate", "公开生成的中间态", sha256_text("公开生成的中间态")
    )
    assert doc.provenance == "public_generated"
    payload = bundle.register_payload({"task": "atomic_seed", "units": []},
                                      built_from=["gen1"])
    assert payload.provenance == {"gen1": sha256_text("公开生成的中间态")}


def test_refuses_non_generator_payload_types():
    bundle = PublicContextBundle(MANIFEST)
    for bad in (42, 3.5, object(), None):
        with pytest.raises(PublicEvaluationError, match="exact generator argument"):
            bundle.register_payload(bad, built_from=[])


# ---------------------------------------------------------------------------
# Annotation protection at any nesting depth
# ---------------------------------------------------------------------------


def test_annotation_keys_blocked_at_any_depth():
    bundle = PublicContextBundle(MANIFEST)
    bundle.register_fixture("src", "dialogue_user_ai_01")
    nested = {
        "task": "atomic_seed",
        "wrapper": {"deep": [{"expected_units": ["leak"]}]},
    }
    with pytest.raises(PublicEvaluationError, match="expected_units"):
        bundle.register_payload(nested, built_from=["src"])
    with pytest.raises(PublicEvaluationError, match="prohibited_overclaims"):
        bundle.register_payload({"a": [{"b": {"prohibited_overclaims": 1}}]},
                                built_from=["src"])
    with pytest.raises(PublicEvaluationError, match="expected_speaker_markers"):
        bundle.register_payload([{"x": [{"expected_speaker_markers": []}]}],
                                built_from=["src"])


def test_annotation_values_not_key_checked_allow_legit_fixture_content():
    """Values overlapping annotation strings are legitimate model content.

    The real seed payload's speaker is literally a manifest
    expected_speaker_marker; only annotation KEYS are refused.
    """
    bundle = PublicContextBundle(MANIFEST)
    bundle.register_fixture("src", "dialogue_user_ai_01")
    payload = bundle.register_payload(
        {"task": "atomic_seed", "units": [
            {"id": 0, "source": "s", "quote": "q", "kind": "assertion",
             "speaker": "林舟（用户）", "body_line": 3},
        ]},
        built_from=["src"],
    )
    assert "林舟（用户）" in payload.to_json()


# ---------------------------------------------------------------------------
# Exact generator payload preservation (deep JSON equality, no wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload_fn", [
    source_chunk_payload, seed_units_payload, concept_documents_payload,
    case_documents_payload, topic_documents_payload,
])
def test_deep_json_equality_with_generator_argument(tmp_path, payload_fn):
    payload_obj = payload_fn()
    bundle = make_bundle()
    registered = register_payload_for_shape(bundle, payload_obj)
    assert isinstance(registered, PublicPayload)
    # canonicalized key order, deep-equal value, no wrapper added
    canonical = json.loads(registered.to_json())
    assert canonical == payload_obj
    assert set(canonical.keys()) == set(payload_obj.keys())
    # arrays preserve element order (part of the value)
    if isinstance(payload_obj, dict) and "documents" in payload_obj:
        assert [d["path"] for d in canonical["documents"]] == \
               [d["path"] for d in payload_obj["documents"]]


def test_stdin_payload_is_exact_generator_json(tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["input"] = kwargs["input"]
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    payload_obj = topic_documents_payload()
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, payload_obj)
    adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)
    sent = json.loads(seen["input"].decode("utf-8"))
    assert sent == payload_obj  # deep equality with the generator argument
    assert "documents" in sent and sent["task"] == "question_led_topic_synthesis"


def test_no_annotation_content_in_stdin_for_all_real_shapes(tmp_path):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["input"] = kwargs["input"]
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    for shape in (source_chunk_payload, seed_units_payload,
                  concept_documents_payload, case_documents_payload,
                  topic_documents_payload):
        payload = register_payload_for_shape(bundle, shape())
        adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)
        text = seen["input"].decode("utf-8")
        for fix_id in ("dialogue_user_ai_01", "research_summary_uncited_01",
                       "project_case_01", "project_case_01_followup",
                       "project_case_01_counterexample"):
            for note in fixture_annotation(fix_id, MANIFEST)["prohibited_overclaims"]:
                assert note not in text
        assert "林舟（用户）" in text or "青梧书店" in text  # real fixture content IS present


# ---------------------------------------------------------------------------
# No private/root path reads
# ---------------------------------------------------------------------------


def test_adapter_never_touches_private_paths(tmp_path, monkeypatch):
    """Instrument open() to catch any read of private config files."""
    opened: list[str] = []

    real_open = open

    def guarded_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", guarded_open)

    def fake_run(argv, **kwargs):
        return FakeCompleted(make_envelope("ok"))

    adapter = make_adapter(tmp_path, fake_run)
    bundle = make_bundle()
    payload = register_payload_for_shape(bundle, seed_units_payload())
    adapter.bind_for_round(0)(GOOD_SYSTEM_PROMPT, payload)

    for name in opened:
        for marker in (".env", "config.json"):
            assert marker not in name.lower(), f"adapter opened {name}"
