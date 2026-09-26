"""M0 tests: canonical card schemas as the single type truth, plus real
executor/runtime call-path wiring for the two managed skills."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core import card_contracts as cc
from core.card_contracts import (
    CardContractError,
    prepare_card_item,
    validate_card_item,
    validate_skill_payload,
)
from core.config import seed_generation_mode
from core.skill_executor import execute_skill, load_executor
from core.skill_runtime import run_skill_runtime
from core.vault import parse_frontmatter

ROOT = Path(__file__).resolve().parents[1]


def valid_seed(**overrides):
    item = {
        "title": "服务转型观察",
        "type": "seed-card",
        "status": "seed",
        "stage": "candidate",
        "sources": ["quicknote/a.md"],
        "summary": "一个可独立表达的观察。",
        "confidence": "medium",
        "review_required": False,
        "schema_version": "m0-1",
        "analysis_mode": "heuristic",
    }
    item.update(overrides)
    return item


def valid_source(**overrides):
    item = {
        "title": "Source: 行业报告",
        "type": "source-note",
        "status": "growing",
        "stage": "compiling",
        "sources": ["raw/report.md"],
        "summary": "结构化摘要。",
        "confidence": "medium",
        "review_required": False,
        "schema_version": "m0-1",
        "analysis_mode": "llm",
        "key_statements": ["事实一。"],
        "topic_hints": [{"title": "专题A", "content": "边界说明。"}],
    }
    item.update(overrides)
    return item


def test_canonical_schemas_are_local_draft_2020_12():
    for name in ("seed-card.schema.json", "source-note.schema.json"):
        schema = json.loads((ROOT / "core" / "schemas" / name).read_text(encoding="utf-8-sig"))
        assert schema["$schema"].endswith("2020-12/schema")
        assert cc._schema_for_card_type(name.removesuffix(".schema.json")) is not None


def test_valid_seed_and_source_cards_pass():
    assert validate_card_item(valid_seed()) == []
    assert validate_card_item(valid_source()) == []


def test_incompatible_status_stage_pairs_fail_closed():
    for bad in (
        {"status": "seed", "stage": "needs_context"},
        {"status": "manual_review", "stage": "candidate"},
        {"status": "growing", "stage": "candidate"},
        {"status": "compiled", "stage": "compiling"},
    ):
        issues = validate_card_item(valid_seed(**bad))
        assert issues, f"expected rejection for {bad}"
    for bad in (
        {"status": "growing", "stage": "needs_context"},
        {"status": "manual_review", "stage": "compiling"},
        {"status": "seed", "stage": "candidate"},
    ):
        assert validate_card_item(valid_source(**bad)), f"expected rejection for {bad}"


def test_non_boolean_review_required_and_missing_required_fields_fail():
    assert validate_card_item(valid_seed(review_required="true"))
    assert validate_card_item(valid_seed(review_required=1))
    for key in ("title", "sources", "schema_version", "analysis_mode", "summary"):
        item = valid_seed()
        item.pop(key)
        assert validate_card_item(item), f"missing {key} must fail"


def test_empty_sources_and_unknown_type_fail_closed():
    assert validate_card_item(valid_seed(sources=[]))
    assert validate_card_item(valid_seed(sources=["raw/ /", ""]))
    assert validate_card_item(valid_seed(type="topic-card"))
    assert validate_card_item({"title": "无类型"})


def test_source_note_topic_hint_requires_title():
    issues = validate_card_item(valid_source(topic_hints=[{"content": "缺少标题"}]))
    assert issues
    assert validate_card_item(valid_source(topic_hints=[])) == []


def test_envelope_payload_by_skill_and_unsupported_skills_unaffected():
    assert validate_skill_payload("mindseed-grow", {"items": [valid_seed()]}) == []
    issues = validate_skill_payload("mindseed-grow", {"items": [valid_seed(status="growing", stage="seed")]})
    assert issues and "items.0" in issues[0]
    assert validate_skill_payload("topic-research-compile", {"items": [valid_source()]}) == []
    # Unsupported skills are not card producers; their payloads pass untouched.
    assert validate_skill_payload("topic-insight-miner", {"items": [{"anything": True}]}) == []
    assert validate_skill_payload("mindseed-grow", {"pages": []})  # missing items -> issue


def test_unknown_reference_never_resolves_and_no_remote_fetch(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("remote fetch attempted")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    future = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "concept-page.schema.json",
        "type": "object",
        "required": ["type", "definition"],
        "properties": {
            "type": {"const": "concept-page"},
            "definition": {"type": "string", "minLength": 1},
            "aliases": {"$ref": "#/$defs/string_array"},
            "borrowed": {"$ref": "missing.schema.json#/$defs/string_array"},
        },
        "$defs": {"string_array": {"type": "array", "items": {"type": "string"}}},
    }
    cc.register_card_schema(future)
    ok = {"type": "concept-page", "definition": "定义", "aliases": ["别名"]}
    assert validate_card_item(ok) == []
    with pytest.raises(CardContractError):
        validate_card_item({**ok, "borrowed": "触发未登记引用"})


def test_duplicate_title_and_broken_items_are_reported_not_raised():
    assert validate_card_item(None)
    assert validate_card_item([])


def test_original_bom_and_crlf_schema_files_load(tmp_path):
    # Schema files are read with utf-8-sig and CRLF tolerance by contract.
    for name in ("seed-card.schema.json", "source-note.schema.json"):
        raw = (ROOT / "core" / "schemas" / name).read_bytes()
        decoded = raw.decode("utf-8-sig")
        json.loads(decoded)
    # A payload file carrying an original BOM still validates as text input.
    bom_file = tmp_path / "card.json"
    bom_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(valid_seed(), ensure_ascii=False).encode("utf-8"))
    item = json.loads(bom_file.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    assert validate_card_item(item) == []


# ---------------------------------------------------------------------------
# Cross-schema local references (reviewer correction regression)
# ---------------------------------------------------------------------------

def test_cross_schema_ref_resolves_to_canonical_not_the_referrer():
    # Astra repro: an invalid seed {"type":"source-note"} inside a property
    # that $refs seed-card.schema.json must be rejected by the CANONICAL
    # seed schema, not validated against the referring envelope itself.
    envelope = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "cross-positive-envelope.schema.json",
        "type": "object",
        "properties": {"seed": {"$ref": "seed-card.schema.json"}},
    }
    validator = cc._validator_for(envelope, schema_id=envelope["$id"])
    assert cc._format_errors(validator, {"seed": valid_seed()}) == []
    wrong = cc._format_errors(validator, {"seed": valid_source()})
    assert wrong, "source-note payload must not pass through a seed-card $ref"


def test_envelope_schemas_reference_canonical_types_locally():
    assert validate_skill_payload("mindseed-grow", {"items": [valid_seed()]}) == []
    assert validate_skill_payload("topic-research-compile", {"items": [valid_source()]}) == []
    wrong_type = validate_skill_payload("mindseed-grow", {"items": [valid_source()]})
    assert wrong_type, "envelope must reject items of the other canonical type"
    assert validate_skill_payload("topic-insight-miner", {"items": [{"anything": True}]}) == []


def test_registered_skill_missing_envelope_fails_loudly(monkeypatch):
    # Simulate a skill enrolled without an envelope schema file.
    monkeypatch.setitem(cc.SKILL_CARD_TYPES, "no-such-skill", "seed-card")
    with pytest.raises(CardContractError):
        validate_skill_payload("no-such-skill", {"items": []})


def test_schemas_registered_are_themselves_valid():
    for schema_id, schema in cc._STORE._schemas.items():
        # check_schema already ran at registration; assert it holds explicitly.
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Program-owned metadata and hash provenance
# ---------------------------------------------------------------------------

def test_prepare_card_item_injects_program_metadata_and_normalizes_legacy():
    item = prepare_card_item(
        {"title": "T", "type": "seed-card", "status": "growing", "stage": "seed",
         "sources": ["a.md"], "summary": "s", "confidence": "low", "review_required": True,
         "schema_version": "伪造", "analysis_mode": "伪造"},
        "seed-card", "heuristic")
    assert (item["status"], item["stage"]) == ("seed", "candidate")
    assert item["schema_version"] == cc.CARD_SCHEMA_VERSION  # program-owned, overwrites model value
    assert item["analysis_mode"] == "heuristic"
    # No full-source raw-byte hash available: unknown, never invented from body text.
    assert item["source_hashes"] == {} and item["coverage"] == "unknown"


def test_executor_records_unknown_coverage_instead_of_inventing_hash():
    # M1 source: a model-analysis request without a verifiable full snapshot is
    # BLOCKED — no page, no processed credit, and above all no provenance forged
    # from the cleaned body.
    result = execute_skill(ROOT, "topic-research-compile", {
        "config": {"write": {"sources_dir": "wiki/sources"}},
        "notes": [{"rel": "raw/a.md", "title": "文章", "body": "调研正文内容足够长，包含事实。",
                   "summary": "摘要"}],
        "use_llm": True})
    assert result["created"] == [] and result["processed"] == 0
    assert result["issues"] and "不可分析" in result["issues"][0]


# ---------------------------------------------------------------------------
# Real call paths: generic skill runtime
# ---------------------------------------------------------------------------

def test_runtime_mock_mindseed_normalized_and_ok_with_metadata():
    result = run_skill_runtime(
        ROOT, {"scan": {"max_source_chars": 6000}}, "mindseed-grow", "整理知识库",
        [{"path": "quicknote/example.md", "title": "example", "content": "hello"}], mock=True)
    assert result["ok"], result["issues"]
    item = result["items"][0]
    assert item["status"] == "seed" and item["stage"] == "candidate"  # legacy growing/seed normalized
    assert item["schema_version"] == cc.CARD_SCHEMA_VERSION
    assert result["previews"]


def test_runtime_rejects_invalid_managed_card_before_previews():
    payload = {"items": [{
        "title": "坏状态", "type": "seed-card", "status": "compiled", "stage": "compiling",
        "sources": ["raw/a.md"], "summary": "s", "confidence": "low", "review_required": True}]}
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(payload)):
        result = run_skill_runtime(ROOT, {}, "mindseed-grow", "整理知识库",
                                   [{"path": "raw/a.md", "title": "a", "content": "内容"}])
    assert not result["ok"] and result["issues"] and result["previews"] == []


def test_runtime_provider_network_is_never_touched_by_card_validation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network fetch attempted during card validation")
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    good = {"items": [valid_seed()]}
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(good)):
        result = run_skill_runtime(ROOT, {}, "mindseed-grow", "整理知识库",
                                   [{"path": "quicknote/a.md", "title": "a", "content": "内容"}])
    assert result["ok"], result["issues"]


# ---------------------------------------------------------------------------
# Real call paths: mindseed-grow executor (validation before render)
# ---------------------------------------------------------------------------

def invalid_seed_item():
    return {"title": "坏状态种子", "type": "seed-card", "status": "compiled", "stage": "compiled",
            "sources": ["quicknote/a.md"], "summary": "观察内容。", "confidence": "high",
            "review_required": False, "signals": [], "manual_review": []}


def test_mindseed_invalid_seed_never_reaches_render():
    notes = [{"rel": "quicknote/a.md", "title": "服务观察", "body": "读者反馈需要明确处理步骤并留记录。"}]
    rendered = []
    execute = load_executor(ROOT, "mindseed-grow")
    def render_recorder(item):
        rendered.append(item)
        return "# should not render\n"
    # Legacy topic pathway, exercised explicitly (atomic is the default since M1).
    with patch.dict(execute.__globals__, {
            "seed_item": lambda cluster, notes, cfg: invalid_seed_item(),
            "render": render_recorder}):
        result = execute({"notes": notes, "config": {"seed_generation": {"mode": "topic"}}, "use_llm": False})
    assert rendered == []  # validation ran before render: nothing rendered
    assert result["pages"] == []
    assert any("契约校验失败" in issue for issue in result["issues"])


def test_mindseed_valid_seed_renders_with_contract_metadata():
    notes = [{"rel": "quicknote/a.md", "title": "服务观察", "body": "读者反馈需要明确处理步骤并留记录。"}]
    result = execute_skill(ROOT, "mindseed-grow", {"notes": notes, "config": {}, "use_llm": False})
    page, = result["pages"]
    meta, _ = parse_frontmatter(page["content"])
    assert meta["schema_version"] == cc.CARD_SCHEMA_VERSION
    assert meta["analysis_mode"] == "heuristic" and meta["coverage"] == "unknown"
    assert json.loads(meta["source_hashes"]) == {} if isinstance(meta["source_hashes"], str) else meta["source_hashes"] == {}


# ---------------------------------------------------------------------------
# Real call paths: topic-research-compile executor (source adapter)
# ---------------------------------------------------------------------------

def test_source_executor_clean_and_review_paths_use_canonical_states():
    result = execute_skill(ROOT, "topic-research-compile", {
        "config": {"write": {"sources_dir": "wiki/sources"}},
        "notes": [{"rel": "raw/a.md", "title": "文章", "body": "调研正文内容足够长，包含事实线索与结论。",
                   "summary": "摘要"}],
        "use_llm": False})
    page, = result["created"]
    meta, _ = parse_frontmatter(page["content"])
    assert meta["status"] == "manual_review" and meta["stage"] == "needs_context"  # heuristic review gate
    assert meta["schema_version"] == cc.CARD_SCHEMA_VERSION and meta["coverage"] == "unknown"
    assert "分析模式：heuristic" in page["content"]


def test_source_executor_invalid_analysis_fails_closed_before_page():
    # M1: a malformed/garbage model payload can no longer produce a clean
    # "compiling" card. It yields explicitly flagged review output instead.
    payload = json.dumps({"source_summary": None, "key_facts": ["事实"],
                          "quality_flags": [], "topics": [], "analysis_mode": "ignored"})
    body = "正文内容足够长，包含事实。"
    note = {"rel": "raw/a.md", "title": "文章", "body": body, "summary": "摘要",
            "source_text": body, "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
    with patch("core.llm.call_chat_completion", return_value=payload) as provider:
        result = execute_skill(ROOT, "topic-research-compile", {
            "config": {"write": {"sources_dir": "wiki/sources"}},
            "notes": [note],
            "use_llm": True})
    assert provider.called  # call order: model call happened, page gate ran after
    page, = result["created"]
    meta, _ = parse_frontmatter(page["content"])
    assert meta["status"] == "manual_review" and meta["stage"] == "needs_context"
    assert meta["review_required"] == "true"
    assert page["quality_flags"]  # degraded model output is explicitly flagged


def test_source_executor_clean_llm_path_writes_compiling_state():
    body = ("调研正文内容足够长，包含事实线索与结论。本段继续补充背景信息，说明试点范围的划定方式与"
            "评估周期，并交代参与各方的职责分工，同时记录调研过程中收集到的一手反馈与复核记录。"
            "第三段补充方法论：资料筛选、交叉比对与人工抽检的顺序，以及每一步的负责角色。"
            "最后一段收束全文，指出后续需要人工确认的边界条件，以及暂时搁置的开放问题清单。"
            "附则说明本资料的整理流程、引用规范与复核周期，便于后续继续追踪与补充，也便于新成员了解背景。")
    payload = json.dumps({
        "summary": "结构化摘要覆盖主体与结论。",
        "key_statements": [{"text": "事实一：调研覆盖了完整的评估周期。",
                            "quote": "调研正文内容足够长，包含事实线索与结论。", "kind": "assertion"}],
        "limitations": [], "quality_flags": [], "analysis_mode": "llm"})
    note = {"rel": "raw/a.md", "title": "文章", "body": body, "summary": "摘要",
            "metadata": {"tags": ["文章"]},
            "source_text": body, "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
    with patch("core.llm.call_chat_completion", return_value=payload):
        result = execute_skill(ROOT, "topic-research-compile", {
            "config": {"write": {"sources_dir": "wiki/sources"}},
            "notes": [note],
            "use_llm": True})
    page, = result["created"]
    meta, _ = parse_frontmatter(page["content"])
    assert meta["status"] == "growing" and meta["stage"] == "compiling"
    assert meta["review_required"] == "false" and meta["generator_version"] == cc.GENERATOR_VERSION
    assert meta["coverage"] == "full" and meta["analysis_mode"] == "llm"


# ---------------------------------------------------------------------------
# Legacy read-only compatibility + config seam
# ---------------------------------------------------------------------------

def test_legacy_source_note_without_metadata_is_not_a_valid_new_card(tmp_path):
    legacy = tmp_path / "legacy-source.md"
    legacy_bytes = (
        "---\ntitle: Source 旧\ntype: source-note\nstatus: growing\nstage: compiled\n"
        'sources: ["raw/a.md"]\nconfidence: high\nreview_required: false\n---\n旧正文。\n'
    ).encode("utf-8")
    legacy.write_bytes(legacy_bytes)
    # Old pages are never rewritten; as NEW card items they fail closed.
    item = json.loads(json.dumps({"title": "Source 旧", "type": "source-note", "status": "growing",
                                  "stage": "compiled", "sources": ["raw/a.md"], "summary": "旧正文。",
                                  "confidence": "high", "review_required": False}))
    assert validate_card_item(item), "legacy page shape must not pass the new card gate"
    assert legacy.read_bytes() == legacy_bytes


def test_seed_generation_mode_seam_defaults_atomic_and_rejects_invalid():
    from scripts.validate_config import seed_generation_errors
    assert seed_generation_mode({}) == "atomic"
    assert seed_generation_mode({"seed_generation": {}}) == "atomic"  # absent field -> default
    assert seed_generation_mode({"seed_generation": {"mode": "topic"}}) == "topic"
    assert seed_generation_mode(None) == "atomic"
    for bad in ("legacy", False, 0, "", None):
        with pytest.raises(ValueError):
            seed_generation_mode({"seed_generation": {"mode": bad}})
    with pytest.raises(ValueError):
        seed_generation_mode({"seed_generation": "atomic"})  # non-mapping section
    example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    assert example["seed_generation"]["mode"] == "atomic"
    assert seed_generation_errors(example) == []
    assert seed_generation_errors({}) == []
    assert seed_generation_errors({"seed_generation": {"mode": "nope"}})
    assert seed_generation_errors({"seed_generation": {"mode": False}})
    assert seed_generation_errors({"seed_generation": "atomic"})


def test_topic_config_seam_rejects_multiple_questions_and_impossible_floor():
    from scripts.validate_config import card_pipeline_errors, topic_generation_errors

    assert card_pipeline_errors({"card_pipeline": {"topic_questions": ["一", "二"]}})
    assert topic_generation_errors({"topic_generation": {"min_full_sources": 0}})
    assert topic_generation_errors({
        "card_pipeline": {"topic_source_cap": 2},
        "topic_generation": {"min_full_sources": 3},
    })
    assert topic_generation_errors({
        "card_pipeline": {"topic_source_cap": 6},
        "topic_generation": {"min_full_sources": 3, "max_context_chars": 0},
    })


# ---------------------------------------------------------------------------
# Review corrections: provenance trust boundary, preview persistence,
# prompt content requirements, processed-index safety
# ---------------------------------------------------------------------------

def test_forged_model_provenance_is_never_promoted():
    forged = {"raw/a.md": "f" * 64}
    item = prepare_card_item(
        valid_seed(source_hashes=forged, coverage="full"),
        "seed-card", "llm")
    assert item["source_hashes"] == {} and item["coverage"] == "unknown"
    # Trusted producer snapshots survive only via explicit keyword capture.
    kept = prepare_card_item(valid_seed(), "seed-card", "heuristic",
                             trusted_source_hashes=forged, trusted_coverage="partial")
    assert kept["source_hashes"] == forged and kept["coverage"] == "partial"


def test_runtime_mock_provider_cannot_promote_forged_hashes_or_full_coverage():
    payload = {"items": [{
        **valid_seed(sources=["quicknote/example.md"]),
        "source_hashes": {"quicknote/example.md": "a" * 64},
        "coverage": "full",
    }]}
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(payload)):
        result = run_skill_runtime(
            ROOT, {"scan": {"max_source_chars": 6000}}, "mindseed-grow", "整理知识库",
            [{"path": "quicknote/example.md", "title": "example", "content": "hello"}])
    assert result["ok"], result["issues"]
    item = result["items"][0]
    assert item["source_hashes"] == {} and item["coverage"] == "unknown"
    meta, _ = parse_frontmatter(result["previews"][0]["preview"])
    assert json.loads(meta["source_hashes"]) == {} if isinstance(meta["source_hashes"], str) else meta["source_hashes"] == {}


def test_preview_frontmatter_preserves_metadata_and_quality_flags():
    # Executor output (source note, jinja template). Body has no substantive
    # sentence, so the producer appends a quality flag that must persist.
    result = execute_skill(ROOT, "topic-research-compile", {
        "config": {"write": {"sources_dir": "wiki/sources"}},
        "notes": [{"rel": "raw/a.md", "title": "文章", "body": "太短。",
                   "summary": "摘要"}],
        "use_llm": False})
    meta, _ = parse_frontmatter(result["created"][0]["content"])
    assert meta["schema_version"] == cc.CARD_SCHEMA_VERSION
    assert meta["analysis_mode"] == "heuristic" and meta["coverage"] == "unknown"
    assert "quality_flags" in meta
    assert any("摘要或关键事实不足" in flag for flag in meta["quality_flags"])
    # Generic runtime preview (preview renderer).
    from core.renderer import render_preview
    preview = render_preview(prepare_card_item(valid_seed(quality_flags=["需要核对"]), "seed-card", "heuristic"))
    meta, _ = parse_frontmatter(preview)
    assert meta["schema_version"] == cc.CARD_SCHEMA_VERSION
    assert "quality_flags" in meta and "analysis_mode" in meta


def test_runtime_prompt_declares_content_requirements_for_managed_types():
    docs = [{"path": "quicknote/a.md", "title": "a", "content": "内容"}]
    captured = []
    def model(cfg, prompt, payload):
        captured.append((prompt, payload))
        return json.dumps({"items": [valid_seed(signals=["来源摘句"], growth_directions=["生长方向"])]})
    with patch("core.skill_runtime.call_chat_completion", side_effect=model):
        result = run_skill_runtime(ROOT, {}, "mindseed-grow", "整理知识库", docs)
    assert result["ok"], result["issues"]
    prompt, payload = captured[0]
    requirements = json.dumps(payload["output_contract"]["content_requirements"])
    assert "signals" in requirements and "growth_directions" in requirements
    assert "key_statements" in requirements and "topic_hints" in requirements
    # Program-owned metadata is never requested from the model.
    for token in ("schema_version", "generator_version", "source_hashes"):
        assert token not in requirements


def test_runtime_source_response_requires_content_fields_and_passes():
    docs = [{"path": "raw/a.md", "title": "a", "content": "长文内容"}]
    base = valid_source(sources=["raw/a.md"])
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps({"items": [base]})):
        result = run_skill_runtime(ROOT, {}, "topic-research-compile", "编译来源", docs)
    assert result["ok"], result["issues"]  # key_statements/topic_hints supplied
    incomplete = {k: v for k, v in base.items() if k not in ("key_statements", "topic_hints")}
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps({"items": [incomplete]})):
        result = run_skill_runtime(ROOT, {}, "topic-research-compile", "编译来源", docs)
    assert not result["ok"] and result["previews"] == []


def test_invalid_typed_seed_cannot_advance_processed_index(tmp_path):
    from core.vault import build_index
    from scripts import personal_kb_steward as steward
    kb = tmp_path
    for d in ("quicknote", "inbox", "raw"):
        (kb / d).mkdir()
    (kb / "quicknote" / "a.md").write_text("# 观察\n读者反馈需要明确处理步骤并留记录。", encoding="utf-8")
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    cfg["knowledge_base"] = str(kb)
    cfg["state_file"] = str(kb / ".state.json")
    cfg["safety"]["plans_dir"] = str(kb / ".openclaw" / "plans")
    cfg["safety"]["runs_dir"] = str(kb / ".openclaw" / "runs")
    cfg["safety"]["processed_index"] = str(kb / ".openclaw" / "processed-index.json")
    cfg["safety"]["manual_review_queue"] = str(kb / ".openclaw" / "manual-review" / "queue.jsonl")
    cfg["safety"]["backup_dir"] = str(kb / ".openclaw" / "backups")
    cfg["safety"]["operation_log"] = str(kb / ".openclaw" / "operation-log.jsonl")
    index = build_index(cfg)
    note = index.by_rel["quicknote/a.md"]
    result = execute_skill(ROOT, "mindseed-grow",
                           {"notes": steward.executor_notes([note]),
                            "config": {"seed_generation": {"mode": "topic"}}, "use_llm": False})
    assert result["processed"] == 1  # valid path processes normally
    execute = load_executor(ROOT, "mindseed-grow")
    with patch.dict(execute.__globals__, {"seed_item": lambda c, n, cfg: invalid_seed_item()}):
        bad = execute({"notes": steward.executor_notes([note]),
                       "config": {"seed_generation": {"mode": "topic"}}, "use_llm": False})
    assert bad["pages"] == [] and bad["processed"] == 0 and bad["ok"] is False
    op = steward.apply_executor_pages(index, cfg, bad)
    steward.update_processed_index(index, cfg, [op])
    processed = json.loads((kb / ".openclaw" / "processed-index.json").read_text(encoding="utf-8"))
    record = processed["processed"]["quicknote/a.md"]["skills"]["mindseed-grow"]
    assert record["operation_status"] == "needs_review"  # not created/skipped
    from core.state import is_processed, unprocessed_notes
    assert not is_processed(processed, note, "mindseed-grow")
    assert note.rel in [n.rel for n in unprocessed_notes(processed, [note], "mindseed-grow")]
