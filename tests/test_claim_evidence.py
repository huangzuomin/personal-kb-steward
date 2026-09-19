"""Regression tests for exact, source-versioned evidence in the real plan/apply path."""
import hashlib
import json
from unittest.mock import Mock, patch

import pytest

from core.claims import EvidenceError, compile_claims, digest, normalized_text, render_claims
from core.config import sha256_text
from core.reconcile import END, START, ReconcileConflict, _patch_header, make_reconcile_plan
from core.vault import parse_frontmatter
from scripts import claims as inspect_cli
from scripts import personal_kb_steward as steward
from tests.test_reconcile import vault, review_apply


def claim(statement="The source records an observation.", source="raw/a.md", quote="An evidence record.", **kwargs):
    return {"statement": statement, "kind": "fact", "confidence": "medium",
            "evidence": [{"source": source, "quote": quote, "relation": "supports"}], **kwargs}


def proposal(case, items=None, *, target=None, rid="claim-test", decision="create", sources=None):
    return make_reconcile_plan(case.cfg, "Evidence", sources or ["raw/a.md"], target=target, plan_run_id=rid,
        completion=Mock(return_value=json.dumps({"decision": decision, "reason": "Cited fragment", "conflicts": [],
                                                "claims": items if items is not None else [claim()]})))


def state_of(content):
    return parse_frontmatter(content.lstrip("\ufeff"))[0]["reconcile_state"]


def test_claim_evidence_roundtrip_audit_and_readonly_inspection(vault, capsys):
    source = vault.root / "raw/a.md"
    source.write_bytes(b"# Source\r\n\r\nAn evidence record.")
    first = proposal(vault)
    record = state_of(first["planned_pages"][0]["content"])["claims"][0]
    evidence = record["evidence"][0]
    assert evidence["start_line"] == evidence["end_line"] == 3
    assert evidence["quote_sha256"] == digest("An evidence record.")
    assert evidence["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    review_apply(vault, first)
    page = first["planned_pages"][0]
    audit = json.loads((vault.root / ".openclaw/runs/claim-test.json").read_text())
    assert audit["created"][0]["claim_ids"] == [record["claim_id"]]
    before = {p: p.read_bytes() for p in vault.root.rglob("*") if p.is_file()}
    with patch.object(inspect_cli, "config", return_value=vault.cfg), patch("core.reconcile.call_chat_completion") as model:
        assert inspect_cli.main([page["object_id"]]) == 0
        model.assert_not_called()
    output = capsys.readouterr().out
    assert '"match_status": "matched"' in output
    assert record["claim_id"] in output
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("broken", [claim(quote="A fabricated quotation."), claim(source="raw/missing.md"), claim(evidence=[])])
def test_fabricated_missing_and_unbacked_claims_never_produce_writable_pages(vault, broken):
    result = proposal(vault, [broken])
    assert result["reconcile"]["decision"] == "conflict"
    assert result["planned_pages"] == []
    assert not list((vault.root / "wiki/topics").glob("*.md"))


def test_repeated_quote_requires_disambiguation_and_offsets_are_not_model_supplied():
    raw = "\ufeff标题\r\n重复句。\r\n补充材料\r\n重复句。\r\n".encode()
    documents = [{"path": "raw/中文.md", "sha256": hashlib.sha256(raw).hexdigest(), "content": raw.decode()}]
    item = claim(source="raw/中文.md", quote="重复句。")
    with pytest.raises(EvidenceError, match="位置不唯一"):
        compile_claims([item], documents)
    item["evidence"][0].update(start_line=4, start=0, end=1, quote_sha256="invented")
    e = compile_claims([item], documents)[0].evidence[0]
    text = normalized_text(raw.decode())
    assert text[e.start:e.end] == "重复句。"
    assert e.start == text.rindex("重复句。")
    assert e.start_line == e.end_line == 4
    assert e.source_sha256 == documents[0]["sha256"]
    item["evidence"][0]["start_line"] = 3
    with pytest.raises(EvidenceError):
        compile_claims([item], documents)


def test_multiline_bom_crlf_quotes_display_literal_markup_without_control_injection(vault):
    text = '\ufeff# 标题\r\n第一行 [[raw/不应生成链接.md]]\r\n<!-- kb-steward:reconcile:start -->\r\n'
    quote = '第一行 [[raw/不应生成链接.md]]\n<!-- kb-steward:reconcile:start -->'
    docs = [{"path": "raw/中文.md", "content": text, "sha256": digest(text)}]
    claims = compile_claims([claim(source="raw/中文.md", quote=quote)], docs)
    e = claims[0].evidence[0]
    assert (e.start_line, e.end_line) == (2, 3)
    rendered = render_claims(claims)
    assert START not in rendered
    assert "[[raw/不应生成链接.md]]" not in rendered
    assert "[[raw/中文.md]]" in rendered
    source = vault.root / "raw/中文.md"
    source.write_bytes(text.encode())
    result = proposal(vault, [claim(source="raw/中文.md", quote=quote)], sources=["raw/中文.md"])
    review_apply(vault, result)
    report = inspect_cli.inspect(vault.cfg, result["planned_pages"][0]["object_id"])
    assert report["claims"][0]["evidence"][0]["match_status"] == "matched"


def test_unchanged_statement_keeps_id_when_evidence_grows_and_rewording_gets_new_id(vault):
    first = proposal(vault)
    review_apply(vault, first)
    page = first["planned_pages"][0]
    first_claim = state_of(page["content"])["claims"][0]
    vault.install_note("raw/b.md", "# Observation\nA second record.")
    amended = claim()
    amended["evidence"].append({"source": "raw/b.md", "quote": "A second record.", "relation": "supports"})
    second = proposal(vault, [amended], target=page["object_id"], rid="second-claim", decision="update", sources=["raw/b.md"])
    review_apply(vault, second)
    new_page = second["planned_pages"][0]
    new_claim = state_of(new_page["content"])["claims"][0]
    assert new_claim["claim_id"] == first_claim["claim_id"]
    assert len(new_claim["evidence"]) == 2
    assert new_page["object_id"] == page["object_id"] and new_page["revision"] == 2
    docs = [{"path": "raw/a.md", "content": "An evidence record.", "sha256": digest("An evidence record.")}]
    changed = compile_claims([claim(statement="The source does NOT record an observation.")], docs)
    assert changed[0].claim_id != first_claim["claim_id"]


def test_counterevidence_is_preserved_in_conflict_report_not_silently_accepted(vault):
    vault.install_note("raw/b.md", "The record was disputed.")
    item = claim()
    item["evidence"].append({"source": "raw/b.md", "quote": "The record was disputed.", "relation": "contradicts"})
    result = proposal(vault, [item], sources=["raw/a.md", "raw/b.md"])
    assert result["reconcile"]["decision"] == "conflict"
    assert result["planned_pages"] == []
    path = steward.write_execution_plan(vault.cfg, result)
    saved = json.loads(path.read_text())["reconcile"]["claims"][0]
    assert [e["relation"] for e in saved["evidence"]] == ["supports", "contradicts"]
    assert saved["evidence"][1]["quote"] == "The record was disputed."
    with pytest.raises(SystemExit, match="没有 planned_pages"):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)


@pytest.mark.parametrize("when", ["before_save", "after_save"])
def test_forged_locator_rejected_at_save_and_apply_even_when_plan_hash_recomputed(vault, when):
    result = proposal(vault)
    if when == "after_save":
        path = steward.write_execution_plan(vault.cfg, result)
    page = result["planned_pages"][0]
    state = state_of(page["content"])
    e = state["claims"][0]["evidence"][0]
    e["start"] += 1
    e["end"] += 1
    page["content"] = _patch_header(page["content"], {"reconcile_state": state})
    page["content_sha256"] = sha256_text(page["content"])
    with pytest.raises(ReconcileConflict, match="不匹配"):
        if when == "before_save":
            steward.write_execution_plan(vault.cfg, result)
        else:
            path.write_text(json.dumps(result), encoding="utf-8")
            steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert not (vault.root / page["rel_path"]).exists()


def test_freeform_text_cannot_diverge_from_stored_claims(vault):
    result = proposal(vault)
    page = result["planned_pages"][0]
    page["content"] = page["content"].replace("The source records an observation.\n", "An unsupported addition.\n")
    state = state_of(page["content"])
    section = page["content"][page["content"].index(START):page["content"].index(END) + len(END)]
    state["section_sha256"] = sha256_text(section)
    page["content"] = _patch_header(page["content"], {"reconcile_state": state})
    page["content_sha256"] = sha256_text(page["content"])
    with pytest.raises(ReconcileConflict, match="不一致"):
        steward.write_execution_plan(vault.cfg, result)


def test_inspector_reports_changed_then_unavailable_sources_without_rebinding(vault):
    first = proposal(vault)
    review_apply(vault, first)
    page = first["planned_pages"][0]
    source = vault.root / "raw/a.md"
    target = vault.root / page["rel_path"]
    original = target.read_bytes()
    source.write_bytes(b"Inserted line\n" + source.read_bytes())
    report = inspect_cli.inspect(vault.cfg, page["object_id"])
    assert report["claims"][0]["evidence"][0]["match_status"] == "source_changed"
    source.unlink()
    report = inspect_cli.inspect(vault.cfg, page["object_id"])
    assert report["claims"][0]["evidence"][0]["match_status"] == "unavailable"
    assert target.read_bytes() == original


def test_legacy_plan_readable_and_explicit_reconcile_upgrades_only_selected_page(vault):
    # Build a stored v1 proposal, as emitted by the previous released engine.
    result = proposal(vault)
    page = result["planned_pages"][0]
    state = state_of(page["content"])
    state.pop("claims")
    state["version"] = 1
    page.pop("reconcile_version")
    result["reconcile"]["version"] = 1
    page["content"] = _patch_header(page["content"], {"reconcile_state": state})
    page["content_sha256"] = sha256_text(page["content"])
    review_apply(vault, result)
    page = result["planned_pages"][0]
    assert inspect_cli.inspect(vault.cfg, page["object_id"])["legacy"]
    untouched = vault.install_note("wiki/topics/untouched.md", vault.content("My old note"))
    before = untouched.read_bytes()
    upgraded = proposal(vault, target=page["object_id"], rid="upgrade", decision="update")
    review_apply(vault, upgraded)
    assert not inspect_cli.inspect(vault.cfg, page["object_id"])["legacy"]
    assert untouched.read_bytes() == before
    with patch("core.reconcile.call_chat_completion") as model:
        again = make_reconcile_plan(vault.cfg, "Evidence", ["raw/a.md"], plan_run_id="noop")
        assert again["reconcile"]["decision"] == "noop"
        model.assert_not_called()


def test_partial_reporting_failure_keeps_written_claim_ids_and_original_attempt(vault):
    result = proposal(vault)
    path = steward.write_execution_plan(vault.cfg, result)
    ids = [c["claim_id"] for c in state_of(result["planned_pages"][0]["content"])["claims"]]
    with patch.object(steward, "update_processed_index", side_effect=OSError("failed index")), pytest.raises(OSError):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    manifest = vault.root / ".openclaw/runs/claim-test.json"
    before = manifest.read_bytes()
    record = json.loads(before)
    assert record["status"] == "failed" and record["phase"] == "update_processed_index"
    assert record["created"][0]["claim_ids"] == ids
    assert record["created"][0]["content_verified"]
    with pytest.raises(ValueError, match="execution history"):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert manifest.read_bytes() == before
