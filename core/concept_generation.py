"""M2 concept generator: evidence-qualified concept pages from verified snapshots.

Integration seam (the final integrator owns eligibility and passing data):

    generate_concepts(
        notes: list[dict],
        cfg: dict,
        *,
        known_paths: list[str] | None = None,
        analysis_mode: str = "llm",
        call_provider: Callable[[dict, str, dict], str] | None = None,
        now: str | None = None,
    ) -> dict

Input note dict (per note, all keys required — identical to core.topic_generation):

    rel            str  SAFE vault-relative source path
    title          str  human title of the source
    body           str  cleaned body used only for substance checks
    metadata       dict free-form provenance metadata
    source_text    str  FULL original UTF-8 decoded snapshot whose
                        utf-8 encoding reproduces the file's raw bytes
    source_sha256  str  sha256 hex of those ORIGINAL RAW BYTES

Return value (always a dict, never raises for input/protocol problems):

    state     "full" | "stub" | "zero" | "disabled" | "error"
    reason    str | None (required for zero/disabled/error)
    items     list[dict]  typed concept-page candidates (schema-validated);
                          one model call may yield zero or more distinct
                          concepts; exact duplicates are deduped
    pages     list[dict]  {"template", "rel_path_hint", "content"} parallel to
                          items, card_state persisted IN the frontmatter
    claims    list[dict]  flat compiled core.claims records across items
    analysis  dict        {"items": [...], "analysis_mode", "schema_version",
                          "generator_version", "source_hashes", "issues"}
    issues    list[str]

Key guarantees (shared discipline lives in core.evidence_cards):
- Single type truth: core/schemas/concept-page.schema.json is loaded and
  registered via core.card_contracts.register_card_schema; no Python copy.
- ONE bounded provider call (injectable; default core.llm.call_chat_completion),
  no hidden retries; secret screening pre and post; Jinja preflight first;
  oversized input rejected BEFORE the call, never truncated.
- A single source can qualify a concept; there is deliberately NO minimum
  source count. If the material holds no concept the model must return
  concept_found=false plus a reason — a legitimate zero; a missing/invalid
  viability flag is a malformed response and an error.
- Source-defined boundaries must cite a compiled judgment (exact statement);
  entries without compiled evidence are DOWNGRADED to labeled interpretation.
  Suggested interpretation is always labeled inference with supporting
  context; no invented ontology or causality is preserved as fact.
- Every freeform field is sanitized ([[...]] rendered inert); related links
  only to known_paths; everything else stays pending bare text.
- A candidate with zero compiled claims is dropped (error if none survive):
  no generic-summary substitute for missing evidence.
- card_state {"version": 1, "type": "concept-page", "claims": [...],
  "analysis": {...}} is written into the rendered frontmatter and reloads via
  core.claims.read_claims / validate_claims against the same raw snapshots.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .card_contracts import validate_card_item
from .claims import render_claims
from .evidence_cards import (
    EvidenceCardError,
    EVIDENCE_CARD_STATE_VERSION,
    absorb_claims,
    base_page_context,
    bounded_call,
    claims_by_statement,
    compile_model_claims,
    default_provider,
    load_owned_schema,
    normalize_provenance_map,
    patch_card_state,
    resolve_claim_refs,
    sanitize_freeform,
    split_links,
)
from .jinja_renderer import render_template

CONCEPT_SCHEMA_VERSION = "concept-1"
CONCEPT_GENERATOR_VERSION = "pks-concept-m2"
CONCEPT_FULL_STATES = ("growing", "draft")
CONCEPT_REVIEW_STATES = ("manual_review", "needs_context")
TEMPLATE_NAME = "concept_page.j2"
CONFIG_SECTION = "concept_generation"
VIABILITY_KEY = "concept_found"
CARD_STATE_VERSION = EVIDENCE_CARD_STATE_VERSION

_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "concept-page.schema.json"
load_owned_schema(_SCHEMA_PATH)

_SYSTEM_PROMPT = (
    "你是个人知识库的概念提炼器。只依据提供的来源作答：\n"
    "1. 判断来源中是否包含独立有用的概念（有明确定义、可与其他内容区分的术语或机制）；"
    "没有概念时置 concept_found=false 并给出 reason，不要为凑数编造概念。\n"
    "2. 每个概念必须有 definition_claim：精确引用一条你给出的 judgment 原句。"
    "定义、边界、结果等被引用字段的权威文字一律使用该 judgment 的原句——"
    "不要另写一份平行的定义文本；解释性的改写只能放进 explanation。\n"
    "3. source_defined_boundary 每条只给 evidence_claim（精确引用一条你的 judgment "
    "原句）；引用无法编译的边界会被整条丢弃。来源没有说清的边界可以放进 "
    "suggested_interpretation，每条必须以 supporting_claim 精确引用一条 judgment "
    "作为支撑语境——解读是推断，不得发明本体论或因果性。\n"
    "4. aliases 只写来源中实际出现的别名；不确定就留空。\n"
    "5. 每条 judgment 的 evidence 必须含来源 path 的逐字 quote、relation"
    "（supports 或 contradicts）与必要 start_line；片段必须与来源原文完全一致。\n"
    "6. related 只能引用提供的 known_paths 中真实存在的路径；其余目标写成 pending_paths "
    "裸文本。所有自由文本中不得输出 [[维基链接]] 语法。\n"
    "可以给出多个彼此不同的概念，也可以只给一个；输出严格 JSON 对象。"
    "不要输出任何密钥、token 或凭据内容。"
)


def _user_payload(documents: list[dict[str, str]], known: list[str],
                  upstream: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": "concept_extraction",
        "documents": documents,
        "known_paths": known,
        "output_contract": {
            "concept_found": "boolean",
            "reason": "string, required when concept_found is false",
            "concepts": [{
                "name": "string, non-empty",
                "aliases": ["string"],
                "definition_claim": "exact statement string of one of your judgments; REQUIRED; its statement IS the definition",
                "explanation": "string, model organization/paraphrase, clearly separated from the source-defined definition",
                "confidence": "low|medium|high",
                "source_defined_boundary": [{
                    "evidence_claim": "exact statement string of one of your judgments; REQUIRED; its statement IS the boundary text"}],
                "suggested_interpretation": [{
                    "text": "string, explicitly interpretive",
                    "supporting_claim": "exact statement string of one of your judgments; REQUIRED",
                    "supporting_context": "string"}],
                "judgments": [{
                    "statement": "string", "kind": "fact|inference",
                    "confidence": "low|medium|high",
                    "evidence": [{"source": "string from documents.path",
                                  "quote": "exact verbatim fragment from that source",
                                  "relation": "supports or contradicts",
                                  "start_line": "int, required when the quote occurs more than once"}],
                }],
                "related": ["string, only from known_paths"],
                "pending_paths": ["string"],
            }],
            "provenance_map": [{"rel": "string from documents.path",
                                "provenance": "string, non-empty",
                                "limitations": ["string"]}],
            "shared_provenance": ["string; note any sources sharing origin"],
        },
    }
    if upstream:
        payload["upstream_source_analysis"] = upstream
    return payload


def _preflight() -> None:
    render_template(TEMPLATE_NAME, _skeleton_context())


def _skeleton_context() -> dict[str, Any]:
    skeleton = {
        "title": "preflight", "type": "concept-page", "status": "manual_review",
        "stage": "needs_context", "sources": ["preflight"], "related": [],
        "tags": ["concept-page"], "confidence": "low", "review_required": True,
        "origin": {}, "schema_version": CONCEPT_SCHEMA_VERSION,
        "generator_version": CONCEPT_GENERATOR_VERSION, "analysis_mode": "unknown",
        "coverage": "unknown", "source_hashes": {}, "quality_flags": [],
        "concept_name": "preflight", "definition": "", "explanation": "",
        "aliases": [], "source_defined_boundary": [], "suggested_interpretation": [],
        "provenance_map": [], "shared_provenance": [], "claims_section": "",
        "pending_links": [], "generation_issues": [], "limited_stub": False,
        "limited_reason": "", "manual_review": [],
    }
    return _page_context(skeleton, [], [], skeleton, None)


def _page_context(candidate: dict[str, Any], claims: list, issues: list[str],
                  _unused: Any = None, now: str | None = None) -> dict[str, Any]:
    # candidate doubles as the context when called from _skeleton_context.
    ctx = base_page_context(candidate, now)
    # Human-readable ordinal evidence references (view layer only): the
    # ordinals follow the existing claims render order; machine claim IDs
    # stay exclusively in card_state frontmatter.
    evidence_refs = {c.claim_id: f"证据 {i}" for i, c in enumerate(claims, 1)}

    def _refs(ids: list[str]) -> str:
        return "、".join(evidence_refs.get(i, "证据 ?") for i in ids)

    ctx.update({
        "tags": candidate["tags"],
        "concept_name": candidate["concept_name"],
        "definition": candidate["definition"],
        # role label derived from the ACCEPTED claim's kind (no schema change)
        "definition_inference": any(
            c.kind == "inference" and c.statement == candidate["definition"]
            for c in claims),
        "explanation": candidate["explanation"],
        "aliases": candidate["aliases"],
        "source_defined_boundary": [{"statement": b["statement"],
                                     "evidence_refs": _refs(b["claim_ids"])}
                                    for b in candidate["source_defined_boundary"]],
        "suggested_interpretation": [{**item, "evidence_refs": _refs(item["claim_ids"])}
                                     for item in candidate["suggested_interpretation"]],
        "provenance_map": candidate["provenance_map"],
        "shared_provenance": candidate["shared_provenance"],
        "claims_section": render_claims(claims) if claims else "（无已编译判断）",
        "pending_links": candidate["pending_links"],
        "generation_issues": issues,
        "limited_stub": candidate["status"] == "manual_review",
        "limited_reason": candidate["manual_review"][0] if candidate["manual_review"] else "",
    })
    return ctx


def _normalize_concept(entry: Any, index: int, verified: list[dict[str, Any]],
                       note_rels: set[str], known: list[str], issues: list[str]):
    """Return (candidate dict or None, claims, usable_sources)."""
    where = f"concepts[{index}]"
    if not isinstance(entry, dict):
        issues.append(f"{where} 不是对象，已丢弃")
        return None, [], set()
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(f"{where} 缺少合法 name，已丢弃")
        return None, [], set()
    name = sanitize_freeform(name.strip(), issues, f"{where}.name")

    claims, usable = compile_model_claims(entry.get("judgments"), verified,
                                          issues, where)
    if not claims:
        issues.append(f"{where} 没有任何判断通过证据编译，已丢弃（不以泛泛摘要替代证据）")
        return None, [], set()
    by_statement = claims_by_statement(claims)

    # definition_claim stays REQUIRED: without an exact compiled claim
    # reference the candidate is dropped — a free definition string backed by
    # UNRELATED judgments is not accepted.
    raw_def_claim = entry.get("definition_claim")
    def_claim_ids = resolve_claim_refs([raw_def_claim], by_statement, issues,
                                       f"{where}.definition_claim")
    if not def_claim_ids:
        issues.append(f"{where} 缺少可编译的 definition_claim，已丢弃"
                      "（定义必须绑定已编译判断，不接受与判断无关的自由定义）")
        return None, [], set()
    def_claim = by_statement[raw_def_claim]

    # SINGLE authoritative text: the definition IS the referenced compiled
    # claim's statement. Any parallel model "definition" string is ignored
    # with a diagnostic — never retained as a contradictory duplicate
    # (final-review decision; closes the astra-M2-probe-after counterexample).
    if isinstance(entry.get("definition"), str) and entry["definition"].strip() \
            and entry["definition"].strip() != def_claim.statement:
        issues.append(f"{where}.definition 与 definition_claim 指向的判断原文不一致，"
                      "已忽略模型文本；定义以引用判断原句为唯一权威文字")
    definition = def_claim.statement
    # Role preservation (M2 late review): the definition may legitimately be a
    # model abstraction. An inference-kind definition stays rendered but is
    # VISIBLY labeled "建议性定义（模型推断）" (view layer derives the label
    # from the accepted claim's kind); it is never presented as source text.
    definition_inference = def_claim.kind == "inference"
    explanation = sanitize_freeform(
        entry.get("explanation") if isinstance(entry.get("explanation"), str) else "",
        issues, f"{where}.explanation").strip()

    aliases = sanitize_freeform(
        [a for a in (entry.get("aliases") if isinstance(entry.get("aliases"), list) else [])
         if isinstance(a, str) and a.strip()], issues, f"{where}.aliases")

    # Source-defined boundary entries: the boundary text IS the referenced
    # compiled claim's statement. Entries whose evidence reference does not
    # compile are DROPPED with a diagnostic; a model-side "text" differing
    # from the statement is ignored, never retained (final-review decision).
    source_boundary: list[dict[str, Any]] = []
    interpretation: list[dict[str, Any]] = []
    raw_boundary = entry.get("source_defined_boundary")
    for i, item in enumerate(raw_boundary if isinstance(raw_boundary, list) else []):
        if not isinstance(item, dict):
            issues.append(f"{where}.source_defined_boundary[{i}] 不是对象，已丢弃")
            continue
        claim_ids = resolve_claim_refs([item.get("evidence_claim")], by_statement,
                                       issues, f"{where}.source_defined_boundary[{i}]")
        if not claim_ids:
            issues.append(
                f"{where}.source_defined_boundary[{i}] 的证据引用未通过编译，"
                "整条丢弃（不保留为无证据解读）")
            continue
        if isinstance(item.get("text"), str) and item["text"].strip() \
                and item["text"].strip() != by_statement[item["evidence_claim"]].statement:
            issues.append(f"{where}.source_defined_boundary[{i}].text 与引用判断原文"
                          "不一致，已忽略；边界文字以判断原句为唯一权威")
        bound = by_statement[item["evidence_claim"]]
        # Source-defined boundary requires a FACT-kind (attributed source
        # claim — never independently verified). An inference reference is
        # dropped with an explicit issue, never silently relabeled as source
        # text (M2 late review).
        if bound.kind != "fact":
            issues.append(f"{where}.source_defined_boundary[{i}] 引用了推断判断，"
                          "不能作为来源定义边界，整条丢弃（推断不得冒充来源原话）")
            continue
        source_boundary.append({
            "statement": bound.statement,
            "claim_ids": claim_ids,
        })
    raw_interp = entry.get("suggested_interpretation")
    for i, item in enumerate(raw_interp if isinstance(raw_interp, list) else []):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) \
                or not item["text"].strip():
            issues.append(f"{where}.suggested_interpretation[{i}] 缺少合法 text，已丢弃")
            continue
        support_ids = resolve_claim_refs([item.get("supporting_claim")], by_statement,
                                         issues, f"{where}.suggested_interpretation[{i}]")
        if not support_ids:
            issues.append(
                f"{where}.suggested_interpretation[{i}] 缺少可编译的 supporting_claim，"
                "已丢弃（推断必须有已编译的支撑语境，不接受“证据缺失”之类的文字自辩）")
            continue
        interpretation.append({
            # program-owned explicit inference marker on every entry
            "text": sanitize_freeform(item["text"], issues,
                                      f"{where}.suggested_interpretation[{i}].text"),
            "supporting_claim": item.get("supporting_claim"),
            "supporting_context": sanitize_freeform(
                item.get("supporting_context")
                if isinstance(item.get("supporting_context"), str) else "",
                issues, f"{where}.suggested_interpretation[{i}].supporting_context"),
            "claim_ids": support_ids,
            "inference": True,
        })

    related, pending = split_links(entry.get("related"), entry.get("pending_paths"),
                                   known, note_rels, issues)
    confidence = entry.get("confidence") if entry.get("confidence") in ("high", "medium", "low") \
        else "low"
    return {
        "name": name, "definition": definition,
        "definition_claim": raw_def_claim,
        "explanation": explanation,
        "aliases": aliases, "source_boundary": source_boundary,
        "interpretation": interpretation, "related": related, "pending": pending,
        "confidence": confidence, "claims": claims, "usable": usable,
    }, claims, usable


def _dedupe_concepts(norms: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    """Exact identity (name + definition) dedupe; ambiguous synonym conflicts
    (same alias, different definitions) are kept and flagged for review only."""
    kept: list[dict[str, Any]] = []
    by_identity: dict[tuple[str, str], int] = {}
    alias_owners: dict[str, tuple[str, str]] = {}
    for norm in norms:
        key = (norm["name"].casefold(), norm["definition"])
        if key in by_identity:
            kept_idx = by_identity[key]
            existing = kept[kept_idx]
            before = {(c.statement, c.kind) for c in existing["claims"]}
            absorb_claims(existing["claims"], norm["claims"], issues,
                          f"概念 {norm['name']}")
            # recompute the unioned usable source set after evidence merging
            existing["usable"] = {e.source for c in existing["claims"]
                                  for e in c.evidence}
            if {(c.statement, c.kind) for c in existing["claims"]} == before:
                issues.append(f"概念 {norm['name']} 与已有候选完全相同，已去重")
            continue
        by_identity[key] = len(kept)
        kept.append(norm)
        alias_names = [norm["name"].casefold()] + [a.casefold() for a in norm["aliases"]]
        for alias in alias_names:
            owner = alias_owners.get(alias)
            if owner is not None and owner != key:
                issues.append(
                    f"别名“{alias}”同时对应不同定义的概念（疑似同义词冲突），"
                    "仅标记人工复核，不做合并裁决")
            else:
                alias_owners.setdefault(alias, key)
    return kept


def _candidate_from_norm(norm: dict[str, Any], verified: list[dict[str, Any]],
                         note_rels: set[str], provenance_map: list[dict[str, Any]],
                         shared_flags: list[str], coverage: str,
                         issues: list[str]) -> dict[str, Any]:
    usable_sources = sorted(norm["usable"] & note_rels)
    sources = usable_sources or sorted(note_rels)
    confidence = norm["confidence"]
    if confidence == "high" and shared_flags:
        confidence = "medium"
        issues.append("存在共享来源披露，置信度上限降为 medium")
    gaps: list[str] = []
    if not norm["explanation"]:
        gaps.append("模型未给出非空的概念解释")
    if not norm["source_boundary"]:
        # near-concept boundary from the source is a MINIMUM requirement:
        # absence is an honestly limited page, never a full concept
        gaps.append("缺少来源定义的边界证据（近似概念边界），不能作为完整概念")
    is_full = not gaps
    status, stage = CONCEPT_FULL_STATES if is_full else CONCEPT_REVIEW_STATES
    limited_reason = "；".join(gaps)
    if not is_full:
        issues.append(f"受限概念页（不构成完整概念基线）：{limited_reason}")
    title = norm["name"]
    candidate: dict[str, Any] = {
        "title": title,
        "type": "concept-page",
        "status": status,
        "stage": stage,
        "sources": sources,
        "summary": norm["definition"],
        "confidence": confidence,
        "review_required": True,  # program-owned: candidates always need review
        "schema_version": CONCEPT_SCHEMA_VERSION,
        "generator_version": CONCEPT_GENERATOR_VERSION,
        "analysis_mode": "llm",
        "source_hashes": {n["rel"]: n["source_sha256"] for n in verified
                          if n["rel"] in set(sources)},
        "coverage": coverage,
        "related": norm["related"],
        "pending_links": norm["pending"],
        "manual_review": ([] if is_full else [limited_reason]),
        "quality_flags": [f"{CONFIG_SECTION}_issues"] if issues else [],
        "tags": ["concept-page"],
        "origin": {"concept_name": norm["name"], "source_paths": sources},
        "concept_name": norm["name"],
        "definition": norm["definition"],
        "definition_claim": norm["definition_claim"],
        "explanation": norm["explanation"],
        "aliases": norm["aliases"],
        "source_defined_boundary": norm["source_boundary"],
        "suggested_interpretation": norm["interpretation"],
        "provenance_map": provenance_map,
        "shared_provenance": shared_flags,
        "claims": [c.to_dict() for c in norm["claims"]],
    }
    return candidate


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate_concepts(
    notes: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    known_paths: list[str] | None = None,
    analysis_mode: str = "llm",
    call_provider: Callable[[dict[str, Any], str, dict[str, Any]], str] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Run one bounded concept extraction. See module docstring for the exact
    input/output contract."""
    provider = call_provider or default_provider()
    ctx, result = bounded_call(
        notes=notes, cfg=cfg, section=CONFIG_SECTION, system_prompt=_SYSTEM_PROMPT,
        payload_builder=lambda verified, known: _user_payload(
            [{"path": n["rel"], "title": n["title"], "content": n["source_text"],
              "sha256": n["source_sha256"]} for n in verified], known,
            [{"rel": n["rel"], **n["upstream"]} for n in verified if n["upstream"]]),
        preflight=_preflight, provider=provider, viability_key=VIABILITY_KEY,
        analysis_mode=analysis_mode, known_paths=known_paths,
    )
    if ctx is None:
        return result
    data, verified, issues = ctx["data"], ctx["verified"], ctx["issues"]
    known, note_rels, settings = ctx["known"], ctx["note_rels"], ctx["settings"]

    raw_concepts = data.get("concepts")
    if not isinstance(raw_concepts, list) or not raw_concepts:
        result["state"] = "error"
        result["reason"] = ("模型声称发现概念但未给出合法的 concepts 数组；"
                            "无法区分真实产出与格式错误，拒绝生成")
        result["issues"] = issues
        return result

    provenance_map = normalize_provenance_map(data.get("provenance_map"),
                                              verified, issues)
    shared_flags = _shared_provenance(verified, data.get("shared_provenance"), issues)
    all_read = len(verified) == len(notes) and all(n["body"].strip() for n in verified)
    coverage = "full" if all_read else "partial"
    if not all_read:
        issues.append("范围受限：部分输入未通过校验或无实质内容，coverage=partial")

    norms: list[dict[str, Any]] = []
    for i, entry in enumerate(raw_concepts):
        norm, _claims, _usable = _normalize_concept(entry, i, verified, note_rels,
                                                    known, issues)
        if norm is not None:
            norms.append(norm)
    norms = _dedupe_concepts(norms, issues)
    if not norms:
        result["state"] = "error"
        result["reason"] = ("没有任何概念候选同时具备合法定义与已编译判断；"
                            "拒绝以无证据摘要生成概念页")
        result["issues"] = issues
        return result

    items: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    analyses: list[dict[str, Any]] = []
    flat_claims: list[dict[str, Any]] = []
    limited: list[str] = []
    for norm in norms:
        candidate = _candidate_from_norm(norm, verified, note_rels, provenance_map,
                                         shared_flags, coverage, issues)
        schema_issues = validate_card_item(candidate, "concept-page")
        if schema_issues:
            issues.append(f"概念 {candidate['concept_name']} 未通过 concept-page 契约校验，"
                          "已丢弃：" + "；".join(schema_issues[:5]))
            continue
        analysis = {
            "concept_name": candidate["concept_name"],
            "aliases": candidate["aliases"],
            "usable_sources": candidate["sources"],
            "source_defined_boundary_count": len(candidate["source_defined_boundary"]),
            "suggested_interpretation_count": len(candidate["suggested_interpretation"]),
            "outcome": "full" if candidate["status"] == "growing" else "stub",
            "limited_reason": candidate["manual_review"][0] if candidate["manual_review"] else "",
            "coverage": coverage,
            "analysis_mode": "llm",
            "schema_version": CONCEPT_SCHEMA_VERSION,
            "generator_version": CONCEPT_GENERATOR_VERSION,
            "source_hashes": candidate["source_hashes"],
            "issues": issues,
        }
        card_state = {
            "version": CARD_STATE_VERSION,
            "type": "concept-page",
            "claims": candidate["claims"],
            "analysis": analysis,
        }
        try:
            content_md = patch_card_state(
                render_template(TEMPLATE_NAME,
                                _page_context(candidate, norm["claims"], issues, now=now)),
                card_state, EvidenceCardError)
        except Exception as exc:
            from .content_safety import safe_error_message
            result["state"] = "error"
            result["reason"] = f"页面渲染或持久化失败：{safe_error_message(exc)}"
            result["issues"] = issues
            return result
        if candidate["manual_review"]:
            limited.append(candidate["manual_review"][0])
        items.append(candidate)
        pages.append({
            "template": TEMPLATE_NAME,
            # Path/identity assignment stays with the plan boundary; hint only.
            "rel_path_hint": "wiki/concepts/",
            "content": content_md,
        })
        analyses.append(analysis)
        flat_claims.extend(candidate["claims"])

    if not items:
        result["state"] = "error"
        result["reason"] = "所有概念候选均未通过契约校验，未产出任何页面"
        result["issues"] = issues
        return result

    result.update({
        "state": "full" if any(a["outcome"] == "full" for a in analyses) else "stub",
        "reason": "；".join(limited) or None,
        "items": items,
        "pages": pages,
        "claims": flat_claims,
        "analysis": {
            "items": analyses,
            "analysis_mode": "llm",
            "schema_version": CONCEPT_SCHEMA_VERSION,
            "generator_version": CONCEPT_GENERATOR_VERSION,
            "source_hashes": {n["rel"]: n["source_sha256"] for n in verified},
            "coverage": coverage,
            "issues": issues,
        },
        "issues": issues,
    })
    return result


def _shared_provenance(notes: list[dict[str, Any]], model_flags: Any,
                       issues: list[str]) -> list[str]:
    """Shared-origin disclosure; byte-identical copies are flagged explicitly."""
    flags: list[str] = sanitize_freeform(
        [f for f in (model_flags if isinstance(model_flags, list) else [])
         if isinstance(f, str) and f], issues, "shared_provenance")
    if flags:
        issues.append("存在共享来源/背景说明，已披露；相关来源不计为相互独立的佐证")
    by_hash: dict[str, list[str]] = {}
    for note in notes:
        by_hash.setdefault(note["source_sha256"], []).append(note["rel"])
    for sha, rels in by_hash.items():
        if len(rels) > 1:
            flags.append(
                f"以下来源的原始字节完全一致，按同一来源计：{('、'.join(sorted(rels)))}"
                f"（sha256:{sha[:12]}…）")
            issues.append("检测到字节级重复来源，不重复计入来源数")
    return flags
