import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from core.layout import relative_dir
from core.jinja_renderer import render_markdown
from core.content_safety import assert_safe_content
from core.card_contracts import prepare_card_item, validate_card_item
from core.source_analysis import plain_text


def safe_source_rel(value: Any) -> str:
    """Validate the source path as a canonical vault-relative path.

    Only this explicit, validated actual source path becomes a wikilink; anything
    else degrades to plain text so model text can never mint links.
    """
    text = str(value or "").strip()
    path = PurePosixPath(text)
    if (text and "\\" not in text and not path.is_absolute() and ".." not in path.parts
            and PureWindowsPath(text).drive == "" and path.as_posix() == text
            and not any(c in text for c in "[]|#\r\n\x00")):
        return text
    return ""


def safe_link(rel: str) -> str:
    return f"- [[{rel}]]" if rel else f"- {plain_text(str(rel))}"


def slug(text: str, fallback: str = "topic") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text).strip()
    cleaned = re.sub(r"[，。；;、\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", cleaned).strip("-").lower()
    return (cleaned or ascii_part or fallback)[:72]


def short_hash(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def render(data: dict[str, Any]) -> list[dict[str, Any]]:
    assert_safe_content(data)
    mode = str(data.get("analysis_mode") or "unknown")
    if mode not in ("llm", "heuristic", "heuristic-fallback", "unknown"):
        raise ValueError(f"analysis_mode 非法，拒绝生成来源页：{mode!r}")
    flags = data.get("quality_flags", [])
    if not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags):
        raise ValueError("quality_flags must be an array of strings")
    facts = data.get("key_facts", [])
    if not isinstance(facts, list) or not all(isinstance(fact, str) for fact in facts):
        raise ValueError("key_facts must be an array of strings")
    summary = data.get("source_summary", "")
    if not isinstance(summary, str):
        raise ValueError("source_summary must be a string")
    flags = list(flags)
    coverage = data.get("coverage")
    if coverage not in ("full", "partial", "unknown", None):
        raise ValueError(f"coverage 非法，拒绝生成来源页：{coverage!r}")
    source_type = data.get("source_type")
    if source_type is not None and (not isinstance(source_type, str) or not source_type.strip()):
        raise ValueError("source_type must be a non-empty string or None")
    limitations = data.get("limitations", [])
    if not isinstance(limitations, list) or not all(isinstance(x, str) for x in limitations):
        raise ValueError("limitations must be an array of strings")
    if not summary.strip() or not facts:
        flags.append("摘要或关键事实不足，需要人工复核。")
    # A partial read can never be presented as a complete analysis; unknown
    # coverage (legacy/no snapshot) keeps the legacy flag-driven behavior.
    if coverage == "partial":
        flags.append("源文本未完整读取（coverage: partial），本次分析不完整，不能作为完整结论。")
    review = mode != "llm" or bool(flags) or coverage == "partial"
    confidence = "low" if review else "medium"
    source_rel = safe_source_rel(data.get("source_rel", ""))
    source_name = str(data.get("source_rel", "")).split("/")[-1].replace(".md", "")
    sources_dir = relative_dir(data.get("sources_dir") or "wiki/sources")
    source_target = f"{sources_dir}/source-{slug(source_name, 'source')}-{short_hash(source_rel)}.md"
    topic_specs = [
        {**topic, "title": topic.get("title", f"Topic-{idx}")}
        for idx, topic in enumerate(data.get("topics", []))
    ]

    # Typed contract gate BEFORE rendering: adapt the renderer-shaped analysis
    # data into the canonical source-note item, inject program-owned metadata,
    # and fail closed. An invalid item never becomes a page.
    # Provenance is trusted only when the producer explicitly computed it;
    # model/unknown-shaped values are dropped by prepare_card_item.
    trusted_hashes = data.get("source_hashes")
    trusted_hashes = (trusted_hashes if isinstance(trusted_hashes, dict)
                      and all(isinstance(k, str) and isinstance(v, str) for k, v in trusted_hashes.items())
                      else None)
    trusted_coverage = data.get("coverage") if data.get("coverage") in ("full", "partial") else None
    item = prepare_card_item({
        "title": f"Source: {data.get('source_title', source_name)}",
        "type": "source-note",
        "status": "manual_review" if review else "growing",
        "stage": "needs_context" if review else "compiling",
        "sources": [source_rel],
        "summary": summary,
        "confidence": confidence,
        "review_required": review,
        "origin": {"source_paths": [source_rel], "operation": "topic-research-compile"},
        "key_statements": list(facts),
        "topic_hints": topic_specs,
        "quality_flags": flags,
        "coverage": coverage,
        "source_type": source_type,
        "limitations": limitations,
        "tags": ["source"],
    }, "source-note", mode,
        trusted_source_hashes=trusted_hashes, trusted_coverage=trusted_coverage)
    contract_issues = validate_card_item(item, "source-note")
    if contract_issues:
        raise ValueError("source-note 契约校验失败，未生成页面：" + "；".join(contract_issues[:5]))
    source_rel = item["sources"][0]

    # card_state: versioned structured record owned by this Markdown page so a
    # later integrator can reload verified evidence without parsing display
    # paraphrases. Must agree with the returned structured payload.
    info_units = []
    for unit in data.get("info_units", []):
        if not isinstance(unit, dict):
            continue
        info_units.append({
            "text": unit.get("text", ""), "quote": unit.get("quote", ""),
            "start": unit.get("start"), "end": unit.get("end"),
            "start_line": unit.get("start_line"), "end_line": unit.get("end_line"),
            "verified": bool(unit.get("verified")), "kind": unit.get("kind", "assertion"),
            "chunk": unit.get("chunk"), "speaker": unit.get("speaker"),
            "source": unit.get("source", source_rel),
            "source_sha256": unit.get("source_sha256"),
        })
    card_state = {
        "version": 1,
        "type": "source-note",
        "info_units": info_units,
        "analysis": {
            "analysis_mode": item["analysis_mode"],
            "coverage": item["coverage"],
            "source_type": source_type,
            "speakers": data.get("speakers", []),
            "read_ranges": data.get("coverage_info", {}).get("read_ranges", []),
            "error_ranges": data.get("coverage_info", {}).get("error_ranges", []),
            "excluded_ranges": data.get("coverage_info", {}).get("excluded_ranges", []),
            "source_hashes": item["source_hashes"],
            "errors": data.get("errors", []),
            # Persisted explicitly so the integrator can reload source-specific
            # limitations and proposed topic hints without parsing display
            # prose. Limitations here are program+model stored strings
            # (plain_text sanitized above); topic hints are proposed research
            # frames, never authoritative claims.
            "limitations": list(limitations),
            "topic_hints": [{"title": str(t.get("title", "")),
                             "content": str(t.get("content", ""))}
                            for t in topic_specs],
        },
    }
    from core.reconcile import _patch_header
    # Rendered display text is sanitized (no model wikilinks, ever); the
    # verification quote inside card_state stays verbatim.
    facts_display = data.get("facts_display")
    if not isinstance(facts_display, list) or not facts_display:
        facts_display = [{"speaker": None, "text": fact} for fact in facts]
    facts_display = [{"speaker": plain_text(str(f.get("speaker"))) if f.get("speaker") else None,
                      "text": plain_text(str(f.get("text", "")))}
                     for f in facts_display if isinstance(f, dict)]
    display = {
        "summary": plain_text(summary),
        "limitations": [plain_text(x) for x in limitations],
        "quality_flags_display": [plain_text(x) for x in flags],
        "topics_display": [{"title": plain_text(str(t.get("title", ""))),
                            "content": plain_text(str(t.get("content", "")))}
                           for t in topic_specs],
        "facts_display": facts_display,
    }
    source_content = _patch_header(render_markdown("source_note.j2", {
        "title": item["title"],
        "type": "source-note",
        "status": item["status"],
        "stage": item["stage"],
        "source_rel": source_rel,
        "sources": item["sources"],
        "tags": ["source"],
        "confidence": confidence,
        "review_required": review,
        "origin": item["origin"],
        "schema_version": item["schema_version"],
        "generator_version": item["generator_version"],
        "analysis_mode": item["analysis_mode"],
        "coverage": item["coverage"],
        "source_hashes": item["source_hashes"],
        "quality_flags": display["quality_flags_display"],
        "coverage": item["coverage"],
        "source_type": source_type,
        "limitations": display["limitations"],
        "speakers": data.get("speakers", []),
        "summary": display["summary"],
        "topics": display["topics_display"],
        "key_facts": [f["text"] for f in display["facts_display"]],
        "facts_display": display["facts_display"],
    }), {"card_state": card_state})
    return [{
        "skill": "topic-research-compile",
        "target": source_target,
        "sources": [source_rel],
        "content": source_content,
        "quality_flags": flags,
        "analysis_mode": item["analysis_mode"],
        "review_required": review,
        "confidence": confidence,
    }]
