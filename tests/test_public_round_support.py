"""T10 checkpoint B (rev 2) tests — offline round fixtures, ACTUAL generators.

All provider responses are the deterministic offline mock from
tests/public_round_support.py; no live model or network is touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import public_round_support as support  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_round(tmp_path: Path):
    return support.run_public_round(output_dir=tmp_path / "offline-round-v2")


def _plain(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Call schedule: actual provider count = 8, chunk bounds proven
# ---------------------------------------------------------------------------


def test_round_makes_exactly_the_expected_8_provider_calls(tmp_path):
    run = run_round(tmp_path)
    log = run["log"]
    assert len(log.calls) == 8
    assert [c["stage"] for c in log.calls] == support.EXPECTED_CALL_SCHEDULE
    assert log.stage_count("source:") == 4
    assert log.stage_count("seed:") == 1
    for stage in ("concept:", "case:", "topic:"):
        assert log.stage_count(stage) == 1


def test_source_texts_fit_chunk_bounds_without_cropping(tmp_path):
    run = run_round(tmp_path)
    report = run["summary"]["chunk_report"]
    for fid, info in report.items():
        assert info["coverage"] == "full", fid
        assert info["chunk_count"] == 1  # each doc fits ONE chunk: 4 source calls
        assert info["total_chars"] <= info["chunk_chars_bound"]
        assert info["total_chars"] > 0
    assert sum(i["chunk_count"] for i in report.values()) == 4


# ---------------------------------------------------------------------------
# Prompt fidelity and no answer injection
# ---------------------------------------------------------------------------


def test_prompts_carry_exact_fixture_bytes_and_no_annotations(tmp_path):
    run = run_round(tmp_path)
    notes = run["notes"]
    for call in run["log"].calls:
        payload_json = call["payload_json"]
        for key in support.manifest_annotation_keys():
            assert f'"{key}"' not in payload_json, (call["stage"], key)
        for claim in support.manifest_prohibited_overclaims():
            assert claim not in payload_json, (call["stage"], claim)
        # no mock ANSWER text is ever fed back into a later input payload
        for other in run["log"].calls:
            if other is not call:
                try:
                    response_obj = json.loads(other["response"])
                except ValueError:
                    continue
                for fragment in _answer_fragments(response_obj):
                    assert fragment not in payload_json or _fragment_is_fixture(
                        fragment, notes), (call["stage"], fragment[:40])


def _answer_fragments(obj, depth=0):
    """Model-authored free-text fields (not verbatim fixture quotes)."""
    if depth > 3 or not isinstance(obj, dict):
        return []
    out = []
    for key in ("explanation", "theme_boundary", "summary", "reason"):
        val = obj.get(key)
        if isinstance(val, str) and len(val) > 20:
            out.append(val)
    for key in ("concepts", "cases", "tensions"):
        for item in obj.get(key) or []:
            out.extend(_answer_fragments(item, depth + 1))
    return out


def _fragment_is_fixture(fragment: str, notes: dict) -> bool:
    return any(fragment in note["source_text"] for note in notes.values())


def test_source_chunks_received_full_text_and_mock_verified_quotes(tmp_path):
    run = run_round(tmp_path)
    from core.claims import normalized_text
    for call in run["log"].calls:
        if not call["stage"].startswith("source:"):
            continue
        fid = call["stage"].split(":", 1)[1]
        fixture_norm = normalized_text(support.load_fixture(fid)["text"])
        chunk_body = call["payload"]["text"].split("\n\n", 1)[-1]
        assert chunk_body in fixture_norm


def test_seed_prompt_units_come_from_dialogue_with_in_text_speakers(tmp_path):
    run = run_round(tmp_path)
    seed_call = next(c for c in run["log"].calls if c["stage"].startswith("seed"))
    units = seed_call["payload"]["units"]
    assert units, "seed prompt must carry the extracted information units"
    speakers = {u.get("speaker") for u in units}
    assert any("用户" in s for s in speakers if s)
    assert any("AI" in s for s in speakers if s)
    for u in units:
        assert u["quote"] in support.load_fixture("dialogue_user_ai_01")["text"]


# ---------------------------------------------------------------------------
# All five types compile with traceable outputs (curated MOCK quality)
# ---------------------------------------------------------------------------


def test_source_stage_renders_cards_and_keeps_verified_traceable_units(tmp_path):
    run = run_round(tmp_path)
    source_run = run["source_run"]
    assert source_run["processed"] == 4
    assert len(source_run["created"]) == 4  # rendered source Markdown cards
    for page in source_run["created"]:
        content = page.get("content") or ""
        # rendered source-note Markdown (frontmatter + body)
        assert content.lstrip().startswith(("#", "---")), "rendered Markdown expected"
    for rel, data in run["source_analysis"].items():
        assert data["status"] == "ok", (rel, data.get("errors"))
        assert data["analysis_mode"] == "llm"
        assert data["coverage"] == "full"
        sha = run["notes"][  # sha keyed by rel -> fixture
            next(fid for fid, note in run["notes"].items()
                 if note["rel"] == rel)]["source_sha256"]
        assert data["source_hashes"] == {rel: sha}
        verified = [u for u in data.get("info_units", []) if u.get("verified")]
        assert verified, rel
        for unit in verified:
            assert unit["source_sha256"] == sha
            fixture_text = support.load_fixture(
                next(fid for fid, note in run["notes"].items()
                     if note["rel"] == rel))["text"]
            assert unit["quote"] in fixture_text


def test_seed_items_carry_user_vs_ai_attribution_and_tail_boundary(tmp_path):
    run = run_round(tmp_path)
    seed = run["seed_result"]
    assert seed["ok"] and seed["items"], seed.get("issues")
    sha = support.load_fixture("dialogue_user_ai_01")["sha256"]
    speakers, scopes = set(), []
    for item in seed["items"]:
        for row in item["evidence"]:
            assert row["source_sha256"] == sha
            if row.get("speaker"):
                speakers.add(row["speaker"])
        scopes.extend(item.get("negative_scope", []))
    assert any("用户" in s for s in speakers), speakers
    assert any("AI" in s for s in speakers), speakers
    assert any("提案" in s or "边界" in s or "误删" in s for s in scopes), scopes


# ---------------------------------------------------------------------------
# Rev 2: explicit ROLE assertions on the compiled cards
# ---------------------------------------------------------------------------


def test_concept_definition_is_source_mechanism_claim_with_source_boundary(tmp_path):
    run = run_round(tmp_path)
    result = run["concept_result"]
    assert result["state"] == "full", result.get("reason")
    concept = result["items"][0]
    # definition = the SOURCE-DESCRIBED mechanism chain claim (fact role),
    # NOT the causal-effect inference
    assert concept["definition_claim"] == support.CONCEPT_DEFINITION_STATEMENT
    assert concept["definition"] == support.CONCEPT_DEFINITION_STATEMENT
    assert support.CASE_INFERENCE_STATEMENT not in concept["definition"]
    # source-defined boundary = the counterexample's own scope statement
    boundary = _plain(concept["source_defined_boundary"])
    assert boundary, "concept must carry a source-defined boundary"
    boundary_blob = json.dumps(boundary, ensure_ascii=False)
    assert support.CONCEPT_BOUNDARY_STATEMENT in boundary_blob
    # the compiled claim behind the definition is fact-kind
    kinds = {c["statement"]: c["kind"] for c in concept["claims"]}
    assert kinds[support.CONCEPT_DEFINITION_STATEMENT] == "fact"


def test_case_reusable_and_inference_roles_are_distinct_with_correct_kinds(tmp_path):
    run = run_round(tmp_path)
    result = run["case_result"]
    assert result["state"] == "full", result.get("reason")
    case = result["items"][0]
    # distinct role bindings
    assert case["reusable_mechanism"] == support.CASE_REUSABLE_STATEMENT
    assert case["mechanism_inference"] == support.CASE_INFERENCE_STATEMENT
    assert case["reusable_mechanism"] != case["mechanism_inference"]
    # observed self-report figure, attributed and distinct from both roles
    assert case["result"]["figures"], "figures must be present"
    assert case["result"]["source_asserted"] is True
    figure_blob = json.dumps(_plain(case["result"]["figures"]), ensure_ascii=False)
    assert support.CASE_FIGURE_STATEMENT in figure_blob
    # bound kinds: reusable -> fact claim, inference -> inference claim
    kinds = {c["statement"]: c["kind"] for c in case["claims"]}
    assert kinds[support.CASE_REUSABLE_STATEMENT] == "fact"
    assert kinds[support.CASE_INFERENCE_STATEMENT] == "inference"
    # counterexample scope is an attributed source claim (fact), the free-
    # alternative reading keeps a separate genuinely inferred commentary
    assert kinds[support.judgment_statement("fact_counter_scope")] == "fact"
    assert kinds[support.judgment_statement("inference_free_constraint")] == "inference"


def test_seed_mock_selects_concrete_insight_and_proposal_three_with_tail(tmp_path):
    run = run_round(tmp_path)
    log = run["log"]
    seed_call = next(c for c in log.calls if c["stage"].startswith("seed"))
    units = {u["id"]: u for u in seed_call["payload"]["units"]}
    thoughts = json.loads(seed_call["response"])["thoughts"]
    by_title = {t["title"]: t for t in thoughts}

    insight = by_title[support.SEED_INSIGHT_TITLE]
    assert len(insight["unit_ids"]) == 1
    insight_unit = units[insight["unit_ids"][0]]
    assert insight_unit["speaker"] and "用户" in insight_unit["speaker"]
    assert any(m in insight_unit["quote"] for m in
               ("我想写的东西", "觉得有用", "错配")), insight_unit["quote"]

    tail = by_title[support.SEED_TAIL_TITLE]
    assert len(tail["unit_ids"]) == 2
    proposal_unit = units[tail["unit_ids"][0]]
    boundary_unit = units[tail["unit_ids"][1]]
    assert proposal_unit["speaker"] and "AI" in proposal_unit["speaker"]
    # the proposal idea and its OWN tail boundary are both cited as evidence
    assert "反向过滤" in proposal_unit["quote"]
    assert "暂不判断" in boundary_unit["quote"] and "漂移" in boundary_unit["quote"]

    # thought-specific (not quota-filling) growth steps
    assert insight["growth_directions"][0]["action"] == support.SEED_INSIGHT_GROWTH
    assert tail["growth_directions"][0]["action"] == support.SEED_TAIL_GROWTH
    assert (insight["growth_directions"][0]["action"]
            != tail["growth_directions"][0]["action"])

    # the user card stays ATOMIC about the mismatch only: no borrowed slogan
    # from the opening turn, no second thought without a cited unit
    insight_response = insight
    assert insight_response["statement"] == support.SEED_INSIGHT_STATEMENT
    assert "存了笔记不等于存下了思考" not in insight_response["statement"]

    # the user card's boundary limits the SELF-REPORT's reach; the AI
    # method's scope (选题漂移/暂不判断) belongs to the AI card only
    assert insight["negative_scope"] == support.SEED_INSIGHT_SCOPE
    assert not any("漂移" in s for s in insight["negative_scope"])
    assert any("漂移" in s for s in tail["negative_scope"])
    # growth is phrased as a proposed next step, never a historical user action
    assert insight["growth_directions"][0]["action"].startswith("模型建议的下一步")

    # compiled items keep the readable titles and the exact evidence binding
    titles = {item["title"] for item in run["seed_result"]["items"]}
    assert support.SEED_INSIGHT_TITLE in titles
    assert support.SEED_TAIL_TITLE in titles
    for item in run["seed_result"]["items"]:
        quotes = [row["quote"] for row in item["evidence"]]
        bound = insight if item["title"] == support.SEED_INSIGHT_TITLE else tail
        assert any(units[i]["quote"] in quotes for i in bound["unit_ids"])


def test_topic_structure_exact_gaps_actions_tensions_sources(tmp_path):
    run = run_round(tmp_path)
    result = run["topic_result"]
    assert result["state"] == "full", result.get("reason")
    analysis = result["analysis"]

    # source_map covers all three case-family sources; >=3 usable sources
    assert {m["rel"] for m in analysis["source_map"]} == set(support.CASE_FAMILY)
    assert len(analysis["usable_sources"]) >= 3

    # exact structured gap/action arrays
    gaps = analysis["evidence_gaps"]
    actions = analysis["next_actions"]
    assert len(gaps) >= 2
    assert len(actions) >= 2
    gap_texts = {g["gap"] for g in gaps}
    for action in actions:
        # the generator keeps priority as explicit ordering; every action must
        # resolve to a REAL recorded gap (never null)
        assert action["addresses_gap"] in gap_texts
    # priority-1 action comes first (the generator sorts by priority)
    assert actions[0]["action"] == "在素材设定内补记一次错峰或对照条件的转化台账"

    # tensions: measured-window and scene differences are context_difference;
    # the owner/advisor interpretation dispute is unverified_tension
    tensions = analysis["tensions"]
    classifications = sorted(t["classification"] for t in tensions)
    assert classifications == ["context_difference", "context_difference",
                               "unverified_tension"]
    unverified = next(t for t in tensions if t["classification"] == "unverified_tension")
    claim_stmt = {c["claim_id"]: c["statement"] for c in result["claims"]}
    assert {claim_stmt[cid] for cid in unverified["claim_ids"]} == {
        support.judgment_statement("fact_owner"),
        support.judgment_statement("fact_advisor"),
    }


# ---------------------------------------------------------------------------
# Actual seed renderer: multi-evidence rows render as DISTINCT list lines
# ---------------------------------------------------------------------------


def test_seed_renderer_joins_multi_evidence_rows_on_separate_lines():
    """Production display defect regression: evidence rows were joined with
    "" (one line). Claim contents/hashes/state must be unchanged — only the
    joining newline is fixed."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "mindseed_renderer_under_test",
        REPO_ROOT / "skills" / "mindseed-grow" / "renderer.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)

    item = {
        "title": "多证据渲染回归", "type": "seed-card", "status": "seed",
        "stage": "candidate", "sources": ["quicknote/dialogue_user_ai_01.md"],
        "summary": "测试念头", "kind": "assertion", "confidence": "low",
        "review_required": True, "tags": [], "keywords": [], "related": [],
        "thought_units": ["unit:a", "unit:b"],
        "evidence": [
            {"source": "quicknote/dialogue_user_ai_01.md", "quote": "第一条证据原文",
             "kind": "assertion", "speaker": "林舟（用户）", "start_line": 9,
             "source_sha256": "a" * 64, "verified": True},
            {"source": "quicknote/dialogue_user_ai_01.md", "quote": "提案边界：若选题漂移需保留暂不判断状态",
             "kind": "assertion", "speaker": "AI 助手（提案三）", "start_line": 21,
             "source_sha256": "a" * 64, "verified": True},
        ],
    }
    rendered = renderer.render(item)

    evidence_section = rendered.split("## 证据与出处", 1)[1].split("## 可生长方向", 1)[0]
    lines = [ln for ln in evidence_section.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2, lines
    assert lines[0].startswith("- ") and lines[1].startswith("- ")
    # each quote stays on its OWN line: the second quote must not be
    # concatenated onto the tail of the first row
    assert "第一条证据原文" in lines[0] and "提案边界" in lines[1]
    assert "）- " not in rendered  # the old one-line concatenation artifact
    # raw machine evidence/hash/state untouched
    state = renderer.card_state(item)
    assert state["evidence"] == item["evidence"]


# ---------------------------------------------------------------------------
# Module separation: mock answers cannot leak into the production path
# ---------------------------------------------------------------------------


def test_generators_never_import_the_mock_corpus():
    offenders = []
    smoke_harness = (REPO_ROOT / "scripts" / "evaluate_public_baseline.py").resolve()
    for base in ("core", "skills", "scripts"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.resolve() == smoke_harness:
                # The public evaluation runner is the sole allowed consumer:
                # its mock import is lazy and confined to explicit --smoke.
                import ast
                tree = ast.parse(text, filename=str(path))
                parents = {}
                for parent in ast.walk(tree):
                    for child in ast.iter_child_nodes(parent):
                        parents[child] = parent
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Import):
                        continue
                    if not any(alias.name == "public_round_support"
                               for alias in node.names):
                        continue
                    current = parents.get(node)
                    while current is not None and not isinstance(
                            current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        current = parents.get(current)
                    assert (isinstance(current, ast.FunctionDef)
                            and current.name == "make_smoke_provider")
                continue
            if "public_round_support" in text or "offline_provider" in text \
                    or "seed_response" in text or "concept_response" in text:
                offenders.append(str(path))
    assert offenders == []


def test_mock_responses_fail_closed_on_unknown_payloads():
    log = support.CallLog()
    provider = support.make_offline_provider(log)
    with pytest.raises(ValueError):
        provider("system", {"unexpected": "shape"})
    with pytest.raises(ValueError):
        # a seed payload missing the required units fails loudly, never guesses
        provider({"task": "atomic_seed", "units": []})


def test_manifest_annotations_never_appear_in_mock_responses(tmp_path):
    run = run_round(tmp_path)
    for call in run["log"].calls:
        for key in support.manifest_annotation_keys():
            assert f'"{key}"' not in call["response"]
        for claim in support.manifest_prohibited_overclaims():
            assert claim not in call["response"]


def test_round_writer_refuses_non_empty_output_dir(tmp_path):
    out = tmp_path / "offline-round-v2"
    out.mkdir()
    (out / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        support.run_public_round(output_dir=out)
