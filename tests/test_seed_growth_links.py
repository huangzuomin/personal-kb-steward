"""M1-seed growth-direction specificity and relation-link honesty."""
import hashlib
import json
import re
from pathlib import Path

import pytest

from core import atomic_seed, card_relations
from core.card_contracts import validate_card_item
from core.retrieval import Retriever
from core.seed_updates import prepare_seed_updates
from core.skill_executor import execute_skill, load_executor
from core.vault import build_index, parse_frontmatter

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "atomic-seed"
DIALOGUE = (FIXTURES / "source-dialogue.md").read_bytes().decode("utf-8")


def _kb(tmp_path: Path) -> dict:
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    kb = tmp_path / "kb"
    kb.mkdir()
    cfg["knowledge_base"] = str(kb)
    cfg["state_file"] = str(kb / ".state.json")
    for key in ("plans_dir", "runs_dir", "processed_index", "manual_review_queue",
                "backup_dir", "operation_log"):
        cfg["safety"][key] = str(kb / ".openclaw" / key)
    return cfg


def install(cfg, rel: str, text: str) -> None:
    target = Path(cfg["knowledge_base"]) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes: no platform newline translation, so the on-disk bytes equal
    # the text the generator verified (Windows write_text would add CRLF).
    target.write_bytes(text.encode("utf-8"))


def install_dialogue(cfg) -> None:
    """Install the source file with its REAL bytes so the vault index hash
    matches the snapshot the generator verified (placeholder text must not
    disagree with provenance)."""
    install(cfg, "quicknote/dialogue.md", DIALOGUE)


def make_item(statement="检索机死机影响读者找书", unit_ids=(1, 5), title=None) -> dict:
    note = {"rel": "quicknote/dialogue.md", "title": "对话", "source_text": DIALOGUE}
    units = atomic_seed.information_units(note)
    response = {"thoughts": [{"title": title or statement[:20], "kind": "assertion",
                              "statement": statement, "unit_ids": list(unit_ids),
                              "growth_directions": [{"action": "核对死机频率统计。", "basis": "回应复现未知。"}],
                              "negative_scope": ["不评估厂商选型。"]}]}
    items, _, _ = atomic_seed.generate_atomic_items(
        [note], model_fn=lambda s, p: json.dumps(response, ensure_ascii=False))
    return items[0]


def atomic_context(cfg, **extra):
    raw = (FIXTURES / "source-dialogue.md").read_bytes()
    note = {"rel": "quicknote/dialogue.md", "title": "对话", "source_text": DIALOGUE,
            "source_sha256": hashlib.sha256(raw).hexdigest()}
    return {"notes": [note], "config": cfg, "use_llm": False, **extra}


# ── Relation search honesty ──────────────────────────────────────────────────

def test_relations_not_attempted_without_index(tmp_path):
    report = card_relations.relation_candidates(make_item(), {}, None, None)
    assert report["link_search"] == "not_attempted"
    assert report["related"] == [] and "未尝试" in report["relation_explanations"][0]


def test_relations_no_match_valid_candidate_and_pending(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    install(cfg, "wiki/seeds/旧卡.md", "---\ntitle: 完全无关的主题\ntype: seed-card\n---\n无关正文。")
    index = build_index(cfg)
    item = make_item()
    report = card_relations.relation_candidates(item, cfg, index, Retriever(cfg, index))
    # An unrelated seed exists but shares nothing: honest no-match, no first-N links.
    assert report["link_search"] == "no_match" and report["related"] == []

    install(cfg, "wiki/seeds/检索死机观察.md",
            "---\ntitle: 检索机死机观察\ntype: seed-card\n---\n检索机死机影响读者找书。")
    index = build_index(cfg)
    report = card_relations.relation_candidates(item, cfg, index, Retriever(cfg, index))
    assert report["link_search"] == "candidates_found"
    assert "wiki/seeds/检索死机观察.md" in report["related"]
    assert any("关键词命中" in e for e in report["relation_explanations"])

    item["pending_links"] = ["wiki/seeds/不存在.md"]
    report = card_relations.relation_candidates(item, cfg, index, Retriever(cfg, index))
    assert "wiki/seeds/不存在.md" in report["pending_links"]  # unverifiable target stays pending
    assert all(p not in report["related"] for p in report["pending_links"])


def test_same_title_seed_is_suspected_duplicate_not_related(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    install(cfg, "wiki/seeds/检索机死机.md",
            "---\ntitle: 检索机死机影响读者找书\ntype: seed-card\n---\n既有卡。")
    index = build_index(cfg)
    report = card_relations.relation_candidates(make_item(), cfg, index, Retriever(cfg, index))
    assert report["related"] == []
    assert report["suspected_duplicates"] and "疑似重复" in report["suspected_duplicates"][0]


def test_no_candidate_relations_leave_the_card_empty_but_searched(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    index = build_index(cfg)
    execute = load_executor(ROOT, "mindseed-grow")
    with _no_hits_retriever():
        result = execute(atomic_context(cfg))
    item = result["items"][0]
    assert item["link_search"] == "no_match"
    assert item["related"] == []  # empty relation is legal; nothing invented


class _no_hits_retriever:
    """Patch Retriever.select to return an empty, truthful selection."""
    def __enter__(self):
        self.patcher = pytest.MonkeyPatch()
        self.patcher.setattr(Retriever, "select", lambda self, query, **kw: None)
        import core.card_relations as cr
        self.prev = cr.relation_candidates
        def limited(item, cfg, index, retriever=None):
            report = {"related": [], "pending_links": list(item.get("pending_links", [])),
                      "link_search": "no_match",
                      "relation_explanations": ["已检索当前索引，无候选。"], "suspected_duplicates": []}
            return report
        cr.relation_candidates = limited
        return self

    def __exit__(self, *exc):
        import core.card_relations as cr
        cr.relation_candidates = self.prev
        self.patcher.undo()
        return False


# ── Update identity: same title is not the same thought ─────────────────────

def test_repeat_generation_of_identical_units_creates_no_duplicate(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    index = build_index(cfg)
    result = execute_skill(ROOT, "mindseed-grow", atomic_context(cfg))
    pages, _ = prepare_seed_updates(index, cfg, result["pages"])
    for page in pages:
        page.setdefault("operation", "create")  # mvp envelope default before planning
    assert pages and all(p["operation"] == "create" for p in pages)
    for page in pages:
        target = index.root / page["rel_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page["content"], encoding="utf-8")
    expected = len(pages)
    index2 = build_index(cfg)
    result2 = execute_skill(ROOT, "mindseed-grow", atomic_context(cfg))
    pages2, _ = prepare_seed_updates(index2, cfg, result2["pages"])
    assert pages2 == []  # unchanged repeat: already incorporated, no duplicate card
    assert len(list((index.root / "wiki/seeds").glob("*.md"))) == expected


def test_manual_body_and_custom_yaml_survive_reviewed_update(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")
    units = atomic_seed.information_units({"rel": "quicknote/dialogue.md", "source_text": DIALOGUE})
    ids1 = [i for i, u in enumerate(units) if "找了三次" in u["quote"]]

    def seeded_with(ids):
        def call(system, payload):
            return json.dumps({"thoughts": [{"title": "检索观察", "kind": "assertion",
                "statement": "检索机死机影响读者找书。",
                "unit_ids": [i for i in ids if i < len(payload["units"])],
                "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
                "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)
        return call

    result = execute(atomic_context(cfg, use_llm=True, model_fn=seeded_with(ids1)))
    pages, _ = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
    target = build_index(cfg).root / pages[0]["rel_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        pages[0]["content"].replace("type: seed-card", "my_note: 手写保留\ntype: seed-card")
        + "\n我的手写判断：先访谈十名读者。\n", encoding="utf-8")
    index = build_index(cfg)
    note = index.by_rel[pages[0]["rel_path"]]
    revision_before = note.revision
    object_id_before = note.object_id
    extended = [i for i, u in enumerate(units) if "找了三次" in u["quote"] or "还能查到吗" in u["quote"]]
    result2 = execute(atomic_context(cfg, use_llm=True, model_fn=seeded_with(extended)))
    page2, = result2["pages"]
    page2.setdefault("operation", "create")
    updated, _ = prepare_seed_updates(index, cfg, [page2])
    assert updated and updated[0]["operation"] == "update"
    # Update targets the exact confirmed object snapshot (identity pinned at generation).
    assert updated[0]["base_object_id"] == object_id_before
    assert updated[0]["base_revision"] == revision_before
    content = updated[0]["content"]
    assert "我的手写判断：先访谈十名读者。" in content
    assert "my_note: 手写保留" in content


def test_same_title_distinct_thoughts_become_two_cards(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")

    def seeded(system, payload):
        units = payload["units"]
        return json.dumps({"thoughts": [
            {"title": "社区观察", "kind": "assertion", "statement": "检索机死机影响读者找书。",
             "unit_ids": [i for i, u in enumerate(units) if "找了三次" in u["quote"]],
             "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
             "negative_scope": ["不评估选型。"]},
            {"title": "社区观察", "kind": "question", "statement": "旧借书记录能否迁移没有答案？",
             "unit_ids": [i for i, u in enumerate(units) if "还能查到吗" in u["quote"]],
             "growth_directions": [{"action": "追问迁移条目。", "basis": "回应读者问题。"}],
             "negative_scope": ["不推测方案。"]},
        ]}, ensure_ascii=False)

    result = execute(atomic_context(cfg, use_llm=True, model_fn=seeded))
    assert len(result["pages"]) == 2
    pages, issues = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
    rels = [p["rel_path"] for p in pages]
    assert len(rels) == 2 and len(set(rels)) == 2  # two distinct targets, no swallowing
    assert any("同名不同念头" in i or "不自动合并" in i for i in issues)
    assert all(p.get("operation", "create") == "create" for p in pages)


def test_partial_overlap_updates_existing_seed_same_object(tmp_path):
    """Same claim + added evidence => reviewed update of the confirmed object,
    preserving its identity; the plan pins generation-time provenance."""
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")

    def seeded_with(ids, statement="检索机死机影响读者找书。"):
        def call(system, payload):
            units = payload["units"]
            return json.dumps({"thoughts": [{
                "title": "检索观察", "kind": "assertion", "statement": statement,
                "unit_ids": [i for i in ids if i < len(units)],
                "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
                "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)
        return call

    # Round 1: single-excerpt thought.
    context = atomic_context(cfg, use_llm=True, model_fn=seeded_with(
        [i for i, u in enumerate(atomic_seed.information_units(
            {"rel": "quicknote/dialogue.md", "source_text": DIALOGUE})) if "找了三次" in u["quote"]]))
    result = execute_skill(ROOT, "mindseed-grow", context)
    pages, _ = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
    assert len(pages) == 1
    target = build_index(cfg).root / pages[0]["rel_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pages[0]["content"], encoding="utf-8")
    index = build_index(cfg)
    recorded = index.by_rel[pages[0]["rel_path"]].metadata["seed_state"]
    assert recorded["thought_id"] and recorded["statement_sha256"]

    # Round 2: same statement + one MORE excerpt (evidence added).
    units = atomic_seed.information_units({"rel": "quicknote/dialogue.md", "source_text": DIALOGUE})
    extended_ids = [i for i, u in enumerate(units) if "找了三次" in u["quote"] or "还能查到吗" in u["quote"]]
    result2 = execute_skill(ROOT, "mindseed-grow",
                            atomic_context(cfg, use_llm=True, model_fn=seeded_with(extended_ids)))
    page2, = result2["pages"]
    assert page2["item"]["thought_id"] != recorded["thought_id"]  # evidence change => new identity
    page2.setdefault("operation", "create")
    updated, issues = prepare_seed_updates(index, cfg, [page2])
    assert len(updated) == 1 and updated[0]["operation"] == "update", issues
    assert updated[0]["rel_path"] == pages[0]["rel_path"]  # same object: appended, not duplicated
    content = updated[0]["content"]
    seed_state = parse_frontmatter(content)[0]["seed_state"]
    assert isinstance(seed_state, dict)
    # Post-merge state is coherent with the merged evidence version.
    assert seed_state["thought_id"] == page2["item"]["thought_id"]
    assert seed_state["statement_sha256"] == recorded["statement_sha256"]
    assert seed_state["kind"] == "assertion"
    assert set(seed_state["thought_units"]) == set(recorded["thought_units"]) | {
        u for u in page2["item"]["thought_units"]}
    assert parse_frontmatter(content)[0]["source_hashes"] == seed_state["source_hashes"]
    # Persisted card_state evidence now includes the newly rendered evidence.
    card_state = parse_frontmatter(content)[0]["card_state"]
    assert len(card_state["evidence"]) == 2
    assert card_state["thought_id"] == seed_state["thought_id"]
    assert card_state["source_hashes"] == seed_state["source_hashes"]
    # Generation-time provenance pinned: no silent rebind to current index hashes.
    assert updated[0]["retrieval_source_hashes"]["quicknote/dialogue.md"] \
        == updated[0]["item"]["evidence"][0]["source_sha256"]


def test_create_update_identical_repeat_is_noop(tmp_path):
    """Astra probe scenario: create -> evidence update -> identical repeat must
    be a NOOP (no second card), with manual content retained."""
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")
    units = atomic_seed.information_units({"rel": "quicknote/dialogue.md", "source_text": DIALOGUE})

    def seeded_with(ids):
        def call(system, payload):
            return json.dumps({"thoughts": [{"title": "检索观察", "kind": "assertion",
                "statement": "检索机死机影响读者找书。",
                "unit_ids": [i for i in ids if i < len(payload["units"])],
                "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
                "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)
        return call

    def run(ids):
        result = execute(atomic_context(cfg, use_llm=True, model_fn=seeded_with(ids)))
        pages, issues = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
        for page in pages:
            page.setdefault("operation", "create")
            target = build_index(cfg).root / page["rel_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(page["content"].encode("utf-8"))
        return pages, issues

    ids1 = [i for i, u in enumerate(units) if "找了三次" in u["quote"]]
    ids2 = ids1 + [i for i, u in enumerate(units) if "还能查到吗" in u["quote"]]
    pages1, _ = run(ids1)
    assert len(pages1) == 1 and pages1[0]["operation"] == "create"
    seed_rel = pages1[0]["rel_path"]
    seed_file = build_index(cfg).root / seed_rel
    seed_file.write_bytes(seed_file.read_bytes() + "\n我的手写判断：保留。\n".encode("utf-8"))
    pages2, _ = run(ids2)
    assert len(pages2) == 1 and pages2[0]["operation"] == "update"
    assert pages2[0]["rel_path"] == seed_rel
    pages3, issues3 = run(ids2)
    assert pages3 == [], issues3  # identical repeat after merge: NOOP, no second card
    index = build_index(cfg)
    assert len(list((index.root / "wiki/seeds").glob("*.md"))) == 1
    final = index.by_rel[seed_rel]
    assert final.metadata["seed_state"]["thought_id"] == pages2[0]["item"]["thought_id"]
    assert "我的手写判断：保留。" in (index.root / seed_rel).read_text(encoding="utf-8")


def test_changed_retained_source_fails_closed_not_rebound(tmp_path):
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")
    units = atomic_seed.information_units({"rel": "quicknote/dialogue.md", "source_text": DIALOGUE})
    ids1 = [i for i, u in enumerate(units) if "找了三次" in u["quote"]]
    ids2 = ids1 + [i for i, u in enumerate(units) if "还能查到吗" in u["quote"]]

    def seeded_with(ids):
        def call(system, payload):
            return json.dumps({"thoughts": [{"title": "检索观察", "kind": "assertion",
                "statement": "检索机死机影响读者找书。",
                "unit_ids": [i for i in ids if i < len(payload["units"])],
                "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
                "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)
        return call

    result = execute(atomic_context(cfg, use_llm=True, model_fn=seeded_with(ids1)))
    pages, _ = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
    seed_root = build_index(cfg).root
    target = seed_root / pages[0]["rel_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pages[0]["content"].encode("utf-8"))
    # The RETAINED source changes after round 1.
    install(cfg, "quicknote/dialogue.md", "# 对话\n占位（来源已编辑）。\n还能查到吗？")
    index = build_index(cfg)
    result2 = execute(atomic_context(cfg, use_llm=True, model_fn=seeded_with(ids2)))
    page2, = result2["pages"]
    page2.setdefault("operation", "create")
    updated, issues = prepare_seed_updates(index, cfg, [page2])
    assert updated == [], issues  # old evidence stale: fail closed, never rebound
    assert any("冲突" in i or "不一致" in i or "快照" in i or "已发生变化" in i for i in issues)
    assert "本轮补充提案" not in target.read_text(encoding="utf-8")


def test_atomic_page_against_legacy_titled_seed_creates_reviewed_card(tmp_path):
    """atomic mode never adopts/rewrites an old seed lacking versioned
    card_state just because the title matches."""
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    install(cfg, "wiki/seeds/检索观察.md",
            "---\ntitle: 检索观察\ntype: seed-card\nstatus: seed\nstage: candidate\n"
            "sources: [\"quicknote/dialogue.md\"]\n---\n旧的手写种子，无 card_state。")
    legacy_file = Path(cfg["knowledge_base"]) / "wiki/seeds/检索观察.md"
    original = legacy_file.read_bytes()
    execute = load_executor(ROOT, "mindseed-grow")
    note = {"rel": "quicknote/dialogue.md", "title": "对话", "source_text": DIALOGUE}
    response = {"thoughts": [{"title": "检索观察", "kind": "assertion", "statement": "新念头表述。",
                              "unit_ids": [0],
                              "growth_directions": [{"action": "核对记录。", "basis": "回应复现未知。"}],
                              "negative_scope": ["不评估选型。"]}]}
    result = execute({"notes": [note], "config": cfg, "use_llm": True,
                      "model_fn": lambda s, p: json.dumps(response, ensure_ascii=False)})
    pages, issues = prepare_seed_updates(build_index(cfg), cfg, result["pages"])
    assert len(pages) == 1 and pages[0]["rel_path"] != "wiki/seeds/检索观察.md"
    assert any("card_state" in i or "不自动改写" in i for i in issues)
    assert legacy_file.read_bytes() == original


def test_same_excerpt_supports_two_thoughts_and_rerun_is_stable(tmp_path):
    """One exact excerpt can legitimately ground two different thoughts; both
    persist as separate cards, and an identical rerun duplicates nothing."""
    cfg = _kb(tmp_path)
    install_dialogue(cfg)
    execute = load_executor(ROOT, "mindseed-grow")

    def seeded(system, payload):
        units = payload["units"]
        ids = [i for i, u in enumerate(units) if "找了三次" in u["quote"]]
        thoughts = []
        for statement in ("检索机死机已实际阻碍读者找书。", "借书检索失败可能与索引机故障直接相关。"):
            thoughts.append({"title": "社区观察", "statement": statement, "kind": "assertion",
                             "unit_ids": ids,
                             "growth_directions": [{"action": "核对死机与找书失败记录。", "basis": "同一片段支撑两个判断。"}],
                             "negative_scope": ["不评估选型。"]})
        return json.dumps({"thoughts": thoughts}, ensure_ascii=False)

    result = execute(atomic_context(cfg, use_llm=True, model_fn=seeded))
    assert len(result["pages"]) == 2
    index = build_index(cfg)
    pages, issues = prepare_seed_updates(index, cfg, result["pages"])
    rels = sorted(p["rel_path"] for p in pages)
    assert len(rels) == 2 and any("同名不同念头" in i or "不自动合并" in i for i in issues)
    for page in pages:
        target = index.root / page["rel_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page["content"], encoding="utf-8")
    # Rerun: identical thoughts resolve by confirmed identity — nothing new, no churn.
    index2 = build_index(cfg)
    result2 = execute(atomic_context(cfg, use_llm=True, model_fn=seeded))
    pages2, issues2 = prepare_seed_updates(index2, cfg, result2["pages"])
    assert pages2 == []
    assert len(list((index.root / "wiki/seeds").glob("*.md"))) == 2


def _two_source_setup(tmp_path, text_a):
    """Shared probe harness: confirmed thought with evidence from A+B."""
    cfg = _kb(tmp_path)
    texts = {"quicknote/a.md": text_a, "quicknote/b.md": DIALOGUE + "\n第二份独立记录。\n"}
    for rel, text in texts.items():
        install(cfg, rel, text)
    execute = load_executor(ROOT, "mindseed-grow")

    def gen(current_texts=None):
        sources = current_texts or texts
        notes = [{"rel": rel, "title": rel, "source_text": text,
                  "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
                 for rel, text in sources.items()]

        def model(system, payload):
            ids = [i for i, u in enumerate(payload["units"]) if "找了三次" in u["quote"]]
            return json.dumps({"thoughts": [{"title": "检索观察", "kind": "assertion",
                "statement": "检索机死机影响读者找书。", "unit_ids": ids,
                "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
                "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)
        return execute({"notes": notes, "config": cfg, "use_llm": True, "model_fn": model})

    return cfg, gen


def test_same_path_version_conflict_fails_closed(tmp_path):
    """Astra probe: confirmed A+B thought; A's text changes; the new A'+B
    proposal must NOT merge — old and new versions of one path never mix."""
    cfg, gen = _two_source_setup(tmp_path, DIALOGUE)
    index = build_index(cfg)
    first, _ = prepare_seed_updates(index, cfg, gen()["pages"])
    assert first and first[0].get("operation", "create") == "create"
    seed_root = index.root / first[0]["rel_path"]
    seed_root.parent.mkdir(parents=True, exist_ok=True)
    seed_root.write_bytes(first[0]["content"].encode("utf-8"))
    # A changes; the new proposal is generated from the NEW bytes and its hash
    # matches the current index — but it conflicts with the recorded A hash.
    changed = DIALOGUE + "\n新补充：还应复查安装记录。\n"
    install(cfg, "quicknote/a.md", changed)
    index = build_index(cfg)  # the index now reflects the changed A
    texts = {"quicknote/a.md": changed, "quicknote/b.md": DIALOGUE + "\n第二份独立记录。\n"}
    notes = [{"rel": rel, "title": rel, "source_text": text,
              "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
             for rel, text in texts.items()]

    def model(system, payload):
        ids = [i for i, u in enumerate(payload["units"]) if "找了三次" in u["quote"]]
        return json.dumps({"thoughts": [{"title": "检索观察", "kind": "assertion",
            "statement": "检索机死机影响读者找书。", "unit_ids": ids,
            "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
            "negative_scope": ["不评估选型。"]}]}, ensure_ascii=False)

    result = load_executor(ROOT, "mindseed-grow")(
        {"notes": notes, "config": cfg, "use_llm": True, "model_fn": model})
    updated, issues = prepare_seed_updates(index, cfg, result["pages"])
    assert updated == [], issues  # version conflict: fail closed
    assert any("冲突" in i or "复核" in i for i in issues)
    persisted = parse_frontmatter(seed_root.read_text(encoding="utf-8"))[0]
    assert "本轮补充提案" not in seed_root.read_text(encoding="utf-8")
    for row in persisted["card_state"]["evidence"]:
        assert row["source_sha256"] != hashlib.sha256(
            changed.encode("utf-8")).hexdigest() or row["source"] != "quicknote/a.md"


def test_stale_proposal_after_source_change_is_reported_not_silent_noop(tmp_path):
    """Source changes after generation but before prepare_seed_updates: the
    repeat must report a source mismatch, not count as a harmless NOOP."""
    cfg, gen = _two_source_setup(tmp_path, DIALOGUE)
    index = build_index(cfg)
    first, _ = prepare_seed_updates(index, cfg, gen()["pages"])
    assert first and first[0].get("operation", "create") == "create"
    seed_root = index.root / first[0]["rel_path"]
    seed_root.parent.mkdir(parents=True, exist_ok=True)
    seed_root.write_bytes(first[0]["content"].encode("utf-8"))
    # The source changes AFTER generation (proposal now stale vs the index).
    install(cfg, "quicknote/a.md", DIALOGUE + "\n生成后才追加的一行。\n")
    index = build_index(cfg)
    stale_pages, issues = prepare_seed_updates(index, cfg, gen()["pages"])
    assert stale_pages == []  # not persisted
    assert any("已发生变化" in i or "不一致" in i for i in issues)  # reported, not silent


def test_growth_directions_vary_by_thought_and_cite_their_basis(tmp_path):
    note = {"rel": "quicknote/dialogue.md", "title": "对话", "source_text": DIALOGUE}
    units = atomic_seed.information_units(note)
    response = {"thoughts": [
        {"title": "死机", "kind": "assertion", "statement": "检索机死机影响读者找书。",
         "unit_ids": [i for i, u in enumerate(units) if "找了三次" in u["quote"]],
         "growth_directions": [{"action": "核对死机记录。", "basis": "回应复现未知。"}],
         "negative_scope": ["不评估选型。"]},
        {"title": "迁移", "kind": "question", "statement": "旧借书记录能否迁移没有答案？",
         "unit_ids": [i for i, u in enumerate(units) if "还能查到吗" in u["quote"]],
         "growth_directions": [{"action": "追问迁移条目。", "basis": "回应读者问题。"}],
         "negative_scope": ["不推测方案。"]},
    ]}
    items, _, _ = atomic_seed.generate_atomic_items(
        [note], model_fn=lambda s, p: json.dumps(response, ensure_ascii=False))
    assert items[0]["growth_directions"] != items[1]["growth_directions"]  # no canned pair
    for item in items:
        assert all("依据：" in g for g in item["growth_directions"])
        assert item["negative_scope"]  # every thought carries an explicit boundary
