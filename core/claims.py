"""Lightweight claim/evidence records; exact fragments, not semantic truth checks.

The owning Markdown page is authoritative. Locators use Unicode character offsets
in UTF-8 text with an initial BOM removed and CRLF/CR normalized to LF. Source
hashes always cover the original bytes. No database or model calls live here.
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass
from typing import Any


class EvidenceError(ValueError):
    """An assertion or its purported source fragment cannot be verified."""


def normalized_text(text: str) -> str:
    return text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _statement(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2000 or any(c in value for c in "\r\n"):
        raise EvidenceError("判断必须是非空、最多 2000 字符的单行文本")
    return value.strip()


def claim_id(statement: str, kind: str) -> str:
    # Exact wording + kind, not fuzzy semantic identity. Unchanged assertions keep
    # the same ID when evidence changes; meaningful rewording gets a different ID.
    return "claim:" + digest(kind + "\0" + statement)


@dataclass(frozen=True)
class Evidence:
    source: str
    source_sha256: str
    quote: str
    quote_sha256: str
    start: int
    end: int
    start_line: int
    end_line: int
    relation: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    statement: str
    kind: str
    confidence: str
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence"] = list(result["evidence"])
        return result


def _locate(item: dict[str, Any], documents: dict[str, dict[str, str]]) -> Evidence:
    source, quote = item.get("source"), item.get("quote")
    relation = item.get("relation")
    if not isinstance(source, str) or source not in documents or any(c in source for c in "[]|#\r\n"):
        raise EvidenceError(f"证据引用了未提供或不可链接的来源：{source}")
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 2000:
        raise EvidenceError("每份证据必须含非空且不超过 2000 字符的原文片段")
    if not isinstance(relation, str) or relation not in {"supports", "contradicts"}:
        raise EvidenceError("证据关系只能是 supports 或 contradicts")
    doc = documents[source]
    text, quote = normalized_text(doc["content"]), normalized_text(quote)
    hint = item.get("start_line")
    if hint is not None and (type(hint) is not int or hint < 1):
        raise EvidenceError("start_line 必须是从 1 开始的行号")
    matches = []
    pos = text.find(quote)
    while pos >= 0:
        if hint is None or text.count("\n", 0, pos) + 1 == hint:
            matches.append(pos)
            if len(matches) > 1:
                break
        pos = text.find(quote, pos + 1)
    if len(matches) != 1:
        raise EvidenceError(f"原文片段不存在或位置不唯一：{source}；提供准确片段及必要的 start_line")
    start, end = matches[0], matches[0] + len(quote)
    return Evidence(source, doc["sha256"], quote, digest(quote), start, end,
                    text.count("\n", 0, start) + 1,
                    text.count("\n", 0, end - 1) + 1, relation)


def compile_claims(items: Any, documents: list[dict[str, str]]) -> list[Claim]:
    """Build records from model statements and exact source quotes, never its IDs."""
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise EvidenceError("create/update 必须提供 1 至 50 条带证据的判断")
    sources = {doc["path"]: doc for doc in documents}
    claims, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise EvidenceError("每条判断必须是一个对象")
        statement = _statement(item.get("statement"))
        kind, confidence = item.get("kind"), item.get("confidence")
        if not isinstance(kind, str) or kind not in {"fact", "inference"}:
            raise EvidenceError("kind 只能是 fact 或 inference；fact 也不表示事实已证实")
        if not isinstance(confidence, str) or confidence not in {"low", "medium", "high"}:
            raise EvidenceError("confidence 只能是 low、medium 或 high")
        citations = item.get("evidence")
        if not isinstance(citations, list) or not 1 <= len(citations) <= 20 or not all(isinstance(e, dict) for e in citations):
            raise EvidenceError("每条判断必须有 1 至 20 份具体证据")
        evidence = tuple(dict.fromkeys(_locate(e, sources) for e in citations))
        identifier = claim_id(statement, kind)
        if identifier in seen:
            raise EvidenceError("同一提案包含重复判断，请合并其证据")
        seen.add(identifier)
        claims.append(Claim(identifier, statement, kind, confidence, evidence))
    return claims


def read_claims(state: dict[str, Any]) -> list[Claim]:
    """Strictly deserialize stored records without treating a stale source as loss."""
    items = state.get("claims")
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise EvidenceError("缺少合法的 claims 记录")
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise EvidenceError("非法判断记录")
        statement = _statement(item.get("statement"))
        kind, confidence = item.get("kind"), item.get("confidence")
        if kind not in ("fact", "inference") or confidence not in ("low", "medium", "high"):
            raise EvidenceError("非法判断类别或置信度")
        identifier = claim_id(statement, kind)
        if item.get("claim_id") != identifier or identifier in seen:
            raise EvidenceError("判断 ID 与正文不一致或重复")
        seen.add(identifier)
        citations = item.get("evidence")
        if not isinstance(citations, list) or not 1 <= len(citations) <= 20:
            raise EvidenceError("判断缺少证据")
        evidence = []
        for raw in citations:
            if not isinstance(raw, dict) or set(raw) != set(Evidence.__dataclass_fields__):
                raise EvidenceError("非法证据字段")
            e = Evidence(**raw)
            if (not isinstance(e.source, str) or not e.source or any(c in e.source for c in "[]|#\r\n")
                    or not isinstance(e.quote, str) or not e.quote.strip() or len(e.quote) > 2000
                    or normalized_text(e.quote) != e.quote or digest(e.quote) != e.quote_sha256
                    or not isinstance(e.source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", e.source_sha256)
                    or e.relation not in ("supports", "contradicts")
                    or any(type(n) is not int for n in (e.start, e.end, e.start_line, e.end_line))
                    or e.start < 0 or e.end != e.start + len(e.quote)
                    or e.start_line < 1 or e.end_line < e.start_line):
                raise EvidenceError("证据片段、版本或位置记录无效")
            evidence.append(e)
        result.append(Claim(identifier, statement, kind, confidence, tuple(evidence)))
    return result


def evidence_status(e: Evidence, document: dict[str, str] | None) -> str:
    """Report matching state only. A matched quote is NOT a proven assertion."""
    if document is None:
        return "unavailable"
    if document["sha256"] != e.source_sha256:
        return "source_changed"
    text = normalized_text(document["content"])
    if (text[e.start:e.end] != e.quote
            or text.count("\n", 0, e.start) + 1 != e.start_line
            or text.count("\n", 0, e.end - 1) + 1 != e.end_line):
        return "mismatch"
    return "matched"


def validate_claims(state: dict[str, Any], documents: list[dict[str, str]]) -> list[Claim]:
    claims = read_claims(state)
    sources = {doc["path"]: doc for doc in documents}
    for claim in claims:
        for e in claim.evidence:
            if e.relation != "supports":
                raise EvidenceError("存在反驳证据的提案必须先解决冲突，不能直接写入")
            if evidence_status(e, sources.get(e.source)) != "matched":
                raise EvidenceError(f"证据位置、片段或来源版本不匹配：{e.source}")
    return claims


def _literal(text: str) -> str:
    # Quotes are displayed as literal text, never executable HTML/control comments
    # or fresh wikilinks copied from an untrusted source document.
    return re.sub(r"([\\`*_\[\]#!|^])", r"\\\1", html.escape(text, quote=False))


def render_claims(claims: list[Claim]) -> str:
    lines = ["以下判断待人工审核。片段匹配不等于事实已证实；置信度为模型判断。"]
    for i, claim in enumerate(claims, 1):
        label = "事实性判断" if claim.kind == "fact" else "推断"
        lines += ["", f"### {i}. {label} · {claim.confidence}", "", _literal(claim.statement)]
        for e in claim.evidence:
            relation = "支持" if e.relation == "supports" else "反驳"
            lines += ["", f"{relation}依据：[[{e.source}]] · 第 {e.start_line}–{e.end_line} 行", ""]
            lines.extend("> " + _literal(line) for line in e.quote.split("\n"))
    return "\n".join(lines)
