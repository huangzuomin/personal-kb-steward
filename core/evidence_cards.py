"""Shared concept/case generator plumbing (M2).

Small, deliberately narrow helper reused by core.concept_generation and
core.case_generation. It owns ONLY the mechanics both generators share:

- input note snapshot verification (same rules as core.topic_generation;
  the FULL raw snapshot must hash-match its declared raw-byte sha256),
- budget constraint parsing and enforcement (never truncate; refuse),
- freeform sanitization (model [[wikilink]] syntax is made inert),
- link splitting (real wikilinks only to known existing paths),
- single bounded provider call with pre/post secret screening and a Jinja
  preflight BEFORE the call,
- claim compilation through core.claims (duplicate judgments merged),
- card_state frontmatter patching via the narrow _patch_header semantics.

It does NOT define any card type truth: canonical schemas live in
core/schemas/*.json and are registered through
core.card_contracts.register_card_schema. Path rules are imported from
core.topic_generation (is_safe_rel_path) so all M2/M3 generators share one
definition of a safe vault-relative path.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from .card_contracts import register_card_schema
from .claims import Claim, EvidenceError, compile_claims
from .content_safety import assert_safe_content, safe_error_message
from .jinja_renderer import render_template
from .json_contract import extract_json
from .llm import call_chat_completion
from .topic_generation import is_safe_rel_path
from . import text_integrity

EVIDENCE_CARD_STATE_VERSION = 1

# Compact upstream source-card analysis seam (Astra review item 3): the
# integration adapter MAY attach a small program-provided analysis object per
# note via note.metadata["upstream_analysis"]. Only the fields below, size
# bounded and screened, are transmitted or persisted — arbitrary whole-index
# metadata is never passed through. The ORIGINAL snapshot stays the evidence.
UPSTREAM_KEY = "upstream_analysis"
_UPSTREAM_LIST_KEYS = ("limitations", "speakers")
_MAX_UPSTREAM_ITEMS = 10
_MAX_UPSTREAM_VALUE_CHARS = 500


def extract_upstream_analysis(metadata: Any, rel: str,
                              issues: list[str]) -> dict[str, Any]:
    """Return a bounded, sanitized upstream analysis dict ({} when absent).

    Anything outside the allow-list, oversized, or non-string is recorded as
    an issue and dropped — never forwarded."""
    if not isinstance(metadata, dict) or UPSTREAM_KEY not in metadata:
        return {}
    raw = metadata[UPSTREAM_KEY]
    if not isinstance(raw, dict):
        issues.append(f"{rel}: {UPSTREAM_KEY} 不是对象，已忽略")
        return {}
    upstream: dict[str, Any] = {}
    kind = raw.get("source_kind")
    if isinstance(kind, str) and kind.strip():
        upstream["source_kind"] = sanitize_freeform(
            kind.strip()[:_MAX_UPSTREAM_VALUE_CHARS], issues, f"{rel}.{UPSTREAM_KEY}.source_kind")
    elif kind is not None:
        issues.append(f"{rel}: {UPSTREAM_KEY}.source_kind 非字符串，已忽略")
    for key in _UPSTREAM_LIST_KEYS:
        items = raw.get(key)
        if items is None:
            continue
        if not isinstance(items, list):
            issues.append(f"{rel}: {UPSTREAM_KEY}.{key} 不是数组，已忽略")
            continue
        cleaned = [sanitize_freeform(v[:_MAX_UPSTREAM_VALUE_CHARS], issues,
                                     f"{rel}.{UPSTREAM_KEY}.{key}")
                   for v in items if isinstance(v, str) and v.strip()]
        if len(cleaned) > _MAX_UPSTREAM_ITEMS:
            issues.append(
                f"{rel}: {UPSTREAM_KEY}.{key} 超过 {_MAX_UPSTREAM_ITEMS} 条，已截断记录")
            cleaned = cleaned[:_MAX_UPSTREAM_ITEMS]
        upstream[key] = cleaned
    return upstream


class EvidenceCardError(RuntimeError):
    """A fail-closed generation problem surfaced to the caller, never retried."""


def load_owned_schema(schema_path: Path) -> dict[str, Any]:
    """Load an owned canonical schema file and register it (single truth)."""
    schema = json.loads(
        schema_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n"))
    register_card_schema(schema)
    return schema


def parse_generation_settings(cfg: dict[str, Any], section: str) -> dict[str, int]:
    """Validate <section>.max_source_chars / max_context_chars (positive ints)."""
    raw = (cfg or {}).get(section, {})
    if not isinstance(raw, dict):
        raise EvidenceCardError(f"{section} 配置必须是对象")
    settings: dict[str, int] = {}
    for key, default in (
        ("max_source_chars", 20000), ("max_context_chars", 60000),
    ):
        value = raw.get(key, default)
        if type(value) is not int or value < 1:
            raise EvidenceCardError(f"{section}.{key} 必须是正整数：{value!r}")
        settings[key] = value
    return settings


# ---------------------------------------------------------------------------
# Input verification (same contract as topic_generation notes)
# ---------------------------------------------------------------------------
def verify_snapshot(note: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (normalized note, issues); None means the note is refused."""
    if not isinstance(note, dict):
        raise EvidenceCardError(f"notes[{index}] 必须是对象")
    for key in ("rel", "title", "body", "metadata", "source_text", "source_sha256"):
        if key not in note:
            raise EvidenceCardError(f"notes[{index}] 缺少必填字段：{key}")
    rel = note["rel"]
    if not is_safe_rel_path(rel):
        raise EvidenceCardError(
            f"notes[{index}].rel 不是安全的 vault 相对路径（拒绝绝对路径、反斜杠、"
            f"穿越、控制字符或链接元字符）：{rel!r}")
    source_text = note["source_text"]
    sha = note["source_sha256"]
    if not isinstance(source_text, str):
        return None, [f"{rel}: 缺少完整原始快照（source_text），已拒绝该来源"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None, [f"{rel}: 缺少合法的原始字节 hash（source_sha256），已拒绝该来源"]
    if hashlib.sha256(source_text.encode("utf-8")).hexdigest() != sha:
        # Never accept a cleaned-body hash as an original snapshot hash.
        return None, [f"{rel}: 原始快照与 source_sha256 不匹配，已拒绝该来源；不得以清洗后正文 hash 冒充"]
    # T10: U+FFFD means the original text was damaged in decoding; refuse the
    # input (per-input issue) BEFORE any provider call. Unaffected sources in a
    # mixed batch keep their own provenance; the batch is never "complete".
    damaged = text_integrity.damaged_reasons(note, rel)
    if damaged:
        return None, damaged
    body, title, metadata = note["body"], note["title"], note["metadata"]
    if not isinstance(body, str) or not isinstance(title, str) or not isinstance(metadata, dict):
        raise EvidenceCardError(f"notes[{index}] 的 title/body/metadata 类型非法")
    local_issues: list[str] = []
    upstream = extract_upstream_analysis(metadata, rel, local_issues)
    return {
        "rel": rel, "title": title, "body": body, "metadata": metadata,
        "source_text": source_text, "source_sha256": sha, "upstream": upstream,
    }, local_issues


def source_document(note: dict[str, Any]) -> dict[str, str]:
    """Provider context AND claim quote coordinates use the FULL raw snapshot."""
    return {"path": note["rel"], "title": note["title"], "content": note["source_text"],
            "sha256": note["source_sha256"]}


def dedupe_verified(notes: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    """Drop same-rel repeats with an identical snapshot; conflicting hashes for
    one rel are a hard error (the trusted version is ambiguous)."""
    seen: dict[str, str] = {}
    kept: list[dict[str, Any]] = []
    for note in notes:
        rel = note["rel"]
        if rel in seen:
            if seen[rel] != note["source_sha256"]:
                raise EvidenceCardError(
                    f"同一路径 {rel} 提供了两个不同的原始快照 hash，"
                    "无法确定可信版本；拒绝生成")
            issues.append(f"来源 {rel} 重复提供且快照一致，已去重")
            continue
        seen[rel] = note["source_sha256"]
        kept.append(note)
    return kept


# ---------------------------------------------------------------------------
# Freeform sanitization and links
# ---------------------------------------------------------------------------
def sanitize_freeform(value: Any, issues: list[str], where: str) -> Any:
    """Render [[wikilink]] syntax in model freeform text inert (literal text)."""
    if isinstance(value, str):
        if "[[" in value or "]]" in value:
            issues.append(f"{where}: 自由文本包含链接语法，已按纯文本处理（不生成未验证链接）")
            return value.replace("[[", "［").replace("]]", "］")
        return value
    if isinstance(value, list):
        return [sanitize_freeform(v, issues, where) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_freeform(v, issues, where) for k, v in value.items()}
    return value


def safe_paths(raw: Any) -> list[str]:
    return [p for p in (raw if isinstance(raw, list) else [])
            if isinstance(p, str) and is_safe_rel_path(p)]


def split_links(raw_related: Any, raw_pending: Any, known_paths: list[str],
                note_rels: set[str], issues: list[str]) -> tuple[list[str], list[str]]:
    """Real wikilinks only to known existing paths; everything else stays
    pending, and pending text is stored WITHOUT link syntax."""
    allowed = set(known_paths) - note_rels
    related: list[str] = []
    pending: list[str] = []
    for item in raw_related if isinstance(raw_related, list) else []:
        if not isinstance(item, str) or not item:
            continue
        if item in allowed:
            related.append(item)
        else:
            issues.append(f"related 引用了未知或非法路径 {item!r}，降级为待创建裸文本路径")
            clean = item.replace("[[", "［").replace("]]", "］")
            if clean not in pending:
                pending.append(clean)
    for item in raw_pending if isinstance(raw_pending, list) else []:
        if isinstance(item, str) and item.strip():
            clean = item.replace("[[", "［").replace("]]", "］")
            if clean != item:
                issues.append("pending_paths 含链接语法，已按裸文本保留")
            if clean not in related and clean not in pending:
                pending.append(clean)
    return related, pending


def normalize_provenance_map(raw: Any, notes: list[dict[str, Any]],
                             issues: list[str]) -> list[dict[str, Any]]:
    """Keep only entries referencing provided sources; attach trusted hashes.

    Program-provided upstream analysis (limitations/source_kind) is MERGED in
    and can be neither erased nor overwritten by the model (Astra item 3):
    the model may add limitations, never remove or replace upstream ones.
    Missing/blank entries are recorded, never silently nulled."""
    result: list[dict[str, Any]] = []
    known = {n["rel"]: n for n in notes}
    if not isinstance(raw, list):
        if raw:
            issues.append("模型未提供合法的 provenance_map 数组")
    else:
        seen: set[str] = set()
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                issues.append(f"provenance_map[{i}] 不是对象，已丢弃")
                continue
            rel = item.get("rel")
            if not is_safe_rel_path(rel) or rel not in known:
                issues.append(f"provenance_map[{i}].rel 不在提供来源中或路径非法，已丢弃")
                continue
            if rel in seen:
                continue
            seen.add(rel)
            provenance = item.get("provenance")
            if not isinstance(provenance, str) or not provenance.strip():
                issues.append(f"provenance_map[{i}].provenance 为空，已补空记录")
                provenance = ""
            limitations = sanitize_freeform(
                item.get("limitations") if isinstance(item.get("limitations"), list)
                and all(isinstance(x, str) for x in item["limitations"]) else [],
                issues, f"provenance_map[{i}].limitations")
            result.append({"rel": rel,
                           "source_sha256": known[rel]["source_sha256"],
                           "provenance": sanitize_freeform(
                               provenance, issues, f"provenance_map[{i}].provenance"),
                           "limitations": limitations})
    for note in notes:
        rel = note["rel"]
        entry = next((e for e in result if e["rel"] == rel), None)
        upstream = note.get("upstream") or {}
        if entry is None:
            entry = {"rel": rel, "source_sha256": note["source_sha256"],
                     "provenance": "", "limitations": []}
            result.append(entry)
            issues.append(f"provenance_map 缺少来源 {rel} 的条目，已补空记录")
        if upstream.get("source_kind") and not entry.get("source_kind"):
            # Program-owned classification: the model cannot overwrite it.
            entry["source_kind"] = upstream["source_kind"]
        upstream_limits = upstream.get("limitations") or []
        if upstream_limits:
            merged = list(upstream_limits)
            for limit in entry["limitations"]:
                if limit not in merged:
                    merged.append(limit)
            if merged != entry["limitations"]:
                issues.append(f"{rel}: 已合并上游来源限制（模型不可删除上游限制）")
            entry["limitations"] = merged
    return result


# ---------------------------------------------------------------------------
# Claim compilation (duplicate judgments merged, bad evidence dropped)
# ---------------------------------------------------------------------------
def compile_model_claims(
    raw_items: Any, notes: list[dict[str, Any]], issues: list[str], where: str,
) -> tuple[list[Claim], set[str]]:
    """Compile model judgments through core.claims; bad evidence is dropped.

    Exact duplicate judgments (same statement+kind) are MERGED: their distinct
    validated evidence is combined into one claim. Returns the compiled claims
    and the set of source paths actually cited by surviving claims.
    """
    claims: list[Claim] = []
    by_key: dict[tuple[str, str], int] = {}
    documents = [source_document(n) for n in notes]
    if not isinstance(raw_items, list):
        if raw_items:
            issues.append(f"{where}：模型未提供合法的 judgments 数组；视作无已支持判断")
        return claims, set()
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            issues.append(f"{where}.judgments[{i}] 不是对象，已丢弃")
            continue
        try:
            compiled = compile_claims([item], documents)[0]
        except EvidenceError as exc:
            issues.append(
                f"{where}.judgments[{i}] 证据编译失败，已丢弃（不接受伪造证据或路径）：{exc}")
            continue
        key = (compiled.statement, compiled.kind)
        if key in by_key:
            idx = by_key[key]
            existing = claims[idx]
            merged = {e for e in existing.evidence} | set(compiled.evidence)
            if len(merged) != len(existing.evidence):
                claims[idx] = Claim(existing.claim_id, existing.statement,
                                    existing.kind, existing.confidence,
                                    tuple(sorted(merged, key=lambda e: (e.source, e.start))))
                issues.append(
                    f"{where}.judgments[{i}] 与已有判断完全重复，证据已合并（claim {existing.claim_id}）")
            else:
                issues.append(f"{where}.judgments[{i}] 与已有判断完全重复且证据相同，已去重")
            continue
        by_key[key] = len(claims)
        claims.append(compiled)
    usable = {e.source for c in claims for e in c.evidence}
    return claims, usable


def merge_claims(existing: Claim, extra: Claim) -> tuple[Claim, bool]:
    """UNION the evidence of two identical (statement, kind) claims.

    Returns (merged claim, changed) — used by dedupe so evidence from
    complementary inputs is never silently discarded (Astra item 4)."""
    merged = {e for e in existing.evidence} | set(extra.evidence)
    if len(merged) == len(existing.evidence):
        return existing, False
    return (Claim(existing.claim_id, existing.statement, existing.kind,
                  existing.confidence,
                  tuple(sorted(merged, key=lambda e: (e.source, e.start)))), True)


def absorb_claims(claims: list[Claim], incoming: list[Claim],
                  issues: list[str], where: str) -> None:
    """Absorb incoming claims into claims in place, unioning evidence of
    identical (statement, kind) judgments."""
    by_key = {(c.statement, c.kind): i for i, c in enumerate(claims)}
    for claim in incoming:
        key = (claim.statement, claim.kind)
        if key in by_key:
            merged, changed = merge_claims(claims[by_key[key]], claim)
            claims[by_key[key]] = merged
            if changed:
                issues.append(f"{where}：与已有判断完全重复，新证据已合并"
                              f"（claim {claim.claim_id}）")
        else:
            by_key[key] = len(claims)
            claims.append(claim)


def claims_by_statement(claims: list[Claim]) -> dict[str, Claim]:
    """Map statement -> first compiled claim; duplicates cannot multiply sides."""
    by_statement: dict[str, Claim] = {}
    for c in claims:
        by_statement.setdefault(c.statement, c)
    return by_statement


def resolve_claim_refs(refs: Any, by_statement: dict[str, Claim],
                       issues: list[str], where: str) -> list[str]:
    """Resolve exact claim-statement references to claim IDs; unknown refs are
    recorded, never silently accepted."""
    claim_ids: list[str] = []
    for ref in refs if isinstance(refs, list) else []:
        claim = by_statement.get(ref) if isinstance(ref, str) else None
        if claim is not None and claim.claim_id not in claim_ids:
            claim_ids.append(claim.claim_id)
        elif claim is None and isinstance(ref, str) and ref:
            issues.append(f"{where} 引用了未编译判断，已忽略：{ref[:50]}…")
    return claim_ids


# ---------------------------------------------------------------------------
# Rendering / persistence
# ---------------------------------------------------------------------------
def patch_card_state(rendered: str, card_state: dict[str, Any],
                     err_cls: type[Exception]) -> str:
    """Insert card_state as a frontmatter field after template render.

    Mirrors core.reconcile._patch_header semantics narrowly: only adds the one
    owned field, preserves everything else, refuses without full frontmatter.
    """
    lines = rendered.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise err_cls("渲染结果缺少 frontmatter，无法持久化 card_state")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise err_cls("渲染结果 frontmatter 未闭合，无法持久化 card_state")
    encoded = json.dumps(card_state, ensure_ascii=False)
    return "".join(lines[:end]) + f"card_state: {encoded}\n" + "".join(lines[end:])


def base_page_context(candidate: dict[str, Any], today: str | None) -> dict[str, Any]:
    """Context vars required by base_frontmatter.j2 (program-owned metadata)."""
    import datetime as dt

    return {
        "title": candidate["title"],
        "type": candidate["type"],
        "status": candidate["status"],
        "stage": candidate["stage"],
        "sources": candidate["sources"],
        "related": candidate["related"],
        "tags": candidate["tags"],
        "confidence": candidate["confidence"],
        "review_required": candidate["review_required"],
        "origin": candidate["origin"],
        "schema_version": candidate["schema_version"],
        "generator_version": candidate["generator_version"],
        "analysis_mode": candidate["analysis_mode"],
        "coverage": candidate["coverage"],
        "source_hashes": candidate["source_hashes"],
        "quality_flags": candidate["quality_flags"],
        "today": today or dt.date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# One bounded provider call (shared pre-call / post-call discipline)
# ---------------------------------------------------------------------------
def bounded_call(
    *,
    notes: Any,
    cfg: dict[str, Any],
    section: str,
    system_prompt: str,
    payload_builder: Callable[[list[dict[str, Any]], list[str]], dict[str, Any]],
    preflight: Callable[[], None],
    provider: Callable[[dict[str, Any], str, dict[str, Any]], str],
    viability_key: str,
    analysis_mode: str,
    known_paths: list[str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Run input verification, budgets, preflight, secrets and ONE provider
    call plus JSON/viability parsing.

    Returns (context, terminal_result): when context is None the caller must
    return terminal_result (a complete generator result dict). Otherwise
    context = {"data", "verified", "issues", "known", "note_rels", "settings"}
    and the caller finishes with module-specific post-processing.
    """
    result: dict[str, Any] = {
        "state": "error", "reason": None, "items": [], "pages": [],
        "claims": [], "analysis": {}, "issues": [],
    }

    if analysis_mode != "llm":
        result["state"] = "disabled"
        result["reason"] = (
            f"analysis_mode={analysis_mode}：生成依赖模型综合，非 LLM 模式拒绝产出结论")
        return None, result

    try:
        settings = parse_generation_settings(cfg, section)
    except EvidenceCardError as exc:
        result["state"] = "error"
        result["reason"] = str(exc)
        return None, result
    if not isinstance(notes, list) or not notes:
        result["state"] = "error"
        result["reason"] = "未提供任何来源"
        return None, result

    verified: list[dict[str, Any]] = []
    issues: list[str] = []
    for i, note in enumerate(notes):
        try:
            ok, note_issues = verify_snapshot(note, i)
        except EvidenceCardError as exc:
            result["state"] = "error"
            result["reason"] = str(exc)
            result["issues"] = issues
            return None, result
        issues.extend(note_issues)
        if ok is not None:
            verified.append(ok)
    try:
        verified = dedupe_verified(verified, issues)
    except EvidenceCardError as exc:
        result["state"] = "error"
        result["reason"] = str(exc)
        result["issues"] = issues
        return None, result

    # Budget validation BEFORE any call: never truncate, refuse instead.
    for note in verified:
        if len(note["source_text"]) > settings["max_source_chars"]:
            result["state"] = "error"
            result["reason"] = (
                f"来源 {note['rel']} 原始快照 {len(note['source_text'])} 字符超过 "
                f"{section}.max_source_chars={settings['max_source_chars']}，"
                "拒绝截断后调用模型")
            result["issues"] = issues
            return None, result
    known = [p for p in (known_paths or []) if isinstance(p, str) and is_safe_rel_path(p)]
    payload = payload_builder(verified, known)
    payload_size = len(json.dumps(payload, ensure_ascii=False))
    if payload_size > settings["max_context_chars"]:
        result["state"] = "error"
        result["reason"] = (
            f"完整载荷（含全部原始快照与 known_paths）{payload_size} 字符超过 "
            f"{section}.max_context_chars={settings['max_context_chars']}，"
            "拒绝截断后调用模型")
        result["issues"] = issues
        return None, result
    if not verified:
        result["state"] = "error"
        result["reason"] = "所有来源的原始快照缺失或校验失败，已全部拒绝；不生成任何内容"
        result["issues"] = issues
        return None, result
    if not any(n["body"].strip() for n in verified):
        result["state"] = "zero"
        result["reason"] = "所有可用来源均为空或无实质内容，不强行生成卡片"
        result["issues"] = issues
        return None, result

    try:
        preflight()
    except Exception as exc:
        result["state"] = "error"
        result["reason"] = f"渲染预检失败，未发起模型调用：{safe_error_message(exc)}"
        result["issues"] = issues
        return None, result
    try:
        assert_safe_content(payload)  # pre-response secret screening
    except Exception as exc:
        result["state"] = "error"
        result["reason"] = f"敏感内容检查阻断输入，未发起模型调用：{safe_error_message(exc)}"
        result["issues"] = issues
        return None, result

    try:
        content = provider(cfg, system_prompt, payload)
    except Exception as exc:
        result["state"] = "error"
        result["reason"] = f"模型调用失败（单次有界调用，无重试）：{safe_error_message(exc)}"
        result["issues"] = issues
        return None, result
    try:
        assert_safe_content(content)  # post-response secret screening
    except Exception as exc:
        result["state"] = "error"
        result["reason"] = f"模型返回内容被敏感内容检查阻断：{safe_error_message(exc)}"
        result["issues"] = issues
        return None, result
    try:
        # T10: encoding-damaged response is an error, not a valid zero/full.
        text_integrity.assert_clean_response(content, section)
    except ValueError as exc:
        result["state"] = "error"
        result["reason"] = safe_error_message(exc)
        result["issues"] = issues
        return None, result

    try:
        data = extract_json(content)
        # JSON � escapes hide the character from the raw string.
        text_integrity.assert_clean_data(data, section)
    except ValueError as exc:
        result["state"] = "error"
        result["reason"] = safe_error_message(exc)
        result["issues"] = issues
        return None, result
    except Exception as exc:
        result["state"] = "error"
        result["reason"] = f"模型输出无法解析为 JSON 对象：{safe_error_message(exc)}"
        result["issues"] = issues
        return None, result
    if not isinstance(data, dict):
        result["state"] = "error"
        result["reason"] = "模型输出必须是 JSON 对象"
        result["issues"] = issues
        return None, result

    if data.get(viability_key) is not True:
        if data.get(viability_key) is False and isinstance(data.get("reason"), str) \
                and data["reason"].strip():
            # Explicit, well-formed irrelevance: a legitimate zero.
            result["state"] = "zero"
            result["reason"] = data["reason"]
            result["issues"] = issues
            return None, result
        # Missing or invalid viability is a malformed response, never a
        # legitimate irrelevance claim.
        result["state"] = "error"
        result["reason"] = (
            f"模型输出缺少合法的 {viability_key} 判定（got {data.get(viability_key)!r}），"
            "无法区分真实无关与格式错误；拒绝生成")
        result["issues"] = issues
        return None, result

    return {
        "data": data, "verified": verified, "issues": issues, "known": known,
        "note_rels": {n["rel"] for n in verified}, "settings": settings,
    }, result


def default_provider() -> Callable[[dict[str, Any], str, dict[str, Any]], str]:
    return call_chat_completion
