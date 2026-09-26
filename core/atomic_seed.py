"""Atomic seed generation: one card expresses one independently expressible thought.

Thoughts are built from attributable information units (verbatim quotes with a
verified source snapshot and a locator), never from cluster reasoning. The
deterministic path is a LIMITED PREVIEW: without a model it must never claim
atomic success. Source provenance is verified EXACTLY: sha256 of the supplied
original text bytes (BOM/CRLF preserved by the source handoff) must match the
supplied hash — no normalized or BOM-padded variant is accepted. Pre-extracted
units are accepted only together with verified snapshots; every quote is
located in the snapshot text, so arbitrary quotes cannot bypass the source
check. Evidence is compiled in claims-record shape (core.claims fields, exact
coordinates) so persisted state roundtrips against the original snapshot.
Malformed model responses are errors, never a valid zero output.
"""
from __future__ import annotations

import json
import re

from .claims import Evidence, claim_id, digest, normalized_text
from .content_safety import SensitiveContentError, assert_safe_content, sensitive_reason
from .json_contract import extract_json
from .signal_extraction import signal_excerpts
from .source_analysis import speaker_map
from . import text_integrity

MAX_UNITS = 64               # bounded batch; exceeding this means PARTIAL coverage
MAX_TOTAL_QUOTE_CHARS = 24000  # explicit total context budget
MAX_UNITS_PER_NOTE = 64      # full-input extraction budget per note (not a prefix cut)
_QUESTION = re.compile(r"[?？]\s*$")
_LABEL = re.compile(r"^(?:[-*+]\s*)?(?:\*\*)?([^：:*#`\n]{1,16})(?:\*\*)?[：:]\s*(.*)$", re.S)
_EVIDENCE_FIELDS = set(Evidence.__dataclass_fields__)


def safe_error_message(exc: BaseException) -> str:
    detail = str(exc)
    if sensitive_reason(detail) or len(detail) > 300:
        return type(exc).__name__ + "（错误细节已省略）"
    return f"{type(exc).__name__}: {detail}"


def literal(text: str) -> str:
    """Model/carrier free text must never grow fresh wikilinks in rendered prose."""
    return str(text).replace("[[", "［［").replace("]]", "］］")


def unit_identity(unit: dict) -> str:
    """Exact source-information identity: kind + source + original-byte hash + quote digest."""
    return "unit:" + digest("\0".join((
        str(unit.get("kind", "assertion")), str(unit.get("source", "")),
        str(unit.get("source_sha256", "")),
        digest(normalized_text(str(unit.get("quote", "")))))))


def thought_identity(statement: str, kind: str, identities: list[str]) -> str:
    """Thought identity = exact claim wording AND its stable evidence identities.

    Hashes the unit identities (source/hash/quote), never transient array
    indices: reordering must not change identity, a different source at the
    same index must not collide, and added evidence changes identity so an
    unchanged confirmed thought with new evidence is a reviewed update.
    """
    return "thought:" + digest("\0".join((kind, statement, *sorted(identities))))


def _verify_snapshot(source_text: str, source_sha256: str) -> bool:
    """True only when sha256 EXACTLY matches the supplied original bytes.
    The source handoff preserves BOM/CRLF; no normalized variant is accepted."""
    if not (isinstance(source_text, str) and isinstance(source_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", source_sha256)):
        return False
    return digest(source_text) == source_sha256


def _speaker_map(text: str) -> dict[int, str | None]:
    """Nearest explicit speaker label active at each 1-based line: a label
    holds across subsequent sentences on the same line and continuation lines."""
    return speaker_map(text)


def information_units(note: dict) -> list[dict]:
    """Bounded full-input extraction from one note dict.

    Speaker/role comes ONLY from explicit in-text labels of the source (or
    stays unknown) — never from note-level metadata, which cannot attribute
    alternating dialogue. A note whose supplied hash does not EXACTLY match
    its source_text is an INVALID snapshot; the caller must block.
    """
    text = note.get("source_text") if isinstance(note.get("source_text"), str) and note.get("source_text") \
        else str(note.get("body", ""))
    verified = _verify_snapshot(note.get("source_text"), note.get("source_sha256") or "")
    invalid_snapshot = (isinstance(note.get("source_text"), str) and bool(note.get("source_text"))
                        and bool(note.get("source_sha256")) and not verified)
    speakers = _speaker_map(text) if verified else {}
    units = []
    for excerpt in signal_excerpts(text, limit=MAX_UNITS_PER_NOTE):
        kind = "question" if _QUESTION.search(excerpt.text) else "assertion"
        units.append({
            "source": str(note.get("rel", "")), "quote": excerpt.text,
            "body_line": excerpt.body_line, "kind": kind,
            "speaker": speakers.get(excerpt.body_line),
            "source_sha256": note.get("source_sha256") if verified else "",
            "verified": verified, "invalid_snapshot": invalid_snapshot,
        })
    if verified:
        for unit in units:
            coords = _locate_evidence(text, unit["quote"], unit["body_line"])
            if coords:
                unit.update(coords)
    return units


def _locate_evidence(text: str, quote: str, line_hint: int | None) -> dict | None:
    """Locator contract aligned with core.claims: with a start_line hint ONLY
    the hinted occurrence qualifies (a unique quote with a WRONG hint is
    rejected, not silently relocated); without a hint the quote must be unique.
    A later repeated occurrence with its correct hint resolves."""
    doc = normalized_text(text)
    quote = normalized_text(quote)
    positions, pos = [], doc.find(quote)
    while pos >= 0:
        positions.append(pos)
        pos = doc.find(quote, pos + 1)
    if not positions:
        return None
    start = None
    if line_hint is not None:
        hinted = [p for p in positions if doc.count("\n", 0, p) + 1 == line_hint]
        if len(hinted) == 1:
            start = hinted[0]
    elif len(positions) == 1:
        start = positions[0]
    if start is None:
        return None
    end = start + len(quote)
    return {"start": start, "end": end,
            "start_line": doc.count("\n", 0, start) + 1, "end_line": doc.count("\n", 0, end - 1) + 1}


def _compile_evidence_row(unit: dict) -> dict:
    """Evidence row in core.claims shape (exact fields + coordinates + hashes);
    assertions carry a real compiled claim_id. Quote bytes stay verbatim for
    verification."""
    row = {"source": unit["source"], "quote": unit["quote"], "kind": unit["kind"],
           "speaker": unit.get("speaker"), "verified": bool(unit.get("verified")),
           "relation": "supports",
           "source_sha256": unit.get("source_sha256", ""),
           "quote_sha256": digest(normalized_text(unit["quote"]))}
    if unit.get("verified") and unit.get("start") is not None:
        row.update({"start": unit["start"], "end": unit["end"],
                    "start_line": unit["start_line"], "end_line": unit["end_line"]})
    else:
        row.update({"start": None, "end": None,
                    "start_line": unit.get("body_line"), "end_line": unit.get("body_line")})
    if unit["kind"] == "assertion":
        # core.claims identity: exact wording + kind; fact ≠ independently verified.
        row["claim_id"] = claim_id(normalized_text(unit["quote"]), "fact")
    return row


def verify_supplied_units(units: list[dict], snapshots: dict | None) -> tuple[list[dict], list[str]]:
    """Check every supplied unit against a verified snapshot: exact hash match,
    quote located, speaker re-derived from the original context (a caller-forged
    speaker is not retained merely because the quote matches). Units that fail
    are rejected, never silently included."""
    accepted, issues = [], []
    verified_snaps: dict[str, dict] = {}
    for source, snap in (snapshots or {}).items():
        if isinstance(snap, dict) and _verify_snapshot(snap.get("source_text"), snap.get("source_sha256") or ""):
            verified_snaps[source] = snap
    for i, unit in enumerate(units):
        source = unit.get("source") if isinstance(unit.get("source"), str) else None
        snap = verified_snaps.get(source or "")
        if snap is None:
            issues.append(f"信息单元 {i} 缺少已验证的原始字节快照，拒绝纳入：{source!r}")
            continue
        quote = unit.get("quote")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 2000:
            issues.append(f"信息单元 {i} 的原文片段缺失或超长，拒绝纳入。")
            continue
        coords = _locate_evidence(snap["source_text"], quote, unit.get("body_line"))
        if coords is None:
            issues.append(f"信息单元 {i} 的原文片段无法在来源快照中唯一定位，拒绝纳入。")
            continue
        row = dict(unit)
        row["source_sha256"] = snap["source_sha256"]
        row["verified"] = True
        row.update(coords)
        speakers = _speaker_map(snap["source_text"])
        row["speaker"] = speakers.get(coords["start_line"])
        row["kind"] = "question" if _QUESTION.search(quote) else str(unit.get("kind") or "assertion")
        accepted.append(row)
    return accepted, issues


# ── Model composition ────────────────────────────────────────────────────────

ATOMIC_SYSTEM_PROMPT = """\
你是一个个人知识库的原子 seed 编辑。给定一组带出处原文片段（信息单元），
请把其中的念头提炼成原子 seed 候选：一张卡只表达一个可独立表达的念头。

输出规则：
- 必须返回严格合法的纯 JSON，顶层字段为 "thoughts"，值为数组（0-8 个）。禁止 Markdown 代码围栏、注释以及对象或数组末尾的逗号；返回前检查 JSON 语法。
- 每个 thought 必须包含：
  - statement（str，≤200 字，单行，不得截断或改写证据）：念头本身的一句话表述。
  - kind（str）："question"（未决问题）或 "assertion"（陈述/推断）。单元是问题的必须保持 question，
    不得写成事实；推断也只能是 assertion 并保留不确定性，不得宣称已核实。
  - unit_ids（array<int>）：支持该念头的输入单元编号；只能引用给出的编号，引用不存在的编号将整条拒绝。
  - growth_directions（array<object>，1-3 项）：每项含 action（具体下一步）和 basis（≥4 字的实质依据，
    说明它回应哪个未知点或哪条证据）。不要与其他念头共用模板方向，不要用同义改写凑数。
  - negative_scope（array<string>，1-3 项）：这张卡明确暂不扩展的方向、边界或失效条件。
- 一个单元可以支撑多个念头；一个念头也可以组合多个单元。来源中已标注的说话人必须保留归属，
  不得把一方的话写成另一方的观点，不得虚构用户第一人称偏好。
- 输入若声明“仅含部分单元”，说明后面还有未纳入内容，不要据此宣称覆盖完整。
- 内容无实质念头时返回 {"thoughts": []}。
"""


def _single_line_text(value, limit: int) -> str | None:
    """Validate (not coerce): nonempty, single-line, within limit; None otherwise."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit or any(c in text for c in "\r\n"):
        return None
    return text


# Clause/sentence boundaries. Selection is by POSITION, not by strength: the
# latest boundary inside the budget is used, because it keeps the most of the
# point while still reading as a finished phrase. (Ordering by strength instead
# was tried and regresssed: it cut at an early comma and dropped the subject.)
_TITLE_BOUNDARIES = "。！？!?；;，,、：:"
_TITLE_TRAILING = "，,、；;：:。"


def _short_title(text: str, limit: int = 40) -> str:
    """Shorten to a COMPLETE short phrase instead of a blind character slice.

    Blind slicing (``text[:40]``) produced half-sentence and even half-word titles
    such as ``…被淘汰，Com`` — a title is the one field a human reads to decide
    whether to open a card, so a truncated one is worse than a short one.

    Strategy: cut at the **latest** usable clause boundary inside the budget, so
    the title keeps as much of the point as still reads as finished; strip the
    dangling punctuation; never split a Latin word; append an ellipsis only when
    a hard cut was unavoidable, so a shortened title is visibly shortened.
    """
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    window = clean[:limit]
    floor = max(4, limit // 3)
    cut = max((window.rfind(ch) for ch in _TITLE_BOUNDARIES), default=-1)
    if cut >= floor:
        candidate = window[:cut].strip().rstrip(_TITLE_TRAILING)
        if candidate:
            return candidate
    # No usable boundary: back off to a word boundary rather than split a word.
    # Reserve one character for the ellipsis so the result still fits the limit.
    hard = clean[: max(1, limit - 1)]
    if hard[-1].isalnum() and clean[len(hard)].isalnum():
        space = hard.rfind(" ")
        if space >= floor:
            return hard[:space].strip().rstrip(_TITLE_TRAILING) + "…"
    return hard.strip().rstrip(_TITLE_TRAILING) + "…"


def _parse_model_thoughts(data, units: list[dict], issues: list[str]) -> tuple[list[dict], int]:
    """Strict parse. Returns (accepted, dropped_count); every malformed candidate
    is dropped with an issue — dropping is reported, never a silent zero."""
    thoughts = data.get("thoughts") if isinstance(data, dict) else None
    if not isinstance(thoughts, list):
        raise ValueError("atomic 响应缺少 thoughts 数组")
    result = []
    dropped = 0
    for i, raw in enumerate(thoughts):
        def reject(reason: str) -> None:
            nonlocal dropped
            dropped += 1
            issues.append(f"atomic 思考 {i} 已拒绝：{reason}")
        if not isinstance(raw, dict):
            reject("不是对象")
            continue
        statement = _single_line_text(raw.get("statement"), 200)
        if statement is None:
            reject("statement 缺失、超 200 字或含换行")
            continue
        kind = raw.get("kind")
        if kind not in ("question", "assertion"):
            reject("kind 必须是 question 或 assertion")
            continue
        ids = raw.get("unit_ids")
        if (not isinstance(ids, list) or not ids
                or not all(type(j) is int for j in ids)
                or any(not 0 <= j < len(units) for j in ids)):
            reject("unit_ids 缺失、类型错误或引用了不存在的单元")
            continue
        unit_ids = list(dict.fromkeys(ids))
        raw_growth = raw.get("growth_directions")
        if not isinstance(raw_growth, list) or not 1 <= len(raw_growth) <= 5:
            reject("growth_directions 缺失或数量非法")
            continue
        growth = []
        for g in raw_growth:
            action = _single_line_text(g.get("action") if isinstance(g, dict) else None, 200)
            basis = _single_line_text(g.get("basis") if isinstance(g, dict) else None, 200)
            if action is None or basis is None or len(basis) < 4:
                growth = []
                reject("生长方向缺少具体 action 或实质 basis")
                break
            growth.append({"action": literal(action), "basis": literal(basis)})
        if not growth:
            continue
        raw_scope = raw.get("negative_scope")
        if not isinstance(raw_scope, list) or not 1 <= len(raw_scope) <= 5:
            reject("negative_scope 缺失或数量非法")
            continue
        scope = [_single_line_text(s, 200) for s in raw_scope]
        if None in scope:
            reject("negative_scope 含空、超长或多行文本")
            continue
        support_kinds = {units[j]["kind"] for j in unit_ids}
        review = []
        if kind == "assertion" and "question" in support_kinds:
            review.append("问题性证据被写成断言，需人工复核，不得当作事实使用。")
        if kind == "question" and not _QUESTION.search(statement):
            review.append("kind 与表述形式不一致（question 但无疑问句式），需人工复核。")
        title = _single_line_text(raw.get("title"), 60)
        if title is None:
            supplied = raw.get("title")
            if isinstance(supplied, str) and supplied.strip():
                # 模型给了标题但超长或含换行：收短成完整短语，而不是整条丢弃后再盲切正文。
                title = _short_title(supplied, 60)
            else:
                title = _short_title(statement, 40)
        result.append({
            "statement": literal(statement), "kind": kind, "title": literal(title),
            "unit_ids": unit_ids, "growth_directions": growth,
            "negative_scope": [literal(s) for s in scope],
            "review_flags": review,
            "is_question": kind == "question",
            "thought_id": thought_identity(
                statement, kind, [units[j].get("identity") or unit_identity(units[j]) for j in unit_ids]),
            "statement_sha256": digest(statement),
        })
    return result, dropped


def _model_thoughts(units: list[dict], model_fn, issues: list[str], partial_note: str) -> tuple[list[dict], int] | None:
    payload = {"task": "atomic_seed", "coverage_note": partial_note, "units": [
        {"id": i, "source": u["source"], "quote": u["quote"], "kind": u["kind"],
         "speaker": u["speaker"] or "未知", "body_line": u["body_line"]}
        for i, u in enumerate(units)]}
    try:
        payload_text = json.dumps(payload, ensure_ascii=False)
        assert_safe_content(payload_text)  # exact outbound payload, before any model call
        raw = model_fn(ATOMIC_SYSTEM_PROMPT, payload)
        assert_safe_content(str(raw))      # whole raw response, including unused fields
        # T10: an encoding-damaged response is an error; the clean-input limited
        # preview fallback stays non-llm, non-complete, processed=0.
        text_integrity.assert_clean_response(str(raw), "atomic 模型响应")
        data = extract_json(raw)
        text_integrity.assert_clean_data(data, "atomic 模型输出")
        return _parse_model_thoughts(data, units, issues)
    except SensitiveContentError:
        raise
    except Exception as exc:
        issues.append("atomic 模型提炼失败，回退受限预览：" + safe_error_message(exc))
        return None


# ── Item construction ────────────────────────────────────────────────────────

def _signal_line(u: dict) -> str:
    prefix = "来源问题：" if u["kind"] == "question" else "来源陈述："
    speaker = f"，说话人：{u['speaker']}" if u.get("speaker") else "，说话人未知"
    locator = f"，原文第 {u['start_line']} 行" if u.get("start_line") else \
        (f"，原文第 {u['body_line']} 行" if u.get("body_line") else "")
    return f"{prefix}{literal(u['quote'])}（[[{u['source']}]]{locator}{speaker}）"


def _thought_item(thought: dict, units: list[dict]) -> dict:
    support = [units[j] for j in thought["unit_ids"]]
    sources = list(dict.fromkeys(u["source"] for u in support))
    signals = [_signal_line(u) for u in support]
    review = list(thought["review_flags"])
    if thought["kind"] == "question":
        review.append("该念头仍是未决问题，尚未获得证据支持，不得当作事实使用。")
    if any(not u.get("verified") for u in support):
        review.append("部分来源缺少已验证的原始字节快照，出处可追溯性有限（provenance unknown）。")
    identities = [u.get("identity") or unit_identity(u) for u in support]
    return {
        "title": thought["title"], "type": "seed-card",
        "status": "manual_review" if review else "seed",
        "stage": "needs_context" if review else "candidate",
        "sources": sources,
        "summary": thought["statement"],
        "kind": thought["kind"],
        "statement_sha256": thought["statement_sha256"],
        "thought_id": thought["thought_id"],
        "signals": signals,
        "evidence": [_compile_evidence_row(u) for u in support],
        "growth_directions": [f"{g['action']}（依据：{g['basis']}）" for g in thought["growth_directions"]],
        "negative_scope": thought["negative_scope"],
        "is_question": thought["is_question"],
        "thought_units": identities,
        "keywords": [], "related": [], "pending_links": [],
        "tags": ["原子种子"], "confidence": "low",
        "review_required": True,
        "origin": {"source_paths": sources, "operation": "mindseed-grow"},
        "manual_review": review or ["原子 seed 只是候选念头，主题边界与证据支持需人工确认。"],
    }


def _preview_item(unit: dict) -> dict:
    """Deterministic limited preview for one unit — explicitly NOT atomic success."""
    identity = unit.get("identity") or unit_identity(unit)
    thought_id = thought_identity(unit["quote"], "preview", [identity])
    return {
        "title": literal(_short_title(unit["quote"], 40)) or "未命名念头",
        "type": "seed-card", "status": "manual_review", "stage": "needs_context",
        "sources": [unit["source"]],
        "summary": literal(unit["quote"]),
        "kind": "question" if unit["kind"] == "question" else "assertion",
        "statement_sha256": digest(unit["quote"]),
        "thought_id": thought_id,
        "signals": [_signal_line(unit)],
        "evidence": [_compile_evidence_row(unit)],
        "growth_directions": [],
        "negative_scope": ["受限预览未确定边界；生长方向需模型提炼或人工补充。"],
        "is_question": unit["kind"] == "question",
        "limited_preview": True,
        "thought_units": [identity],
        "keywords": [], "related": [], "pending_links": [],
        "tags": ["原子种子", "受限预览"], "confidence": "low",
        "review_required": True,
        "origin": {"source_paths": [unit["source"]], "operation": "mindseed-grow"},
        "manual_review": [
            "atomic 无模型受限预览：未做念头提炼，仅保留可追溯单元，不能视为 atomic 达标产出。",
        ] + (["该念头仍是未决问题，不得写成事实。"] if unit["kind"] == "question" else [])
        + (["来源缺少已验证的原始字节快照，出处可追溯性有限。"] if not unit.get("verified") else []),
    }


def _stamp_identities(units: list[dict]) -> None:
    for unit in units:
        unit.setdefault("identity", unit_identity(unit))


def generate_atomic_items(
    notes: list[dict] | None = None,
    units: list[dict] | None = None,
    cfg: dict | None = None,
    *,
    model_fn=None,
    snapshots: dict | None = None,
) -> tuple[list[dict], list[str], dict]:
    """Reusable atomic generator entry.

    Accepts note dictionaries and/or already-extracted information units.
    Supplied units REQUIRE verified snapshots (original text + exact-byte
    SHA256); each quote is verified against the snapshot before use. Invalid
    provenance blocks BOTH paths — no provider call on a reduced set. Returns
    (items, issues, meta); meta.complete marks full checked coverage with no
    drops; meta.zero_reason marks a VALID model zero on fully checked input;
    meta.blocked_reason marks inputs that may not proceed at all.
    """
    issues: list[str] = []
    meta: dict = {"mode": "atomic", "model": "none", "coverage": "unknown",
                  "zero_reason": "", "blocked_reason": "", "complete": False}
    # T10: U+FFFD anywhere in a source string means damaged original text.
    # Blocked before any provider call on ANY path, including supplied
    # units/snapshots; damaged inputs can never yield a complete batch.
    if units is not None:
        unit_damaged = text_integrity.damaged_unit_reasons(units, snapshots)
        if unit_damaged:
            meta["blocked_reason"] = "提供的输入包含 U+FFFD 损坏字符，已阻断原子生成（damaged_source）。"
            return [], issues + unit_damaged + [meta["blocked_reason"]], meta
    supplied = units is not None
    if units is None:
        units = []
        for note in notes or []:
            damaged = text_integrity.damaged_reasons(note, str(note.get("rel") or ""))
            if damaged:
                # Blocked in any batch position — never a silently reduced run.
                meta["blocked_reason"] = damaged[0]
                issues.extend(damaged)
                return [], issues, meta
            batch_units = information_units(note)
            invalid = [u for u in batch_units if u.get("invalid_snapshot")]
            if invalid and (batch_units or note.get("source_text")):
                # A supplied snapshot whose hash does not match is an error, in
                # any batch position — never a silently reduced "full" run.
                meta["blocked_reason"] = f"来源 {note.get('rel')} 的快照哈希与原文不匹配（原始字节校验失败），已阻断。"
                issues.append(meta["blocked_reason"])
                return [], issues, meta
            units.extend(batch_units)
    else:
        units, verified_issues = verify_supplied_units(units, snapshots)
        issues.extend(verified_issues)
        if verified_issues:
            meta["blocked_reason"] = "提供的部分信息单元无法通过来源快照核验，已阻断原子生成。"
            issues.append(meta["blocked_reason"])
            return [], issues, meta
    if not units:
        meta["zero_reason"] = "输入为空或无实质内容，未提取到可归属的信息单元；零产出。"
        issues.append(meta["zero_reason"])
        return [], issues, meta
    # Bounded batch: over-budget means explicit PARTIAL coverage, never a
    # silent early prefix presented as complete input.
    excluded = max(0, len(units) - MAX_UNITS)
    total_chars = sum(len(u["quote"]) for u in units)
    over_budget = excluded or total_chars > MAX_TOTAL_QUOTE_CHARS
    partial_note = ""
    if over_budget:
        kept = []
        budget = MAX_TOTAL_QUOTE_CHARS
        for unit in units[:MAX_UNITS]:
            if budget - len(unit["quote"]) < 0:
                break
            budget -= len(unit["quote"])
            kept.append(unit)
        excluded = max(excluded, len(units) - len(kept))
        units = kept
        meta["coverage"] = "partial"
        meta["excluded_units"] = excluded
        partial_note = (f"本次仅纳入 {len(units)} 个单元，另有 {excluded} 个未纳入，非完整覆盖。")
        issues.append("信息单元超出批次预算：" + partial_note)
    _stamp_identities(units)
    if all(u.get("verified") for u in units):
        meta["coverage"] = "full" if not over_budget else "partial"
    if model_fn is None:
        meta["model"] = "none"
        issues.append("atomic 无模型受限预览：仅保留信息单元，未生成提炼念头。")
        return [_preview_item(u) for u in units], issues, meta
    parsed = _model_thoughts(units, model_fn, issues, partial_note)
    if parsed is None:
        meta["model"] = "failed"
        return [_preview_item(u) for u in units], issues, meta
    thoughts, dropped = parsed
    if dropped and not thoughts:
        # Malformed responses are errors, never a successful zero output.
        meta["model"] = "invalid"
        meta["blocked_reason"] = f"atomic 模型响应的 {dropped} 个候选全部非法，已阻断而非记为零产出。"
        issues.append(meta["blocked_reason"])
        return [], issues, meta
    if dropped:
        issues.append(f"atomic 模型响应有 {dropped} 个候选因字段非法被拒绝。")
    if not thoughts:
        meta["model"] = "llm"
        meta["zero_reason"] = "模型判断输入不含可独立表达的念头，零产出。"
        issues.append(meta["zero_reason"])
        meta["complete"] = meta["coverage"] == "full" and not over_budget
        return [], issues, meta
    meta["model"] = "llm"
    meta["complete"] = meta["coverage"] == "full" and not over_budget and not dropped
    return [_thought_item(t, units) for t in thoughts], issues, meta
