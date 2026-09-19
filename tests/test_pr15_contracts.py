"""Regression proofs for the handover's actual failures, using isolated vaults."""
import copy
import json
from pathlib import Path
import runpy
from unittest.mock import patch

import pytest

from core.derived_index import cache_path, rebuild, search, show, status, DerivedIndexError
from core.dependencies import stale
from core.initializer import promote_candidate_pages
from core.knowledge_objects import ObjectIdentityError, new_object_id
from core.run_records import RunRecordConflict
from core.reconcile import make_reconcile_plan
from core.retrieval import Retriever
from core.skill_runtime import run_skill_runtime
from core.vault import build_index, extract_wikilinks, parse_frontmatter, resolve_link
from scripts import personal_kb_steward as steward
from tests.test_reconcile import provider, review_apply, vault

ROOT = Path(__file__).resolve().parents[1]


def custom_layout(case):
    for key, value in list(case.cfg["write"].items()):
        if value.startswith("wiki/"):
            case.cfg["write"][key] = value.replace("wiki/", "Notes/Knowledge.v2/", 1)
    case.cfg["scan"]["include_dirs"] = ["raw"]  # Outputs must join scan scope, not their broad parent.


def test_custom_paths_reconcile_review_apply_rebuild_and_replay_without_main_binding(vault):
    custom_layout(vault)
    raw = vault.root / "raw/a.md"
    before = raw.read_bytes()
    first = make_reconcile_plan(vault.cfg, "Evidence", ["raw/a.md"], plan_run_id="custom-first", completion=provider("create"))
    assert first["reconcile"]["decision"] == "create", first
    review_apply(vault, first)
    page = first["planned_pages"][0]
    assert page["rel_path"].startswith("Notes/Knowledge.v2/topics/")
    assert page["object_id"] and page["revision"] == 1
    original_index = build_index(vault.cfg)
    rebuild(vault.cfg)
    assert show(vault.cfg, page["object_id"])["note"]["revision"] == 1
    assert search(vault.cfg, "measured", kind="claim")["hits"][0]["object_id"] == page["object_id"]
    # Loading another layout in the same process cannot mutate the first index.
    other = copy.deepcopy(vault.cfg)
    other["write"]["topics_dir"] = "Other/topics"
    build_index(other)
    assert original_index.by_object_id[page["object_id"]].revision == 1
    vault.install_note("raw/b.md", "# Another source\nA second observation.")
    second = make_reconcile_plan(vault.cfg, "Evidence", ["raw/b.md"], target=page["object_id"], plan_run_id="custom-update",
                                completion=provider("update", "Both observations. [[raw/a.md]] [[raw/b.md]]"))
    assert second["reconcile"]["decision"] == "update"
    path = review_apply(vault, second)
    assert (second["planned_pages"][0]["object_id"], second["planned_pages"][0]["revision"]) == (page["object_id"], 2)
    record = vault.root / ".openclaw/runs/custom-update.json"
    record_bytes = record.read_bytes()
    assert json.loads(record_bytes)["created"][0]["object_id"] == page["object_id"]
    with pytest.raises(RunRecordConflict):
        steward.command_apply_plan(vault.cfg, str(path), allow_reviewed=True)
    assert record.read_bytes() == record_bytes
    with pytest.raises(SystemExit, match="包含更新页面"):
        steward.command_rollback(vault.cfg, "custom-update")
    rebuild(vault.cfg)
    raw.write_bytes(before + b"\nChanged evidence")
    assert page["rel_path"] in str(stale(vault.cfg))
    assert not list((vault.root / "wiki/topics").glob("*.md"))


def test_custom_object_stale_plan_is_rejected_and_no_global_scope_leaks(vault):
    custom_layout(vault)
    target = "Notes/Knowledge.v2/topics/edit.md"
    note_path = vault.install_note(target, vault.content("Original", new_object_id(), 2))
    result = make_reconcile_plan(vault.cfg, "Edit", ["raw/a.md"], target=target,
                                plan_run_id="edit", completion=provider("update"))
    saved = steward.write_execution_plan(vault.cfg, result)
    note_path.write_bytes(note_path.read_bytes() + b"\nHuman edit")
    with pytest.raises(ObjectIdentityError):
        steward.command_apply_plan(vault.cfg, str(saved), allow_reviewed=True)
    assert note_path.read_bytes().endswith(b"Human edit")
    assert build_index(vault.cfg).by_rel[target].revision == 2
    unrelated = vault.install_note("Notes/Personal/private.md", vault.content("Unrelated", new_object_id()))
    index = build_index(vault.cfg)
    assert unrelated.relative_to(vault.root).as_posix() not in index.by_rel


def test_scan_exclusions_root_nested_and_derived_cache_are_consistent(vault):
    custom_layout(vault)
    vault.cfg["scan"]["exclude_files"] = ["0-MOC.md"]
    for name in ("0-MOC.md", "raw/0-MOC.md", "Notes/Knowledge.v2/topics/0-MOC.md"):
        vault.install_note(name, "# IndexSpamUnique\nEvery topic everywhere")
    target = "Notes/Knowledge.v2/topics/real.md"
    vault.install_note(target, vault.content("Real record", new_object_id()))
    index = build_index(vault.cfg)
    assert target in index.by_rel
    assert all(not rel.endswith("0-MOC.md") for rel in index.by_rel)
    rebuild(vault.cfg)
    assert search(vault.cfg, "IndexSpamUnique")["hits"] == []
    assert status(vault.cfg)["counts"]["notes"] == len(index.by_rel)
    vault.cfg["scan"]["exclude_files"] = []
    with pytest.raises(DerivedIndexError):
        search(vault.cfg, "IndexSpamUnique")  # Old scope cannot masquerade as the new one.


def test_candidate_rules_count_only_matching_sources_and_require_review(vault):
    vault.install_note("raw/related.md", "# Climate\nUniqueClimateMarker and measured change.")
    for i in range(6):
        vault.install_note(f"raw/photo-{i}.md", "# Historic photography\nUnrelated pictures.")
    notes = list(build_index(vault.cfg).by_rel.values())
    for kind, dir_key in [("topic", "topics_dir"), ("concept", "concepts_dir"), ("case", "cases_dir"), ("material-pack", "materials_dir")]:
        spec = {"kind": kind, "title": "Climate candidate", "rel_dir_key": dir_key,
                "match_any": ["UniqueClimateMarker"], "min_sources": 2}
        vault.cfg["candidate_promotion"] = [spec]
        assert promote_candidate_pages(vault.cfg, notes, "batch") == []
        spec["min_sources"] = 1
        candidate = promote_candidate_pages(vault.cfg, notes, "batch")[0]
        assert candidate["sources"] == ["raw/related.md"]
        assert candidate["review_required"] is True
        assert parse_frontmatter(candidate["content"])[0]["review_required"] == "true"
        assert set(candidate["retrieval_source_hashes"]) == {"raw/related.md"}
        spec["match_any"] = []
        assert promote_candidate_pages(vault.cfg, notes, "batch") == []


def source_note(case, name, topic, fact):
    case.install_note(f"raw/{name}.md", f"# {topic}\n{fact}")
    return case.install_note(f"wiki/sources/{name}.md", (
        f'---\ntitle: {name}\ntype: source-note\nsources: ["raw/{name}.md"]\n'
        'custom: preserve\n# preserve header comment\nrelated: []\ntags: []\n---\n'
        f'# {name}\n\n## 提取的专题\n- {topic}：specific scope\n\n## 关键事实\n- {fact}\n'))


def test_finalize_does_not_claim_unrelated_sources_or_drop_custom_source_headers(vault):
    from core.finalizer import make_finalize_plan
    original = source_note(vault, "climate", "Climate", "UniqueClimateFinding")
    source_note(vault, "photography", "Photography", "UnrelatedPhotoFinding")
    result = make_finalize_plan(vault.cfg, plan_run_id="scope", stamp="test")
    topic = next(p for p in result["planned_pages"] if p["rel_path"].startswith("wiki/topics/"))
    assert len(topic["sources"]) == 1
    assert not ("UniqueClimateFinding" in topic["content"] and "UnrelatedPhotoFinding" in topic["content"])
    assert topic["review_required"] is True
    update = next(p for p in result["planned_pages"] if p["rel_path"] == original.relative_to(vault.root).as_posix())
    newline = "\r\n" if b"\r\n" in original.read_bytes() else "\n"
    assert f"custom: preserve{newline}# preserve header comment" in update["content"]
    assert update["review_required"] is True
    assert set(update["sources"]).issubset(update["retrieval_source_hashes"])


def test_finalize_refuses_overwriting_handwritten_aggregate(vault):
    from core.finalizer import make_finalize_plan
    source_note(vault, "a", "Climate", "Climate fact")
    source_note(vault, "b", "Climate", "Other climate fact")
    target = vault.install_note("wiki/topics/Climate.md", vault.content("My handwritten notes"))
    before = target.read_bytes()
    with pytest.raises(ObjectIdentityError, match="unchanged owned aggregate"):
        make_finalize_plan(vault.cfg, plan_run_id="collision", stamp="test")
    assert target.read_bytes() == before


def test_retrieval_and_fallback_respect_small_total_budgets_and_redistribute(vault):
    vault.install_note("raw/b.md", "# Long\n" + "x" * 100)
    vault.install_note("raw/c.md", "# Longer\n" + "y" * 100)
    index = build_index(vault.cfg)
    notes = index.notes
    retriever = Retriever(vault.cfg, index)
    for budget in (0, 1, 2, 3, 10, 151):
        for docs in (retriever.documents(notes, 100, budget), steward.llm_documents(notes, 100, budget)):
            assert len(docs) == len(notes)
            assert all(len(d["content"]) <= 100 for d in docs)
            assert not budget or sum(len(d["content"]) for d in docs) <= budget
    notes[0].body = "x"
    docs = retriever.documents(notes, 100, 150)
    assert sum(len(d["content"]) for d in docs) == 150
    for builder in (retriever.documents, steward.llm_documents):
        with pytest.raises(ValueError):
            builder(notes, 100, -1)


def test_llm_prompt_types_follow_the_skill_and_invalid_shapes_are_reported():
    docs = [{"path": "raw/a.md", "title": "source", "content": "facts"}]
    good = {"items": [{"title": "Seed", "type": "seed-card", "status": "seed", "stage": "candidate",
                       "sources": ["raw/a.md"], "summary": "Summary", "confidence": "medium", "review_required": True}]}
    with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(good)) as model:
        result = run_skill_runtime(ROOT, {}, "mindseed-grow", "整理知识库", docs)
        assert result["ok"]
        assert "固定 topic-card" not in model.call_args.args[1]
        assert "固定 topic-card" not in str(model.call_args.args[2]["output_contract"])
    for bad in ([], None, {"items": [None]}, {"items": [{**good["items"][0], "related": None}]},
                {"items": [{**good["items"][0], "sources": [None]}]}):
        with patch("core.skill_runtime.call_chat_completion", return_value=json.dumps(bad)):
            result = run_skill_runtime(ROOT, {}, "mindseed-grow", "整理知识库", docs)
        assert not result["ok"] and result["issues"] and not result["previews"]


def test_obsidian_compat_is_opt_in_and_generated_links_stay_strict(vault):
    vault.install_note("raw/方案（3.0）.md", "# Versioned plan")
    attachment = vault.root / "attachments/报告.pdf"
    attachment.parent.mkdir()
    attachment.write_bytes(b"attachment fixture")
    text = "[[PDF] not a wiki](https://example.invalid) then [[方案（3.0）]] ![[报告.pdf]]"
    assert extract_wikilinks(text) == ["方案（3.0）", "报告.pdf"]
    vault.install_note("quicknote/links.md", text)
    strict = build_index(vault.cfg)
    assert resolve_link(strict, "报告.pdf") is None
    vault.cfg["link_resolution"] = {"obsidian_compat": True}
    compat = build_index(vault.cfg)
    assert resolve_link(compat, "方案（3.0）") == "raw/方案（3.0）.md"
    assert resolve_link(compat, "报告.pdf") == "attachments/报告.pdf"
    assert resolve_link(compat, "attachments/报告.pdf") == "attachments/报告.pdf"
    assert any("非规范" in x for x in steward.validate_markdown(compat, "[[方案（3.0）]]", ["raw/方案（3.0）.md"]))
    assert steward.healthcheck(strict, vault.cfg)["noncanonical_links"]
    assert not steward.healthcheck(compat, vault.cfg)["noncanonical_links"]
    assert strict.obsidian_compat is False
    assert compat.obsidian_compat is True


def test_attachments_do_not_escape_or_leak_runtime_files(vault):
    vault.cfg["link_resolution"] = {"obsidian_compat": True}
    vault.install_note(".openclaw/private.txt", "runtime data")
    vault.install_note("outputs/private.txt", "excluded data")
    first = vault.install_note("attachments/a/report.pdf", "one")
    vault.install_note("attachments/b/report.pdf", "two")
    index = build_index(vault.cfg)
    assert resolve_link(index, "report.pdf") is None
    assert resolve_link(index, "attachments/a/report.pdf") == first.relative_to(vault.root).as_posix()
    assert resolve_link(index, "private.txt") is None
    assert resolve_link(index, "../attachments/a/report.pdf") is None
    link = vault.root / "raw/external.pdf"
    try:
        link.symlink_to(ROOT / "requirements.txt")
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    assert resolve_link(build_index(vault.cfg), "external.pdf") is None


def test_legacy_repair_scripts_cannot_mutate_files():
    for script in ("fix_broken_links.py", "fix_broken_links_v2.py"):
        with patch("shutil.move") as move, patch("pathlib.Path.write_text") as write:
            namespace = runpy.run_path(str(ROOT / "scripts" / script))
            assert namespace["main"]() == 1
            move.assert_not_called()
            write.assert_not_called()


def test_new_configuration_errors_are_reported_not_silently_ignored(vault):
    from core.layout import validate_options
    assert validate_options(vault.cfg) == []
    for key, value in [("topics_dir", "../outside"), ("sources_dir", "/absolute"),
                       ("topics_dir", "C:/absolute"), ("topics_dir", "raw/topics"),
                       ("topics_dir", ".openclaw/topics")]:
        cfg = copy.deepcopy(vault.cfg)
        cfg["write"][key] = value
        assert validate_options(cfg)
    for key, value in [("max_total_source_chars", -1), ("exclude_files", "0-MOC.md")]:
        cfg = copy.deepcopy(vault.cfg)
        cfg["scan"][key] = value
        assert validate_options(cfg)
    cfg = copy.deepcopy(vault.cfg)
    cfg["link_resolution"] = {"obsidian_compat": "false"}
    assert validate_options(cfg)


def test_real_llm_topic_plan_enforces_config_budget_and_canonical_related(vault):
    custom_layout(vault)
    for name in ("a", "b", "c"):
        vault.install_note(f"raw/{name}.md", "# Media AI\n" + "media AI observations. " * 300)
    vault.cfg["scan"]["max_total_source_chars"] = 1100
    captured = []
    def model(cfg, prompt, payload):
        captured.append(payload)
        paths = [doc["path"] for doc in payload["documents"]]
        return json.dumps({"items": [{"title": "Real model content", "type": "topic-card", "status": "growing",
                    "stage": "candidate", "sources": paths, "summary": "Different from executor template.",
                    "confidence": "medium", "review_required": True, "related": ["[[a]]"]}]})
    with patch("core.skill_runtime.call_chat_completion", side_effect=model):
        proposal = steward.make_execution_plan(vault.cfg, "发现选题 media AI", use_llm=True, include_all=True)
    assert len(captured) == 1
    assert sum(len(d["content"]) for d in captured[0]["documents"]) <= 1100
    assert proposal["llm_runtime"]["writeback_used"] is True
    assert proposal["planned_pages"][0]["rel_path"].startswith("Notes/Knowledge.v2/topics/")
    assert proposal["llm_runtime"]["items"][0]["related"] == ["raw/a.md"]
    saved = steward.write_execution_plan(vault.cfg, proposal)
    assert proposal["planned_pages"][0]["object_id"]
    with pytest.raises(SystemExit, match="人工审核"):
        steward.command_apply_plan(vault.cfg, str(saved))
    assert not (vault.root / proposal["planned_pages"][0]["rel_path"]).exists()


def test_source_compiler_proposal_keeps_generation_source_hash(vault):
    custom_layout(vault)
    index = build_index(vault.cfg)
    result = steward.mvp_executor_plan(index, vault.cfg, "初始化知识库", "topic-research-compile",
                                      index.notes, {}, "compile", use_llm=False)
    page = result["planned_pages"][0]
    assert page["rel_path"].startswith("Notes/Knowledge.v2/sources/")
    assert page["retrieval_source_hashes"] == {"raw/a.md": index.by_rel["raw/a.md"].sha256}
    proposal = vault.plan(page)
    raw = vault.root / "raw/a.md"
    raw.write_bytes(raw.read_bytes() + b"\nHuman edit during model call")
    with pytest.raises(ObjectIdentityError, match="Retrieval source changed"):
        steward.write_execution_plan(vault.cfg, proposal)
    assert not (vault.root / page["rel_path"]).exists()
