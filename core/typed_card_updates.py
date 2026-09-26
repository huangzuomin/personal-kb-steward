"""T8 typed-card update planner: pure identity/replacement proposals.

`prepare_typed_updates(index, cfg, pages) -> {"pages": [...], "outcomes": [...],
"issues": [...]}` plans create/update/noop/blocked proposals for NEW
source-note, concept-page, case-story and topic-page cards so that
core.plan_objects can later bind object_id/revision exclusively at the plan
boundary. This module NEVER writes to disk and NEVER invents identities.

Input page spec (one dict per proposed card):

    content                 str  generator output (frontmatter + Markdown body)
    rel_path                str  proposed vault-relative target
    operation               str  "create" (updates are derived here, not input)
    sources                 list[str] original source paths
    retrieval_source_hashes dict {rel: sha256 of ORIGINAL raw bytes}
    skill                   str  producing skill name
    item                    dict the structured generator candidate. REQUIRED
                                 for concept-page/case-story; source-note derives
                                 identity/provenance from its persisted
                                 card_state/frontmatter without item; topic-page
                                 has persisted question + claims.

Accepted shapes are the ACTUAL generator outputs (v2 contract, supersedes the
earlier surrogate shapes):

- case-story candidates carry `reusable_mechanism` + `reusable_mechanism_claim_ids`
  and `mechanism_inference` + `mechanism_inference_claim_ids` (the `_claim` string
  fields exist only in the MODEL response, never in the compiled candidate). The
  helper resolves the actual IDs against the persisted compiled claims and
  enforces exact statement/kind/role consistency.
- source-note card_state is `{version, type, info_units, analysis}` (no claims).
  Every info_unit is re-verified against the captured raw snapshot via
  core.source_analysis.locate_quote with exact coords/kind/hash.

Identity (conservative, deterministic, versioned; role/kind is part of the key):
- source-note : the exact single original path
- concept-page: bound definition statement + its kind + concept_name
- case-story  : bound mechanism/inference statement + its kind + role
                (reusable|inference) + card_level + origin title
- topic-page  : exact explicit research question
Evidence overlap identity = (original path, exact quote) pairs. Automatic reuse
of a matched card (concept/case/topic) additionally REQUIRES verified
overlapping evidence; a same-semantic-key candidate with fully disjoint
evidence is blocked for manual review — never silently re-bound. Same title
with different semantics is never merged; there is no fuzzy title matching.

Snapshot fidelity: every dependency must be an ACTUAL indexed Note; bytes are
re-read and compared against the captured note.sha256 AND the proposal hash
(reconcile._text discipline). Hash VALUES are validated across item,
frontmatter, card_state (analysis.source_hashes / info_units) and every claim
evidence — a forged value anywhere blocks. Nothing is silently rebased.

Managed region: the generated Markdown BODY (only) is wrapped in exactly one
`<!-- pks:generated:start -->` / `<!-- pks:generated:end -->` pair. On a
reviewed update the block is replaced in full from the freshly compiled
candidate; machine-owned frontmatter fields are synchronized through
reconcile._patch_header restricted to a locally validated allowlist
(sources, source_hashes, related, status, stage, confidence, coverage,
analysis_mode, schema_version, generator_version, quality_flags, origin,
created-independent `updated`, card_state, card_update_state, review_required
pinned True, tags policy: safe user tags are retained and merged). `created`
and the user-edited display title are never touched; custom YAML, comments
and all text outside the block are preserved byte-for-byte. Tag policy: the
union of existing string tags and the new candidate's tags (user tags are
kept when they are plain strings; non-string junk is dropped with the
replacement being machine-reviewed anyway).

Proposals keep `item`, `origin`, `analysis_mode`, `confidence` and
`review_required=True` on every create/update; rel_path/target/canonical_path
agree. No production write authority is added here.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .claims import EvidenceError, evidence_status, read_claims, validate_claims
from .knowledge_objects import identity_from_metadata
from .reconcile import _patch_header
from .source_analysis import STATEMENT_KINDS, locate_quote, normalized_text
from .vault import VaultIndex, parse_frontmatter

CARD_UPDATE_STATE_VERSION = 1
GENERATED_START = "<!-- pks:generated:start -->"
GENERATED_END = "<!-- pks:generated:end -->"
_HEADER = re.compile(r"\A(?:﻿)?---[^\S\r\n]*\r?\n(.*?)^---[^\S\r\n]*(?:\r?\n|\Z)", re.M | re.S)

# Frontmatter fields this helper may (re)write on an update. `created` and
# `title` are deliberately absent: creation date and user-edited display
# title are always preserved.
_SYNC_FIELDS = ("sources", "source_hashes", "related", "status", "stage",
                "confidence", "coverage", "analysis_mode", "schema_version",
                "generator_version", "quality_flags", "origin", "tags",
                "updated", "card_state", "card_update_state", "review_required")

_TYPE_DIR_KEYS = {
    "source-note": "sources_dir",
    "concept-page": "concepts_dir",
    "case-story": "cases_dir",
    "topic-page": "topics_dir",
}
_ITEM_REQUIRED = ("concept-page", "case-story")


class TypedUpdateError(ValueError):
    """Structural/fidelity problem with one page spec (fail closed, per page)."""


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _digest(value: Any) -> str:
    return _sha_text(_json(value))


def _state_value(meta: dict[str, Any], key: str) -> Any:
    value = meta.get(key)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


# ---------------------------------------------------------------------------
# Captured-note discipline (reconcile._text semantics, index-enforced)
# ---------------------------------------------------------------------------
def _canonical_rel(index: VaultIndex, rel: str) -> str | None:
    if not isinstance(rel, str) or not rel:
        return None
    if "\\" in rel or ".." in PurePosixPath(rel).parts:
        return None
    if PurePosixPath(rel).as_posix() != rel or rel.endswith("/"):
        return None
    resolved = (index.root / rel).resolve()
    if not resolved.is_relative_to(index.root.resolve()):
        return None
    if resolved.relative_to(index.root.resolve()).as_posix() != rel:
        return None  # symlink/junction escape
    return rel


def _captured_note(index: VaultIndex, rel: str,
                   expected: str | None = None) -> tuple[Any, bytes, str]:
    """Return (note, raw bytes, decoded text) for an ACTUAL indexed Note.

    Enforces: indexed presence, canonical path without alias/escape, byte
    equality with the CAPTURED note.sha256 (metadata changed after capture =>
    blocked), and — when given — equality with the proposal's expected hash
    (stale capture => blocked). No silent refresh.
    """
    canon = _canonical_rel(index, rel)
    if canon is None or canon != rel:
        raise TypedUpdateError(f"依赖路径非法或存在别名/逃逸：{rel!r}")
    note = index.by_rel.get(rel)
    if note is None or note.rel != rel:
        raise TypedUpdateError(f"依赖不在当前捕获索引中（未落盘、已删除或未扫描）：{rel}")
    try:
        raw = note.path.read_bytes()
    except OSError as exc:
        raise TypedUpdateError(f"依赖读取失败：{rel}：{exc}") from exc
    if hashlib.sha256(raw).hexdigest() != note.sha256:
        raise TypedUpdateError(f"依赖文件在捕获索引后已变化：{rel}；请重建索引后重试")
    if expected is not None and note.sha256 != expected:
        raise TypedUpdateError(
            f"提案声明的 hash 与捕获索引不符（拒绝静默刷新）：{rel}")
    try:
        text = raw.decode("utf-8")  # preserve BOM/CRLF exactly
    except UnicodeDecodeError as exc:
        raise TypedUpdateError(f"依赖不是可解码的 UTF-8：{rel}：{exc}") from exc
    return note, raw, text


# ---------------------------------------------------------------------------
# Compiled-claim revalidation against captured originals (concept/case/topic)
# ---------------------------------------------------------------------------
def _validate_compiled_claims(state: dict[str, Any], docs: list[dict[str, str]],
                              where: str) -> str | None:
    """Revalidate every persisted compiled claim against the captured
    originals via core.claims (exact locators/quote/hash/claim ID). Claims
    are REQUIRED to be nonempty; malformed evidence is blocked, never
    fabricated or repaired. A pure supports/contradicts disagreement is a
    legitimate compiled record, so the contradicts-only restriction of
    validate_claims is relaxed by falling back to per-evidence matching."""
    if not _claims_of(state):
        return f"{where}: 没有任何已编译判断，不能作为证据卡（拒绝空壳创建）"
    try:
        validate_claims({"claims": state["claims"]}, docs)
    except EvidenceError as exc:
        if "反驳证据" not in str(exc):
            return f"{where}: 编译判断未通过 core.claims 复验：{exc}"
        try:
            claims = read_claims({"claims": state["claims"]})
        except EvidenceError as exc2:
            return f"{where}: 编译判断未通过 core.claims 复验：{exc2}"
        by_path = {d["path"]: d for d in docs}
        for claim in claims:
            for e in claim.evidence:
                if evidence_status(e, by_path.get(e.source)) != "matched":
                    return f"{where}: 编译判断证据与原始快照不匹配：{e.source}"
    return None


def _validate_stored_semantic(old_state: dict[str, Any],
                              old_card_state: dict[str, Any]) -> str | None:
    """Stored semantic kind/role must agree with the target's CURRENT
    card_state claims — not merely statement membership."""
    key = old_state.get("semantic") or {}
    by_statement: dict[str, dict[str, Any]] = {}
    for claim in _claims_of(old_card_state):
        s = claim.get("statement")
        if isinstance(s, str) and s not in by_statement:
            by_statement[s] = claim
    definition = key.get("definition")
    if isinstance(definition, str):
        claim = by_statement.get(definition)
        if claim is None or claim.get("kind") != key.get("definition_kind"):
            return "存储语义身份的 definition/kind 与目标 card_state 不一致（疑似人工修改）"
    mechanism = key.get("mechanism")
    if isinstance(mechanism, str):
        claim = by_statement.get(mechanism)
        if claim is None or claim.get("kind") != key.get("mechanism_kind"):
            return "存储语义身份的 mechanism/kind 与目标 card_state 不一致（疑似人工修改）"
        role = key.get("mechanism_role")
        if role == "reusable" and claim.get("kind") != "fact":
            return "存储语义身份 role=reusable 但绑定判断不是 fact（不一致）"
        if role == "inference" and claim.get("kind") != "inference":
            return "存储语义身份 role=inference 但绑定判断不是 inference（不一致）"
    return None


# ---------------------------------------------------------------------------
# Frontmatter / managed block
# ---------------------------------------------------------------------------
def _split_frontmatter(content: str) -> tuple[dict[str, Any], str, str, re.Match]:
    match = _HEADER.match(content)
    if not match:
        raise TypedUpdateError("缺少完整 frontmatter，无法规划类型化卡片更新")
    meta, body = parse_frontmatter(content.lstrip("﻿"))
    return meta, content[match.end():], content[:match.end()], match


def _card_state_of(meta: dict[str, Any], where: str,
                   expected_type: str | None = None) -> dict[str, Any]:
    """Strict persisted-state validation: EXACT int version == 1 (bool/float/
    str rejected) and card type equal to the outer frontmatter type."""
    state = _state_value(meta, "card_state")
    if not isinstance(state, dict):
        raise TypedUpdateError(f"{where}: 缺少合法 card_state 对象")
    version = state.get("version")
    if type(version) is not int or version != CARD_UPDATE_STATE_VERSION:
        raise TypedUpdateError(
            f"{where}: card_state.version 必须是精确整数 {CARD_UPDATE_STATE_VERSION}，"
            f"得到 {version!r}（bool/浮点/字符串一律拒绝）")
    if expected_type is not None and state.get("type") != expected_type:
        raise TypedUpdateError(
            f"{where}: card_state.type {state.get('type')!r} 与外层类型 "
            f"{expected_type!r} 不一致")
    return state


def _wrap_body(body: str) -> str:
    """The managed REGION ends exactly at END; callers append the newline
    OUTSIDE the region so region digests are stable."""
    if GENERATED_START in body or GENERATED_END in body:
        raise TypedUpdateError("生成正文包含托管区块标记，拒绝创建歧义区块")
    return f"{GENERATED_START}\n{body.rstrip()}\n{GENERATED_END}"


def _locate_block(text: str) -> tuple[int, int] | None:
    starts, ends = text.count(GENERATED_START), text.count(GENERATED_END)
    if starts == 0 and ends == 0:
        return None
    if starts != 1 or ends != 1:
        raise TypedUpdateError("托管区块标记缺失、重复或畸形，保留原文请先人工修正")
    begin = text.index(GENERATED_START)
    end = text.index(GENERATED_END) + len(GENERATED_END)
    header = _HEADER.match(text)
    if end <= begin or header is None or begin < header.end():
        raise TypedUpdateError("托管区块标记无效或进入 frontmatter")
    return begin, end


def _patch_owned_fields(text: str, fields: dict[str, Any],
                        candidate_keys: set[str] | None = None) -> str:
    """Locally validate the allowlist, protect user multiline custom YAML
    blocks, then delegate to reconcile._patch_header (which handles owned
    field replacement/comments correctly for single-line values)."""
    unknown = set(fields) - set(_SYNC_FIELDS)
    if unknown:
        raise TypedUpdateError(f"字段不在本 helper 的允许清单内：{sorted(unknown)}")
    match = _HEADER.match(text)
    if not match:
        raise TypedUpdateError("目标缺少完整 frontmatter，不能安全局部更新")
    lines = match.group(1).splitlines(keepends=True)
    protected: list[str] = []
    kept: list[str] = []
    i = 0
    candidate_keys = candidate_keys or set()
    while i < len(lines):
        line = lines[i]
        m = re.match(r"([^\s:#][^:]*):(\s|$)", line)
        key = m.group(1) if m else None
        custom = (key is not None and key not in _SYNC_FIELDS
                  and key not in candidate_keys)
        if custom:
            # protect this user block (key + indented/blank continuation)
            block = [line]
            i += 1
            while i < len(lines) and (not lines[i].strip()
                                      or lines[i][0].isspace()):
                block.append(lines[i])
                i += 1
            protected.extend(block)
            continue
        kept.append(line)
        i += 1
    working = text[:match.start(1)] + "".join(kept) + text[match.end(1):]
    patched = _patch_header(working, fields)
    if protected:
        # re-insert the user blocks byte-for-byte before the closing '---'
        header = _HEADER.match(patched)
        body_lines = header.group(1).splitlines(keepends=True)
        insert_at = len(body_lines)
        while insert_at > 0 and not body_lines[insert_at - 1].strip():
            insert_at -= 1
        body_lines[insert_at:insert_at] = protected
        patched = (patched[:header.start(1)] + "".join(body_lines)
                   + patched[header.end(1):])
    return patched


# ---------------------------------------------------------------------------
# Evidence identity and hash consistency
# ---------------------------------------------------------------------------
def _claims_of(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in state.get("claims", []) if isinstance(c, dict)]


def _evidence_pairs(state: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for claim in _claims_of(state):
        for e in claim.get("evidence", []) or []:
            if isinstance(e, dict) and isinstance(e.get("source"), str) \
                    and isinstance(e.get("quote"), str):
                pairs.add((e["source"], e["quote"]))
    return pairs


def _recorded_evidence(state: dict[str, Any]) -> set[tuple[str, str]]:
    """Read the persisted identity evidence with a strict JSON shape gate.

    The update planner must block one malformed target instead of allowing an
    unhashable list/dict pair to escape as a batch-level ``TypeError``.
    """
    value = state.get("evidence", [])
    if not isinstance(value, list):
        raise TypedUpdateError("card_update_state.evidence 必须是数组，拒绝采用畸形状态")
    recorded: set[tuple[str, str]] = set()
    for i, pair in enumerate(value):
        if (not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(part, str) for part in pair)):
            raise TypedUpdateError(
                f"card_update_state.evidence[{i}] 必须是 [source, quote] 字符串数组，"
                "拒绝采用畸形状态")
        recorded.add((pair[0], pair[1]))
    return recorded


def _check_hash_consistency(hashes: dict[str, str], actual: dict[str, str],
                            item: dict[str, Any] | None, meta: dict[str, Any],
                            state: dict[str, Any]) -> str | None:
    """Every declared hash VALUE anywhere must equal the actual captured hash
    of that dependency — key-set equality alone is not trusted."""
    def bad(where: str) -> str:
        return f"{where} 的 hash 值与实际捕获字节不一致（伪造或过期），拒绝"

    for rel, expected in hashes.items():
        if actual.get(rel) != expected:
            return f"检索快照与实际文件字节不符（拒绝静默刷新）：{rel}"
    declared_maps = [("item.source_hashes", (item or {}).get("source_hashes")),
                     ("frontmatter.source_hashes", meta.get("source_hashes")),
                     ("card_state.analysis.source_hashes",
                      (state.get("analysis") or {}).get("source_hashes")
                      if isinstance(state.get("analysis"), dict) else None)]
    for where, declared in declared_maps:
        if declared is None:
            continue
        if not isinstance(declared, dict):
            return f"{where} 不是对象"
        for rel, value in declared.items():
            if rel in actual and value != actual[rel]:
                return bad(where)
    for claim in _claims_of(state):
        for e in claim.get("evidence", []) or []:
            if not isinstance(e, dict):
                continue
            rel = e.get("source")
            if isinstance(rel, str) and rel in actual \
                    and e.get("source_sha256") != actual[rel]:
                return "判断证据的 source_sha256 与实际捕获字节不一致（伪造或过期），拒绝"
    analysis = state.get("analysis")
    if isinstance(analysis, dict):
        for unit in state.get("info_units", []) or []:
            if isinstance(unit, dict) and unit.get("source") in actual \
                    and unit.get("source_sha256") != actual[unit["source"]]:
                return "info_unit.source_sha256 与实际捕获字节不一致（伪造或过期），拒绝"
    return None


# ---------------------------------------------------------------------------
# Semantic identity (actual candidate shapes, role/kind preserved)
# ---------------------------------------------------------------------------
def _resolve_claim_ids(ids: Any, by_id: dict[str, dict[str, Any]],
                       where: str) -> list[dict[str, Any]]:
    resolved = []
    for cid in ids if isinstance(ids, list) else []:
        claim = by_id.get(cid) if isinstance(cid, str) else None
        if claim is None:
            raise TypedUpdateError(f"{where} 引用了持久化 claims 中不存在的 claim_id：{cid!r}")
        resolved.append(claim)
    return resolved


def _semantic_key(card_type: str, item: dict[str, Any] | None, meta: dict[str, Any],
                  state: dict[str, Any], sources: list[str],
                  where: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (ingredients, block-reason). Role/kind is part of the key so a
    fact statement and an inference statement never collapse."""
    claims = _claims_of(state)
    by_id = {c.get("claim_id"): c for c in claims if isinstance(c.get("claim_id"), str)}
    statements = {c.get("statement") for c in claims}
    if card_type == "source-note":
        if len(sources) != 1:
            return None, "source-note 身份需要恰好一个原始来源路径"
        return {"kind": "source", "original": sources[0]}, None
    if card_type == "concept-page":
        definition = item.get("definition_claim")
        name = item.get("concept_name")
        if not isinstance(definition, str) or not definition.strip() \
                or not isinstance(name, str) or not name.strip():
            return None, "缺少绑定的 definition_claim/concept_name，进入人工复核（不从展示文本推断）"
        if definition not in statements:
            return None, "definition_claim 未出现在持久化 card_state 判断中，拒绝采用"
        def_kind = next(c.get("kind") for c in claims if c.get("statement") == definition)
        return {"kind": "concept", "concept_name": name, "definition": definition,
                "definition_kind": def_kind}, None
    if card_type == "case-story":
        level = item.get("card_level")
        origin = item.get("title")
        if level not in ("project", "mechanism") or not isinstance(origin, str) \
                or not origin.strip():
            return None, "缺少绑定的 card_level 或案例名，进入人工复核"
        mech_ids = _resolve_claim_ids(item.get("reusable_mechanism_claim_ids"),
                                      by_id, f"{where}.reusable_mechanism_claim_ids")
        inf_ids = _resolve_claim_ids(item.get("mechanism_inference_claim_ids"),
                                     by_id, f"{where}.mechanism_inference_claim_ids")
        if mech_ids:
            claim = mech_ids[0]
            role, statement, kind = "reusable", claim.get("statement"), claim.get("kind")
            if item.get("reusable_mechanism") != statement:
                return None, "reusable_mechanism 与 claim_ids 解析出的判断原句不一致，拒绝采用"
            if kind != "fact":
                return None, "reusable_mechanism 绑定的判断不是 fact-kind，拒绝采用"
        elif inf_ids:
            claim = inf_ids[0]
            role, statement, kind = "inference", claim.get("statement"), claim.get("kind")
            if item.get("mechanism_inference") != statement:
                return None, "mechanism_inference 与 claim_ids 解析出的判断原句不一致，拒绝采用"
            if kind != "inference":
                return None, "mechanism_inference 绑定的判断不是 inference-kind，拒绝采用"
        else:
            return None, "缺少绑定的机制/推断 claim_ids，进入人工复核"
        return {"kind": "case", "level": level, "origin": origin,
                "mechanism": statement, "mechanism_kind": kind,
                "mechanism_role": role}, None
    if card_type == "topic-page":
        analysis = state.get("analysis")
        question = analysis.get("research_question") if isinstance(analysis, dict) else None
        if not isinstance(question, str) or not question.strip():
            return None, "缺少显式研究问题（card_state.analysis.research_question），进入人工复核"
        return {"kind": "topic", "question": question}, None
    return None, f"未支持的卡片类型：{card_type!r}"


def _verify_item(item: dict[str, Any] | None, card_type: str,
                 state: dict[str, Any], sources: list[str]) -> str | None:
    if card_type in _ITEM_REQUIRED and not isinstance(item, dict):
        return f"{card_type} 必须携带 page.item（适配器保留结构化候选）"
    if item is None:
        return None
    if item.get("type") != card_type:
        return f"item.type 与 frontmatter type 不一致：{item.get('type')!r} != {card_type!r}"
    item_hashes = item.get("source_hashes")
    if item_hashes is not None:
        if not isinstance(item_hashes, dict) or set(item_hashes) != set(sources):
            return "item.source_hashes 与 page.sources 不一致，拒绝采用"
    for claim in _claims_of(state):
        for e in claim.get("evidence", []) or []:
            if isinstance(e, dict) and isinstance(e.get("source"), str) \
                    and e["source"] not in sources:
                return f"持久化判断引用了 sources 之外的来源：{e['source']}"
    return None


# ---------------------------------------------------------------------------
# Source-note unit verification (actual card_state.info_units shape)
# ---------------------------------------------------------------------------
def _verify_source_units(state: dict[str, Any], meta: dict[str, Any],
                         rel: str, raw_text: str, sha: str) -> str | None:
    """Re-verify persisted info_units against the captured raw snapshot via
    sa.locate_quote with exact coords/kind/hash (card_pipeline discipline)."""
    units = state.get("info_units")
    if not isinstance(units, list) or not units:
        return "source-note card_state.info_units 为空或形状非法，无可用信息单元"
    norm_text = normalized_text(raw_text)
    analysis = state.get("analysis")
    inner_hashes = analysis.get("source_hashes") if isinstance(analysis, dict) else None
    if not isinstance(inner_hashes, dict) or inner_hashes.get(rel) != sha:
        return "card_state.analysis.source_hashes 与原始捕获字节不一致"
    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            return f"info_units[{i}] 不是对象"
        if unit.get("verified") is not True:
            return f"info_units[{i}] 自身标记为未通过核验"
        if not isinstance(unit.get("kind"), str) or unit.get("kind") not in STATEMENT_KINDS:
            return f"info_units[{i}].kind 非法（必须是 sa.STATEMENT_KINDS 之一）"
        if unit.get("source") != rel:
            return f"info_units[{i}].source 与来源声明不一致"
        if unit.get("source_sha256") != sha:
            return f"info_units[{i}].source_sha256 与原始字节 hash 不一致"
        coords = {}
        for key in ("start", "end", "start_line", "end_line"):
            value = unit.get(key)
            if type(value) is not int:
                return f"info_units[{i}].{key} 缺失或不是精确整数"
            coords[key] = value
        try:
            located = locate_quote(norm_text, unit.get("quote"), coords["start_line"])
        except Exception:
            return f"info_units[{i}] 引用无法在原文中唯一定位"
        for key in ("start", "end", "start_line", "end_line"):
            if coords[key] != located[key]:
                return f"info_units[{i}].{key} 坐标与原文定位不一致"
    return None


# ---------------------------------------------------------------------------
# Per-page planning
# ---------------------------------------------------------------------------
def _plan_one(index: VaultIndex, cfg: dict[str, Any],
              page: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    rel_input = page.get("rel_path")
    outcome: dict[str, Any] = {"rel_path": rel_input, "chosen_target": None,
                               "outcome": "blocked", "reason": ""}

    def block(reason: str) -> tuple[None, dict[str, Any]]:
        outcome["reason"] = reason
        return None, outcome

    for key in ("content", "rel_path", "sources", "retrieval_source_hashes"):
        if key not in page:
            return block(f"页面缺少必填字段：{key}")
    content = page["content"]
    if not isinstance(content, str) or not content.strip():
        return block("页面内容为空")
    sources = page["sources"]
    if not isinstance(sources, list) or not sources or \
            not all(isinstance(s, str) and s for s in sources):
        return block("sources 必须是非空的具体文件路径列表")
    hashes = page["retrieval_source_hashes"]
    if not isinstance(hashes, dict) or not all(isinstance(p, str) and isinstance(h, str)
                                               and re.fullmatch(r"[0-9a-f]{64}", h)
                                               for p, h in hashes.items()):
        return block("retrieval_source_hashes 非法")
    if any(p not in hashes for p in sources):
        return block("原始来源缺少检索快照 hash")

    # Actual captured notes for EVERY dependency (index-enforced, no refresh).
    actual: dict[str, str] = {}
    texts: dict[str, str] = {}
    for rel, expected in hashes.items():
        try:
            _, raw, text = _captured_note(index, rel, expected)
        except TypedUpdateError as exc:
            return block(str(exc))
        actual[rel] = expected
        texts[rel] = text

    meta, body, prefix, _match = _split_frontmatter(content)
    card_type = meta.get("type")
    if card_type not in _TYPE_DIR_KEYS:
        return block(f"未知或缺失的卡片类型：{card_type!r}")
    try:
        state = _card_state_of(meta, rel_input, expected_type=card_type)
    except TypedUpdateError as exc:
        return block(str(exc))
    item = page.get("item")
    if reason := _verify_item(item, card_type, state, sources):
        return block(reason)

    if reason := _check_hash_consistency(hashes, actual, item, meta, state):
        return block(reason)

    if card_type == "source-note":
        rel = sources[0]
        if reason := _verify_source_units(state, meta, rel, texts[rel], actual[rel]):
            return block(f"source-note 信息单元核验失败：{reason}")
    else:
        # concept/case/topic: revalidate persisted compiled claims against
        # the captured originals (exact locators/quote/hash/claim ID);
        # malformed evidence is blocked, never repaired.
        docs = [{"path": rel, "content": texts[rel], "sha256": actual[rel]}
                for rel in hashes]
        if reason := _validate_compiled_claims(state, docs, rel_input):
            return block(reason)

    semantic, reason = _semantic_key(card_type, item, meta, state, sources, rel_input)
    if semantic is None:
        return block(reason)
    semantic_digest = _digest({"v": CARD_UPDATE_STATE_VERSION, "key": semantic})
    evidence = _evidence_pairs(state)
    try:
        wrapped = _wrap_body(body)
    except TypedUpdateError as exc:
        return block(str(exc))
    generated_digest = _sha_text(wrapped)

    new_state = {
        "version": CARD_UPDATE_STATE_VERSION,
        "card_type": card_type,
        "semantic": semantic,
        "semantic_digest": semantic_digest,
        "generated_digest": generated_digest,
        "source_hashes": dict(hashes),
        "evidence": sorted([list(pair) for pair in evidence]),
    }

    from .layout import knowledge_dirs
    dirs = knowledge_dirs(cfg)
    type_dir = dirs.get(_TYPE_DIR_KEYS[card_type], "")
    rel = _canonical_rel(index, rel_input)
    if rel is None:
        return block(f"目标路径非法或逃逸知识库：{rel_input!r}")
    if not rel.startswith(type_dir + "/"):
        return block(f"目标不在该类型的知识目录 {type_dir}/ 内：{rel}")

    matches = []
    for note in index.notes:
        if not note.is_knowledge or note.metadata.get("type") != card_type:
            continue
        old_state = _state_value(note.metadata, "card_update_state")
        if not isinstance(old_state, dict):
            continue
        old_version = old_state.get("version")
        if type(old_version) is not int or old_version != CARD_UPDATE_STATE_VERSION:
            # A malformed state with the same persisted semantic key must not
            # be bypassed by creating a suffixed sibling. Block this page so
            # the reviewer can repair the existing target explicitly.
            stored_key = old_state.get("semantic")
            if (isinstance(stored_key, dict)
                    and _digest({"v": CARD_UPDATE_STATE_VERSION,
                                 "key": stored_key}) == semantic_digest):
                return block(
                    f"既有卡片 {note.rel} 的 card_update_state.version 必须是精确整数 "
                    f"{CARD_UPDATE_STATE_VERSION}，得到 {old_version!r}；blocked")
            continue
        # Validate the STORED digest against its OWN stored ingredients before
        # trusting any match; a stale/forged digest never matches.
        stored_key = old_state.get("semantic")
        if not isinstance(stored_key, dict) \
                or _digest({"v": CARD_UPDATE_STATE_VERSION, "key": stored_key}) \
                != old_state.get("semantic_digest") \
                or old_state.get("semantic_digest") != semantic_digest:
            continue
        identity = identity_from_metadata(note.metadata)
        if identity is None:
            continue  # A2 interim cards without identity: not eligible
        if not note.rel.startswith(type_dir + "/"):
            continue  # matched target must stay under the type directory
        matches.append((note, old_state, identity))

    if len(matches) > 1:
        return block(f"身份匹配到 {len(matches)} 张既有卡片，歧义 blocked；请先人工合并")
    if matches:
        return _plan_update(index, page, outcome, matches[0], meta, body, state,
                            semantic, semantic_digest, evidence, generated_digest,
                            new_state, wrapped, actual, type_dir)
    return _plan_create(index, page, outcome, meta, prefix, sources, hashes,
                        new_state, wrapped, rel, semantic_digest)


def _plan_create(index: VaultIndex, page: dict[str, Any], outcome: dict[str, Any],
                 meta: dict[str, Any], prefix: str, sources: list[str],
                 hashes: dict[str, str], new_state: dict[str, Any],
                 wrapped: str, rel: str, semantic_digest: str):
    rel, collision_reason = _resolve_create_rel(index, rel, semantic_digest)
    if rel is None:
        outcome.update({"reason": collision_reason})
        return None, outcome
    outcome["reason"] = collision_reason or "无既有同身份卡片，提出 create 提案"
    updated_content = _patch_owned_fields(
        prefix + wrapped + "\n",
        {"card_update_state": new_state, "review_required": True},
        candidate_keys=set(meta))
    outcome.update({"outcome": "create", "chosen_target": rel})
    proposal = _envelope(page, meta, sources, hashes)
    proposal.update({"operation": "create", "rel_path": rel, "target": rel,
                     "canonical_path": rel, "content": updated_content,
                     "content_sha256": _sha_text(updated_content),
                     "card_update_state": new_state, "review_required": True})
    return proposal, outcome


def _envelope(page: dict[str, Any], meta: dict[str, Any],
              sources: list[str], hashes: dict[str, str]) -> dict[str, Any]:
    """dict(page, ...) preserving unknown/future integration metadata, with
    the helper's owned fields overridden. Known supplied values
    (item/origin/analysis_mode/confidence) are never nulled: page values win,
    otherwise they are derived from the candidate frontmatter so they stay
    consistent and meaningful."""
    proposal = dict(page)
    proposal["sources"] = list(sources)
    proposal["retrieval_source_hashes"] = dict(hashes)
    proposal["item"] = page.get("item")
    for key in ("origin", "analysis_mode", "confidence"):
        value = page.get(key)
        if value is None:
            value = meta.get(key)
        proposal[key] = value
    return proposal


def _resolve_create_rel(index: VaultIndex, rel: str,
                        semantic_digest: str) -> tuple[str | None, str | None]:
    occupied = rel in index.by_rel or (index.root / rel).exists()
    if not occupied:
        return rel, None
    suffix = semantic_digest[:8]
    p = PurePosixPath(rel)
    candidate = str(p.with_name(f"{p.stem}-{suffix}{p.suffix}"))
    if candidate in index.by_rel or (index.root / candidate).exists():
        return None, f"目标及其身份后缀路径均被占用：{rel} / {candidate}"
    return candidate, (f"目标 {rel} 已被不同身份的卡片占用；不改写不收编旧卡，"
                       f"改用确定性身份后缀新路径 {candidate}，请人工确认")


def _plan_update(index: VaultIndex, page: dict[str, Any], outcome: dict[str, Any],
                 match: tuple, meta: dict[str, Any], body: str, state: dict[str, Any],
                 semantic: dict[str, Any], semantic_digest: str, evidence: set,
                 generated_digest: str, new_state: dict[str, Any], wrapped: str,
                 actual: dict[str, str], type_dir: str):
    from .plan_objects import update_base
    note, old_state, identity = match
    object_id, revision = identity
    if note.rel != note.canonical_path:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": f"既有卡片 canonical_path 与路径不一致：{note.rel}"})
        return None, outcome
    try:
        _, raw, text = _captured_note(index, note.rel, note.sha256)
    except TypedUpdateError as exc:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": str(exc)})
        return None, outcome
    try:
        located = _locate_block(text)
    except TypedUpdateError as exc:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": str(exc)})
        return None, outcome
    if located is None:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": "既有卡片缺少托管区块；本 helper 不收编无区块卡片，请人工处理"})
        return None, outcome
    begin, end = located
    old_meta = note.metadata
    old = _state_value(old_meta, "card_update_state")
    if not isinstance(old, dict) or old.get("generated_digest") != _sha_text(text[begin:end]):
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": "托管区块摘要与记录不一致（疑似人工修改）；blocked，不覆盖歧义编辑"})
        return None, outcome
    # Stored digest/ingredients must validate against the target's own
    # card_state before the match is trusted at all: EXACT int version == 1
    # and type equal to the stored update-state card_type.
    old_card_state = _card_state_of(old_meta, note.rel,
                                    expected_type=old_state.get("card_type"))
    try:
        recorded = _recorded_evidence(old)
    except TypedUpdateError as exc:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": str(exc)})
        return None, outcome
    if _evidence_pairs(old_card_state) != recorded:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": "frontmatter card_state 证据与记录的语义身份不一致"
                                  "（疑似人工修改）；blocked，不静默覆盖"})
        return None, outcome
    # The stored semantic kind/role must agree with the target's CURRENT
    # card_state claims (not merely statement membership), and the target's
    # compiled claims must revalidate against ITS captured sources before
    # reuse is trusted.
    if reason := _validate_stored_semantic(old_state, old_card_state):
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": reason})
        return None, outcome
    if old_state.get("card_type") != "source-note":
        # Revalidate the target's compiled claims against ITS captured
        # sources — but only pins whose bytes still match the stored hash.
        # Pins whose file legitimately changed are handled by the
        # version-change logic below (their old bytes no longer exist).
        old_docs: list[dict[str, str]] = []
        stale_pins = False
        try:
            for rel, h in (old_state.get("source_hashes") or {}).items():
                note_i = index.by_rel.get(rel)
                if note_i is None or note_i.sha256 != h:
                    stale_pins = True
                    continue
                _, _raw, old_text = _captured_note(index, rel, h)
                old_docs.append({"path": rel, "content": old_text, "sha256": h})
        except TypedUpdateError as exc:
            outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                            "reason": str(exc)})
            return None, outcome
        if not stale_pins:
            if reason := _validate_compiled_claims(old_card_state, old_docs, note.rel):
                outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                                "reason": reason})
                return None, outcome
    stmts = {c.get("statement") for c in _claims_of(old_card_state)}
    key = old_state.get("semantic") or {}
    missing = [key[f] for f in ("definition", "mechanism")
               if isinstance(key.get(f), str) and key[f] not in stmts]
    if missing:
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": "语义身份所引判断已不在目标 card_state 中"
                                  "（疑似人工修改）；blocked，不静默覆盖"})
        return None, outcome

    # Automatic reuse REQUIRES verified overlapping evidence for
    # concept/case/topic: same semantic key with fully disjoint evidence is an
    # ambiguity (never a silent re-bind onto a disjoint object). Source cards
    # are path-identified and allow genuine version replacement.
    new_pairs = {(pair[0], pair[1]) for pair in new_state["evidence"]}
    if old_state.get("card_type") != "source-note" and not (new_pairs & recorded):
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": "语义身份相同但证据完全不相交（疑似同义异证对象）；"
                                  "进入人工复核，不做静默复用"})
        return None, outcome

    old_hashes = old.get("source_hashes") or {}
    hashes_changed = old_hashes != new_state["source_hashes"]
    if generated_digest == old.get("generated_digest") and not hashes_changed \
            and recorded == new_pairs:
        outcome.update({"outcome": "noop", "chosen_target": note.rel,
                        "reason": "语义身份、证据与内容完全一致；不做修订，不产生重复"})
        return None, outcome

    # Version change = ONLY common old/new source paths whose hashes differ.
    # A newly ADDED source is not an old-version change; a removed source must
    # not silently retain obsolete headers (sources/source_hashes are synced).
    common = set(old_hashes) & set(new_state["source_hashes"])
    version_changed = any(old_hashes[rel] != new_state["source_hashes"][rel]
                          for rel in common)
    header = _HEADER.match(text)
    outside_body = text[header.end():begin] + text[end:] if header else text[:begin] + text[end:]
    if version_changed and outside_body.strip():
        outcome.update({"outcome": "blocked", "chosen_target": note.rel,
                        "reason": f"共同来源版本已变化（{sorted(common)}）且区块外存在"
                                  "非空白人工文本；无法判断手写事实是否属于旧版本，"
                                  "blocked 进入人工复核"})
        return None, outcome

    # Synchronize machine-owned outer fields with the FRESH candidate so the
    # updated card is internally and downstream consistent (collector
    # eligibility). created/title/custom YAML/comments stay untouched.
    sync: dict[str, Any] = {"updated": dt.date.today().isoformat(),
                            "card_state": state,
                            "card_update_state": new_state,
                            "review_required": True}
    for key in ("sources", "source_hashes", "related", "status", "stage",
                "confidence", "coverage", "analysis_mode", "schema_version",
                "generator_version", "quality_flags", "origin"):
        if key in meta:
            sync[key] = meta[key]
    # Tag policy: retain existing safe (plain-string) user tags, merged with
    # the new candidate's tags; non-string values are dropped.
    old_tags = old_meta.get("tags")
    new_tags = meta.get("tags")
    merged = [t for t in (old_tags if isinstance(old_tags, list) else [])
              if isinstance(t, str) and t]
    for t in (new_tags if isinstance(new_tags, list) else []):
        if isinstance(t, str) and t and t not in merged:
            merged.append(t)
    if merged or "tags" in meta or isinstance(old_tags, list):
        sync["tags"] = merged
    updated = _patch_owned_fields(text[:begin] + wrapped + text[end:], sync,
                                  candidate_keys=set(meta))
    base = update_base(note)
    proposal = _envelope(page, meta, page["sources"], page["retrieval_source_hashes"])
    proposal.update({"operation": "update", "rel_path": note.rel, "target": note.rel,
                     "canonical_path": note.rel,
                     "content": updated, "content_sha256": _sha_text(updated),
                     "card_update_state": new_state, "review_required": True,
                     "base_sha256": base["base_sha256"],
                     "base_object_id": base["base_object_id"],
                     "base_revision": base["base_revision"]})
    if evidence != new_pairs and not hashes_changed:
        reason = "证据有新增/变化：整块替换生成区（区块外文本逐字节保留）"
    else:
        reason = "证据或来源版本有变化：整块替换生成区并同步机器自有字段（区块外文本逐字节保留）"
    outcome.update({"outcome": "update", "chosen_target": note.rel, "reason": reason})
    return proposal, outcome


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def prepare_typed_updates(index: VaultIndex, cfg: dict[str, Any],
                          pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Plan create/update/noop/blocked proposals for typed generated cards.

    Pure: no writes, no provider calls, no ID invention. Returns
    {"pages": [...], "outcomes": [...], "issues": [...]}. Every create/update
    proposal is review_required=True and keeps item/origin/analysis_mode/
    confidence; identity binding stays with core.plan_objects.
    """
    result: dict[str, Any] = {"pages": [], "outcomes": [], "issues": []}
    if not isinstance(pages, list):
        result["issues"].append("pages 必须是列表")
        return result
    seen: dict[tuple[str, str, frozenset, frozenset], str] = {}
    used_rels: set[str] = set(index.by_rel)
    for page in pages:
        if not isinstance(page, dict):
            result["issues"].append("page 必须是对象")
            continue
        try:
            proposal, outcome = _plan_one(index, cfg, page)
        except TypedUpdateError as exc:
            proposal = None
            outcome = {"rel_path": page.get("rel_path"), "chosen_target": None,
                       "outcome": "blocked", "reason": str(exc)}
        except (OSError, UnicodeDecodeError) as exc:
            proposal = None
            outcome = {"rel_path": page.get("rel_path"), "chosen_target": None,
                       "outcome": "blocked", "reason": f"读取/解码失败：{exc}"}
        result["outcomes"].append(outcome)
        if proposal is None:
            # Only blocked/error proposals are failure-quality issues; a
            # successful noop is never an issue.
            if outcome["outcome"] != "noop":
                result["issues"].append(f"{outcome.get('rel_path')}: {outcome['reason']}")
            continue
        state = proposal["card_update_state"]
        batch_key = (state["semantic_digest"], state["generated_digest"],
                     frozenset((p[0], p[1]) for p in state["evidence"]),
                     frozenset(state["source_hashes"].items()))
        if batch_key in seen:
            first = seen[batch_key]
            outcome.update({"chosen_target": first, "outcome": "noop",
                            "reason": f"同批次完全相同的候选（含来源版本），已并入 {first}"})
            continue
        rel = proposal["rel_path"]
        if rel in used_rels and proposal["operation"] == "create":
            digest = state["semantic_digest"]
            p = PurePosixPath(rel)
            candidate = str(p.with_name(f"{p.stem}-{digest[:8]}{p.suffix}"))
            if candidate in used_rels:
                outcome.update({"chosen_target": None, "outcome": "blocked",
                                "reason": f"同批次路径冲突且后缀路径也被占用：{rel}"})
                result["issues"].append(f"{rel}: {outcome['reason']}")
                continue
            outcome["reason"] = f"同批次不同候选同名，使用稳定身份后缀路径 {candidate}"
            proposal["rel_path"] = candidate
            proposal["target"] = candidate
            proposal["canonical_path"] = candidate
            outcome["chosen_target"] = candidate
        used_rels.add(proposal["rel_path"])
        seen[batch_key] = proposal["rel_path"]
        result["pages"].append(proposal)
    return result
