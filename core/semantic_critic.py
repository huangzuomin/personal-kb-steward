"""Semantic critic layer (generator–critic) for card quality.

The generator (api backend, or agent backend) proposes cards; the critic is an
independent LLM pass that reads the card *against its sources* and produces a
structured objection list. The critic never edits the card and never writes to
the vault — it only flags. Blocking/flagged verdicts route the page to manual
review with the report attached.

Design notes:
- The critic goes through ``core.llm.llm_generate``, so it respects the global
  ``--backend`` override. Typical pairing: generate on ``api`` (fast/cheap),
  critique on ``agent`` (careful, full-text reads) via ``--critic-backend``.
- Risk tiers: ``seed-card`` gets a light checklist; concept/topic/claim cards
  get the strict checklist. Unknown types default to strict (fail-closed on
  quality).
- Every rejection reason comes from ``OBJECTION_CODES`` so rejections are
  structured and can feed back into prompts and deterministic gates.
- Transport/contract failures raise ``CriticError``; callers map that to a
  ``flag`` verdict with a ``critic_error`` objection — never a silent pass.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import kb_root
from .json_contract import extract_json
from .llm import LLMError, llm_generate


class CriticError(RuntimeError):
    pass


# ── Objection taxonomy ──────────────────────────────────────────────────────
# Every structured rejection reason. Keep codes stable; descriptions may evolve.

OBJECTION_CODES: dict[str, str] = {
    "unsupported_claim": "卡片中的断言在来源原文中找不到证据支持",
    "question_as_fact": "来源原文是问题/疑问/假设，卡片写成了确定事实",
    "bad_citation": "引用不实：引用的原文片段不支持卡片的表述",
    "link_mismatch": "链接文不对题：related/来源链接与卡片主题不相关",
    "overgeneralization": "过度泛化：来源的限定条件（时间/范围/人群）在卡片中被丢掉",
    "missing_limitation": "来源原文的明确限定、警告或反例在卡片中被省略",
    "fabricated_detail": "编造细节：卡片包含来源完全没有的具体数字/名称/事件",
    "critic_error": "校验器自身失败（传输错误/输出非法），需人工复核",
}

VERDICTS = ("pass", "flag", "block")
SEVERITIES = ("flag", "block")

# ── Risk tiers ───────────────────────────────────────────────────────────────

TIER_LIGHT = "light"
TIER_STRICT = "strict"

# Card type/skill → tier. Seed cards carry little factual surface; everything
# else gets the strict checklist. Unknown → strict (fail-closed on quality).
CARD_TIER_MAP: dict[str, str] = {
    "seed-card": TIER_LIGHT,
    "seed": TIER_LIGHT,
    "concept-card": TIER_STRICT,
    "concept-page": TIER_STRICT,
    "topic-card": TIER_STRICT,
    "topic-page": TIER_STRICT,
    "claim-check": TIER_STRICT,
    "source-note": TIER_STRICT,
    "material-pack": TIER_STRICT,
}


def tier_for_page(page: dict[str, Any]) -> str:
    """Risk tier for a planned page, from its type/skill/kind markers."""
    for key in ("type", "card_type", "kind", "skill"):
        value = page.get(key)
        if isinstance(value, str) and value.strip():
            hit = CARD_TIER_MAP.get(value.strip().lower())
            if hit:
                return hit
    return TIER_STRICT


# ── Prompt ───────────────────────────────────────────────────────────────────

MAX_SOURCE_CHARS = 8000
MAX_SOURCES = 4

CRITIC_SYSTEM_PROMPT = """你是知识库卡片的语义校验员（critic）。你的唯一职责是对照卡片内容和来源原文，找出语义层面的质量问题。

你不修改卡片，不写库，不做总结发挥。你输出的是一份异议清单，供人工复核。

校验清单（{tier}）：
- light：只检查最严重的问题：编造细节（fabricated_detail）、无证据的核心断言（unsupported_claim）、引用完全不实（bad_citation）。
- strict：全面检查以下全部编码：
  1. unsupported_claim：卡片中的断言在来源原文中找不到证据
  2. question_as_fact：来源是问题/疑问/假设，卡片写成确定事实
  3. bad_citation：引用的原文片段不支持卡片的表述
  4. link_mismatch：related/来源链接与卡片主题不相关
  5. overgeneralization：来源的限定条件（时间/范围/人群）在卡片中被丢掉
  6. missing_limitation：来源的明确限定、警告或反例被省略
  7. fabricated_detail：卡片包含来源完全没有的具体数字/名称/事件

输出要求：只输出一个 JSON 对象，第一个字符必须是 {{ ，最后一个字符必须是 }}，格式如下：
{{
  "verdict": "pass|flag|block",
  "objections": [
    {{"code": "<上述编码之一>", "severity": "flag|block",
      "quote_card": "<卡片原文，逐字引用>",
      "quote_source": "<来源原文，逐字引用；找不到依据时为空字符串>",
      "note": "<一句话说明>"}}
  ],
  "summary": "<一句话总结>"
}}
判定规则：
- pass：无问题，此时 objections 必须为空数组。
- flag：有值得人工看一眼的问题，但不致命。
- block：有致命问题（编造、无证据的核心断言），必须人工处理。
- 任何 severity 为 block 的异议，verdict 必须为 block。
- quote 必须是逐字引用，不得改写、不得概括；找不到来源依据时 quote_source 为空字符串，并在 note 中写明"来源无对应内容"。
"""


def build_critic_payload(page: dict[str, Any],
                         source_texts: dict[str, str],
                         tier: str) -> dict[str, Any]:
    """User payload for the critic call."""
    return {
        "task": "critic-review",
        "tier": tier,
        "card": {
            "title": page.get("title") or page.get("rel_path") or "",
            "type": page.get("type") or page.get("skill") or "",
            "rel_path": page.get("rel_path") or page.get("target") or "",
            "content": page.get("content") or "",
            "sources": page.get("sources") or [],
        },
        "sources": [
            {"rel": rel, "text": text}
            for rel, text in source_texts.items()
        ],
        "taxonomy": OBJECTION_CODES,
        "output_contract": {
            "verdict": "pass | flag | block",
            "objections": "array<object {code, severity, quote_card, quote_source, note}>",
            "summary": "string，一句话总结",
        },
    }


# ── Report validation ────────────────────────────────────────────────────────

def validate_critic_report(report: Any) -> list[str]:
    """Return a list of contract problems; empty means the report is valid."""
    problems: list[str] = []
    if not isinstance(report, dict):
        return ["critic 输出不是 JSON 对象"]
    verdict = report.get("verdict")
    if verdict not in VERDICTS:
        problems.append(f"verdict 非法：{verdict!r}")
    objections = report.get("objections")
    if not isinstance(objections, list):
        problems.append("objections 不是数组")
        objections = []
    for i, obj in enumerate(objections):
        prefix = f"objections[{i}]"
        if not isinstance(obj, dict):
            problems.append(f"{prefix} 不是对象")
            continue
        code = obj.get("code")
        if code not in OBJECTION_CODES:
            problems.append(f"{prefix}.code 非法：{code!r}")
        severity = obj.get("severity")
        if severity not in SEVERITIES:
            problems.append(f"{prefix}.severity 非法：{severity!r}")
        for field in ("quote_card", "note"):
            if not isinstance(obj.get(field), str):
                problems.append(f"{prefix}.{field} 不是字符串")
        if not isinstance(obj.get("quote_source"), str):
            problems.append(f"{prefix}.quote_source 不是字符串")
    summary = report.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("summary 缺失或为空")
    if verdict == "pass" and objections:
        problems.append("verdict 为 pass 但 objections 非空")
    if any(isinstance(o, dict) and o.get("severity") == "block"
           for o in objections) and verdict != "block":
        problems.append("存在 block 级异议但 verdict 不是 block")
    return problems


# ── Review ───────────────────────────────────────────────────────────────────

def critic_review(critic_cfg: dict[str, Any],
                  page: dict[str, Any],
                  source_texts: dict[str, str],
                  tier: str | None = None) -> dict[str, Any]:
    """Run the semantic critic on one planned page.

    ``critic_cfg`` is the config for the *critic* call — pass
    ``override_llm_backend(cfg, ...)`` for a backend independent of the
    generator's. Returns the validated report dict. Raises CriticError on
    transport failure or contract violation (callers map to ``flag``).
    """
    active_tier = tier or tier_for_page(page)
    if active_tier not in (TIER_LIGHT, TIER_STRICT):
        raise CriticError(f"未知校验等级：{active_tier!r}")
    system = CRITIC_SYSTEM_PROMPT.format(tier=active_tier)
    payload = build_critic_payload(page, source_texts, active_tier)
    try:
        raw = llm_generate(critic_cfg, system, payload)
    except (LLMError, OSError) as exc:
        raise CriticError(f"critic 调用失败：{exc}") from exc
    try:
        report = extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CriticError(f"critic 输出不是合法 JSON：{exc}") from exc
    problems = validate_critic_report(report)
    if problems:
        raise CriticError("critic 输出违反 contract：" + "；".join(problems))
    report["tier"] = active_tier
    report["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return report


def read_source_texts(cfg: dict[str, Any],
                      sources: list[str]) -> dict[str, str]:
    """Read up to MAX_SOURCES source texts from the vault, truncated."""
    root = Path(kb_root(cfg))
    texts: dict[str, str] = {}
    for rel in sources:
        if not isinstance(rel, str) or not rel.strip() or len(texts) >= MAX_SOURCES:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        texts[rel] = text[:MAX_SOURCE_CHARS]
    return texts


def save_critic_report(cfg: dict[str, Any], run_id: str,
                       page_key: str, report: dict[str, Any]) -> str:
    """Persist a critic report under the runs dir; returns the rel path."""
    from .config import runs_dir
    safe_key = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_"
                       for c in page_key)[-60:]
    path = runs_dir(cfg) / run_id / "critic" / f"{safe_key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path.as_posix()


def _error_report(note: str) -> dict[str, Any]:
    return {
        "verdict": "flag",
        "tier": TIER_STRICT,
        "objections": [{
            "code": "critic_error",
            "severity": "flag",
            "quote_card": "",
            "quote_source": "",
            "note": note,
        }],
        "summary": f"校验器失败，已降级为人工复核：{note}",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def apply_semantic_critic(cfg: dict[str, Any],
                          critic_cfg: dict[str, Any],
                          plan: dict[str, Any]) -> dict[str, int]:
    """Run the critic over a plan's planned_pages; mutate the plan in place.

    Pages with a ``block``/``flag`` verdict get ``review_required=True`` and a
    ``critic_report`` path; a structured manual_review entry is appended per
    flagged page. Critic failures degrade to ``flag`` (never a silent pass).
    Returns stats: {checked, passed, flagged, blocked, errors, skipped}.
    """
    stats = {"checked": 0, "passed": 0, "flagged": 0, "blocked": 0,
             "errors": 0, "skipped": 0}
    run_id = str(plan.get("run_id") or "unknown")
    manual_review = plan.setdefault("manual_review", [])
    for page in plan.get("planned_pages") or []:
        if not isinstance(page, dict):
            stats["skipped"] += 1
            continue
        content = page.get("content") or ""
        sources = [s for s in (page.get("sources") or []) if isinstance(s, str)]
        if not content.strip() or not sources:
            stats["skipped"] += 1
            continue
        page_key = str(page.get("rel_path") or page.get("target") or "page")
        source_texts = read_source_texts(cfg, sources)
        if not source_texts:
            stats["skipped"] += 1
            continue
        stats["checked"] += 1
        try:
            report = critic_review(critic_cfg, page, source_texts)
        except CriticError as exc:
            stats["errors"] += 1
            report = _error_report(str(exc))
        report_path = save_critic_report(cfg, run_id, page_key, report)
        verdict = report.get("verdict")
        if verdict == "pass":
            stats["passed"] += 1
            continue
        page["review_required"] = True
        page["critic_report"] = report_path
        page["critic_verdict"] = verdict
        codes = sorted({o.get("code") for o in report.get("objections", [])
                        if isinstance(o, dict) and o.get("code")})
        manual_review.append({
            "type": f"semantic_critic_{verdict}",
            "risk": "high" if verdict == "block" else "medium",
            "reason": f"语义校验 {verdict}（{report.get('tier')}）：{report.get('summary')}",
            "items": [page_key],
            "critic_report": report_path,
            "objection_codes": codes,
        })
        stats["flagged" if verdict == "flag" else "blocked"] += 1
    return stats
