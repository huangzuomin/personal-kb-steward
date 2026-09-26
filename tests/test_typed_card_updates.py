"""T8 typed-card update planner tests.

Uses the ACTUAL generators (generate_concepts / generate_cases /
generate_topic / real topic-research-compile source card) with deterministic
mock responses, then real bind_plan_objects + persisted read_note to establish
confirmed identity. Fixture writes simulate apply-like persistence; this is
not pipeline E2E. No network, no live providers, no private vault reads.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core import case_generation as casegen
from core import concept_generation as cg
from core import topic_generation as tg
from core.card_pipeline import collect_eligible_sources
from core.plan_objects import bind_plan_objects
from core.reconcile import _patch_header
from core.typed_card_updates import (
    GENERATED_END,
    GENERATED_START,
    prepare_typed_updates,
)
from core.vault import build_index, parse_frontmatter, read_note

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "concept-case"
# Sources live under raw/ inside the fixture vault so the scanner indexes them
# (retrieval validation requires index entries) and identity uses that path.
CONCEPT_REL = "raw/concept_source_01.md"


def file_sha(rel: str, root: Path | None = None) -> str:
    path = (root or ROOT) / rel
    return hashlib.sha256(path.read_bytes()).hexdigest()


class T8Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.cfg["knowledge_base"] = str(self.root)
        self.cfg["state_file"] = str(self.root / ".state.json")
        for key, filename in {
            "plans_dir": "plans", "runs_dir": "runs", "processed_index": "processed-index.json",
            "manual_review_queue": "manual-review/queue.jsonl", "backup_dir": "backups",
            "operation_log": "operation-log.jsonl",
        }.items():
            self.cfg["safety"][key] = str(self.root / ".openclaw" / filename)
        for folder in ("raw", "inbox", "quicknote", "wiki/topics", "wiki/concepts",
                       "wiki/cases", "wiki/sources"):
            (self.root / folder).mkdir(parents=True)
        # public synthetic fixtures copied INTO the temp vault under raw/
        for name in FIXTURES.glob("*.md"):
            shutil.copy(name, self.root / "raw" / name.name)

    # -- page spec helpers ------------------------------------------------
    def concept_note(self):
        raw = (self.root / CONCEPT_REL).read_bytes().decode("utf-8")
        return {"rel": CONCEPT_REL, "title": "concept_source_01.md", "body": raw,
                "metadata": {}, "source_text": raw,
                "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}

    def fake_provider(self, payload):
        def provider(cfg, system_prompt, user_payload):
            return json.dumps(payload, ensure_ascii=False)
        return provider

    def prepare(self, pages):
        return prepare_typed_updates(self.index, self.cfg, pages)

    def bind_and_install(self, proposal) -> dict:
        """apply-like fixture persistence: bind identities, then write the
        stamped content to disk (not pipeline E2E)."""
        plan = {"run_id": "t8-test", "task": "t8", "entry": "t8",
                "primary_skill": proposal["skill"],
                "planned_pages": [dict(proposal)], "manual_review": []}
        bind_plan_objects(self.index, plan)
        bound = plan["planned_pages"][0]
        target = self.root / bound["rel_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bound["content"], encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        return bound


PIPE = None


def _pipe():
    global PIPE
    if PIPE is None:
        import tests.test_card_pipeline_integration as pipe
        PIPE = pipe
    return PIPE


class ConceptCaseBase(T8Base):
    """Adds concept/case/topic page-spec helpers over ACTUAL generator output."""

    def setUp(self):
        super().setUp()
        self.pipe = _pipe()
        self.pipe.write_raw(self.root)
        self.index = build_index(self.cfg)

    def concept_spec(self, *, response=None, rel_path="wiki/concepts/review-trigger.md",
                     hashes=None, item=None, upstream=None):
        out = cg.generate_concepts(
            [self.concept_note()], self.cfg,
            call_provider=self.fake_provider(response or self.concept_response()),
            now="2026-09-21")
        assert out["state"] == "full", out
        all_hashes = {CONCEPT_REL: file_sha(CONCEPT_REL, self.root)}
        if upstream:
            all_hashes.update(upstream)
        if hashes:
            all_hashes.update(hashes)
        return {"content": out["pages"][0]["content"],
                "rel_path": rel_path, "operation": "create",
                "sources": [CONCEPT_REL], "retrieval_source_hashes": all_hashes,
                "skill": "t8-test", "item": item if item is not None else dict(out["items"][0])}

    def concept_response(self, source_rel=CONCEPT_REL):
        Q_DEF = "触发条件必须引用一条已经存在的卡片或问题"
        Q_BOUNDARY = "定时提醒只依赖时间，回顾触发器依赖已有知识对象"
        Q_ALIAS = "部分团队把它叫做复习钩子，含义与回顾触发器相同"
        Q_STAT = "绑定回顾触发器的卡片 30 天后再访问率约为 62%"
        return {
            "concept_found": True,
            "concepts": [{
                "name": "回顾触发器", "aliases": ["复习钩子"],
                "definition_claim": "回顾触发器必须引用已存在的卡片或问题，而非单纯时间点",
                "explanation": "来源将其与普通日历提醒区分开。",
                "confidence": "medium",
                "source_defined_boundary": [
                    {"evidence_claim": "来源把回顾触发器与定时提醒区分：定时提醒只依赖时间"}],
                "suggested_interpretation": [
                    {"text": "该机制可能提高卡片长期再访问率",
                     "supporting_claim": "绑定回顾触发器的卡片30天后再访问率自报约62%（未独立核实）",
                     "supporting_context": "来源记录了自报数字"}],
                "judgments": [
                    {"statement": "回顾触发器必须引用已存在的卡片或问题，而非单纯时间点",
                     "kind": "fact", "confidence": "medium",
                     "evidence": [{"source": source_rel, "quote": Q_DEF, "relation": "supports"}]},
                    {"statement": "来源把回顾触发器与定时提醒区分：定时提醒只依赖时间",
                     "kind": "fact", "confidence": "medium",
                     "evidence": [{"source": source_rel, "quote": Q_BOUNDARY, "relation": "supports"}]},
                    {"statement": "复习钩子是该概念的来源内别名",
                     "kind": "inference", "confidence": "medium",
                     "evidence": [{"source": source_rel, "quote": Q_ALIAS, "relation": "supports"}]},
                    {"statement": "绑定回顾触发器的卡片30天后再访问率自报约62%（未独立核实）",
                     "kind": "fact", "confidence": "medium",
                     "evidence": [{"source": source_rel, "quote": Q_STAT, "relation": "supports"}]},
                ],
                "related": [], "pending_paths": [],
            }],
            "provenance_map": [{"rel": source_rel, "provenance": "合成概念素材",
                                "limitations": ["数字为自报，未独立核对"]}],
            "shared_provenance": [],
        }

    def case_spec(self, rel_path="wiki/cases/booklist.md", *, override=None,
                  level="project"):
        pipe = self.pipe
        raw = (self.root / pipe.RAW_REL).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        note = {"rel": pipe.RAW_REL, "title": "合成文档", "body": raw.decode("utf-8"),
                "metadata": {}, "source_text": raw.decode("utf-8"), "source_sha256": sha}
        response = pipe.case_response()
        if override:
            override(response)
        gen = casegen.generate_cases([note], self.cfg,
                                     call_provider=self.fake_provider(response))
        assert gen["state"] == "full", gen
        item = dict(gen["items"][0])
        if level != "project":
            item["card_level"] = level
        return {"content": gen["pages"][0]["content"], "item": item,
                "rel_path": rel_path, "operation": "create",
                "sources": [pipe.RAW_REL],
                "retrieval_source_hashes": {pipe.RAW_REL: sha},
                "skill": "case-story-bank-builder"}

    def topic_spec(self, rel_path="wiki/topics/q.md", question="书单绑定活动在什么条件下失效？"):
        pipe = self.pipe
        raw = (self.root / pipe.RAW_REL).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        note = {"rel": pipe.RAW_REL, "title": "合成文档", "body": raw.decode("utf-8"),
                "metadata": {}, "source_text": raw.decode("utf-8"), "source_sha256": sha}
        response = {
            "topic_viable": True, "title": "专题", "theme_boundary": "边界",
            "summary": "小结", "confidence": "low",
            "source_map": [{"rel": pipe.RAW_REL, "provenance": "合成", "limitations": []}],
            "shared_provenance": [],
            "judgments": [{"statement": "来源把回顾触发器绑定到已有卡片",
                           "kind": "fact", "confidence": "low",
                           "evidence": [{"source": pipe.RAW_REL, "quote": pipe.Q_DEF,
                                         "relation": "supports"}]}],
            "tensions": [], "evidence_gaps": [{"gap": "缺对照组"}],
            "next_actions": [{"action": "补充对照组记录", "priority": 1,
                              "addresses_gap": "缺对照组"}],
            "related": [], "pending_paths": [],
        }
        gen = tg.generate_topic(question, {"topic_generation": {"min_full_sources": 3}},
                                [note], call_provider=self.fake_provider(response))
        assert gen["state"] in ("full", "stub"), gen
        return {"content": gen["page"]["content"], "item": None,
                "rel_path": rel_path, "operation": "create",
                "sources": [pipe.RAW_REL],
                "retrieval_source_hashes": {pipe.RAW_REL: sha},
                "skill": "topic-research-compile"}

    def parse_card_state(self, content: str) -> dict:
        meta, _ = parse_frontmatter(content)
        state = meta["card_state"]
        return json.loads(state) if isinstance(state, str) else state


class TestActualShapes(ConceptCaseBase):
    """Root probes 5/6: the helper accepts ACTUAL generator outputs."""

    def test_actual_case_shape_accepted(self):
        spec = self.case_spec()
        out = self.prepare([spec])
        assert out["pages"], out["outcomes"]
        assert out["outcomes"][0]["outcome"] == "create"
        proposal = out["pages"][0]
        # role/kind is part of the semantic identity
        semantic = proposal["card_update_state"]["semantic"]
        assert semantic["mechanism_role"] == "reusable"
        assert semantic["mechanism_kind"] == "fact"

    def test_actual_source_card_accepted_without_item(self):
        pipe = _pipe()
        source_rel = pipe.compile_source_card(self.root, self.cfg)
        self.index = build_index(self.cfg)
        note = self.index.by_rel[pipe.RAW_REL]
        raw = (self.root / note.rel).read_bytes()
        meta, _ = parse_frontmatter(raw.decode("utf-8"))
        spec = {"content": (self.root / source_rel).read_text(encoding="utf-8"),
                "item": {"type": "source-note", "source_hashes": {note.rel: note.sha256}},
                "rel_path": "wiki/sources/actual-new.md", "operation": "create",
                "sources": [note.rel],
                "retrieval_source_hashes": {note.rel: note.sha256},
                "skill": "topic-research-compile"}
        out = self.prepare([spec])
        assert out["outcomes"][0]["outcome"] == "create", out["outcomes"]
        semantic = out["pages"][0]["card_update_state"]["semantic"]
        assert semantic == {"kind": "source", "original": note.rel}

    def test_source_unit_tamper_blocked(self):
        pipe = _pipe()
        source_rel = pipe.compile_source_card(self.root, self.cfg)
        text = (self.root / source_rel).read_text(encoding="utf-8")
        # tamper a persisted unit coordinate
        tampered = text.replace('"verified": true', '"verified": false', 1)
        (self.root / "wiki/sources/tampered.md").write_text(tampered, encoding="utf-8",
                                                            newline="")
        self.index = build_index(self.cfg)
        note = self.index.by_rel[pipe.RAW_REL]
        spec = {"content": tampered, "item": {"type": "source-note"},
                "rel_path": "wiki/sources/tampered.md", "operation": "create",
                "sources": [note.rel],
                "retrieval_source_hashes": {note.rel: note.sha256},
                "skill": "topic-research-compile"}
        out = self.prepare([spec])
        assert out["pages"] == []
        assert "info_unit" in out["outcomes"][0]["reason"]

    def test_source_update_keeps_collector_eligible_after_apply_like_persistence(self):
        """A source update must synchronize outer and inner source hashes.

        The candidate cards come from the real topic-research-compile renderer;
        bind_and_install is the fixture's apply-like persistence seam. The
        final assertion exercises the downstream persisted-source collector.
        """
        pipe = _pipe()
        source_rel = pipe.compile_source_card(self.root, self.cfg)
        source_candidate = (self.root / source_rel).read_text(encoding="utf-8")
        # The renderer's direct output is only the candidate input. Remove it
        # before rebuilding the index so the typed helper owns the target from
        # its first apply-like persistence onward.
        (self.root / source_rel).unlink()
        self.index = build_index(self.cfg)
        source_note = self.index.by_rel[pipe.RAW_REL]
        first_spec = {
            "content": source_candidate,
            "item": {"type": "source-note",
                     "source_hashes": {pipe.RAW_REL: source_note.sha256}},
            "rel_path": source_rel, "operation": "create",
            "sources": [pipe.RAW_REL],
            "retrieval_source_hashes": {pipe.RAW_REL: source_note.sha256},
            "skill": "topic-research-compile",
        }
        first = self.prepare([first_spec])
        assert first["outcomes"][0]["outcome"] == "create", first["outcomes"]
        bound = self.bind_and_install(first["pages"][0])

        raw_path = self.root / pipe.RAW_REL
        raw_path.write_text(raw_path.read_text(encoding="utf-8")
                            + "\n新增的合成来源段落。\n",
                            encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        new_hash = self.index.by_rel[pipe.RAW_REL].sha256

        # The real renderer writes its deterministic target. Preserve the
        # installed old card while capturing the fresh candidate content.
        old_card_bytes = (self.root / source_rel).read_bytes()
        candidate_rel = pipe.compile_source_card(self.root, self.cfg)
        assert candidate_rel == source_rel
        candidate_content = (self.root / candidate_rel).read_text(encoding="utf-8")
        (self.root / source_rel).write_bytes(old_card_bytes)
        self.index = build_index(self.cfg)

        update_spec = {
            "content": candidate_content,
            "item": {"type": "source-note",
                     "source_hashes": {pipe.RAW_REL: new_hash}},
            "rel_path": source_rel, "operation": "create",
            "sources": [pipe.RAW_REL],
            "retrieval_source_hashes": {pipe.RAW_REL: new_hash},
            "skill": "topic-research-compile",
        }
        update = self.prepare([update_spec])
        assert update["outcomes"][0]["outcome"] == "update", update["outcomes"]
        updated = self.bind_and_install(update["pages"][0])
        meta, _ = parse_frontmatter(
            (self.root / updated["rel_path"]).read_text(encoding="utf-8"))
        assert meta["source_hashes"] == {pipe.RAW_REL: new_hash}
        assert meta["card_state"]["analysis"]["source_hashes"] == {
            pipe.RAW_REL: new_hash}

        collected = collect_eligible_sources(self.index, self.cfg)
        assert collected["rejected"] == [], collected["rejected"]
        assert collected["notes"][0]["source_sha256"] == new_hash
        assert collected["source_note_paths"][pipe.RAW_REL] == [updated["rel_path"]]
        assert collected["upstream_hashes"][updated["rel_path"]] == \
            hashlib.sha256((self.root / updated["rel_path"]).read_bytes()).hexdigest()

    def test_malformed_recorded_evidence_blocks_only_that_page(self):
        """Malformed persisted evidence cannot abort a sibling proposal."""
        installed = self.bind_and_install(self.prepare(
            [self.concept_spec()])["pages"][0])
        path = self.root / installed["rel_path"]
        text = path.read_text(encoding="utf-8")
        malformed = dict(installed["card_update_state"])
        malformed["evidence"] = [["raw/concept_source_01.md", {"quote": "bad"}]]
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.startswith("card_update_state:"):
                eol = "\r\n" if line.endswith("\r\n") else "\n"
                lines[i] = ("card_update_state: "
                            + json.dumps(malformed, ensure_ascii=False) + eol)
                break
        else:
            raise AssertionError("fixture card missing card_update_state")
        path.write_text("".join(lines), encoding="utf-8", newline="")
        self.index = build_index(self.cfg)

        result = self.prepare([self.concept_spec(),
                               self.case_spec(rel_path="wiki/cases/sibling.md")])
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "card_update_state.evidence" in result["outcomes"][0]["reason"]
        assert result["outcomes"][1]["outcome"] == "create", result["outcomes"]
        assert len(result["pages"]) == 1
        assert result["pages"][0]["rel_path"] == "wiki/cases/sibling.md"


class TestCreateNoopUpdate(ConceptCaseBase):
    def test_candidate_bool_version_is_blocked(self):
        spec = self.concept_spec()
        meta, _ = parse_frontmatter(spec["content"])
        state = meta["card_state"]
        state = json.loads(state) if isinstance(state, str) else state
        state["version"] = True
        spec["content"] = _patch_header(spec["content"], {"card_state": state})
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "精确整数 1" in result["outcomes"][0]["reason"]

    def test_existing_bool_update_version_is_blocked(self):
        bound = self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])
        path = self.root / bound["rel_path"]
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        state = meta["card_update_state"]
        state = json.loads(state) if isinstance(state, str) else state
        state["version"] = True
        path.write_text(_patch_header(path.read_text(encoding="utf-8"),
                                      {"card_update_state": state}),
                        encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec()])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "card_update_state.version" in result["outcomes"][0]["reason"]

    def test_forged_compiled_quote_is_blocked(self):
        spec = self.concept_spec()
        meta, _ = parse_frontmatter(spec["content"])
        state = meta["card_state"]
        state = json.loads(state) if isinstance(state, str) else state
        state["claims"][0]["evidence"][0]["quote"] = "THIS QUOTE DOES NOT EXIST"
        spec["content"] = _patch_header(spec["content"], {"card_state": state})
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "core.claims" in result["outcomes"][0]["reason"]

    def test_create_then_identical_is_noop(self):
        spec = self.concept_spec()
        spec["root_probe_annotation"] = {"keep": True}
        result = self.prepare([spec])
        assert len(result["pages"]) == 1
        proposal = result["pages"][0]
        assert result["outcomes"][0]["outcome"] == "create"
        # proposal envelope: item/review metadata retained, aliases agree
        assert proposal["item"]["type"] == "concept-page"
        assert proposal["review_required"] is True
        assert proposal["rel_path"] == proposal["target"] == proposal["canonical_path"]
        assert proposal["analysis_mode"] == "llm"
        assert proposal["origin"]["concept_name"] == "回顾触发器"
        assert proposal["root_probe_annotation"] == {"keep": True}
        assert proposal["content"].count(GENERATED_START) == 1
        assert "object_id:" not in proposal["content"]

        bound = self.bind_and_install(proposal)
        note = read_note(self.root / bound["rel_path"], self.root)
        assert note.object_id == bound["object_id"]

        result2 = self.prepare([self.concept_spec()])
        assert result2["pages"] == []
        assert result2["outcomes"][0]["outcome"] == "noop"
        assert result2["outcomes"][0]["chosen_target"] == bound["rel_path"]
        assert result2["issues"] == []
        note2 = read_note(self.root / bound["rel_path"], self.root)
        assert (note2.object_id, note2.revision) == (bound["object_id"], bound["revision"])

    def test_identity_preserved_across_full_update_cycle(self):
        # create -> bind -> apply-like -> update -> identical repeat:
        # object_id/revision stable, second identical run is noop
        bound = self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])
        response = self.concept_response()
        response["concepts"][0]["judgments"][2]["evidence"].append(
            {"source": CONCEPT_REL, "quote": "复习钩子", "relation": "supports"})
        update = self.prepare([self.concept_spec(response=response)])["pages"][0]
        bound2 = self.bind_and_install(update)
        assert (bound2["object_id"], bound2["revision"]) == \
            (bound["object_id"], bound["revision"] + 1)
        result = self.prepare([self.concept_spec(response=response)])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "noop"
        assert result["issues"] == []
        note = read_note(self.root / bound2["rel_path"], self.root)
        assert (note.object_id, note.revision) == (bound["object_id"], bound["revision"] + 1)

    def test_additive_evidence_reviewed_update_preserves_identity(self):
        bound = self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])
        response = self.concept_response()
        response["concepts"][0]["judgments"][2]["evidence"].append(
            {"source": CONCEPT_REL, "quote": "复习钩子", "relation": "supports"})
        update_spec = self.concept_spec(response=response)
        update_spec["root_probe_annotation"] = {"keep": True}
        update = self.prepare([update_spec])["pages"][0]
        assert update["operation"] == "update"
        assert update["root_probe_annotation"] == {"keep": True}
        assert update["base_object_id"] == bound["object_id"]
        assert update["base_revision"] == bound["revision"]
        bound2 = self.bind_and_install(update)
        note = read_note(self.root / bound2["rel_path"], self.root)
        assert note.object_id == bound["object_id"]
        assert note.revision == bound["revision"] + 1
        state = note.metadata["card_state"]
        if isinstance(state, str):
            state = json.loads(state)
        alias = next(c for c in state["claims"] if c["statement"].startswith("复习钩子"))
        assert len(alias["evidence"]) == 2  # replaced in full, not relabeled

    def test_source_raw_version_change_fully_replaces_region(self):
        bound = self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])
        source = self.root / CONCEPT_REL
        text = source.read_text(encoding="utf-8")
        source.write_text(text.replace(
            "绑定回顾触发器的卡片 30 天后再访问率约为 62%",
            "绑定回顾触发器的卡片 30 天后再访问率约为 70%"),
            encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        update = self.prepare([self.concept_spec()])["pages"][0]
        assert update["operation"] == "update"
        state = update["card_update_state"]
        assert ("raw/concept_source_01.md",
                "绑定回顾触发器的卡片 30 天后再访问率约为 62%") not in \
            [tuple(p) for p in state["evidence"]]
        # outer machine-owned hash synchronized with the fresh candidate
        meta, _ = parse_frontmatter(update["content"])
        assert meta["source_hashes"][CONCEPT_REL] == file_sha(CONCEPT_REL, self.root)
        assert meta["source_hashes"] == state["source_hashes"]

    def test_stale_original_hash_blocks_without_refresh(self):
        spec = self.concept_spec()
        source = self.root / CONCEPT_REL
        source.write_text(source.read_text(encoding="utf-8") + "\n追加段落",
                          encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "捕获索引" in result["outcomes"][0]["reason"]

    def test_stale_upstream_hash_blocks(self):
        upstream_rel = "wiki/sources/upstream.md"
        (self.root / upstream_rel).write_text("# upstream\n", encoding="utf-8",
                                               newline="")
        spec = self.concept_spec(upstream={upstream_rel: file_sha(upstream_rel, self.root)})
        (self.root / upstream_rel).write_text("# upstream\nchanged\n",
                                              encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"

    def test_forged_item_hash_blocked(self):
        spec = self.concept_spec()
        spec["item"]["source_hashes"][CONCEPT_REL] = "0" * 64
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "伪造或过期" in result["outcomes"][0]["reason"]


class TestReplacementSafety(ConceptCaseBase):
    def _installed(self):
        return self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])

    def test_outside_manual_text_and_custom_yaml_preserved(self):
        bound = self._installed()
        path = self.root / bound["rel_path"]
        text = path.read_text(encoding="utf-8")
        text = text.replace('title: "回顾触发器"', 'title: "我的回顾触发器笔记"', 1)
        text = text.replace("review_required: true",
                            "review_required: true\nowner:\n  name: 张三\n  since: 2026-01-01",
                            1)
        text = text.rstrip("\n") + "\n\n手写补充：下次复查这条。\n"
        path.write_text(text, encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        response = self.concept_response()
        response["concepts"][0]["judgments"][2]["evidence"].append(
            {"source": CONCEPT_REL, "quote": "复习钩子", "relation": "supports"})
        update = self.prepare([self.concept_spec(response=response)])["pages"][0]
        assert update["operation"] == "update"
        assert "手写补充：下次复查这条。" in update["content"]
        assert "owner:" in update["content"] and "name: 张三" in update["content"]
        assert "我的回顾触发器笔记" in update["content"]  # display title preserved
        def after_header(segment: str) -> str:
            return segment[_header_of(segment):]
        assert after_header(text[:text.index(GENERATED_START)]) == \
            after_header(update["content"][:update["content"].index(GENERATED_START)])
        old_end = text.index(GENERATED_END) + len(GENERATED_END)
        assert text[old_end:] == update["content"][
            update["content"].index(GENERATED_END) + len(GENERATED_END):]
        # custom multiline YAML survived value rewrites byte-for-byte
        assert "owner:\n  name: 张三\n  since: 2026-01-01" in update["content"]

    def test_source_version_change_with_outside_manual_text_blocks(self):
        bound = self._installed()
        path = self.root / bound["rel_path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(text.rstrip("\n") + "\n手写事实：某个旧版本的笔记。\n",
                        encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        source = self.root / CONCEPT_REL
        source.write_text(source.read_text(encoding="utf-8").replace(
            "绑定回顾触发器的卡片 30 天后再访问率约为 62%", "再访问率约为 70%"),
            encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec()])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "手写事实" in result["outcomes"][0]["reason"]

    def test_added_source_with_outside_manual_text_allows_update(self):
        # a newly ADDED source is not a version change of an old source:
        # reviewed update proceeds and preserves outside hand text
        bound = self._installed()
        path = self.root / bound["rel_path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(text.rstrip("\n") + "\n手写补充：保留我。\n",
                        encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        pipe = self.pipe
        raw = (self.root / pipe.RAW_REL).read_bytes()
        spec = self.concept_spec(upstream={pipe.RAW_REL: hashlib.sha256(raw).hexdigest()})
        result = self.prepare([spec])
        assert result["outcomes"][0]["outcome"] == "update", result["outcomes"]
        update = result["pages"][0]
        assert "手写补充：保留我。" in update["content"]

    def test_machine_owned_outer_fields_synced_on_update(self):
        # update replaces card_state AND syncs outer machine-owned fields
        # (status/quality_flags/related/pins) with the fresh candidate; an
        # obsolete pinned dependency is not silently retained
        bound = self.bind_and_install(self.prepare(
            [self.concept_spec(upstream={"raw/case_source_02.md":
                                         file_sha("raw/case_source_02.md", self.root)})])["pages"][0])
        # the obsolete upstream pin lives in card_update_state.source_hashes
        assert "raw/case_source_02.md" in bound["card_update_state"]["source_hashes"]
        # new run drops the upstream pin entirely
        update = self.prepare([self.concept_spec()])["pages"][0]
        assert update["operation"] == "update"
        assert "raw/case_source_02.md" not in update["card_update_state"]["source_hashes"]
        update_meta, _ = parse_frontmatter(update["content"])
        assert set(update_meta["source_hashes"]) == {CONCEPT_REL}
        assert update_meta["review_required"] in (True, "true")

    def test_inside_block_edit_blocks(self):
        bound = self._installed()
        path = self.root / bound["rel_path"]
        text = path.read_text(encoding="utf-8")
        edited = text.replace("触发条件必须引用一条已经存在的卡片或问题",
                              "被人工改过的句子", 1)
        assert edited != text
        path.write_text(edited, encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec()])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "人工修改" in result["outcomes"][0]["reason"]

    def test_card_state_frontmatter_tamper_blocks(self):
        bound = self._installed()
        path = self.root / bound["rel_path"]
        text = path.read_text(encoding="utf-8")
        edited = text.replace('"statement": "回顾触发器必须引用已存在的卡片或问题，而非单纯时间点"',
                              '"statement": "被人工改过的句子"', 1)
        assert edited != text
        path.write_text(edited, encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec()])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "card_state" in result["outcomes"][0]["reason"]

    def test_bom_and_crlf_outside_block_preserved(self):
        proposal = self.prepare([self.concept_spec()])["pages"][0]
        bound = self.bind_and_install(proposal)
        path = self.root / bound["rel_path"]
        raw = path.read_bytes()
        if not raw.startswith(b"\xef\xbb\xbf"):
            raw = b"\xef\xbb\xbf" + raw
        raw += "手写补充（CRLF）：\r\n下一行手写内容\r\n".encode("utf-8")
        path.write_bytes(raw)
        self.index = build_index(self.cfg)
        response = self.concept_response()
        response["concepts"][0]["judgments"][2]["evidence"].append(
            {"source": CONCEPT_REL, "quote": "复习钩子", "relation": "supports"})
        update = self.prepare([self.concept_spec(response=response)])["pages"][0]
        assert update["operation"] == "update"
        assert update["content"].startswith("﻿")
        assert "手写补充（CRLF）：\r\n下一行手写内容\r\n" in update["content"]
        old = raw.decode("utf-8")
        old_end = old.index(GENERATED_END) + len(GENERATED_END)
        assert old[old_end:] == update["content"][
            update["content"].index(GENERATED_END) + len(GENERATED_END):]

    def test_raw_input_bytes_never_touched(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.prepare([self.concept_spec()])
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        assert before == after


def _header_of(text: str) -> int:
    import re
    match = re.match(r"\A(?:﻿)?---[^\S\r\n]*\r?\n(.*?)^---[^\S\r\n]*(?:\r?\n|\Z)",
                     text, re.M | re.S)
    return match.end()


class TestIdentityRules(ConceptCaseBase):
    def test_legacy_card_same_title_never_adopted(self):
        legacy_rel = "wiki/concepts/review-trigger.md"
        (self.root / legacy_rel).write_text(
            "---\ntitle: \"回顾触发器\"\ntype: concept-page\nstatus: raw\nstage: draft\n"
            "sources: []\n---\n# 回顾触发器\n旧的手写概念页\n",
            encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec(rel_path=legacy_rel)])
        assert result["outcomes"][0]["outcome"] == "create"
        assert result["pages"][0]["rel_path"] != legacy_rel
        assert "不同身份" in result["outcomes"][0]["reason"]
        assert "旧的手写概念页" in (self.root / legacy_rel).read_text(encoding="utf-8")

    def test_same_title_different_mechanism_not_merged(self):
        def override(response):
            case = response["cases"][0]
            case["reusable_mechanism_claim"] = "另一种机制陈述"
            for j in case["judgments"]:
                if j["statement"].startswith("书单绑定依赖"):
                    j["statement"] = "另一种机制陈述"
        spec_a = self.case_spec(rel_path="wiki/cases/x.md")
        spec_b = self.case_spec(rel_path="wiki/cases/x.md", override=override)
        result = self.prepare([spec_a, spec_b])
        assert len(result["pages"]) == 2  # both kept, distinct stable paths
        assert len({p["rel_path"] for p in result["pages"]}) == 2

    def test_multiple_identity_matches_blocked(self):
        proposal = self.prepare([self.concept_spec()])["pages"][0]
        self.bind_and_install(proposal)
        note = read_note(self.root / proposal["rel_path"], self.root)
        dup_rel = "wiki/concepts/review-trigger-dup.md"
        (self.root / dup_rel).write_text(
            note.path.read_text(encoding="utf-8"), encoding="utf-8", newline="")
        self.index = build_index(self.cfg)
        result = self.prepare([self.concept_spec(rel_path="wiki/concepts/another.md")])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "歧义" in result["outcomes"][0]["reason"]

    def test_batch_identical_candidates_dedupe(self):
        spec = self.concept_spec()
        result = self.prepare([spec, dict(spec)])
        assert len(result["pages"]) == 1
        assert result["outcomes"][1]["outcome"] == "noop"
        assert "同批次" in result["outcomes"][1]["reason"]

    def test_batch_same_name_different_pins_stay_distinct(self):
        # identical semantics but different upstream pins: NOT deduped
        # (different source versions/dependencies), stable distinct paths
        pipe = self.pipe
        pipe.write_raw(self.root)
        spec_a = self.concept_spec(upstream={pipe.RAW_REL: file_sha(pipe.RAW_REL, self.root)},
                                   rel_path="wiki/concepts/x.md")
        spec_b = self.concept_spec(rel_path="wiki/concepts/x.md")
        result = self.prepare([spec_a, spec_b])
        assert len(result["pages"]) == 2
        assert len({p["rel_path"] for p in result["pages"]}) == 2
        pins = [sorted(p["retrieval_source_hashes"]) for p in result["pages"]]
        assert pins[0] != pins[1] or set(pins[0]) != set(pins[1])

    def test_disjoint_evidence_same_semantics_blocked(self):
        bound = self.bind_and_install(self.prepare([self.concept_spec()])["pages"][0])
        # same definition/name but ALL evidence moved to an independent copy:
        # the generator compiles against the copy, producing identical
        # semantics with fully disjoint evidence paths
        other = "raw/independent-copy.md"
        (self.root / other).write_bytes((self.root / CONCEPT_REL).read_bytes())
        self.index = build_index(self.cfg)
        raw = (self.root / other).read_bytes().decode("utf-8")
        note = {"rel": other, "title": "independent-copy.md", "body": raw,
                "metadata": {}, "source_text": raw,
                "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}
        out = cg.generate_concepts([note], self.cfg,
                                   call_provider=self.fake_provider(
                                       self.concept_response(source_rel=other)),
                                   now="2026-09-21")
        assert out["state"] == "full", out
        sha = file_sha(other, self.root)
        spec = {"content": out["pages"][0]["content"], "item": dict(out["items"][0]),
                "rel_path": "wiki/concepts/review-trigger.md", "operation": "create",
                "sources": [other], "retrieval_source_hashes": {other: sha},
                "skill": "t8-test"}
        result = self.prepare([spec])
        assert result["pages"] == [], result["outcomes"]
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "证据完全不相交" in result["outcomes"][0]["reason"]

    def test_marker_collision_in_generated_text_blocks(self):
        spec = self.concept_spec()
        spec["content"] = spec["content"] + f"\n{GENERATED_START}\n"
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"

    def test_missing_bound_fields_blocked_not_inferred(self):
        spec = self.concept_spec()
        del spec["item"]["definition_claim"]
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"
        assert "人工复核" in result["outcomes"][0]["reason"]

    def test_missing_item_blocked_for_concept(self):
        spec = self.concept_spec()
        del spec["item"]
        result = self.prepare([spec])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"

    def test_target_outside_type_dir_blocked(self):
        result = self.prepare([self.concept_spec(rel_path="wiki/cases/misplaced.md")])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"

    def test_path_traversal_blocked(self):
        result = self.prepare([self.concept_spec(rel_path="../escape.md")])
        assert result["pages"] == []
        assert result["outcomes"][0]["outcome"] == "blocked"

    def test_no_links_to_future_candidates(self):
        proposal = self.prepare([self.concept_spec()])["pages"][0]
        _, body = parse_frontmatter(proposal["content"])
        assert "[[wiki/cases/" not in body
        assert "[[wiki/concepts/" not in body


class TestSourceCaseTopicIdentities(ConceptCaseBase):
    def test_source_note_identity_from_persisted_state(self):
        pipe = self.pipe
        source_rel = pipe.compile_source_card(self.root, self.cfg)
        self.index = build_index(self.cfg)
        note = self.index.by_rel[pipe.RAW_REL]
        spec = {"content": (self.root / source_rel).read_text(encoding="utf-8"),
                "item": {"type": "source-note", "source_hashes": {note.rel: note.sha256}},
                "rel_path": "wiki/sources/synthetic.md", "operation": "create",
                "sources": [note.rel],
                "retrieval_source_hashes": {note.rel: note.sha256},
                "skill": "topic-research-compile"}
        result = self.prepare([spec])
        assert result["outcomes"][0]["outcome"] == "create"
        semantic = result["pages"][0]["card_update_state"]["semantic"]
        assert semantic == {"kind": "source", "original": note.rel}

    def test_topic_identity_uses_persisted_question(self):
        spec = self.topic_spec()
        result = self.prepare([spec])
        assert result["outcomes"][0]["outcome"] == "create"
        semantic = result["pages"][0]["card_update_state"]["semantic"]
        assert semantic == {"kind": "topic",
                            "question": "书单绑定活动在什么条件下失效？"}
        # different question => different identity, not merged
        spec_b = self.topic_spec(rel_path="wiki/topics/q2.md",
                                 question="另一个研究问题？")
        result2 = self.prepare([spec, spec_b])
        assert len(result2["pages"]) == 2

    def test_case_project_vs_mechanism_distinct_identity(self):
        project = self.case_spec(rel_path="wiki/cases/a.md")
        mech = self.case_spec(rel_path="wiki/cases/b.md", level="mechanism")
        result = self.prepare([project, mech])
        assert len(result["pages"]) == 2
        digests = {p["card_update_state"]["semantic_digest"] for p in result["pages"]}
        assert len(digests) == 2  # levels never collapse
        roles = {p["card_update_state"]["semantic"]["mechanism_role"]
                 for p in result["pages"]}
        assert "reusable" in roles

    def test_case_role_and_kind_in_identity(self):
        spec = self.case_spec()
        semantic = self.prepare([spec])["pages"][0]["card_update_state"]["semantic"]
        assert semantic["mechanism_kind"] == "fact"
        assert semantic["mechanism_role"] == "reusable"


if __name__ == "__main__":
    unittest.main()
