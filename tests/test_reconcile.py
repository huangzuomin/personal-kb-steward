"""Concrete reconcile regressions; only model I/O is stubbed, writes are real."""
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.reconcile import START, ReconcileConflict, make_reconcile_plan
from core.run_records import RunRecordConflict
from core.vault import build_index
from scripts import personal_kb_steward as steward
from scripts import reconcile as cli
from tests import test_object_plans as fixtures


@pytest.fixture
def vault():
    case = fixtures.ObjectPlanTests()
    case.setUp()
    yield case
    case.doCleanups()


def provider(decision="update", summary="A measured observation. [[raw/a.md]]", **kwargs):
    quotes = {"raw/a.md": "An evidence record.", "raw/b.md": "A second observation."}
    claims = []
    for paragraph in summary.split("\n\n"):
        sources = re.findall(r"\[\[([^]]+)\]\]", paragraph)
        statement = re.sub(r"\[\[[^]]+\]\]", "", paragraph).strip()
        claims.append({"statement": statement, "kind": "fact", "confidence": "medium",
                       "evidence": [{"source": source, "quote": quotes.get(source, "Unknown source."),
                                     "relation": "supports"} for source in sources]})
    return Mock(return_value=json.dumps({"decision": decision, "reason": "New evidence", "claims": claims,
                                        "conflicts": [], **kwargs}))


def plan(case, sources=None, *, target=None, topic="Evidence", rid="reconcile-test", model=None):
    return make_reconcile_plan(case.cfg, topic, sources or ["raw/a.md"], target=target,
                               plan_run_id=rid, completion=model or provider("create"))


def review_apply(case, proposal):
    path = steward.write_execution_plan(case.cfg, proposal)
    assert steward.write_manual_review_queue(case.cfg, proposal) == 1
    with pytest.raises(SystemExit, match="人工审核"):
        steward.command_apply_plan(case.cfg, str(path))
    queued = steward.load_queue(steward.review_queue_path(case.cfg))
    for item in queued:
        if item["run_id"] == proposal["run_id"]:
            assert steward.command_review(case.cfg, SimpleNamespace(review_command="approve", id=item["id"], reason="Reviewed")) == 0
    assert steward.command_review(case.cfg, SimpleNamespace(review_command="apply-approved")) == 0
    return path


def test_create_then_same_title_update_preserves_id_sources_and_manual_text(vault):
    raw = vault.root / "raw/a.md"
    raw_before = raw.read_bytes()
    first = plan(vault)
    assert first["reconcile"]["decision"] == "create"
    assert not list((vault.root / "wiki/topics").glob("*.md"))
    review_apply(vault, first)
    page = first["planned_pages"][0]
    target = vault.root / page["rel_path"]
    object_id = page["object_id"]
    target.write_bytes(target.read_bytes() + "\n## 手写判断\n保留我的观察。\n".encode())
    vault.install_note("raw/b.md", "# Another source\nA second observation.\n")
    model = provider(summary="Both observations remain relevant. [[raw/a.md]] [[raw/b.md]]")
    second = plan(vault, ["raw/b.md"], model=model, rid="second")
    assert second["reconcile"]["decision"] == "update"
    assert {d["path"] for d in model.call_args.args[2]["sources"]} == {"raw/a.md", "raw/b.md"}
    saved = review_apply(vault, second)
    note = build_index(vault.cfg).by_rel[page["rel_path"]]
    assert (note.object_id, note.revision) == (object_id, 2)
    assert "## 手写判断\n保留我的观察。" in target.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8").count(START) == 1
    assert len(build_index(vault.cfg).objects.by_id) == 1
    assert raw.read_bytes() == raw_before
    record_path = vault.root / ".openclaw/runs/second.json"
    audit = record_path.read_bytes()
    record = json.loads(audit)
    assert record["created"][0]["object_id"] == object_id
    assert Path(record["created"][0]["backup_path"]).is_file()
    processed = steward.load_processed_index(vault.cfg)["processed"]
    assert processed["raw/b.md"]["skills"]["kb-reconcile"]["outputs"] == [page["rel_path"]]
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(saved), allow_reviewed=True)
    assert record_path.read_bytes() == audit
    with pytest.raises(SystemExit, match="包含更新页面"):
        steward.command_rollback(vault.cfg, "second")
    assert target.exists()


def test_unchanged_sources_noop_avoids_model_plan_and_revision(vault):
    first = plan(vault)
    review_apply(vault, first)
    snapshot = {p: p.read_bytes() for p in vault.root.rglob("*") if p.is_file()}
    with patch.object(cli, "config", return_value=vault.cfg), patch("core.reconcile.call_chat_completion") as model:
        assert cli.main(["Evidence", "--source", "raw/a.md"]) == 0
        model.assert_not_called()
    assert snapshot == {p: p.read_bytes() for p in vault.root.rglob("*") if p.is_file()}


def test_ambiguous_title_requires_explicit_identity_and_never_creates_suffix(vault):
    first_id = new_object_id()
    vault.install_note("wiki/topics/first.md", vault.content("First", first_id))
    vault.install_note("wiki/topics/second.md", vault.content("Second", new_object_id()))
    model = provider()
    ambiguous = plan(vault, topic=" Sample   TOPIC ", model=model)
    assert ambiguous["reconcile"]["decision"] == "conflict"
    assert not ambiguous["planned_pages"]
    model.assert_not_called()
    explicit = plan(vault, target=first_id, model=model)
    assert explicit["reconcile"]["decision"] == "update"
    assert explicit["planned_pages"][0]["rel_path"] == "wiki/topics/first.md"


@pytest.mark.parametrize("target", ["kb:unknown", "wiki/topics/missing.md", "raw/a.md"])
def test_explicit_missing_or_raw_target_is_never_reinterpreted_as_create(vault, target):
    model = provider("create")
    result = plan(vault, target=target, model=model)
    assert result["reconcile"]["decision"] == "conflict"
    assert result["planned_pages"] == []
    model.assert_not_called()


def test_semantic_conflict_has_no_executable_pages_even_after_approval(vault):
    target = vault.install_note("wiki/topics/a.md", vault.content("Original claim", new_object_id(), 3))
    before = target.read_bytes()
    result = plan(vault, target="wiki/topics/a.md", model=provider("update", conflicts=["The two sources disagree."]))
    assert result["reconcile"]["decision"] == "conflict"
    path = steward.write_execution_plan(vault.cfg, result)
    assert not result["planned_pages"]
    with pytest.raises(SystemExit, match="没有 planned_pages"):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert target.read_bytes() == before


@pytest.mark.parametrize("when", ["during_model", "after_save"])
def test_human_edit_blocks_update_from_actual_generation_snapshot(vault, when):
    target = vault.install_note("wiki/topics/a.md", vault.content("Before", new_object_id(), 2))
    response = provider().return_value
    def model(*args):
        if when == "during_model":
            target.write_bytes(target.read_bytes() + b"Human edit\n")
        return response
    result = plan(vault, target="wiki/topics/a.md", model=model)
    if when == "during_model":
        with pytest.raises(ObjectIdentityError, match="Generation base"):
            steward.write_execution_plan(vault.cfg, result)
    else:
        path = steward.write_execution_plan(vault.cfg, result)
        target.write_bytes(target.read_bytes() + b"Human edit\n")
        with pytest.raises(ObjectIdentityError):
            steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert target.read_bytes().endswith(b"Human edit\n")
    assert build_index(vault.cfg).by_rel["wiki/topics/a.md"].revision == 2


@pytest.mark.parametrize("when", ["before_save", "after_save"])
def test_changed_source_blocks_stale_evidence_without_marking_processed(vault, when):
    result = plan(vault)
    if when == "after_save":
        path = steward.write_execution_plan(vault.cfg, result)
    source = vault.root / "raw/a.md"
    source.write_bytes(source.read_bytes() + b"Changed evidence\n")
    with pytest.raises(ReconcileConflict, match="来源已变化"):
        if when == "before_save":
            steward.write_execution_plan(vault.cfg, result)
        else:
            steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert not (vault.root / result["reconcile"]["target"]).exists()
    assert not steward.processed_index_path(vault.cfg).exists()


def test_manually_edited_managed_section_is_not_silently_replaced(vault):
    first = plan(vault)
    review_apply(vault, first)
    target = vault.root / first["reconcile"]["target"]
    target.write_bytes(target.read_bytes().replace(b"measured observation", b"human correction"))
    before = target.read_bytes()
    model = provider()
    result = plan(vault, model=model)
    assert result["reconcile"]["decision"] == "conflict"
    assert "人工修改" in result["reconcile"]["reason"]
    model.assert_not_called()
    assert target.read_bytes() == before


def test_bom_crlf_and_unowned_yaml_body_are_preserved(vault):
    text = "\ufeff" + vault.content("## Handwritten\nKeep this exactly.", new_object_id(), 3)
    text = text.replace('sources: ["raw/a.md"]', "sources:\n  - raw/a.md\n# evidence record\n  - raw/a.md")
    text = text.replace("custom: keep-me", "custom: keep-me\ncustom_map:\n  nested: keep-this-too\n# a comment")
    target = vault.root / "wiki/topics/中文.md"
    target.write_bytes(text.replace("\n", "\r\n").encode())
    result = plan(vault, target="wiki/topics/中文.md", model=provider())
    review_apply(vault, result)
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"custom_map:\r\n  nested: keep-this-too\r\n# a comment\r\n" in raw
    assert b"## Handwritten\r\nKeep this exactly.\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    note = build_index(vault.cfg).by_rel["wiki/topics/中文.md"]
    assert note.revision == 4
    assert note.metadata["sources"] == ["raw/a.md"]
    assert b"# evidence record\r\n" in raw


@pytest.mark.parametrize("answer", ["not json", json.dumps({"decision": "delete"}), json.dumps({"decision": []}),
    provider("create", summary="No evidence.").return_value,
    provider("create", summary="Invented link. [[raw/missing.md]]").return_value,
    provider("create", summary="Claim [[raw/a.md]]\n\nUnattributed second paragraph.").return_value])
def test_invalid_model_outputs_become_non_writing_conflicts(vault, answer):
    result = plan(vault, model=Mock(return_value=answer))
    assert result["reconcile"]["decision"] == "conflict"
    assert not result["planned_pages"]
    assert not list((vault.root / "wiki/topics").glob("*.md"))


def test_context_limit_is_explicit_not_silent_truncation(vault):
    vault.cfg["reconcile"] = {"max_context_chars": 5}
    model = provider("create")
    result = plan(vault, model=model)
    assert result["reconcile"]["decision"] == "conflict"
    assert "不静默截断" in result["reconcile"]["reason"]
    model.assert_not_called()


def test_cli_proposes_without_applying_and_create_can_rollback(vault, capsys):
    with patch.object(cli, "config", return_value=vault.cfg), patch("core.reconcile.call_chat_completion", provider("create")):
        assert cli.main(["Evidence", "--source", "raw/a.md"]) == 0
    assert "dry-run" in capsys.readouterr().out
    paths = list(steward.plan_dir(vault.cfg).glob("*.json"))
    assert len(paths) == 1
    proposal = json.loads(paths[0].read_text(encoding="utf-8"))
    target = vault.root / proposal["reconcile"]["target"]
    assert not target.exists()
    steward.command_apply_plan(vault.cfg, str(paths[0]), allow_reviewed=True)
    assert target.exists()
    steward.command_rollback(vault.cfg, proposal["run_id"])
    assert not target.exists()


def test_post_write_failure_preserves_actual_reconcile_mutation_and_audit(vault):
    result = plan(vault)
    path = steward.write_execution_plan(vault.cfg, result)
    with patch.object(steward, "update_index", side_effect=OSError("injected index failure")), pytest.raises(OSError):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    manifest = vault.root / f".openclaw/runs/{result['run_id']}.json"
    before = manifest.read_bytes()
    record = json.loads(before)
    assert (record["status"], record["phase"]) == ("failed", "update_index")
    assert record["created"][0]["object_id"] == result["planned_pages"][0]["object_id"]
    assert record["created"][0]["content_verified"]
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert manifest.read_bytes() == before
