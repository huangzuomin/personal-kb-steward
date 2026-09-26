"""T6 checkpoint A1: persisted source-note eligibility for downstream promotion.

collect_eligible_sources(index, cfg) reads ONLY the captured index (no disk
writes, no model calls, no re-index) and returns the eligible persisted
source-note cards as generator-shaped notes plus the bookkeeping the later
plan-binding seam needs.

Eligibility (fail closed, never silently refreshed or repaired):
- BOTH captured snapshots are verified before any use: the source CARD's own
  bytes must still match the captured hash (via core.reconcile._text) and the
  ORIGINAL file's bytes must likewise match. A changed, deleted or
  undecodable file is a per-card rejection, never an uncaught exception, and
  never a silent refresh of stored analysis.
- Only files under the configured sources_dir with metadata.type=source-note
  and a card_state {version: exact int 1, type: source-note} block. Legacy
  pages without card_state, heuristic/fallback/unknown analysis, non-full
  coverage and unknown provenance are rejected with an explicit reason.
- coverage=full and analysis_mode=llm are required BOTH in the outer
  frontmatter and inside card_state.analysis; they must agree.
- Field SHAPES are validated before access (hash maps must be {str: str};
  units/limitations/speakers/topic_hints/quality_flags must be lists of the
  documented element shapes). A malformed field rejects that card with a
  reason while other valid cards still collect; no broad exception catching.
- Every declared hash (outer frontmatter, card_state.analysis and each info
  unit) must equal the sha256 of the ORIGINAL file's actual bytes. A stale or
  changed original is rejected; old analysis is never rebound to a new hash.
- Each persisted info unit's quote is re-located in the BOM/CRLF-normalized
  original text with the SAME core.source_analysis locating machinery that
  produced it, and ALL FOUR coordinates (start/end/start_line/end_line) must
  be present as exact ints with valid ranges and equal to the located values.
  start/end are normalized Unicode CHARACTER offsets of the original text
  (the sha256 covers the original RAW BYTES). One missing/forged unit
  invalidates the whole card (evidence is never downgraded to "partial");
  unit kinds/attributions are checked as-is, never upgraded.
- Originals are deduplicated by exact path+hash across valid cards; inherited
  restrictions are merged order-independently. source_kind is resolved at
  finalization from the set of known kinds over ALL contributing cards: no
  known kind (none/unknown alone) stays "unknown"; one known kind plus
  unknowns preserves the known kind (recorded as mixed provenance); genuinely
  conflicting known kinds resolve to "unknown" with a visible limitation and
  issue listing the alternatives — the lexicographic minimum is never
  semantic truth. All currently eligible persisted sources are returned, not
  just the latest batch; this helper does not concatenate them into one call.
- Returned notes carry rel/title/body/metadata/source_text/source_sha256 from
  the ACTUAL original files plus a whitelisted
  metadata["upstream_analysis"] {source_kind, limitations, speakers}; outer
  quality_flags are folded into limitations so source-specific restrictions
  survive even when a downstream model omits them. Returned topic_hints keep
  their ACTUAL originating source card (one entry per origin), never
  cards[0]; they are proposed research frames, never authoritative claims.
- upstream_hashes pins each eligible source CARD's own snapshot hash and
  source_note_paths maps original -> contributing cards, so the plan seam can
  pin both. Ordering is deterministic (sorted paths); rejected entries carry a
  reason only — never source text or credentials.
"""
from __future__ import annotations

import re
from typing import Any

from .claims import normalized_text
from .layout import knowledge_dirs, knowledge_prefixes
from .reconcile import ReconcileConflict, _text as captured_note_text
from .source_analysis import STATEMENT_KINDS, locate_quote
from .topic_generation import is_safe_rel_path
from .vault import Note, VaultIndex

CARD_STATE_VERSION = 1
_HASH_RE = re.compile(r"[0-9a-f]{64}")

# Whitelist of inherited upstream analysis fields handed to generators.
UPSTREAM_FIELDS = ("source_kind", "limitations", "speakers")


def _reject(rejected: list[dict[str, str]], note: Note, reason: str) -> None:
    rejected.append({"source_note": note.rel, "reason": reason})


def _full_hash(value: Any) -> str | None:
    return value if isinstance(value, str) and _HASH_RE.fullmatch(value) else None


def _is_exact_int(value: Any) -> bool:
    return type(value) is int  # bool/float/str are invalid coordinates


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _hash_map(value: Any) -> bool:
    return (isinstance(value, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()))


def _unit_problem(unit: Any, norm_text: str, rel: str, sha: str) -> str | None:
    """Return a rejection reason when one persisted unit fails re-verification."""
    if not isinstance(unit, dict):
        return "info_unit 不是对象"
    if unit.get("verified") is not True:
        return "info_unit 自身标记为未通过核验"
    if unit.get("kind") not in STATEMENT_KINDS:
        return f"info_unit.kind 非法：{unit.get('kind')!r}"
    if not isinstance(unit.get("source"), str) or unit["source"] != rel:
        return "info_unit.source 与来源声明不一致"
    if unit.get("source_sha256") != sha:
        return "info_unit.source_sha256 与原始字节 hash 不一致"
    quote = unit.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        return "info_unit.quote 缺失或为空"
    # The typed persisted contract requires all four coordinates as exact
    # ints; missing metadata is NOT reconstructed as if evidence were valid.
    coords = {}
    for key in ("start", "end", "start_line", "end_line"):
        value = unit.get(key)
        if not _is_exact_int(value):
            return f"info_unit.{key} 缺失或不是精确整数（持久化契约要求完整坐标）"
        coords[key] = value
    if not (0 <= coords["start"] < coords["end"]):
        return "info_unit.start/end 范围非法"
    if coords["start_line"] < 1 or coords["end_line"] < coords["start_line"]:
        return "info_unit.start_line/end_line 范围非法"
    try:
        located = locate_quote(norm_text, quote, coords["start_line"])
    except Exception:
        return "info_unit 引用无法在原文中唯一定位"
    for key in ("start", "end", "start_line", "end_line"):
        if coords[key] != located[key]:
            return f"info_unit.{key} 坐标与原文定位不一致"
    return None


def _shape_problems(note: Note, meta: dict[str, Any],
                    analysis: dict[str, Any]) -> str | None:
    """Validate persisted field shapes BEFORE any element access."""
    if not _hash_map(meta.get("source_hashes") or {}):
        return "frontmatter source_hashes 不是 {路径: hash} 映射"
    if not _hash_map(analysis.get("source_hashes") or {}):
        return "card_state.analysis.source_hashes 不是 {路径: hash} 映射"
    if "quality_flags" in meta and not _string_list(meta["quality_flags"]):
        return "frontmatter quality_flags 不是字符串数组"
    if "limitations" in analysis and not _string_list(analysis["limitations"]):
        return "card_state.analysis.limitations 不是字符串数组"
    if "speakers" in analysis and not _string_list(analysis["speakers"]):
        return "card_state.analysis.speakers 不是字符串数组"
    hints = analysis.get("topic_hints")
    if hints is not None and (not isinstance(hints, list)
                              or not all(isinstance(h, dict) for h in hints)):
        return "card_state.analysis.topic_hints 不是对象数组"
    return None


def _evaluate_card(index: VaultIndex, cfg: dict[str, Any], note: Note,
                   knowledge_prefixes: tuple[str, ...],
                   rejected: list[dict[str, str]]) -> dict[str, Any] | None:
    """Validate one persisted source card; return its evidence bundle or None."""
    # Verify the CARD's own captured snapshot first: metadata parsed at index
    # build is only trustworthy while the bytes still match.
    try:
        captured_note_text(note)
    except (ReconcileConflict, UnicodeDecodeError, OSError):
        _reject(rejected, note, "来源卡自身快照与捕获 hash 不一致、已删除或不可解码；拒绝使用其元数据")
        return None
    meta = note.metadata
    state = meta.get("card_state")
    if not isinstance(state, dict):
        _reject(rejected, note, "缺少 card_state（legacy 或未版本化页面），不作为晋级证据")
        return None
    if type(state.get("version")) is not int or state["version"] != CARD_STATE_VERSION \
            or state.get("type") != "source-note":
        _reject(rejected, note, "card_state 版本或类型不是精确 version=1 的 source-note")
        return None
    analysis = state.get("analysis")
    if not isinstance(analysis, dict):
        _reject(rejected, note, "card_state.analysis 缺失")
        return None
    shape_problem = _shape_problems(note, meta, analysis)
    if shape_problem:
        _reject(rejected, note, shape_problem)
        return None
    mode_outer = meta.get("analysis_mode")
    mode_inner = analysis.get("analysis_mode")
    if mode_outer != "llm" or mode_inner != "llm":
        _reject(rejected, note,
                f"analysis_mode 非 llm（outer={mode_outer!r}, analysis={mode_inner!r}）；"
                "启发式/回退输出不作为完整语义证据")
        return None
    cov_outer, cov_inner = meta.get("coverage"), analysis.get("coverage")
    if cov_outer != "full" or cov_inner != "full":
        _reject(rejected, note,
                f"coverage 非 full（outer={cov_outer!r}, analysis={cov_inner!r}）；"
                "部分覆盖不得作为完整晋级证据")
        return None
    units = state.get("info_units")
    if not isinstance(units, list) or not units:
        _reject(rejected, note, "card_state.info_units 为空或形状非法，无可用信息单元")
        return None
    sources = meta.get("sources")
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], str):
        _reject(rejected, note, "sources 必须是恰好一个来源路径")
        return None
    rel = sources[0]
    if not is_safe_rel_path(rel):
        _reject(rejected, note, "来源路径不是规范的 vault 相对路径")
        return None
    if rel.startswith(knowledge_prefixes):
        _reject(rejected, note, "来源指向派生知识页（自引用/派生源循环），拒绝")
        return None
    original = index.by_rel.get(rel)
    if original is None:
        _reject(rejected, note, "原始来源文件不在当前索引中（未落盘或已删除）")
        return None
    sha = _full_hash(original.sha256)
    if sha is None:
        _reject(rejected, note, "原始来源捕获 hash 非法")
        return None
    declared_outer = (meta.get("source_hashes") or {}).get(rel)
    declared_inner = (analysis.get("source_hashes") or {}).get(rel)
    if declared_outer != sha or declared_inner != sha:
        # Never rebind stored analysis to a new index hash: the card must be
        # regenerated through review/apply against the new snapshot.
        _reject(rejected, note,
                "声明 hash 与原始文件当前字节不一致（原始来源已变化或声明伪造）；"
                "不静默刷新旧分析")
        return None
    try:
        raw_text = captured_note_text(original)
    except (ReconcileConflict, UnicodeDecodeError, OSError):
        _reject(rejected, note, "原始来源读取/校验失败（已删除、被修改或不可解码）")
        return None
    norm_text = normalized_text(raw_text)
    for i, unit in enumerate(units):
        problem = _unit_problem(unit, norm_text, rel, sha)
        if problem:
            _reject(rejected, note, f"info_units[{i}]：{problem}；整卡证据视为无效")
            return None
    limitations = [x for x in (analysis.get("limitations") or []) if x.strip()]
    flags = [x for x in (meta.get("quality_flags") or []) if x.strip()]
    kind = analysis.get("source_type")
    kind = kind.strip() if isinstance(kind, str) and kind.strip() else None
    return {
        "rel": rel,
        "sha": sha,
        "source_text": raw_text,
        "kind": kind,
        "speakers": sorted({x for x in (analysis.get("speakers") or []) if x.strip()}),
        # Explicit limitations first, then outer quality flags — combined from
        # stored state, never by parsing display prose.
        "limitations": limitations + flags,
        "hints": [{"title": str(h.get("title", "")), "content": str(h.get("content", "")),
                   "origins": [note.rel]}
                  for h in (analysis.get("topic_hints") or [])
                  if str(h.get("title", "")).strip()],
    }


def _kind_accumulators(kind: str | None) -> tuple[set[str], bool]:
    """(known kinds, saw an unknown/blank classification) for one card."""
    if kind and kind != "unknown":
        return {kind}, False
    return set(), kind is None or kind == "unknown"


def _resolve_source_kind(known: set[str], saw_unknown: bool
                         ) -> tuple[str | None, str | None]:
    """Order-independent source_kind resolution over ALL contributing cards.

    Returns (resolved_kind, provenance_note). "unknown"/blank never competes
    with a known kind; genuinely conflicting known kinds NEVER resolve by
    lexicographic minimum — they fall back to "unknown" with a visible note
    listing the alternatives.
    """
    if len(known) == 1:
        kind = next(iter(known))
        if saw_unknown:
            return kind, (f"部分来源卡的来源类型归类为 unknown，已知归类 {kind} 保留"
                          "（混合来源，需人工确认）")
        return kind, None
    if len(known) > 1:
        alternatives = "、".join(sorted(known))
        return "unknown", f"存在冲突的来源类型归类（{alternatives}），保守按 unknown 处理，需人工裁决"
    return ("unknown" if saw_unknown else None), None


def collect_eligible_sources(index: VaultIndex, cfg: dict[str, Any]) -> dict[str, Any]:
    """Return the compact eligibility structure documented in the module docstring."""
    sources_prefix = knowledge_dirs(cfg)["sources_dir"] + "/"
    knowledge_prefixes = tuple(dict.fromkeys(
        path + "/" for path in knowledge_dirs(cfg).values()))
    issues: list[str] = []
    rejected: list[dict[str, str]] = []
    per_original: dict[str, dict[str, Any]] = {}
    cards_by_original: dict[str, list[str]] = {}

    candidates = [n for n in index.notes
                  if n.rel.startswith(sources_prefix)
                  and str(n.metadata.get("type") or "") == "source-note"]
    for note in sorted(candidates, key=lambda n: n.rel):
        bundle = _evaluate_card(index, cfg, note, knowledge_prefixes, rejected)
        if bundle is None:
            continue
        rel, sha = bundle["rel"], bundle["sha"]
        cards_by_original.setdefault(rel, []).append(note.rel)
        existing = per_original.get(rel)
        if existing is None:
            known, saw_unknown = _kind_accumulators(bundle["kind"])
            bundle.update(known_kinds=known, saw_unknown=saw_unknown, kind=None)
            per_original[rel] = bundle
            continue
        if existing["sha"] != sha:
            # Same path, two valid cards, different original hashes: the bytes
            # decide, and order must not. This cannot normally happen (the
            # hash check above compares against actual bytes) — record it.
            issues.append(f"同一来源 {rel} 出现不同声明 hash 的有效卡，以实际字节 {sha[:12]}… 为准")
        # Order-independent merge of inherited restrictions. Known kinds are
        # accumulated over ALL cards; "unknown"/blank is not a known kind.
        existing["limitations"] = sorted(set(existing["limitations"]) | set(bundle["limitations"]))
        existing["speakers"] = sorted(set(existing["speakers"]) | set(bundle["speakers"]))
        known, saw_unknown = _kind_accumulators(bundle["kind"])
        existing["known_kinds"] |= known
        existing["saw_unknown"] = existing["saw_unknown"] or saw_unknown
        merged_hints: dict[tuple[str, str], list[str]] = {
            (h["title"], h["content"]): list(h["origins"]) for h in existing["hints"]}
        for hint in bundle["hints"]:
            merged_hints.setdefault((hint["title"], hint["content"]), []).extend(hint["origins"])
        existing["hints"] = [{"title": t, "content": c, "origins": sorted(set(o))}
                             for (t, c), o in merged_hints.items()]

    notes: list[dict[str, Any]] = []
    upstream_hashes: dict[str, str] = {}
    source_note_paths: dict[str, list[str]] = {}
    topic_hints: list[dict[str, str]] = []
    for rel in sorted(per_original):
        bundle = per_original[rel]
        original = index.by_rel[rel]
        known_kinds = bundle["known_kinds"]
        saw_unknown = bundle["saw_unknown"]
        kind, provenance = _resolve_source_kind(known_kinds, saw_unknown)
        if provenance and known_kinds:
            bundle["limitations"] = sorted(set(bundle["limitations"]) | {provenance})
            if len(known_kinds) != 1:
                issues.append(f"来源 {rel}：{provenance}")
        metadata = dict(original.metadata)
        metadata["upstream_analysis"] = {
            "source_kind": kind,
            "limitations": bundle["limitations"],
            "speakers": bundle["speakers"],
        }
        notes.append({
            "rel": rel,
            "title": original.title,
            "body": original.body,
            "metadata": metadata,
            "source_text": bundle["source_text"],
            "source_sha256": bundle["sha"],
        })
        cards = sorted(cards_by_original[rel])
        source_note_paths[rel] = cards
        for card in cards:
            upstream_hashes[card] = index.by_rel[card].sha256
        for hint in bundle["hints"]:
            # One entry per ACTUAL originating card — never attributed to
            # cards[0] when the hint only exists in a later card.
            for origin in hint["origins"]:
                topic_hints.append({"title": hint["title"], "content": hint["content"],
                                    "source_note": origin})
    topic_hints.sort(key=lambda h: (h["source_note"], h["title"], h["content"]))
    rejected.sort(key=lambda r: r["source_note"])
    return {
        "notes": notes,
        "upstream_hashes": dict(sorted(upstream_hashes.items())),
        "source_note_paths": dict(sorted(source_note_paths.items())),
        "issues": sorted(issues),
        "rejected": rejected,
        "topic_hints": topic_hints,
    }


# ---------------------------------------------------------------------------
# T6 checkpoint A2: thin typed generation adapters (concept/case) over the
# accepted collector. One eligibility scan per discovery; ONE bounded
# generate_concepts/generate_cases call per kind; injectable provider via the
# generators' own seam; no source floor; zero/disabled/error/stub stay
# distinct; planned page specs pin BOTH original bytes and their upstream
# source-card snapshots. plan_objects remains the only identity authority.
# ---------------------------------------------------------------------------
GEN_KINDS = ("concept", "case", "topic")
GEN_DIR_KEYS = {"concept": "concepts_dir", "case": "cases_dir", "topic": "topics_dir"}


def _readable_filename(title: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title).strip()
    cleaned = re.sub(r"[，。；;、\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned[:80] or fallback


def _positive_cap(cfg: dict[str, Any], key: str, default: int) -> int:
    section = cfg.get("card_pipeline") if isinstance(cfg.get("card_pipeline"), dict) else {}
    value = section.get(key, default)
    if type(value) is not int or value < 1:
        raise ValueError(f"card_pipeline.{key} 必须是正整数：{value!r}")
    return value


def _topic_questions(cfg: dict[str, Any]) -> list[str] | None:
    """Configured explicit research questions; None = malformed config.

    Absent key or empty list = not configured (no model call). Persisted topic
    hints are NEVER auto-promoted into questions: they stay proposals.
    """
    section = cfg.get("card_pipeline") if isinstance(cfg.get("card_pipeline"), dict) else {}
    raw = section.get("topic_questions")
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(q, str) and q.strip() for q in raw):
        raise ValueError("card_pipeline.topic_questions 必须是非空字符串列表")
    if len(raw) > 1:
        raise ValueError("card_pipeline.topic_questions 本轮最多支持一个问题；多问题配置必须拆分为多次运行")
    return [q.strip() for q in raw if q.strip()]


def executor_stage(entry: str, stage_name: str, skill_label: str,
                   exec_result: dict[str, Any]) -> dict[str, Any]:
    """Normalize ONE specialized executor result into a truthful stage envelope.

    Source's accepted `input_outcomes` (ok/zero/partial/blocked/error +
    complete flags) is preserved verbatim and drives the stage outcome —
    success is never inferred from issue strings or output counts. Executors
    without input_outcomes fall back to the reported processed count without
    claiming per-input truth.
    """
    from collections import Counter
    outcomes = [o for o in (exec_result.get("input_outcomes") or []) if isinstance(o, dict)]
    counts = Counter(str(o.get("outcome")) for o in outcomes)
    complete = sum(1 for o in outcomes if o.get("complete") is True)
    # A complete zero is still zero.  Check the explicit zero contract before
    # the generic complete flag so a no-content batch is never reported as
    # executed merely because the executor marked its input complete.
    if outcomes and counts.get("zero", 0) == len(outcomes):
        outcome = "zero"
    elif outcomes and complete:
        outcome = "executed" if complete == len(outcomes) else "partial_input"
    elif outcomes:
        outcome = "partial_input"
    elif int(exec_result.get("processed", 0) or 0) > 0:
        outcome = "executed"
    else:
        outcome = "blocked"
    return {
        "operation": "pipeline_stage",
        "entry": entry,
        "stage": stage_name,
        "skill": skill_label,
        "risk": "medium",
        "outcome": outcome,
        "planned_inputs": len(exec_result.get("inputs", [])),
        "processed": int(exec_result.get("processed", 0) or 0),
        "input_outcomes": outcomes,
        "outcome_counts": dict(sorted(counts.items())),
        "planned_pages": len(exec_result.get("planned_pages", []) or []),
    }


def _eligible_source_index(index: VaultIndex,
                           notes: list[dict[str, Any]]) -> VaultIndex:
    """Build a request-local index containing only eligible original notes.

    Retriever remains the ranking/diagnostic implementation.  Restricting its
    live view before selection prevents derived or rejected pages from using
    the bounded topic limit and crowding out a qualifying original source.
    """
    selected = [index.by_rel[n["rel"]] for n in notes if n.get("rel") in index.by_rel]
    by_rel = {n.rel: n for n in selected}
    by_stem: dict[str, list[Note]] = {}
    by_title: dict[str, list[Note]] = {}
    for note in selected:
        by_stem.setdefault(note.path.stem, []).append(note)
        by_title.setdefault(note.title.strip().lower(), []).append(note)
    return VaultIndex(
        root=index.root,
        notes=selected,
        by_rel=by_rel,
        by_stem=by_stem,
        by_title=by_title,
        by_attachment=index.by_attachment,
        knowledge_prefixes=index.knowledge_prefixes,
        obsidian_compat=index.obsidian_compat,
    )


def _topic_source_cap(cfg: dict[str, Any]) -> int:
    """Validate topic budgets before a provider can be reached."""
    cap = _positive_cap(cfg, "topic_source_cap", 6)
    from .topic_generation import TopicGenerationError, topic_settings
    try:
        settings = topic_settings(cfg)
    except TopicGenerationError as exc:
        raise ValueError(str(exc)) from exc
    minimum = settings["min_full_sources"]
    if minimum > cap:
        raise ValueError(
            "topic_generation.min_full_sources 不能大于 "
            f"card_pipeline.topic_source_cap（{minimum} > {cap}）；"
            "该配置无法生成满足 full 来源下限的专题"
        )
    return cap


def _topic_retrieval_query(question: str) -> str:
    """Add bounded Chinese n-grams while keeping the user's question intact.

    The existing Retriever deliberately uses conservative lexical terms.  A
    continuous Chinese sentence otherwise becomes one long term and misses
    sources that contain the same subject words with different punctuation or
    wording.  Four-character windows preserve question-led ranking without
    introducing a second retrieval implementation.
    """
    chunks = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+", question)
    windows: list[str] = []
    for chunk in chunks:
        if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
            windows.extend(chunk[i:i + 4] for i in range(max(0, len(chunk) - 3)))
        else:
            windows.append(chunk)
    return " ".join(dict.fromkeys([*windows, question]))


def _stage_outcome(kind: str, result: dict[str, Any] | None, *,
                   eligible: int, rejected: int, calls: int) -> dict[str, Any]:
    """Normalize one generator result into an explicit, JSON-safe stage outcome.

    provider_calls is the ACTUAL number of provider invocations observed by the
    counting wrapper at the provider seam — never inferred from state strings.
    """
    stage: dict[str, Any] = {
        "stage": f"{kind}_generation", "eligible_sources": eligible,
        "rejected_sources": rejected, "provider_calls": calls,
        "planned_items": 0, "collisions": [], "issues": [],
    }
    if result is None:  # caller-level short circuit: no eligible inputs
        stage.update(state="blocked", reason="no_eligible_sources",
                     reason_detail="没有符合条件的已沉淀 source note（含被拒来源数，见 rejected_sources）")
        return stage
    state, reason = result.get("state"), result.get("reason")
    stage["issues"] = list(result.get("issues") or [])
    if state == "error":
        if "max_source_chars" in (reason or "") or "max_context_chars" in (reason or ""):
            stage.update(state="blocked", reason="oversize_input_deferred",
                         reason_detail=reason)  # pre-call budget block, 0 calls
        else:
            stage.update(state="error",
                         reason="model_error" if calls else "pre_call_error",
                         reason_detail=reason)
        return stage
    stage.update(state=state, reason="zero_output" if state == "zero" else None,
                 reason_detail=reason)
    if state == "zero":
        stage["reason"] = "zero_output"
    elif state == "disabled":
        stage["reason"] = "not_configured"
    elif state == "stub":
        stage["reason"] = "partial_input"
    return stage


def discover_cards(index: VaultIndex, cfg: dict[str, Any], *, run_id: str,
                   use_llm: bool = True, kinds: tuple[str, ...] = GEN_KINDS,
                   providers: dict[str, Any] | None = None,
                   skill: str = "kb-finalize", now: str | None = None,
                   retriever: Any | None = None,
                   focus_rels: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Run typed concept/case/topic discovery over eligible persisted sources.

    - ONE bounded generate_concepts/generate_cases/generate_topic call per
      kind; the provider actually invoked (including the default) is wrapped
      in a counting wrapper, so stage.provider_calls reports REAL
      invocations: disabled / invalid config / no inputs / preflight blocks
      count 0; an attempt that raises counts 1. Pre-call errors are
      distinguished from model errors in the stage reason.
    - Concept/case focus (GP001): when `focus_rels` names a NON-EMPTY current
      input scope (init-kb: this run's raw batch), concept/case supplied notes
      narrow to the eligible pool members derived from those originals — the
      cumulative pool stays wide, but historical unrelated cards are no longer
      fed to the generator (RELEVANCE_FILTER_MISSING fix). Nothing in scope =>
      zero/no_relevant_sources without a call. An EMPTY `focus_rels` (a pure
      backlog run with no fresh input) or `focus_rels=None` keeps the prior
      whole-pool behavior: cross-source backlog typing is that contract (see
      test_initializer_and_finalizer_share_derived_receipt_identity).

    - ONE bounded generate_concepts/generate_cases/generate_topic call per
      kind; the provider actually invoked (including the default) is wrapped
      in a counting wrapper, so stage.provider_calls reports REAL
      invocations: disabled / invalid config / no inputs / preflight blocks
      count 0; an attempt that raises counts 1. Pre-call errors are
      distinguished from model errors in the stage reason.
    - Topic (B1a): requires an EXPLICIT configured research question in
      `cfg["card_pipeline"]["topic_questions"]` (bounded nonempty-string
      list). No configured question => disabled/not_configured with zero
      model calls; a malformed list => error/invalid_topic_question_config
      with zero model calls. Persisted source topic hints are surfaced ONLY
      as clearly-labeled proposals (stage.proposed_topic_hints) and are never
      auto-sent to the model. Topic sources are a bounded relevant selection
      (existing Retriever over the question, cap
      `card_pipeline.topic_source_cap`, default 6) mapped back to actual
      eligible captured originals; nothing relevant selected => zero without
      a call. min_full_sources and budget constraints are validated by the
      accepted generator BEFORE any call (impossible values => pre-call
      error, never a quiet override).
    - Related candidates come from ONE request-scoped existing Retriever
      selection (bounded cap, config `card_pipeline.related_paths_cap`,
      default 6) over confirmed existing knowledge targets only. Input
      originals are excluded; the whole index is NEVER sent as known_paths.
      Oversize source sets are still an explicit block, never truncated.
    - Planned page specs retain the EXACT generator candidate as page["item"]
      (no renormalization); retrieval_source_hashes pins ALL supplied
      originals + their upstream source cards + retrieved context, while
      item.sources/item.source_hashes stay limited to actually cited evidence.
    - plan_objects remains the only id/revision authority; applied only via
      save-plan -> review -> apply.
    """
    from . import llm as llm_module
    from .config import sha256_text
    from .retrieval import Retriever, retrieval_prefixes
    from .pipeline_history import (
        complete_generation_receipt_draft,
        derived_cohort_paths,
        derived_generator_contract,
        lookup_generation_receipt,
        make_generation_receipt_draft,
    )

    collected = collect_eligible_sources(index, cfg)
    eligible_notes = collected["notes"]
    cap = _positive_cap(cfg, "related_paths_cap", 6)
    dirs = knowledge_dirs(cfg)
    # Preserve the caller's seam separately from the request-scoped Retriever
    # used for related candidates.  The latter must never become the topic
    # selector by assignment when no Retriever was supplied.
    supplied_retriever = retriever

    # One existing Retriever is reused per request; each derived kind gets its
    # own bounded selection so its receipt captures the exact context it saw.
    related_retriever = supplied_retriever or Retriever(cfg, index)

    provider_counts: dict[str, int] = {kind: 0 for kind in GEN_KINDS}

    def _counting(kind, provider):
        def wrapped(cfg_, prompt, payload):
            provider_counts[kind] += 1
            return provider(cfg_, prompt, payload)
        return wrapped

    generators = {"concept": None, "case": None, "topic": None}
    stages: dict[str, dict[str, Any]] = {}
    planned_pages: list[dict[str, Any]] = []
    issues = list(collected["issues"])
    by_rel_notes = {n["rel"]: n for n in eligible_notes}
    generation_receipt_drafts: list[dict[str, Any]] = []
    all_related_paths: set[str] = set()
    last_retrieval_report: dict[str, Any] | None = None

    def _upstream_snapshots(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for note in notes:
            for rel in collected["source_note_paths"].get(note.get("rel"), []):
                card = index.by_rel.get(rel)
                sha = collected["upstream_hashes"].get(rel) or (card.sha256 if card else "")
                if not sha:
                    continue
                item: dict[str, Any] = {"rel": rel, "sha256": sha}
                if card is not None:
                    item["object_id"] = card.object_id
                    item["revision"] = card.revision
                rows[(rel, sha)] = item
        return [rows[key] for key in sorted(rows)]

    def _cached_stage(kind: str, decision: dict[str, Any], *, eligible: int,
                      retrieval: dict[str, Any] | None, related: list[str],
                      extras: dict[str, Any]) -> dict[str, Any]:
        decision_name = str(decision.get("decision") or "retryable")
        state = {
            "pending_review": "pending_review",
            "unchanged_inputs": "cached",
            "zero_output": "zero",
            "review_rejected": "rejected",
        }.get(decision_name, "blocked")
        stage = _stage_outcome(kind, {"state": state, "reason": decision.get("reason")},
                               eligible=eligible, rejected=len(collected["rejected"]), calls=0)
        stage.update({
            "state": state,
            "reason": decision_name,
            "reason_detail": decision.get("reason"),
            "receipt_decision": decision_name,
            "receipt_ref": decision.get("receipt_ref"),
            "receipt_plan_ref": decision.get("plan_ref"),
            "input_outcomes": decision.get("input_outcomes") or [],
            "target_catalog": decision.get("target_catalog") or {},
            "retrieval": retrieval,
            "related_candidates": list(related),
        })
        stage.update(extras)
        return stage

    for kind in kinds:
        if kind not in GEN_KINDS:
            raise ValueError(f"未知类型化生成种类：{kind}")
        supplied = list(eligible_notes)
        stage_extras: dict[str, Any] = {}
        retrieval_report: dict[str, Any] | None = None
        known_paths: list[str] = []

        if kind in ("concept", "case") and focus_rels is not None and eligible_notes:
            # GP001（RELEVANCE_FILTER_MISSING）：调用方给出非空本轮输入范围时，
            # 类型化生成对象收窄为"该范围对应的已沉淀来源卡"——新输入优先消化，
            # 历史池成员不再搭车进入同一 payload（宽候选池语义不变，见
            # collect_eligible_sources）。focus 为空集 = 本轮无新输入的积压 run，
            # 保持既有全池语义（与 finalize 的跨源聚合契约一致，见
            # test_initializer_and_finalizer_share_derived_receipt_identity）。
            focus = {str(rel) for rel in focus_rels}
            if focus:
                supplied = [n for n in eligible_notes if n["rel"] in focus]
                stage_extras["focus_rels"] = sorted(focus)
                if not supplied:
                    stages[kind] = _stage_outcome(kind, None, eligible=0,
                                                  rejected=len(collected["rejected"]),
                                                  calls=0)
                    stages[kind].update({
                        "state": "zero", "reason": "no_relevant_sources",
                        "reason_detail": "本轮输入范围内没有可类型化的已沉淀来源；"
                                         "不强行生成，候选池不受影响",
                        "retrieval": None,
                    })
                    stages[kind].update(stage_extras)
                    continue

        if kind == "topic":
            # Question seam: explicit configured questions only.
            try:
                questions = _topic_questions(cfg)
            except ValueError as exc:
                stages[kind] = _stage_outcome(kind, None, eligible=0,
                                              rejected=len(collected["rejected"]),
                                              calls=0)
                stages[kind].update(state="error", reason="invalid_topic_question_config",
                                    reason_detail=str(exc), retrieval=retrieval_report)
                continue
            stage_extras["proposed_topic_hints"] = list(collected["topic_hints"])
            if not questions:
                stages[kind] = _stage_outcome(kind, None, eligible=0,
                                              rejected=len(collected["rejected"]),
                                              calls=0)
                stages[kind].update(state="disabled", reason="not_configured",
                                    reason_detail="未配置 card_pipeline.topic_questions："
                                                  "主题生成需要明确的研究问题；来源卡 topic hint 仅为提案，"
                                                  "不会自动发送给模型",
                                    retrieval=retrieval_report, **stage_extras)
                continue
            try:
                topic_cap = _topic_source_cap(cfg)
            except ValueError as exc:
                invalid = _stage_outcome(
                    kind, {"state": "error", "reason": str(exc)},
                    eligible=0, rejected=len(collected["rejected"]), calls=0,
                )
                invalid.update(reason="pre_call_error", reason_detail=str(exc),
                               retrieval=retrieval_report, **stage_extras)
                stages[kind] = invalid
                continue
            question = questions[0]
            stage_extras["question"] = question
            stage_extras["question_source"] = "configured"
            if eligible_notes:
                # Bounded relevant selection over the question, mapped back to
                # ACTUAL eligible captured originals. When using the built-in
                # Retriever, its request-local index contains only eligible
                # originals, so ineligible/derived pages cannot consume the cap.
                topic_retriever = supplied_retriever
                if topic_retriever is None:
                    topic_retriever = Retriever(
                        cfg, _eligible_source_index(index, eligible_notes))
                # A caller-provided Retriever may be a test/integration seam
                # over a wider index. Give it enough bounded recall to survive
                # filtering, then enforce topic_source_cap on eligible results.
                selection_limit = topic_cap if supplied_retriever is None else min(
                    100, max(topic_cap, len(eligible_notes)))
                selection_kwargs = {
                    "limit": selection_limit,
                    "prefixes": retrieval_prefixes(cfg),
                }
                if supplied_retriever is None:
                    # The request-local built-in Retriever owns the complete
                    # eligible scope. Cache recall may rank it, but must not
                    # evict current scoped notes before live matching.
                    selection_kwargs["scope_to_index"] = True
                selection = topic_retriever.select(
                    _topic_retrieval_query(question), **selection_kwargs)
                stage_extras["topic_selection_report"] = selection.report
                selected_rels = {n.rel for n in selection.notes if n.rel in by_rel_notes}
                selected_rels = set(list(sorted(selected_rels))[:topic_cap])
                supplied = [by_rel_notes[n.rel] for n in selection.notes
                            if n.rel in selected_rels]
                # Keep the report truthful when an injected retriever included
                # rejected/derived hits in its wider recall window.
                report = dict(selection.report)
                report["query"] = question
                report["retrieval_query"] = _topic_retrieval_query(question)
                report["hits"] = [h for h in report.get("hits", [])
                                  if h.get("path") in selected_rels]
                report["topic_source_cap"] = topic_cap
                report["eligible_originals"] = len(eligible_notes)
                stage_extras["topic_selection_report"] = report
            if not supplied:
                stages[kind] = _stage_outcome(kind, None, eligible=0,
                                              rejected=len(collected["rejected"]),
                                              calls=0)
                stages[kind].update(state="zero", reason="no_relevant_sources",
                                    reason_detail="检索未找到与问题相关的符合条件的已沉淀来源；"
                                                  "不强行生成专题",
                                    retrieval=retrieval_report, **stage_extras)
                continue

        if not eligible_notes:
            stages[kind] = _stage_outcome(kind, None, eligible=0,
                                          rejected=len(collected["rejected"]),
                                          calls=0)
            stages[kind]["retrieval"] = retrieval_report
            stages[kind].update(stage_extras)
            continue
        if not supplied:
            stages[kind] = _stage_outcome(kind, None, eligible=0,
                                          rejected=len(collected["rejected"]), calls=0)
            stages[kind].update(state="zero", reason="no_relevant_sources",
                                reason_detail="没有可供该派生阶段评估的来源；未调用 provider。",
                                retrieval=retrieval_report, **stage_extras)
            continue

        stage_name = f"{kind}_generation"
        upstream_cards = _upstream_snapshots(supplied)
        semantic = {
            "kind": "derived",
            "derived_kind": kind,
            "skill": skill,
            "question": stage_extras.get("question"),
            "analysis_mode": "llm" if use_llm else "heuristic",
        }
        contract = derived_generator_contract(kind)
        base_draft = make_generation_receipt_draft(
            index, cfg, skill=skill, stage=stage_name, notes=supplied,
            use_llm=use_llm, upstream_cards=upstream_cards,
            retrieval_context=[], semantic=semantic,
            generator_contract=contract,
        )
        cohort = derived_cohort_paths(
            cfg, skill=skill, stage=stage_name,
            input_closure=base_draft["input_closure"], index=index)
        excluded = {note["rel"] for note in supplied}
        excluded.update(item["rel"] for item in upstream_cards if item.get("rel"))
        excluded.update(cohort)
        related_query = " ".join(
            [str(note.get("title") or "") for note in supplied]
            + ([str(stage_extras["question"])] if stage_extras.get("question") else [])
        ).strip()
        selection = related_retriever.select(
            related_query, limit=cap, prefixes=retrieval_prefixes(cfg),
            exclude_paths=excluded)
        retrieval_report = selection.report
        last_retrieval_report = retrieval_report
        known_paths = [
            str(hit.get("path")) for hit in retrieval_report.get("hits", [])
            if isinstance(hit, dict) and str(hit.get("path") or "")
            and str(hit.get("path")) not in excluded
        ][:cap]
        all_related_paths.update(known_paths)
        retrieval_context = [
            dict(hit) for hit in retrieval_report.get("hits", [])
            if isinstance(hit, dict) and str(hit.get("path") or "") in known_paths
        ]
        receipt_draft = make_generation_receipt_draft(
            index, cfg, skill=skill, stage=stage_name, notes=supplied,
            use_llm=use_llm, upstream_cards=upstream_cards,
            retrieval_context=retrieval_context, semantic=semantic,
            generator_contract=contract,
        )
        prior = lookup_generation_receipt(
            cfg, (skill, stage_name),
            fingerprint=receipt_draft["fingerprint_sha256"], use_llm=use_llm)
        if prior and prior.get("decision") in {
                "pending_review", "unchanged_inputs", "zero_output", "review_rejected"}:
            stages[kind] = _cached_stage(
                kind, prior, eligible=len(supplied), retrieval=retrieval_report,
                related=known_paths, extras=stage_extras)
            continue
        if generators[kind] is None:
            # Deferred imports: generator modules load their canonical schemas.
            from .case_generation import generate_cases
            from .concept_generation import generate_concepts
            from .topic_generation import generate_topic
            generators["concept"], generators["case"] = generate_concepts, generate_cases
            generators["topic"] = generate_topic
        base_provider = (providers or {}).get(kind)
        if base_provider is None:
            # Resolved at call time so tests can patch the default provider seam.
            base_provider = llm_module.call_chat_completion
        if kind == "topic":
            result = generators[kind](
                stage_extras["question"], cfg, supplied, known_paths=known_paths,
                analysis_mode="llm" if use_llm else "heuristic",
                call_provider=_counting(kind, base_provider), now=now)
        else:
            result = generators[kind](
                supplied, cfg, known_paths=known_paths,
                analysis_mode="llm" if use_llm else "heuristic",
                call_provider=_counting(kind, base_provider), now=now)
        stage = _stage_outcome(kind, result, eligible=len(supplied),
                               rejected=len(collected["rejected"]),
                               calls=provider_counts[kind])
        typed_update_outcomes: list[dict[str, Any]] = []
        stage["retrieval"] = retrieval_report
        stage["related_candidates"] = list(known_paths)
        stage.update(stage_extras)
        issues.extend(result.get("issues") or [])
        if result.get("state") in ("full", "stub"):
            if kind == "topic" and result.get("candidate") and result.get("page"):
                pairs = [(result["candidate"], result["page"])]
            elif kind == "topic":
                pairs = []
            else:
                pairs = list(zip(result.get("items", []), result.get("pages", [])))
            # Generation-input dependency set: EVERYTHING actually supplied to
            # the call (this kind's supplied originals + their upstream cards)
            # plus retrieved context — NOT just the cited subset.
            pins: dict[str, str] = {}
            for note in supplied:
                pins[note["rel"]] = note["source_sha256"]
            for rel in {card for n in supplied
                        for card in collected["source_note_paths"].get(n["rel"], [])}:
                card_sha = collected["upstream_hashes"].get(rel)
                if card_sha:
                    pins[rel] = card_sha
            for rel in known_paths:
                note = index.by_rel.get(rel)
                if note is not None:
                    pins[rel] = note.sha256
            typed_candidates: list[dict[str, Any]] = []
            for item, page_md in pairs:
                used = sorted(set(item.get("sources") or []))
                title = str(item.get("title") or "")
                target = f"{dirs[GEN_DIR_KEYS[kind]]}/{_readable_filename(title, kind)}.md"
                typed_candidates.append({
                    "skill": skill,
                    "operation": "create",
                    "rel_path": target,
                    "target": target,
                    "sources": used,
                    # Exact generator candidate, retained verbatim (no
                    # renormalization) for identity binding downstream.
                    "item": item,
                    "origin": {"source_paths": used, "operation": skill,
                               "promotion": "typed_card_pipeline", "run_id": run_id},
                    "content_sha256": sha256_text(page_md["content"]),
                    "content": page_md["content"],
                    "review_required": True,
                    "confidence": item.get("confidence") or "medium",
                    "retrieval_source_hashes": dict(sorted(pins.items())),
                    "analysis_mode": "llm",
                })
            if typed_candidates:
                from .typed_card_updates import prepare_typed_updates
                typed = prepare_typed_updates(index, cfg, typed_candidates)
                typed_update_outcomes = typed["outcomes"]
                stage["typed_update_outcomes"] = typed_update_outcomes
                stage["typed_update_issues"] = list(typed["issues"])
                issues.extend(typed["issues"])
                for outcome in typed_update_outcomes:
                    original = outcome.get("rel_path")
                    chosen = outcome.get("chosen_target")
                    if (outcome.get("outcome") == "create" and original and chosen
                            and original != chosen):
                        stage["collisions"].append(original)
                        issues.append(f"{kind} 候选目标已存在，已按身份后缀提出新建目标；"
                                      f"需人工确认身份：{chosen}")
                planned_pages.extend(typed["pages"])
                stage["planned_items"] = len(typed["pages"])
            else:
                stage["typed_update_outcomes"] = []
                stage["typed_update_issues"] = []

        # A derived receipt has one stage-level input outcome because this
        # discovery call is one bounded producer invocation.  The outcome still
        # records every updater target and its disposition, so a successful
        # generator cannot hide a blocked/partial typed update.
        target_paths = [
            str(outcome.get("chosen_target"))
            for outcome in typed_update_outcomes
            if outcome.get("chosen_target") and outcome.get("outcome") != "blocked"
        ]
        noop_targets = [
            str(outcome.get("chosen_target"))
            for outcome in typed_update_outcomes
            if outcome.get("outcome") == "noop" and outcome.get("chosen_target")
        ]
        noop_snapshots: dict[str, dict[str, Any]] = {}
        if noop_targets:
            from .knowledge_objects import identity_from_metadata
            for target in noop_targets:
                note = index.by_rel.get(target)
                if note is None:
                    continue
                try:
                    identity = identity_from_metadata(note.metadata)
                except (TypeError, ValueError):
                    identity = None
                if identity is None:
                    continue
                noop_snapshots[target] = {
                    "canonical_path": target,
                    "content_sha256": note.sha256,
                    "object_id": identity[0],
                    "revision": identity[1],
                    "verification": "updater_index",
                }
        blocked_update = any(item.get("outcome") == "blocked"
                             for item in typed_update_outcomes)
        if blocked_update:
            input_outcome = "blocked"
            complete = False
            updater_disposition = "blocked"
        elif result.get("state") == "zero":
            input_outcome = "zero"
            complete = True
            updater_disposition = "evaluated"
        elif result.get("state") == "full":
            input_outcome = "ok"
            complete = True
            updater_disposition = "noop" if noop_targets and not planned_pages else "evaluated"
        elif result.get("state") == "stub":
            input_outcome = "partial"
            complete = False
            updater_disposition = "evaluated"
        elif result.get("state") == "disabled":
            input_outcome = "blocked"
            complete = False
            updater_disposition = "blocked"
        else:
            input_outcome = "error"
            complete = False
            updater_disposition = "blocked"
        receipt_input = {
            "rel": f"derived:{kind}",
            "source_sha256": receipt_draft["fingerprint_sha256"],
            "outcome": input_outcome,
            "complete": complete,
            "required_targets": sorted(set(target_paths)),
            "targets": sorted(set(target_paths)),
            "reason": str(result.get("reason") or ""),
            "updater_disposition": updater_disposition,
            "updater_noop_targets": sorted(set(noop_targets)),
            "updater_target_snapshots": noop_snapshots,
        }
        completed_receipt = complete_generation_receipt_draft(
            receipt_draft,
            {"input_outcomes": [receipt_input], "issues": result.get("issues") or []},
        )
        generation_receipt_drafts.append(completed_receipt)
        if blocked_update:
            stage.update(state="blocked", reason="updater_blocked",
                         reason_detail="typed updater 在部分候选上 blocked；不将生成结果标记为可完成")
        stages[kind] = stage
    return {
        "planned_pages": planned_pages,
        "stages": stages,
        "issues": issues,
        "eligible_sources": len(eligible_notes),
        "rejected_sources": collected["rejected"],
        "topic_hints": collected["topic_hints"],
        "related_candidates": sorted(all_related_paths),
        "retrieval": last_retrieval_report,
        "generation_receipt_drafts": generation_receipt_drafts,
    }
