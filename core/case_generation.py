"""M2 case generator: evidence-qualified case-story cards from verified snapshots.

Integration seam (the final integrator owns eligibility and passing data):

    generate_cases(
        notes: list[dict],
        cfg: dict,
        *,
        known_paths: list[str] | None = None,
        analysis_mode: str = "llm",
        call_provider: Callable[[dict, str, dict], str] | None = None,
        now: str | None = None,
    ) -> dict

Input note dict (per note, all keys required — identical to core.topic_generation):
rel / title / body / metadata / source_text / source_sha256 (full raw snapshot
whose utf-8 encoding reproduces the file's original bytes, plus that raw-byte
sha256).

Return value (always a dict, never raises for input/protocol problems):

    state     "full" | "stub" | "zero" | "disabled" | "error"
    reason    str | None (required for zero/disabled/error)
    items     list[dict]  typed case-story candidates (schema-validated)
    pages     list[dict]  {"template", "rel_path_hint", "content"} parallel to
                          items, card_state persisted IN the frontmatter
    claims    list[dict]  flat compiled core.claims records across items
    analysis  dict        {"items": [...], "analysis_mode", "schema_version",
                          "generator_version", "source_hashes", "coverage",
                          "issues"}
    issues    list[str]

Key guarantees (shared discipline lives in core.evidence_cards):
- Single type truth: core/schemas/case-story.schema.json loaded and registered
  via core.card_contracts.register_card_schema; no Python copy.
- ONE bounded provider call (injectable; default core.llm.call_chat_completion),
  no hidden retries; secret screening pre and post; Jinja preflight first;
  oversized input rejected BEFORE the call, never truncated.
- Project-level vs mechanism-level cards are distinguished via the model's
  card_level; an entry without a valid level is dropped, never silently
  re-typed. One candidate is produced per case; the SAME story under two
  titles (exact identity: normalized title + identical claim-statement set)
  is deduped; a same-title story with DIFFERENT claims is ambiguous and kept
  with a manual-review issue — never auto-merged.
- Every material number/claimed outcome must be attributed: each result figure
  cites an exact compiled judgment statement. result.source_asserted is
  PROGRAM-OWNED true — source assertions are never presented as independent
  verification. Mechanism inference is kept in its own labeled field and is
  never merged into observed results (no unsupported causal success claim).
- Applicability is concrete conditions + uncertainties; there is deliberately
  NO universal multi-source threshold — one source can qualify a case, and
  insufficient evidence yields manual_review stubs or a legitimate zero, not
  a fabricated card. No second card is created just to meet a count.
- All freeform text sanitized ([[...]] inert); links only to known_paths;
  paths reject traversal/absolute/backslash/control syntax; reused existing
  validators (core.claims, content_safety) are not bypassed.
- card_state {"version": 1, "type": "case-story", "claims": [...],
  "analysis": {...}} persists in the rendered frontmatter and reloads via
  core.claims.read_claims / validate_claims against the same raw snapshots.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .card_contracts import validate_card_item
from .claims import render_claims
from .content_safety import safe_error_message
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

CASE_SCHEMA_VERSION = "case-1"
CASE_GENERATOR_VERSION = "pks-case-m2"
CASE_FULL_STATES = ("growing", "draft")
CASE_REVIEW_STATES = ("manual_review", "needs_context")
TEMPLATE_NAME = "case_story.j2"
CONFIG_SECTION = "case_generation"
VIABILITY_KEY = "case_found"
CARD_STATE_VERSION = EVIDENCE_CARD_STATE_VERSION

_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "case-story.schema.json"
load_owned_schema(_SCHEMA_PATH)

_SYSTEM_PROMPT = (
    "你是个人知识库的案例提炼器。只依据提供的来源作答：\n"
    "1. 判断来源中是否包含具体案例（有背景、行动或结果的具体事件，不是抽象观点）；"
    "没有案例时置 case_found=false 并给出 reason，不要把抽象观点包装成案例。\n"
    "2. card_level 区分项目级（project：一次具体实践）与机制级（mechanism：可复用机制"
    "的记录或复用）；无法判断时不要随意填。\n"
    "3. context/action 分别对应背景、做了什么；result.figures 列出结果性陈述（重要数字"
    "或定性观察结果均可，不要求是数字），每项只给 claim（精确引用一条你的 judgment "
    "原句）；结果性陈述的权威文字就是该 judgment 原句，不要另写平行文本。结果都是来源"
    "断言，一律不得当作独立验证的事实。\n"
    "4. reusable_mechanism_claim 精确引用一条 judgment（来源明确陈述的机制用 fact 类"
    "判断）；mechanism_inference_claim 精确引用一条 kind=inference 的 judgment（机制为何"
    "有效/无效的归因推断，包括来源人物的归因）。两者的权威文字都是所引 judgment 原句；"
    "引用不合法会被整条丢弃，不要为填空编造机制。\n"
    "5. applicability.conditions 每条只给 claim（精确引用一条你的 judgment 原句）；"
    "引用不合法的条件会被整条丢弃。applicability.uncertainties 写来源承认的不确定性"
    "或由此提出的研究问题（会标注为待研究问题，不是来源事实）。没有依据的条件不要编。\n"
    "6. 每条 judgment 的 evidence 必须含来源 path 的逐字 quote、relation"
    "（supports 或 contradicts）与必要 start_line；片段必须与来源原文完全一致。\n"
    "7. related 只能引用提供的 known_paths 中真实存在的路径；其余目标写成 pending_paths "
    "裸文本。所有自由文本中不得输出 [[维基链接]] 语法。\n"
    "同一个案例只输出一个候选，不要用不同标题重复写同一个故事；"
    "输出严格 JSON 对象。不要输出任何密钥、token 或凭据内容。"
)


def _user_payload(documents: list[dict[str, str]], known: list[str],
                  upstream: list[dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": "case_extraction",
        "documents": documents,
        "known_paths": known,
        "output_contract": {
            "case_found": "boolean",
            "reason": "string, required when case_found is false",
            "cases": [{
                "title": "string, non-empty",
                "card_level": "project|mechanism",
                "confidence": "low|medium|high",
                "context": "string, attributed model summary of the background",
                "action": "string, attributed model summary of what was done",
                "result": {
                    "figures": [{
                        "claim": "exact statement string of one of your judgments; its statement IS the outcome text"}],
                },
                "reusable_mechanism_claim": "exact statement string of a fact-kind judgment; REQUIRED for a reusable mechanism",
                "mechanism_inference_claim": "exact statement string of an inference-kind judgment",
                "applicability": {
                    "conditions": [{"claim": "exact statement string of one of your judgments"}],
                    "uncertainties": ["string, open question / uncertainty, labeled as proposed"]},
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
                                "limitations": ["string, ADDITIONAL limitations only — "
                                                "只输出本次组合阶段新发现、且 "
                                                "upstream_source_analysis 中未列出的限制；"
                                                "不得复制、改写或概括上游已列出的任何限制"
                                                "（系统会自动继承全部上游限制，无需你重复）"]}],
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
        "title": "preflight", "type": "case-story", "status": "manual_review",
        "stage": "needs_context", "sources": ["preflight"], "related": [],
        "tags": ["case-story"], "confidence": "low", "review_required": True,
        "origin": {}, "schema_version": CASE_SCHEMA_VERSION,
        "generator_version": CASE_GENERATOR_VERSION, "analysis_mode": "unknown",
        "coverage": "unknown", "source_hashes": {}, "quality_flags": [],
        "card_level": "project", "context": "", "action": "",
        "result": {"summary": "", "source_asserted": True, "figures": []},
        "applicability": {"conditions": [], "uncertainties": []},
        "reusable_mechanism": "", "reusable_mechanism_claim_ids": [],
        "mechanism_inference": "", "mechanism_inference_claim_ids": [],
        "provenance_map": [], "shared_provenance": [], "claims_section": "",
        "pending_links": [], "generation_issues": [], "limited_stub": False,
        "limited_reason": "", "manual_review": [],
    }
    return _page_context(skeleton, [], [], None)


def _page_context(candidate: dict[str, Any], claims: list, issues: list[str],
                  now: str | None = None) -> dict[str, Any]:
    ctx = base_page_context(candidate, now)
    # Human-readable ordinal evidence references (view layer only): the
    # ordinals follow the existing claims render order; machine claim IDs
    # stay exclusively in card_state frontmatter.
    evidence_refs = {c.claim_id: f"证据 {i}" for i, c in enumerate(claims, 1)}
    # role labels derived from the ACCEPTED claims' kinds (no schema change)
    claim_kinds = {c.statement: c.kind for c in claims}

    def _refs(ids: list[str]) -> str:
        return "、".join(evidence_refs.get(i, "证据 ?") for i in ids)

    ctx.update({
        "tags": candidate["tags"],
        "card_level": candidate["card_level"],
        "context": candidate["context"],
        "action": candidate["action"],
        "result_summary": candidate["result"]["summary"],
        "result_figures": [{"statement": f["statement"],
                            "evidence_refs": _refs(f["claim_ids"])}
                           for f in candidate["result"]["figures"]],
        "reusable_mechanism": candidate["reusable_mechanism"],
        "reusable_mechanism_refs": _refs(candidate["reusable_mechanism_claim_ids"]),
        "mechanism_inference": candidate["mechanism_inference"],
        "mechanism_inference_refs": _refs(candidate["mechanism_inference_claim_ids"]),
        "applicability_conditions": [{"statement": c["statement"],
                                      "evidence_refs": _refs(c["claim_ids"]),
                                      "inference": claim_kinds.get(c["statement"]) == "inference"}
                                     for c in candidate["applicability"]["conditions"]],
        "applicability_uncertainties": candidate["applicability"]["uncertainties"],
        "provenance_map": candidate["provenance_map"],
        "shared_provenance": candidate["shared_provenance"],
        "claims_section": render_claims(claims) if claims else "（无已编译判断）",
        "pending_links": candidate["pending_links"],
        "generation_issues": issues,
        "limited_stub": candidate["status"] == "manual_review",
        "limited_reason": candidate["manual_review"][0] if candidate["manual_review"] else "",
    })
    return ctx


def _normalize_case(entry: Any, index: int, verified: list[dict[str, Any]],
                    note_rels: set[str], known: list[str], issues: list[str]):
    """Return (normalized dict or None, claims, usable_sources)."""
    where = f"cases[{index}]"
    if not isinstance(entry, dict):
        issues.append(f"{where} 不是对象，已丢弃")
        return None, [], set()
    title = entry.get("title")
    if not isinstance(title, str) or not title.strip():
        issues.append(f"{where} 缺少合法 title，已丢弃")
        return None, [], set()
    title = sanitize_freeform(title.strip(), issues, f"{where}.title")
    card_level = entry.get("card_level")
    if card_level not in ("project", "mechanism"):
        issues.append(f"{where} 缺少合法 card_level（project|mechanism），已丢弃；"
                      "不猜测层级")
        return None, [], set()

    claims, usable = compile_model_claims(entry.get("judgments"), verified,
                                          issues, where)
    if not claims:
        issues.append(f"{where} 没有任何判断通过证据编译，已丢弃（不以无证据叙述替代证据）")
        return None, [], set()
    by_statement = claims_by_statement(claims)

    context = sanitize_freeform(
        entry.get("context") if isinstance(entry.get("context"), str) else "",
        issues, f"{where}.context").strip()
    action = sanitize_freeform(
        entry.get("action") if isinstance(entry.get("action"), str) else "",
        issues, f"{where}.action").strip()
    # There is deliberately NO free model outcome text: each figure's
    # authoritative text IS the referenced compiled claim's statement. A
    # model-side description is ignored with a diagnostic, never retained
    # (final-review decision; closes the astra-M2-bound-text-probe hole).
    figures: list[dict[str, Any]] = []
    raw_result = entry.get("result")
    if isinstance(raw_result, dict):
        raw_figures = raw_result.get("figures")
        if raw_result.get("summary"):
            issues.append(f"{where}.result.summary 不是合法输出字段，已丢弃；"
                          "结果叙述只能由归因的结果陈述合成")
        for i, item in enumerate(raw_figures if isinstance(raw_figures, list) else []):
            if not isinstance(item, dict):
                issues.append(f"{where}.result.figures[{i}] 不是对象，已丢弃")
                continue
            claim_ids = resolve_claim_refs([item.get("claim")], by_statement, issues,
                                           f"{where}.result.figures[{i}]")
            if not claim_ids:
                issues.append(f"{where}.result.figures[{i}] 未归因到任何已编译判断，"
                              "整条丢弃（结果陈述必须逐项归因）")
                continue
            bound = by_statement[item["claim"]]
            # Results under 来源断言 require FACT-kind references; an
            # inference ref is rejected with a diagnostic — never promoted to
            # a source-reported outcome (M2 late review).
            if bound.kind != "fact":
                issues.append(f"{where}.result.figures[{i}] 引用了推断判断，"
                              "不能作为来源断言的结果，整条丢弃（推断不得冒充来源结果）")
                continue
            statement = bound.statement
            if isinstance(item.get("description"), str) and item["description"].strip() \
                    and item["description"].strip() != statement:
                issues.append(f"{where}.result.figures[{i}].description 与引用判断原文"
                              "不一致，已忽略；结果文字以判断原句为唯一权威")
            figures.append({"statement": statement, "claim_ids": claim_ids})
    else:
        issues.append(f"{where} 缺少合法 result 对象")

    # Mechanism/applicability binding (final-review decision + M2 late
    # review): the mechanism and condition authoritative texts are referenced
    # compiled claims. Role preservation: the source-stated reusable
    # mechanism REQUIRES fact-kind; an inference ref is dropped with an
    # issue (inference can only appear via mechanism_inference_claim, so the
    # same text cannot populate both). The mechanism inference REQUIRES
    # kind=inference. Invalid/absent references drop the item with a
    # diagnostic — never a mechanism invented to fill a section.
    def _bound_claim(ref: Any, *, require_inference: bool = False,
                     require_fact: bool = False, label: str):
        claim_ids = resolve_claim_refs([ref], by_statement, issues, f"{where}.{label}")
        if not claim_ids:
            return None
        claim = by_statement[ref]
        if require_inference and claim.kind != "inference":
            issues.append(f"{where}.{label} 引用的判断 kind={claim.kind}，"
                          "不是 inference；已丢弃（机制推断必须绑定 inference 判断）")
            return None
        if require_fact and claim.kind != "fact":
            issues.append(f"{where}.{label} 引用了推断判断，不能作为来源陈述内容，"
                          "已丢弃（推断只能进入 mechanism_inference_claim，不得冒充来源机制）")
            return None
        return {"statement": claim.statement, "claim_ids": claim_ids}

    reusable_mechanism = _bound_claim(entry.get("reusable_mechanism_claim"),
                                      require_fact=True,
                                      label="reusable_mechanism_claim")
    if isinstance(entry.get("reusable_mechanism"), str) and entry["reusable_mechanism"].strip():
        issues.append(f"{where}.reusable_mechanism 平行自由文本已忽略；机制文字以"
                      " reusable_mechanism_claim 所引判断原句为唯一权威")
    mechanism_inference = _bound_claim(entry.get("mechanism_inference_claim"),
                                       require_inference=True,
                                       label="mechanism_inference_claim")
    if isinstance(entry.get("mechanism_inference"), str) and entry["mechanism_inference"].strip():
        issues.append(f"{where}.mechanism_inference 平行自由文本已忽略；推断文字以"
                      " mechanism_inference_claim 所引判断原句为唯一权威")
    conditions: list[dict[str, Any]] = []
    uncertainties: list[str] = []
    raw_app = entry.get("applicability")
    if isinstance(raw_app, dict):
        raw_conditions = raw_app.get("conditions")
        for i, item in enumerate(raw_conditions if isinstance(raw_conditions, list) else []):
            if not isinstance(item, dict):
                issues.append(f"{where}.applicability.conditions[{i}] 不是对象"
                              "（必须给 claim 引用），已丢弃")
                continue
            bound = _bound_claim(item.get("claim"), require_inference=False,
                                 label=f"applicability.conditions[{i}]")
            if bound is None:
                issues.append(f"{where}.applicability.conditions[{i}] 未归因到任何"
                              "已编译判断，整条丢弃（条件必须逐项绑定判断）")
                continue
            conditions.append(bound)
        uncertainties = sanitize_freeform(
            [u for u in (raw_app.get("uncertainties") if isinstance(raw_app.get("uncertainties"), list)
                         else []) if isinstance(u, str) and u.strip()],
            issues, f"{where}.applicability.uncertainties")
    else:
        issues.append(f"{where} 缺少合法 applicability 对象")
    related, pending = split_links(entry.get("related"), entry.get("pending_paths"),
                                   known, note_rels, issues)
    confidence = entry.get("confidence") if entry.get("confidence") in ("high", "medium", "low") \
        else "low"
    return {
        "title": title, "card_level": card_level, "context": context,
        "action": action, "figures": figures,
        "reusable": reusable_mechanism, "inference": mechanism_inference,
        "conditions": conditions, "uncertainties": uncertainties,
        "related": related, "pending": pending, "confidence": confidence,
        "claims": claims, "usable": usable,
    }, claims, usable


def _dedupe_cases(norms: list[dict[str, Any]], issues: list[str]) -> list[dict[str, Any]]:
    """Exact identity = card_level + identical claim-statement set: the same
    story rewritten under two titles is ONE candidate whose evidence is
    UNIONED (usable sources/hashes recomputed — never silently discarded,
    Astra item 4). The SAME story+claims under BOTH levels is an ambiguous
    duplicate: kept but review-gated, never an automatic second full card.
    A same-title candidate with DIFFERENT claims is ambiguous: kept,
    review-flagged, never auto-merged."""
    kept: list[dict[str, Any]] = []
    by_identity: dict[tuple[str, frozenset[str]], int] = {}
    by_claimset: dict[frozenset[str], list[str]] = {}
    title_owners: dict[str, tuple[str, frozenset[str]]] = {}
    for norm in norms:
        claimset = frozenset((c.statement, c.kind) for c in norm["claims"])
        key = (norm["card_level"], claimset)
        if key in by_identity:
            kept_idx = by_identity[key]
            existing = kept[kept_idx]
            before = {(c.statement, c.kind) for c in existing["claims"]}
            absorb_claims(existing["claims"], norm["claims"], issues,
                          f"案例“{norm['title']}”")
            existing["usable"] = {e.source for c in existing["claims"]
                                  for e in c.evidence}
            if {(c.statement, c.kind) for c in existing["claims"]} == before:
                issues.append(
                    f"案例“{norm['title']}”与已有候选为同一故事（层级与判断集相同），"
                    "已去重（不重写第二张卡）")
            continue
        if claimset in by_claimset and norm["card_level"] not in by_claimset[claimset]:
            # exact same story and claims recorded under BOTH levels
            norm["ambiguous_level_dup"] = True
        by_claimset.setdefault(claimset, []).append(norm["card_level"])
        by_identity[key] = len(kept)
        kept.append(norm)
        owner = title_owners.get(norm["title"].casefold())
        if owner is not None and owner != key:
            issues.append(f"标题“{norm['title']}”对应不同判断集合的多个案例，"
                          "疑似同题异实，仅标记人工复核，不做合并裁决")
        else:
            title_owners.setdefault(norm["title"].casefold(), key)
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
    # Sufficiency is evidence-based, deliberately WITHOUT a universal
    # multi-source threshold: a single-source case can be full.
    # Sufficiency is evidence-based, deliberately WITHOUT a universal
    # multi-source threshold and WITHOUT a numeric quota: qualitative
    # observed outcomes with valid compiled evidence qualify a full case.
    gaps: list[str] = []
    if not norm["context"]:
        gaps.append("缺少案例背景")
    if not norm["action"]:
        gaps.append("缺少行动记录")
    if not norm["figures"]:
        gaps.append("缺少通过证据编译并逐项归因的结果陈述")
    if not norm["reusable"] and not norm["inference"]:
        gaps.append("缺少可复用机制或机制推断记录")
    if not norm["conditions"]:
        gaps.append("缺少具体适用条件")
    if norm.get("ambiguous_level_dup"):
        # Same story+mechanism recorded under BOTH levels is an ambiguous
        # duplicate: the second card is review-gated, never an automatic
        # second full card (Astra item 4).
        gaps.append("与另一层级候选为同一故事且判断集相同，疑似重复登记，需人工裁决")
        issues.append("案例“" + norm["title"] + "”在不同 card_level 下判断集完全相同，"
                      "已强制进入人工复核")
    is_full = not gaps
    status, stage = CASE_FULL_STATES if is_full else CASE_REVIEW_STATES
    limited_reason = "；".join(gaps)
    if not is_full:
        issues.append(f"受限案例卡（证据不足，不构成完整案例基线）：{limited_reason}")
    # GP003 Case B：Result 的正式载体是 figures（每条关键结果事实一次）；
    # 机械拼接的 summary 是「结果区三重陈述」的根源，不再生成。
    result_summary = ""
    candidate: dict[str, Any] = {
        "title": norm["title"],
        "type": "case-story",
        "status": status,
        "stage": stage,
        "sources": sources,
        "summary": norm["context"][:100],
        "confidence": confidence,
        "review_required": True,  # program-owned: candidates always need review
        "schema_version": CASE_SCHEMA_VERSION,
        "generator_version": CASE_GENERATOR_VERSION,
        "analysis_mode": "llm",
        "source_hashes": {n["rel"]: n["source_sha256"] for n in verified
                          if n["rel"] in set(sources)},
        "coverage": coverage,
        "related": norm["related"],
        "pending_links": norm["pending"],
        "manual_review": ([] if is_full else [limited_reason]),
        "quality_flags": [f"{CONFIG_SECTION}_issues"] if issues else [],
        "tags": ["case-story"],
        "origin": {"case_title": norm["title"], "source_paths": sources},
        "card_level": norm["card_level"],
        "context": norm["context"],
        "action": norm["action"],
        # source_asserted is PROGRAM-OWNED true: a source assertion is never
        # presented as independently verified, whatever the model claims. It
        # does NOT claim who reported it — actual provenance stays in the
        # per-source provenance_map (Astra item 2).
        "result": {
            "summary": result_summary,
            "source_asserted": True,
            "figures": norm["figures"],
        },
        # Mechanism fields: the authoritative text IS the referenced compiled
        # claim's statement; the *_claim_ids keep the binding visible.
        "reusable_mechanism": norm["reusable"]["statement"] if norm["reusable"] else "",
        "reusable_mechanism_claim_ids": norm["reusable"]["claim_ids"] if norm["reusable"] else [],
        "mechanism_inference": norm["inference"]["statement"] if norm["inference"] else "",
        "mechanism_inference_claim_ids": norm["inference"]["claim_ids"] if norm["inference"] else [],
        "applicability": {"conditions": norm["conditions"],
                          "uncertainties": norm["uncertainties"]},
        "provenance_map": provenance_map,
        "shared_provenance": shared_flags,
        "claims": [c.to_dict() for c in norm["claims"]],
    }
    return candidate


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def generate_cases(
    notes: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    known_paths: list[str] | None = None,
    analysis_mode: str = "llm",
    call_provider: Callable[[dict[str, Any], str, dict[str, Any]], str] | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Run one bounded case extraction. See module docstring for the exact
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
    known, note_rels = ctx["known"], ctx["note_rels"]

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        result["state"] = "error"
        result["reason"] = ("模型声称发现案例但未给出合法的 cases 数组；"
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
    for i, entry in enumerate(raw_cases):
        norm, _claims, _usable = _normalize_case(entry, i, verified, note_rels,
                                                 known, issues)
        if norm is not None:
            norms.append(norm)
    norms = _dedupe_cases(norms, issues)
    if not norms:
        result["state"] = "error"
        result["reason"] = ("没有任何案例候选同时具备合法结构与已编译判断；"
                            "拒绝以无证据叙述生成案例卡")
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
        schema_issues = validate_card_item(candidate, "case-story")
        if schema_issues:
            issues.append(f"案例 {candidate['title']} 未通过 case-story 契约校验，"
                          "已丢弃：" + "；".join(schema_issues[:5]))
            continue
        analysis = {
            "case_title": candidate["title"],
            "card_level": candidate["card_level"],
            "usable_sources": candidate["sources"],
            "attributed_figures": len(candidate["result"]["figures"]),
            "outcome": "full" if candidate["status"] == "growing" else "stub",
            "limited_reason": candidate["manual_review"][0] if candidate["manual_review"] else "",
            "coverage": coverage,
            "analysis_mode": "llm",
            "schema_version": CASE_SCHEMA_VERSION,
            "generator_version": CASE_GENERATOR_VERSION,
            "source_hashes": candidate["source_hashes"],
            "issues": issues,
        }
        card_state = {
            "version": CARD_STATE_VERSION,
            "type": "case-story",
            "claims": candidate["claims"],
            "analysis": analysis,
        }
        try:
            content_md = patch_card_state(
                render_template(TEMPLATE_NAME,
                                _page_context(candidate, norm["claims"], issues, now)),
                card_state, EvidenceCardError)
        except Exception as exc:
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
            "rel_path_hint": "wiki/cases/",
            "content": content_md,
        })
        analyses.append(analysis)
        flat_claims.extend(candidate["claims"])

    if not items:
        result["state"] = "error"
        result["reason"] = "所有案例候选均未通过契约校验，未产出任何页面"
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
            "schema_version": CASE_SCHEMA_VERSION,
            "generator_version": CASE_GENERATOR_VERSION,
            "source_hashes": {n["rel"]: n["source_sha256"] for n in verified},
            "coverage": coverage,
            "issues": issues,
        },
        "issues": issues,
    })
    return result


def _shared_provenance(notes: list[dict[str, Any]], model_flags: Any,
                       issues: list[str]) -> list[str]:
    """Shared-origin disclosure; byte-identical copies are flagged explicitly.
    A shared source does NOT force shared objects or dedupe by itself."""
    flags: list[str] = sanitize_freeform(
        [f for f in (model_flags if isinstance(model_flags, list) else [])
         if isinstance(f, str) and f], issues, "shared_provenance")
    if flags:
        issues.append("存在共享来源/背景说明，已披露；共享来源不等于同一案例对象")
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
