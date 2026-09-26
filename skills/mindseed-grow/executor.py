from __future__ import annotations

import hashlib
import re

from core.clustering import ClusterInput, cluster_inputs
from core.card_contracts import prepare_card_item, validate_card_item
from renderer import render
from core import atomic_seed, card_relations
from core.config import seed_generation_mode
from core.content_safety import SensitiveContentError
from core.llm import call_chat_completion
from core.seed_quality import seed_item, signal_sentences


def safe_filename(title: str) -> str:
    """把 seed 标题转成面向人的中文文件名，保留中文语义。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', title).strip()
    cleaned = re.sub(r"[：:，,。；;、/\\\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if cleaned.lower().startswith("seed-"):
        cleaned = cleaned[5:].strip("-")
    return cleaned[:80] or "未命名种子卡"


def slug(text: str) -> str:
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if ascii_part:
        return ascii_part[:72]
    return "seed-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _renderer_preflight() -> None:
    """Renderer dependency preflight before any model payload is built."""
    if not callable(render):
        raise RuntimeError("mindseed-grow renderer 不可用，拒绝生成。")


def _input_outcomes(notes, *, outcome: str, complete: bool, reason: str,
                    analysis_mode: str, coverage: str) -> list[dict]:
    """Envelope-only per-input closure for the receipt adapter.

    Atomic generation evaluates a batch as one bounded call.  A source that
    contributes no cited thought is still complete when the producer reports a
    full checked batch; citation membership is mapped to targets later by the
    seed updater.  Partial, blocked, and failed batches stay incomplete.
    """
    return [{
        "rel": str(note.get("rel") or ""),
        "source_sha256": str(note.get("source_sha256") or ""),
        "outcome": outcome,
        "complete": bool(complete),
        "targets": [],
        "required_targets": [],
        "reason": str(reason or ""),
        "analysis_mode": analysis_mode,
        "coverage": coverage,
    } for note in notes]


def _finish_atomic(items, issues, meta, notes, context, cfg):
    pages, contract_issues = [], []
    vault_index = context.get("vault_index")
    retriever = context.get("retriever")
    for item in items:
        # Trusted provenance comes only from verified source snapshots, never
        # from model metadata; unverified units stay unknown, never a body hash.
        support = item.get("evidence", [])
        hashes = {row["source"]: row["source_sha256"] for row in support
                  if isinstance(row, dict) and row.get("verified") and row.get("source_sha256")}
        coverage = "full" if meta.get("coverage") == "full" and len(hashes) == len(item.get("sources", [])) \
            else meta.get("coverage", "unknown")
        item = prepare_card_item(item, "seed-card", _atomic_analysis_mode(meta),
                                 trusted_source_hashes=hashes or None, trusted_coverage=coverage)
        issues_ = validate_card_item(item, "seed-card")
        if issues_:
            contract_issues.append(f"seed 契约校验失败，未生成页面：{item.get('title')}：{'；'.join(issues_[:3])}")
            continue
        relations = card_relations.relation_candidates(item, cfg, vault_index, retriever)
        item["related"] = relations["related"]
        item["pending_links"] = relations["pending_links"]
        item["link_search"] = relations["link_search"]
        item["manual_review"] = list(item.get("manual_review", [])) + relations["suspected_duplicates"]
        if relations["relation_explanations"]:
            item["relation_explanations"] = relations["relation_explanations"]
        pages.append({"rel_dir_key": "seed_dir", "filename": f"{safe_filename(item['title'])}.md",
                      "content": render(item), "sources": item["sources"], "item": item})
    if meta.get("blocked_reason"):
        # Unverifiable inputs / malformed model responses: fail closed, never a
        # processed success, never a fake zero output.
        return {"skill": "mindseed-grow", "mode": "atomic", "pages": [], "processed": 0,
                "ok": False, "inputs": [n["rel"] for n in notes], "issues": issues,
                "items": [], "blocked_reason": meta["blocked_reason"],
                "input_outcomes": _input_outcomes(
                    notes, outcome="blocked", complete=False, reason=meta["blocked_reason"],
                    analysis_mode=_atomic_analysis_mode(meta), coverage=meta.get("coverage", "unknown"))}
    complete = bool(meta.get("complete"))
    if meta.get("zero_reason") and not pages:
        # Valid zero output: only FULLY CHECKED input may count as processed.
        return {"skill": "mindseed-grow", "mode": "atomic", "pages": [],
                "processed": len(notes) if complete else 0,
                "ok": True, "inputs": [n["rel"] for n in notes], "issues": issues,
                "items": [], "zero_reason": meta["zero_reason"],
                "input_outcomes": _input_outcomes(
                    notes, outcome="zero", complete=complete, reason=meta["zero_reason"],
                    analysis_mode=_atomic_analysis_mode(meta), coverage=meta.get("coverage", "unknown"))}
    if not complete:
        # Model failure / partial coverage / rejected candidates: reviewable
        # preview material at most, never a processed success.
        issues.append("atomic 本轮不构成完整语义生成（受限预览或不完整覆盖），不计为已处理。")
    return {"skill": "mindseed-grow", "mode": "atomic", "pages": pages,
            "processed": len(notes) if (pages and complete) else 0,
            "ok": not contract_issues,
            "inputs": [n["rel"] for n in notes],
            "issues": issues + contract_issues,
            "items": [page["item"] for page in pages],
            "input_outcomes": _input_outcomes(
                notes, outcome="ok" if complete else "partial", complete=complete,
                reason="ok" if complete else "atomic batch is incomplete",
                analysis_mode=_atomic_analysis_mode(meta), coverage=meta.get("coverage", "unknown"))}


def _atomic_analysis_mode(meta: dict) -> str:
    if meta.get("model") == "llm":
        return "llm"
    if meta.get("model") == "failed":
        return "heuristic-fallback"
    return "heuristic"


def _execute_atomic(context: dict, cfg: dict) -> dict:
    _renderer_preflight()
    notes = context.get("notes", [])
    use_llm = bool(context.get("use_llm", False))
    # model_fn lets tests and future integrations inject a provider; production
    # routing always goes through the screened call_chat_completion entry.
    model_fn = context.get("model_fn") if callable(context.get("model_fn")) else None
    if model_fn is None and use_llm:
        model_fn = lambda system, payload: call_chat_completion(cfg, system, payload)
    provider_calls = 0
    if model_fn is not None:
        original_model_fn = model_fn

        def counted_model_fn(system, payload):
            nonlocal provider_calls
            provider_calls += 1
            return original_model_fn(system, payload)

        model_fn = counted_model_fn
    units = context.get("units")
    try:
        items, issues, meta = atomic_seed.generate_atomic_items(
            notes, units, cfg, model_fn=model_fn,
            snapshots=context.get("snapshots"))
    except SensitiveContentError as exc:
        # Fail closed on secret screening; no pages, no processed success.
        return {"skill": "mindseed-grow", "mode": "atomic", "pages": [], "processed": 0,
                "ok": False, "inputs": [n["rel"] for n in notes],
                "issues": ["atomic 生成被敏感内容筛查阻断：" + atomic_seed.safe_error_message(exc)],
                "items": [], "blocked_reason": "sensitive_content", "provider_calls": provider_calls,
                "input_outcomes": _input_outcomes(
                    notes, outcome="blocked", complete=False, reason="sensitive_content",
                    analysis_mode="unknown", coverage="unknown")}
    result = _finish_atomic(items, issues, meta, notes, context, cfg)
    result["provider_calls"] = provider_calls
    return result


def _execute_topic(notes: list[dict], cfg: dict, use_llm: bool) -> dict:
    max_clusters = int(cfg.get("clustering", {}).get("max_clusters", 5))
    provider_calls = [0]
    clusters, low_confidence = cluster_inputs(
        [ClusterInput(n["rel"], n["title"], "\n".join(signal_sentences(n.get("body", ""), limit=6))) for n in notes],
        max_clusters=max_clusters,
        cfg=cfg if use_llm else None,
        call_counter=provider_calls,
    )
    pages = []
    contract_issues = []
    for cluster in clusters:
        item = seed_item(cluster, notes, cfg)
        if not item["sources"]:
            continue
        # Typed contract gate BEFORE rendering; an invalid seed never becomes a page.
        item = prepare_card_item(item, "seed-card", "heuristic")
        issues = validate_card_item(item, "seed-card")
        if issues:
            contract_issues.append(f"seed 契约校验失败，未生成页面：{item.get('title')}：{'；'.join(issues[:3])}")
            continue
        pages.append({"rel_dir_key": "seed_dir", "filename": f"{safe_filename(item['title'])}.md",
                      "content": render(item), "sources": item["sources"], "item": item})
    complete = not contract_issues
    return {"skill": "mindseed-grow", "mode": "topic", "pages": pages, "processed": 0 if contract_issues else len(notes),
            "ok": not contract_issues,
            "provider_calls": provider_calls[0],
            "inputs": [n["rel"] for n in notes],
            "issues": [f"动态聚类置信度低：{s}" for s in low_confidence] + contract_issues,
            "items": [page["item"] for page in pages],
            "input_outcomes": _input_outcomes(
                notes, outcome="ok" if complete else "blocked", complete=complete,
                reason="topic mode legacy compatibility" if complete else "seed contract blocked",
                analysis_mode="topic", coverage="full" if complete else "partial")}


def execute(context: dict) -> dict:
    cfg = context.get("config", {})
    if seed_generation_mode(cfg) == "topic":
        return _execute_topic(context.get("notes", []), cfg, bool(context.get("use_llm", True)))
    return _execute_atomic(context, cfg)
