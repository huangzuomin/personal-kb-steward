"""M3/T7 topic generator: question-led synthesis over verified source snapshots.

Integration seam (the final integrator owns eligibility and passing data):

    generate_topic(
        question: str,
        cfg: dict,
        notes: list[dict],
        *,
        known_paths: list[str] | None = None,
        analysis_mode: str = "llm",
        call_provider: Callable[[dict, str, dict], str] | None = None,
        now: str | None = None,
    ) -> dict

Input note dict (per note, all keys required):

    rel            str  SAFE vault-relative source path (no absolute path,
                        backslash, "..", control chars, wikilink metachars)
    title          str  human title of the source
    body           str  cleaned body used only for substance checks; the
                        provider context is built from the FULL raw snapshot
    metadata       dict free-form provenance metadata; never trusted for
                        dates/authors/independence
    source_text    str  FULL original UTF-8 decoded snapshot with BOM and CRLF
                        preserved, such that source_text.encode("utf-8")
                        reproduces the file's original bytes
    source_sha256  str  sha256 hex of those ORIGINAL RAW BYTES (not of cleaned
                        text, not core.claims.digest of normalized text)

`known_paths` is the optional explicit index of EXISTING full vault-relative
object paths; only those become real wikilinks — anything else the model
invents stays a pending plain path.

Return value (always a dict, never raises for input/protocol problems):

    state          "full" | "stub" | "zero" | "disabled" | "error"
    reason         str | None   (required for zero/disabled/error)
    candidate      dict | None  typed topic-page card item (schema-validated)
    page           dict | None  {"template", "rel_path_hint", "content"} with
                                card_state persisted IN the rendered frontmatter
    claims         list[dict]   core.claims claim records; identical to the
                                persisted card_state.claims
    analysis       dict         persisted analysis payload; identical to the
                                persisted card_state.analysis
    issues         list[str]    non-fatal problems, also rendered on the page

Key guarantees:
- Single type truth: core/schemas/topic-page.schema.json is loaded and
  registered via core.card_contracts.register_card_schema; there is no Python
  schema copy.
- Full raw snapshots go to the provider as-is. Oversized input (per source or
  whole payload) is rejected BEFORE the call; text is never truncated and then
  presented as fully read.
- Coverage ("full"/"partial") records READ coverage of the supplied input;
  source sufficiency (full vs stub) is a separate state. Refused sources keep
  the input incomplete: coverage cannot regain "full" by counting survivors.
- A full topic requires >= min_full_sources DISTINCT, related, usable sources
  actually cited by compiled claims — counted AFTER collapsing byte-identical
  copies and records sharing an explicit original-source identity
  (metadata.original_source_id) — plus non-empty model boundary/summary, at
  least one compiled claim, and a non-blank per-source map. Shared-origin
  notes are disclosed and cap confidence at medium but do not by themselves
  force a stub; distinct records about one subject are legitimate full-topic
  material (never counted as independent corroboration). Zero valid compiled
  judgments is an error, not a stub: stubs preserve genuinely supported
  content whose scope/source count is insufficient.
- A proposed disagreement needs >=2 DISTINCT valid compiled side references
  (each side traceable; same-source dialogue qualifies — no global relation
  gate); context_difference needs >=1. Tensions referencing rejected sources
  or uncompilable claims are dropped whole, never folded into the narrative.
  The program cannot adjudicate semantic opposition: real_conflict means
  "model-proposed, semantic review pending", never machine-verified.
- All freeform model text is sanitized: "[[...]]" is rendered as literal
  bracket text and recorded as an issue, so invented links cannot bypass
  _split_links. Paths are validated against absolute/traversal/backslash/
  control characters.
- Exactly ONE bounded provider call (injectable; default
  core.llm.call_chat_completion), no hidden retries; secret screening pre and
  post; Jinja preflight before the call; safe_error_message everywhere.
- Persisted card_state = {"version": 1, "type": "topic-page", "claims": [...],
  "analysis": {...}} is written into the rendered frontmatter and must match
  the returned claims/analysis exactly (the integrator can reload it via
  core.claims.read_claims / validate_claims).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from .card_contracts import register_card_schema, validate_card_item
from .claims import Claim, EvidenceError, compile_claims, render_claims
from .content_safety import assert_safe_content, safe_error_message
from .jinja_renderer import render_template
from .json_contract import extract_json
from .llm import call_chat_completion
from . import text_integrity

TOPIC_SCHEMA_VERSION = "topic-1"
TOPIC_GENERATOR_VERSION = "pks-topic-m3"
TOPIC_FULL_STATES = ("growing", "assembling")
TOPIC_REVIEW_STATES = ("manual_review", "insufficient")
TEMPLATE_NAME = "topic_page.j2"
CARD_STATE_VERSION = 1

_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "topic-page.schema.json"
# Single source of truth: the canonical JSON Schema file, loaded and registered
# through the shared local registry. No Python-side schema duplicate.
register_card_schema(json.loads(
    _SCHEMA_PATH.read_text(encoding="utf-8-sig").replace("\r\n", "\n")))

_CLASSIFICATION_LABELS = {
    "real_conflict": "有记录的对立分歧（模型提出，语义待人工复核）",
    "unverified_tension": "未裁决的张力（模型提出，语义待人工复核）",
    "context_difference": "语境/口径差异（模型提出，语义待人工复核）",
}

# Safe vault-relative path: relative, forward slashes only, no traversal,
# no empty/"."/".." segments, no control characters, no wikilink metachars.
_UNSAFE_PATH = re.compile(r"[\\]\x00-\x1f\[\]#|]")


class TopicGenerationError(RuntimeError):
    """A fail-closed generation problem surfaced to the caller, never retried."""


def is_safe_rel_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or value.endswith("/"):
        return False
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return False  # absolute (posix or windows drive)
    if any(c in value for c in "\\[]#|\x00\r\n") or ".." in value.split("/"):
        return False
    segments = value.split("/")
    if any(seg in ("", ".") for seg in segments):  # raw//x.md, raw/./x.md
        return False
    if any(ord(c) < 0x20 for c in value):
        return False
    return True


def topic_settings(cfg: dict[str, Any]) -> dict[str, int]:
    """Validate topic_generation constraints; called before any provider use."""
    raw = (cfg or {}).get("topic_generation", {})
    if not isinstance(raw, dict):
        raise TopicGenerationError("topic_generation 配置必须是对象")
    settings: dict[str, int] = {}
    for key, default in (
        ("min_full_sources", 3), ("max_source_chars", 20000), ("max_context_chars", 60000),
    ):
        value = raw.get(key, default)
        if type(value) is not int or value < 1:
            raise TopicGenerationError(f"topic_generation.{key} 必须是正整数：{value!r}")
        settings[key] = value
    return settings


# ---------------------------------------------------------------------------
# Input verification
# ---------------------------------------------------------------------------
def _verify_snapshot(note: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (normalized note, issues); None means the note is refused."""
    if not isinstance(note, dict):
        raise TopicGenerationError(f"notes[{index}] 必须是对象")
    for key in ("rel", "title", "body", "metadata", "source_text", "source_sha256"):
        if key not in note:
            raise TopicGenerationError(f"notes[{index}] 缺少必填字段：{key}")
    rel = note["rel"]
    if not is_safe_rel_path(rel):
        raise TopicGenerationError(
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
    # T10: refuse decoding-damaged sources before any provider call.
    damaged = text_integrity.damaged_reasons(note, rel)
    if damaged:
        return None, damaged
    body, title, metadata = note["body"], note["title"], note["metadata"]
    if not isinstance(body, str) or not isinstance(title, str) or not isinstance(metadata, dict):
        raise TopicGenerationError(f"notes[{index}] 的 title/body/metadata 类型非法")
    return {
        "rel": rel, "title": title, "body": body, "metadata": metadata,
        "source_text": source_text, "source_sha256": sha,
    }, []


def _source_document(note: dict[str, Any]) -> dict[str, str]:
    # Provider context AND claim quote coordinates both use the FULL raw
    # snapshot (core.claims strips the initial BOM and normalizes CRLF itself);
    # nothing is truncated behind the model's back. The trusted raw-byte hash
    # is passed through untouched as Evidence.source_sha256.
    return {"path": note["rel"], "title": note["title"], "content": note["source_text"],
            "sha256": note["source_sha256"]}


# ---------------------------------------------------------------------------
# Provider interaction (one bounded call, preflight before it)
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "你是个人知识库的专题综合器。只依据提供的来源作答：\n"
    "1. 判断来源能否支撑研究问题；无关或无实质内容时置 topic_viable=false 并给出 reason。\n"
    "2. source_map 必须覆盖每个提供来源，逐条给出 provenance 与 limitations；"
    "不得虚构日期、作者或独立性。\n"
    "3. 每条 judgment 的 evidence 必须给出来源 path 的逐字原文片段（quote）、relation"
    "（supports 或 contradicts）与必要 start_line；片段必须与来源原文完全一致。\n"
    "4. tension 分类（均为模型提案，语义由人工复核）：real_conflict（实质冲突）仅当两条"
    "判断针对同一对象、同一语境、同一测量口径给出不同主张；数字、时间窗口、分母不同，"
    "或案例适用条件/场景不同，一律归入 context_difference，不是事实冲突。解释性分歧"
    "（如双方对同一数据的解读不同）用 unverified_tension，除非证据可定则用 real_conflict。"
    "对立分歧的两侧必须是分歧双方各自明确主张/原话所支撑的判断，并在 claim_statements "
    "中分别引用；不得为无关判断编造 contradicts 关系；同一来源内记录的双方主张合法。\n"
    "5. gaps 必须指名缺失证据及受影响判断；actions 必须按优先级排序并连接到具体缺口，"
    "不得写通用清单。\n"
    "6. related 只能引用提供的 known_paths 中真实存在的路径；其余目标写成 pending_paths "
    "裸文本。所有自由文本中不得输出 [[维基链接]] 语法。\n"
    "输出严格 JSON 对象。不要输出任何密钥、token 或凭据内容。"
)


def _user_payload(question: str, documents: list[dict[str, str]], known_paths: list[str]) -> dict[str, Any]:
    return {
        "task": "question_led_topic_synthesis",
        "question": question,
        # Full original snapshots; oversized input is rejected before this point.
        "documents": documents,
        "known_paths": known_paths,
        "output_contract": {
            "topic_viable": "boolean",
            "reason": "string, required when topic_viable is false",
            "title": "string",
            "theme_boundary": "string, non-empty required",
            "summary": "string, non-empty required",
            "confidence": "low|medium|high",
            "source_map": [{"rel": "string from documents.path", "provenance": "string, non-empty",
                            "limitations": ["string"]}],
            "shared_provenance": ["string; note any sources that share origin or dependence"],
            "judgments": [{
                "statement": "string", "kind": "fact|inference", "confidence": "low|medium|high",
                "evidence": [{"source": "string from documents.path",
                              "quote": "exact verbatim fragment from that source",
                              "relation": "supports or contradicts",
                              "start_line": "int, required when the quote occurs more than once"}],
            }],
            "tensions": [{
                "statement": "string",
                "classification": "real_conflict|unverified_tension|context_difference",
                "classification_rule": "real_conflict only when both claims address the SAME "
                                       "referent/context/measurement scope; different numbers, "
                                       "time windows, denominators or case conditions are "
                                       "context_difference; interpretation disputes over the "
                                       "same data are unverified_tension unless decidable",
                "sides_rule": "for real_conflict/unverified_tension, claim_statements must "
                              "reference the claims backed by each side's own stated/quoted "
                              "position (same-source dialogue allowed); never attach a "
                              "contradicts relation to an unrelated claim",
                "sources": ["string from documents.path"],
                "claim_statements": ["exact statement strings of the cited judgments"],
                "note": "string",
            }],
            "evidence_gaps": [{"gap": "string", "affected": ["string"]}],
            "next_actions": [{"action": "string, non-generic",
                              "priority": "int, 1 = highest",
                              "addresses_gap": "gap string from evidence_gaps"}],
            "related": ["string, only from known_paths"],
            "pending_paths": ["string"],
        },
    }


def _parse_response(content: str) -> dict[str, Any]:
    data = extract_json(content)
    if not isinstance(data, dict):
        raise TopicGenerationError("模型输出必须是 JSON 对象")
    return data


# ---------------------------------------------------------------------------
# Freeform sanitization: no model text may carry link syntax past _split_links
# ---------------------------------------------------------------------------
def _sanitize_freeform(value: Any, issues: list[str], where: str) -> Any:
    """Render [[wikilink]] syntax in model freeform text inert (literal text)."""
    if isinstance(value, str):
        if "[[" in value or "]]" in value:
            issues.append(f"{where}: 自由文本包含链接语法，已按纯文本处理（不生成未验证链接）")
            return value.replace("[[", "［").replace("]]", "］")
        return value
    if isinstance(value, list):
        return [_sanitize_freeform(v, issues, where) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_freeform(v, issues, where) for k, v in value.items()}
    return value


def _safe_paths(raw: Any) -> list[str]:
    return [p for p in (raw if isinstance(raw, list) else [])
            if isinstance(p, str) and is_safe_rel_path(p)]


# ---------------------------------------------------------------------------
# Post-processing: claims, tensions, gaps, actions, links, source map
# ---------------------------------------------------------------------------
def _compile_model_claims(
    data: dict[str, Any], notes: list[dict[str, Any]], issues: list[str]
) -> tuple[list[Claim], list[dict[str, Any]], set[str]]:
    """Compile each model judgment through core.claims; bad evidence is dropped.

    Exact duplicate judgments (same statement+kind) are MERGED: their distinct
    validated evidence is combined into one claim so the emitted records always
    reload via core.claims. Returns compiled claims, normalized judgment
    entries, and the set of source paths actually cited by surviving claims.
    """
    claims: list[Claim] = []
    judgments: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], int] = {}  # (statement, kind) -> index in claims
    documents = [_source_document(n) for n in notes]
    raw_items = data.get("judgments")
    if not isinstance(raw_items, list):
        issues.append("模型未提供 judgments 数组；视作无已支持判断")
        return claims, judgments, set()
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            issues.append(f"judgments[{i}] 不是对象，已丢弃")
            continue
        try:
            compiled = compile_claims([item], documents)[0]
        except EvidenceError as exc:
            issues.append(f"judgments[{i}] 证据编译失败，已丢弃（不接受伪造证据或路径）：{exc}")
            continue
        key = (compiled.statement, compiled.kind)
        if key in by_key:
            # Merge complementary evidence; keep one claim record.
            idx = by_key[key]
            existing = claims[idx]
            merged = {e for e in existing.evidence} | set(compiled.evidence)
            if len(merged) != len(existing.evidence):
                claims[idx] = Claim(existing.claim_id, existing.statement,
                                    existing.kind, existing.confidence,
                                    tuple(sorted(merged, key=lambda e: (e.source, e.start))))
                issues.append(f"judgments[{i}] 与已有判断完全重复，证据已合并（claim {existing.claim_id}）")
            else:
                issues.append(f"judgments[{i}] 与已有判断完全重复且证据相同，已去重")
            continue
        by_key[key] = len(claims)
        claims.append(compiled)
        entry = {"statement": compiled.statement, "claim_ids": [compiled.claim_id]}
        if isinstance(item.get("note"), str) and item["note"]:
            entry["note"] = _sanitize_freeform(item["note"], issues, f"judgments[{i}].note")
        judgments.append(entry)
    usable = {e.source for c in claims for e in c.evidence}
    return claims, judgments, usable


def _tension_entries(tensions: Any, claims: list[Claim],
                     note_rels: set[str], issues: list[str]) -> list[dict[str, Any]]:
    """Normalize model tensions. The program NEVER adjudicates semantic
    opposition: a two-sided disagreement (real_conflict / unverified_tension)
    requires exactly >=2 DISTINCT valid compiled claim references (both sides
    traceable; a supports quote for each side, including same-source dialogue,
    is fine — no global relation gate). context_difference requires >=1 valid
    compiled claim reference. Any tension whose referenced claims or sources
    were rejected is DROPPED as unusable with an issue — never kept with the
    dead references silently removed, and never folded into the factual
    narrative. A real_conflict label means "model-proposed, semantic review
    pending"; the program cannot verify a contradiction.
    """
    result: list[dict[str, Any]] = []
    by_statement: dict[str, Claim] = {}
    for c in claims:
        by_statement.setdefault(c.statement, c)  # duplicates cannot multiply sides
    required_sides = {"real_conflict": 2, "unverified_tension": 2, "context_difference": 1}
    if not isinstance(tensions, list):
        return result
    for i, item in enumerate(tensions):
        if not isinstance(item, dict):
            issues.append(f"tensions[{i}] 不是对象，已丢弃")
            continue
        statement = item.get("statement")
        if not isinstance(statement, str) or not statement.strip() or len(statement) > 2000:
            issues.append(f"tensions[{i}] 缺少合法 statement，已丢弃")
            continue
        statement = _sanitize_freeform(statement, issues, f"tensions[{i}].statement")
        classification = item.get("classification")
        if classification not in _CLASSIFICATION_LABELS:
            issues.append(f"tensions[{i}] 分类非法，已整体丢弃")
            continue
        raw_sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        sources = [s for s in raw_sources if isinstance(s, str) and s in note_rels]
        rejected = [s for s in raw_sources if s not in sources]
        refs = [r for r in item.get("claim_statements", []) if isinstance(r, str) and r]
        unresolved = [r for r in refs if r not in by_statement]
        # A tension whose sources or claims were rejected is unusable as a whole.
        if rejected or unresolved:
            issues.append(
                f"tensions[{i}] 引用了被拒绝来源或未编译判断（来源 {rejected}，"
                f"判断 {len(unresolved)} 条），整体丢弃，不进入事实叙述")
            continue
        claim_ids: list[str] = []
        for ref in refs:
            cid = by_statement[ref].claim_id
            if cid not in claim_ids:
                claim_ids.append(cid)
        if len(claim_ids) < required_sides[classification]:
            issues.append(
                f"tensions[{i}]（{classification}）需要至少 {required_sides[classification]} 条"
                f"不同的有效编译判断支撑，实际 {len(claim_ids)} 条，已丢弃，仅保留在诊断信息中")
            continue
        entry: dict[str, Any] = {
            "statement": statement, "classification": classification,
            "sources": sources, "claim_ids": claim_ids, "note": "",
        }
        if isinstance(item.get("note"), str) and item["note"]:
            entry["note"] = _sanitize_freeform(item["note"], issues, f"tensions[{i}].note")
        result.append(entry)
    return result


def _normalize_gaps(raw: Any, issues: list[str]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        if raw:
            issues.append("evidence_gaps 不是数组，已丢弃")
        return gaps
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not isinstance(item.get("gap"), str) or not item["gap"].strip():
            issues.append(f"evidence_gaps[{i}] 缺少合法 gap 文本，已丢弃")
            continue
        entry: dict[str, Any] = {"gap": _sanitize_freeform(item["gap"], issues, f"evidence_gaps[{i}]"),
                                 "affected": []}
        affected = item.get("affected")
        if isinstance(affected, list) and all(isinstance(a, str) for a in affected):
            entry["affected"] = _sanitize_freeform(affected, issues, f"evidence_gaps[{i}].affected")
        gaps.append(entry)
    return gaps


def _normalize_actions(raw: Any, gaps: list[dict[str, Any]],
                       issues: list[str]) -> list[dict[str, Any]]:
    """Actions keep explicit priority order and must reference a real gap;
    unknown/missing gap references are recorded, never silently nulled."""
    actions: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        if raw:
            issues.append("next_actions 不是数组，已丢弃")
        return actions
    known_gap_texts = {g["gap"] for g in gaps}
    pending: list[tuple[int, dict[str, Any]]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not isinstance(item.get("action"), str) or not item["action"].strip():
            issues.append(f"next_actions[{i}] 缺少合法 action 文本，已丢弃")
            continue
        text = _sanitize_freeform(item["action"], issues, f"next_actions[{i}].action").strip()
        if len(text) < 4:
            issues.append(f"next_actions[{i}] 过短或过于空泛，已丢弃：{text!r}")
            continue
        entry: dict[str, Any] = {"action": text, "addresses_gap": None}
        ref = item.get("addresses_gap")
        if isinstance(ref, str) and ref in known_gap_texts:
            entry["addresses_gap"] = ref
        else:
            issues.append(f"next_actions[{i}].addresses_gap 未对应已记录缺口（{ref!r}），置空并记为问题")
        priority = item.get("priority")
        priority = priority if type(priority) is int and priority >= 1 else i + 1
        if priority != item.get("priority"):
            issues.append(f"next_actions[{i}].priority 非法，按出现顺序补为 {priority}")
        pending.append((priority, entry))
    pending.sort(key=lambda pair: pair[0])
    return [entry for _, entry in pending]


def _normalize_source_map(raw: Any, notes: list[dict[str, Any]],
                          issues: list[str]) -> tuple[list[dict[str, Any]], bool]:
    """Keep only entries referencing provided sources; attach trusted hashes.

    Returns (map, complete) where complete=False means the model skipped or
    blanked entries — such a blank-filled map cannot support a full topic.
    """
    result: list[dict[str, Any]] = []
    known = {n["rel"]: n["source_sha256"] for n in notes}
    complete = True
    if not isinstance(raw, list):
        issues.append("模型未提供 source_map 数组")
        return result, False
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            issues.append(f"source_map[{i}] 不是对象，已丢弃")
            continue
        rel = item.get("rel")
        if not is_safe_rel_path(rel) or rel not in known:
            issues.append(f"source_map[{i}].rel 不在提供来源中或路径非法，已丢弃")
            continue
        if rel in seen:
            continue
        seen.add(rel)
        provenance = item.get("provenance")
        if not isinstance(provenance, str) or not provenance.strip():
            issues.append(f"source_map[{i}].provenance 为空，已补空记录（影响完整性）")
            provenance = ""
            complete = False
        limitations = _sanitize_freeform(
            item.get("limitations") if isinstance(item.get("limitations"), list)
            and all(isinstance(x, str) for x in item["limitations"]) else [],
            issues, f"source_map[{i}].limitations")
        result.append({"rel": rel, "source_sha256": known[rel],
                       "provenance": _sanitize_freeform(provenance, issues, f"source_map[{i}].provenance"),
                       "limitations": limitations})
    for note in notes:
        if note["rel"] not in seen:
            result.append({"rel": note["rel"], "source_sha256": note["source_sha256"],
                           "provenance": "", "limitations": []})
            issues.append(f"source_map 缺少来源 {note['rel']} 的条目，已补空记录（影响完整性）")
            complete = False
    return result, complete


def _split_links(raw_related: Any, raw_pending: Any, known_paths: list[str],
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


def _shared_provenance(notes: list[dict[str, Any]], model_flags: Any,
                       issues: list[str]) -> tuple[list[str], bool]:
    """Shared-origin disclosure. A model's shared_provenance note alone does
    NOT force a stub: it is disclosed and confidence is capped. Only
    byte-identical duplicates (same raw hash) actually collapse the distinct
    source count (returned as degraded=True)."""
    flags: list[str] = _sanitize_freeform(
        [f for f in (model_flags if isinstance(model_flags, list) else [])
         if isinstance(f, str) and f], issues, "shared_provenance")
    if flags:
        issues.append("存在共享来源/背景说明，已披露；相关来源不计为相互独立的佐证")
    by_hash: dict[str, list[str]] = {}
    for note in notes:
        by_hash.setdefault(note["source_sha256"], []).append(note["rel"])
    degraded = False
    for sha, rels in by_hash.items():
        if len(rels) > 1:
            flags.append(
                f"以下来源的原始字节完全一致，按同一来源计：{('、'.join(sorted(rels)))}（sha256:{sha[:12]}…）")
            degraded = True
            issues.append("检测到字节级重复来源，去重后不重复计入来源数")
    return flags, degraded


def _collapse_key(note: dict[str, Any]) -> str:
    """Collapse identity for sufficiency counting: explicit original-source
    identity (metadata.original_source_id) when given, else the raw-byte hash.
    Byte-identical copies and records of the same original source collapse to
    one source; distinct records ABOUT one subject do not."""
    oid = note["metadata"].get("original_source_id") if isinstance(note["metadata"], dict) else None
    if isinstance(oid, str) and oid.strip():
        return f"id:{oid.strip()}"
    return f"sha:{note['source_sha256']}"


# ---------------------------------------------------------------------------
# Rendering and persistence
# ---------------------------------------------------------------------------
def _page_context(question: str, candidate: dict[str, Any], claims: list[Claim],
                  issues: list[str], now: str | None) -> dict[str, Any]:
    import datetime as dt

    tensions = [
        {**t, "classification_label": _CLASSIFICATION_LABELS[t["classification"]]}
        for t in candidate["tensions"]
    ]
    # Precompute item lines in Python: an inline "{% if %}...{% endif %}" at a
    # template line end loses its newline to trim_blocks, which concatenated
    # consecutive list items in earlier renders. The template then only prints
    # one plain expression per line.
    gap_lines = [
        gap["gap"] + (f"（受影响判断：{'；'.join(gap['affected'])}）" if gap["affected"] else "")
        for gap in candidate["evidence_gaps"]
    ]
    action_lines = [
        f"{i}. {a['action']}"
        + (f"（对应缺口：{a['addresses_gap']}）" if a["addresses_gap"] else "")
        for i, a in enumerate(candidate["next_actions"], 1)
    ]
    return {
        "title": candidate["title"],
        "type": candidate["type"],
        "status": candidate["status"],
        "stage": candidate["stage"],
        "sources": candidate["sources"],
        "related": candidate["related"],
        "tags": ["topic-page", "question-led"],
        "confidence": candidate["confidence"],
        "review_required": candidate["review_required"],
        "origin": {"research_question": question, "source_paths": candidate["sources"]},
        # Program-owned metadata (base_frontmatter.j2 conditional block)
        "schema_version": candidate["schema_version"],
        "generator_version": candidate["generator_version"],
        "analysis_mode": candidate["analysis_mode"],
        "coverage": candidate["coverage"],
        "source_hashes": candidate["source_hashes"],
        "quality_flags": candidate["quality_flags"],
        # Body sections
        "research_question": question,
        "limited_stub": candidate["status"] == "manual_review",
        "limited_reason": candidate["manual_review"][0] if candidate["manual_review"] else "",
        "theme_boundary": candidate["theme_boundary"],
        "summary": candidate["summary"],
        "source_map": candidate["source_map"],
        "shared_provenance": candidate["shared_provenance"],
        "claims_section": render_claims(claims) if claims else "（无已编译判断）",
        "tensions": tensions,
        "evidence_gaps": candidate["evidence_gaps"],
        "next_actions": candidate["next_actions"],
        "gap_lines": gap_lines,
        "action_lines": action_lines,
        "pending_links": candidate["pending_links"],
        "generation_issues": issues,
        "today": now or dt.date.today().isoformat(),
    }


def _preflight_render(question: str) -> str:
    """Render the template with a minimal skeleton BEFORE the provider call."""
    skeleton = {
        "title": "preflight", "type": "topic-page", "status": "manual_review",
        "stage": "insufficient", "sources": ["preflight"], "related": [], "tags": [],
        "confidence": "low", "review_required": True,
        "origin": {}, "schema_version": TOPIC_SCHEMA_VERSION,
        "generator_version": TOPIC_GENERATOR_VERSION, "analysis_mode": "unknown",
        "coverage": "unknown", "source_hashes": {}, "quality_flags": [],
        "research_question": question, "limited_stub": False, "limited_reason": "",
        "theme_boundary": "", "summary": "", "source_map": [], "shared_provenance": [],
        "claims_section": "", "tensions": [], "evidence_gaps": [],
        "next_actions": [], "pending_links": [], "generation_issues": [],
        "gap_lines": [], "action_lines": [],
    }
    return render_template(TEMPLATE_NAME, skeleton)


def _patch_card_state(rendered: str, card_state: dict[str, Any]) -> str:
    """Insert card_state as a frontmatter field after template render.

    Mirrors core.reconcile._patch_header semantics narrowly: only adds the one
    owned field, preserves everything else, refuses without full frontmatter.
    """
    lines = rendered.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise TopicGenerationError("渲染结果缺少 frontmatter，无法持久化 card_state")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise TopicGenerationError("渲染结果 frontmatter 未闭合，无法持久化 card_state")
    encoded = json.dumps(card_state, ensure_ascii=False)
    block = "".join(lines[:end]) + f"card_state: {encoded}\n" + "".join(lines[end:])
    return block


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate_topic(
    question: str,
    cfg: dict[str, Any],
    notes: list[dict[str, Any]],
    *,
    known_paths: list[str] | None = None,
    analysis_mode: str = "llm",
    call_provider: Callable[[dict[str, Any], str, dict[str, Any]], str] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Run one bounded question-led topic synthesis. See module docstring for
    the exact input/output contract."""
    result: dict[str, Any] = {
        "state": "error", "reason": None, "candidate": None, "page": None,
        "claims": [], "analysis": {}, "issues": [],
    }
    provider = call_provider or call_chat_completion

    if not isinstance(question, str) or not question.strip():
        result["reason"] = "缺少明确的研究问题"
        return result
    if analysis_mode != "llm":
        # Non-LLM mode is honest: no model synthesis happens, so no analysis,
        # no judgments and no page is produced — never a fabricated topic.
        result["state"] = "disabled"
        result["reason"] = (
            f"analysis_mode={analysis_mode}：主题生成依赖模型综合，非 LLM 模式拒绝产出结论"
        )
        return result

    try:
        settings = topic_settings(cfg)  # constraint validation BEFORE anything else
    except TopicGenerationError as exc:
        result["reason"] = str(exc)
        return result
    if not isinstance(notes, list) or not notes:
        result["reason"] = "未提供任何来源"
        return result

    verified: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: dict[str, str] = {}  # rel -> sha256 of the first occurrence
    for i, note in enumerate(notes):
        try:
            ok, note_issues = _verify_snapshot(note, i)
        except TopicGenerationError as exc:
            result["reason"] = str(exc)  # structurally invalid input: bounded error
            result["issues"] = issues
            return result
        issues.extend(note_issues)
        if ok is not None:
            if ok["rel"] in seen:
                if seen[ok["rel"]] != ok["source_sha256"]:
                    result["reason"] = (
                        f"同一路径 {ok['rel']} 提供了两个不同的原始快照 hash，"
                        "无法确定可信版本；拒绝生成")
                    result["issues"] = issues
                    return result
                issues.append(f"来源 {ok['rel']} 重复提供且快照一致，已去重")
                continue
            seen[ok["rel"]] = ok["source_sha256"]
            verified.append(ok)

    # Budget validation BEFORE any call: whole payload size including question,
    # known_paths and FULL snapshots. Never truncate; refuse instead.
    for note in verified:
        if len(note["source_text"]) > settings["max_source_chars"]:
            result["reason"] = (
                f"来源 {note['rel']} 原始快照 {len(note['source_text'])} 字符超过 "
                f"topic_generation.max_source_chars={settings['max_source_chars']}，"
                "拒绝截断后调用模型")
            result["issues"] = issues
            return result
    known = [p for p in (known_paths or []) if isinstance(p, str) and is_safe_rel_path(p)]
    payload = _user_payload(question, [_source_document(n) for n in verified], known)
    payload_size = len(json.dumps(payload, ensure_ascii=False))
    if payload_size > settings["max_context_chars"]:
        result["reason"] = (
            f"完整载荷（含全部原始快照、问题与 known_paths）{payload_size} 字符超过 "
            f"topic_generation.max_context_chars={settings['max_context_chars']}，"
            "拒绝截断后调用模型")
        result["issues"] = issues
        return result
    if not verified:
        result["reason"] = "所有来源的原始快照缺失或校验失败，已全部拒绝；不生成任何专题内容"
        result["issues"] = issues
        return result
    if not any(n["body"].strip() for n in verified):
        result["state"] = "zero"
        result["reason"] = "所有可用来源均为空或无实质内容，不强行生成专题"
        result["issues"] = issues
        return result

    # Preflight the template so a render error cannot waste the single call.
    try:
        _preflight_render(question)
    except Exception as exc:
        result["reason"] = f"渲染预检失败，未发起模型调用：{safe_error_message(exc)}"
        result["issues"] = issues
        return result

    try:
        assert_safe_content(payload)  # pre-response secret screening
    except Exception as exc:
        result["reason"] = f"敏感内容检查阻断输入，未发起模型调用：{safe_error_message(exc)}"
        result["issues"] = issues
        return result

    try:
        content = provider(cfg, _SYSTEM_PROMPT, payload)
    except Exception as exc:
        result["reason"] = f"模型调用失败（单次有界调用，无重试）：{safe_error_message(exc)}"
        result["issues"] = issues
        return result
    try:
        assert_safe_content(content)  # post-response secret screening
    except Exception as exc:
        result["reason"] = f"模型返回内容被敏感内容检查阻断：{safe_error_message(exc)}"
        result["issues"] = issues
        return result
    try:
        # T10: encoding-damaged response is an error, not a valid zero/full.
        text_integrity.assert_clean_response(content, "topic_generation")
    except ValueError as exc:
        result["reason"] = safe_error_message(exc)
        result["issues"] = issues
        return result

    try:
        data = _parse_response(content)
        # JSON � escapes hide the character from the raw string.
        text_integrity.assert_clean_data(data, "topic_generation")
    except ValueError as exc:
        result["reason"] = safe_error_message(exc)
        result["issues"] = issues
        return result
    except Exception as exc:
        result["reason"] = f"模型输出无法解析为 JSON 对象：{safe_error_message(exc)}"
        result["issues"] = issues
        return result

    if data.get("topic_viable") is not True:
        if data.get("topic_viable") is False and isinstance(data.get("reason"), str) \
                and data["reason"].strip():
            # Explicit, well-formed irrelevance: a legitimate zero.
            result["state"] = "zero"
            result["reason"] = data["reason"]
            result["issues"] = issues
            return result
        # Missing or invalid topic_viable is a malformed response, never a
        # legitimate irrelevance claim.
        result["reason"] = (
            f"模型输出缺少合法的 topic_viable 判定（got {data.get('topic_viable')!r}），"
            "无法区分真实无关与格式错误；拒绝生成")
        result["issues"] = issues
        return result

    note_rels = {n["rel"] for n in verified}
    claims, judgments, usable = _compile_model_claims(data, verified, issues)
    source_map, map_complete = _normalize_source_map(data.get("source_map"), verified, issues)
    shared_flags, shared_origin = _shared_provenance(verified, data.get("shared_provenance"), issues)
    tensions = _tension_entries(data.get("tensions"), claims, note_rels, issues)
    gaps = _normalize_gaps(data.get("evidence_gaps"), issues)
    actions = _normalize_actions(data.get("next_actions"), gaps, issues)
    related, pending = _split_links(data.get("related"), data.get("pending_paths"),
                                    known, note_rels, issues)

    theme_boundary = _sanitize_freeform(
        data.get("theme_boundary") if isinstance(data.get("theme_boundary"), str) else "",
        issues, "theme_boundary")
    summary = _sanitize_freeform(
        data.get("summary") if isinstance(data.get("summary"), str) else "",
        issues, "summary")

    # --- Sufficiency (state) vs read coverage are decided independently. ---
    # Read coverage: full only when EVERY supplied note was verified AND has
    # substance; refused/empty input keeps coverage partial with a diagnostic.
    all_read = len(verified) == len(notes) and all(n["body"].strip() for n in verified)
    # Usable, distinct, related sources: only those actually cited by compiled
    # claims count toward min_full_sources. Byte-identical copies and records
    # sharing an explicit original-source identity collapse to ONE source;
    # distinct records about one subject do NOT collapse.
    usable_sources = usable & note_rels
    collapse_keys = {_collapse_key(n) for n in verified if n["rel"] in usable_sources}
    sufficiency_gaps: list[str] = []
    if not claims:
        # Zero valid compiled judgments: error, not a stub preserving an
        # unsupported freeform summary (handled after claim compilation below).
        result["reason"] = ("没有任何判断通过证据编译（无有效支撑），拒绝产出实质专题页；"
                            "stub 只保留有真实支撑但范围不足的内容")
        result["issues"] = issues
        return result
    if len(collapse_keys) < settings["min_full_sources"]:
        sufficiency_gaps.append(
            f"被已编译判断实际引用的去重后可用来源数 {len(collapse_keys)} 少于 "
            f"min_full_sources={settings['min_full_sources']}")
    if not map_complete:
        sufficiency_gaps.append("来源地图存在空白条目，不满足完整专题要求")
    if not theme_boundary.strip() or not summary.strip():
        sufficiency_gaps.append("模型未给出非空的主题边界或小结")
    if not gaps or not actions:
        sufficiency_gaps.append("缺少证据缺口或下一步行动记录")
    if any(not a["addresses_gap"] for a in actions):
        sufficiency_gaps.append("存在未连接到具体缺口的行动")
    is_full = not sufficiency_gaps
    coverage = "full" if all_read else "partial"
    review_notes: list[str] = []
    if not all_read:
        review_notes.append("输入存在被拒绝或无实质内容的来源，读取覆盖不完整，专题范围受限")
        issues.append("范围受限：部分输入未通过校验或无实质内容，coverage=partial")
    if is_full:
        status, stage = TOPIC_FULL_STATES
        limited_reason = ""
    else:
        status, stage = TOPIC_REVIEW_STATES
        limited_reason = "；".join(sufficiency_gaps)
        issues.append(f"受限主题（不构成完整专题基线）：{limited_reason}")

    confidence = data.get("confidence") if data.get("confidence") in ("high", "medium", "low") \
        else "low"
    if confidence == "high" and shared_flags:
        confidence = "medium"  # disclosed shared origin caps confidence
        issues.append("存在共享来源披露，置信度上限降为 medium")

    quality_flags = ["topic_generation_issues"] if issues else []

    candidate: dict[str, Any] = {
        "title": data.get("title") if isinstance(data.get("title"), str) and data["title"] else question[:80],
        "type": "topic-page",
        "status": status,
        "stage": stage,
        "sources": sorted(note_rels),
        "summary": summary,
        "confidence": confidence,
        "review_required": True,  # program-owned: candidates always need review
        "schema_version": TOPIC_SCHEMA_VERSION,
        "generator_version": TOPIC_GENERATOR_VERSION,
        "analysis_mode": "llm",
        "source_hashes": {n["rel"]: n["source_sha256"] for n in verified},
        "coverage": coverage,
        "related": related,
        "pending_links": pending,
        "manual_review": review_notes + ([limited_reason] if limited_reason else []),
        "quality_flags": quality_flags,
        "research_question": question,
        "theme_boundary": theme_boundary,
        "source_map": source_map,
        "shared_provenance": shared_flags,
        "supported_judgments": judgments,
        "tensions": tensions,
        "evidence_gaps": gaps,
        "next_actions": actions,
        "claims": [c.to_dict() for c in claims],
    }
    schema_issues = validate_card_item(candidate, "topic-page")
    if schema_issues:
        result["reason"] = "候选专题未通过 topic-page 契约校验：" + "；".join(schema_issues[:5])
        result["issues"] = issues
        return result

    analysis = {
        "research_question": question,
        "source_map": source_map,
        "shared_provenance": shared_flags,
        "supported_judgments": judgments,
        "tensions": tensions,
        "evidence_gaps": gaps,
        "next_actions": actions,
        "usable_sources": sorted(usable_sources),
        "outcome": "full" if is_full else "stub",
        "limited_reason": limited_reason,
        "coverage": coverage,
        "analysis_mode": "llm",
        "schema_version": TOPIC_SCHEMA_VERSION,
        "generator_version": TOPIC_GENERATOR_VERSION,
        "source_hashes": candidate["source_hashes"],
        "issues": issues,
    }
    card_state = {
        "version": CARD_STATE_VERSION,
        "type": "topic-page",
        "claims": candidate["claims"],
        "analysis": analysis,
    }

    try:
        content_md = _patch_card_state(
            render_template(TEMPLATE_NAME,
                            _page_context(question, candidate, claims, issues, now)),
            card_state)
    except Exception as exc:
        result["reason"] = f"页面渲染或持久化失败：{safe_error_message(exc)}"
        result["issues"] = issues
        return result

    result.update({
        "state": "full" if is_full else "stub",
        "reason": limited_reason or None,
        "candidate": candidate,
        "page": {
            "template": TEMPLATE_NAME,
            # Path/identity assignment stays with the plan boundary; this is a
            # hint only, no object_id is minted here.
            "rel_path_hint": "wiki/topics/",
            "content": content_md,
        },
        "claims": candidate["claims"],
        "analysis": analysis,
        "issues": issues,
    })
    return result
