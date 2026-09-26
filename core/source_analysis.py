"""M1 source analysis: full-text, attributable analysis over ORIGINAL source text.

The original bytes/text are the only evidence coordinate system. Never clean the
text first and then use cleaned coordinates as evidence. Coverage, offsets and
hashes all refer to the normalized text (initial BOM removed, CRLF/CR -> LF),
matching core.claims; the raw-byte hash travels separately and unmodified.

Coverage semantics: coverage describes successfully ANALYZED ranges, not merely
planned chunks. Failed/skipped provider chunks become explicit error/excluded
ranges; "full" is only claimed when every planned range was analyzed. Bounded
by construction; no network/model/filesystem access lives here.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from core.claims import digest, normalized_text
from core.content_safety import suspicious_machine_line


class SourceAnalysisError(ValueError):
    """Source text is unusable or a quote cannot be verified; never fabricated."""


DEFAULT_CHUNK_CHARS = 4000
DEFAULT_MAX_CHUNKS = 12
SOURCE_TYPES = ("dialogue", "ai-synthesis", "oral-case", "article", "unknown")
ANALYSIS_MODES = ("llm", "heuristic", "heuristic-fallback", "unknown")
STATEMENT_KINDS = ("assertion", "question", "procedure", "reference")

_SPEAKER_LINE = re.compile(r"\A(?:#{1,6}\s*)?(?:\*\*)?[^*\n：:]{1,16}(?:\*\*)?\s*[：:]\s*\S")
# A label prefix (possibly truncated right after "：") still identifies the
# currently active speaker for attribution purposes.
_SPEAKER_LABEL = re.compile(r"\A(?:#{1,6}\s*)?(?:\*\*)?[^*\n：:]{1,16}(?:\*\*)?\s*[：:]")
_QA_MARKER = re.compile(r"(?:^|\n)\s*(?:问|答|Q|A)\s*[：:]", re.I)
_AI_MARKERS = (
    "作为一个AI", "作为一个 AI", "AI助手", "AI 助手", "由AI生成", "由 AI 生成",
    "本文由AI", "AI生成内容", "以下是AI", "语言模型", "AI整理", "模型生成",
)
_ORAL_MARKERS = (
    "口述", "据其转述", "据……转述", "受访者表示", "访谈记录", "内部案例",
    "当事人回忆", "口头介绍", "回忆称",
)
_DIALOGUE_TAG_MARKERS = ("对话", "dialogue", "访谈", "采访", "聊天记录")
_AI_TAG_MARKERS = ("ai", "ai合成", "ai生成", "机器生成", "语言模型", "synthetic")
_ORAL_TAG_MARKERS = ("口述", "oral", "转述", "内部案例", "回忆")
_ARTICLE_TAG_MARKERS = ("article", "文章", "报道", "评论", "综述", "research")
_FRONTMATTER_KEYS = ("title", "type", "tags", "status", "stage", "sources", "created",
                     "updated", "date", "author", "source", "related", "confidence")
# Real citations only: a bare word like 来源 (which appears in statements such
# as 无外部来源) is NOT proof that references exist.
_CITATION_MARKER = re.compile(r"(参考文献|引自|据《|https?://|\bcitation\b|\[1\])")

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")

# These are structural boundaries or explicit unknown markers, not people.
# The parser below remains label-based; this small set only prevents common
# metadata/placeholder labels from becoming a persistent speaker state.
_UNKNOWN_SPEAKER_LABELS = frozenset({
    "?", "？", "unknown", "unk", "n/a", "na", "none", "null",
    "未知", "不明", "匿名", "未具名", "无名", "不详", "说话人未知",
})
_METADATA_LABELS = frozenset({
    *(_FRONTMATTER_KEYS if "_FRONTMATTER_KEYS" in globals() else ()),
    "creation date", "created at", "updated at", "last modified",
    "description", "aliases", "alias", "keywords", "url", "permalink",
})


# ---------------------------------------------------------------------------
# Configuration (plain dict seam; no core.config changes needed)
# ---------------------------------------------------------------------------
def analysis_settings(cfg: dict[str, Any] | None) -> dict[str, int]:
    raw = (cfg or {}).get("source_analysis") or {}
    if not isinstance(raw, dict):
        raise SourceAnalysisError("source_analysis 配置必须是对象")
    chunk_chars = raw.get("chunk_chars", DEFAULT_CHUNK_CHARS)
    max_chunks = raw.get("max_chunks", DEFAULT_MAX_CHUNKS)
    if type(chunk_chars) is not int or chunk_chars < 200 or chunk_chars > 20000:
        raise SourceAnalysisError(f"source_analysis.chunk_chars 必须是 200-20000 的整数：{chunk_chars!r}")
    if type(max_chunks) is not int or max_chunks < 1 or max_chunks > 64:
        raise SourceAnalysisError(f"source_analysis.max_chunks 必须是 1-64 的整数：{max_chunks!r}")
    return {"chunk_chars": chunk_chars, "max_chunks": max_chunks}


# ---------------------------------------------------------------------------
# Chunk planning over normalized ORIGINAL text
# ---------------------------------------------------------------------------
def plan_chunks(norm_text: str, chunk_chars: int, max_chunks: int) -> dict[str, Any]:
    """Bounded read plan. Unread text becomes an explicit excluded range."""
    total = len(norm_text)
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < total and len(chunks) < max_chunks:
        end = min(start + chunk_chars, total)
        if end < total:
            window = norm_text[end:min(end + 200, total)]
            boundary = max(window.find(mark) for mark in ("。", "！", "？", "；", "\n"))
            if boundary >= 0:
                end += boundary + 1
        chunks.append({"index": len(chunks), "start": start, "end": end,
                       "text": norm_text[start:end]})
        start = end
    excluded = [{"start": start, "end": total}] if start < total else []
    return {
        "chunks": chunks,
        "excluded_ranges": excluded,
        "coverage": "partial" if excluded else "full",
        "total_chars": total,
        "read_chars": min(start, total),
    }


# ---------------------------------------------------------------------------
# Quote verification, consistent with core.claims locate semantics
# ---------------------------------------------------------------------------
def locate_quote(norm_text: str, quote: str, start_line: int | None = None) -> dict[str, int]:
    """Return normalized offsets/lines of ONE exact occurrence of quote.

    A repeated identical quote must be disambiguated with start_line; without
    it an ambiguous quote is rejected, never silently 'verified'.
    """
    if not isinstance(quote, str) or not quote.strip() or len(quote) > 2000:
        raise SourceAnalysisError("引用片段必须是非空且不超过 2000 字符的原文")
    quote = normalized_text(quote)
    if start_line is not None and (type(start_line) is not int or start_line < 1):
        raise SourceAnalysisError("start_line 必须是从 1 开始的行号")
    matches: list[int] = []
    pos = norm_text.find(quote)
    while pos >= 0:
        if start_line is None or norm_text.count("\n", 0, pos) + 1 == start_line:
            matches.append(pos)
            if len(matches) > 1:
                break
        pos = norm_text.find(quote, pos + 1)
    if len(matches) != 1:
        raise SourceAnalysisError("原文片段不存在或位置不唯一；请提供准确片段及必要的 start_line")
    start, end = matches[0], matches[0] + len(quote)
    return {"start": start, "end": end,
            "start_line": norm_text.count("\n", 0, start) + 1,
            "end_line": norm_text.count("\n", 0, end - 1) + 1}


# ---------------------------------------------------------------------------
# Source type / speaker attribution (text + metadata; unknown when uncertain)
# ---------------------------------------------------------------------------
def classify_source(title: str, text: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Evidence-based typing. Dialogue structure wins over an AI mention inside
    the conversation; plain long text stays unknown without genre evidence."""
    meta = metadata if isinstance(metadata, dict) else {}
    tags = " ".join(str(tag).lower() for tag in
                    (meta.get("tags") or meta.get("keywords") or []) if isinstance(tag, str))
    header = " ".join(str(meta.get(key, "")) for key in
                      ("source_type", "record_type", "category", "genre", "type")).lower()
    head_text = text[:2000]

    has_dialogue = (any(marker in f"{title} {tags} {header}" for marker in _DIALOGUE_TAG_MARKERS)
                    or len(_QA_MARKER.findall(text[:4000])) >= 2)
    speaker_lines = [line.strip() for line in _explicit_speaker_lines(text)]
    # Structural evidence: several speaker-labelled lines with at least two
    # distinct labelled names AND question/answer turns. Frontmatter keys and
    # colon-led lists alone are not a conversation.
    labelled = [line for line in speaker_lines
                if re.sub(r"^[#\s]+", "", line).lstrip("*").split("：", 1)[0].split(":", 1)[0]
                .strip("*").strip().lower() not in _FRONTMATTER_KEYS]
    if len(labelled) >= 3 and len({_speaker_name(line) for line in labelled}) >= 2 \
            and len(_QA_MARKER.findall(text[:4000])) >= 1:
        has_dialogue = True
    has_ai = (any(marker in head_text for marker in _AI_MARKERS)
              or any(marker in f"{tags} {header}" for marker in _AI_TAG_MARKERS))
    has_oral = (any(marker in f"{title} {tags} {header} {text[:3000]}" for marker in _ORAL_MARKERS)
                or any(marker in f"{tags} {header}" for marker in _ORAL_TAG_MARKERS))
    has_article = (any(marker in f"{tags} {header}" for marker in _ARTICLE_TAG_MARKERS)
                   or bool(_CITATION_MARKER.search(text)))

    if has_dialogue:
        kind = "dialogue"
    elif has_ai and not has_oral:
        kind = "ai-synthesis"
    elif has_oral:
        kind = "oral-case"
    elif has_article and not has_ai:
        kind = "article"
    else:
        return {"source_type": "unknown", "speakers": [],
                "reason": "类型证据不足或冲突，保持 unknown，不按长度或猜测归类。"}
    speakers: list[str] = []
    if kind == "dialogue":
        speakers = sorted({_speaker_name(line) for line in speaker_lines
                           if _speaker_name(line)
                           and _speaker_name(line) not in _FRONTMATTER_KEYS
                           and not _QA_MARKER.match(line)})[:6]
    return {"source_type": kind, "speakers": speakers, "reason": ""}


# ---------------------------------------------------------------------------
# Heuristic statement extraction over chunk plan (explicitly limited)
# ---------------------------------------------------------------------------
# Sentence boundary, zero-width so the terminator stays attached to the sentence
# that ends with it (quotes must remain verbatim substrings).
# CJK terminators are unambiguous and always split. An ASCII `.`/`!`/`?` only
# ends a sentence when followed by whitespace or the end of the text: otherwise
# it belongs to a URL, filename, version or decimal (`substackcdn.example`,
# `...kL9.png`, `3.14`). Splitting there shreds the token into fragments that
# read as opaque machine lines and then trip the content-safety tripwire.
#
# A newline is a structural boundary too.  The splitter below works on the
# original string rather than a cleaned copy, so offsets remain coordinates in
# normalized ORIGINAL text.  Fenced blocks and a leading YAML frontmatter block
# are skipped as structure before punctuation splitting.
_FENCE_OPEN = re.compile(r"\A\s*(?P<mark>`{3,}|~{3,}).*\Z")
_FENCE_CLOSE = re.compile(r"\A\s*(?P<mark>`{3,}|~{3,})\s*\Z")

# These markers identify an image/embedded-media payload, including the
# percent-encoded JSON emitted by several web clippers.  They are deliberately
# narrower than a URL check: a normal prose sentence containing a citation URL
# remains eligible for extraction.
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]\r\n]*\]\([^\r\n]*\)", re.I)
_MARKDOWN_IMAGE_START = re.compile(r"!\[[^\]\r\n]*\]\(\s*(?:https?://|data:|/)", re.I)
_MEDIA_JSON_FIELD = re.compile(
    r"(?:%22|[\"'])(?:src(?:NoWatermark)?|fullscreen|imageSize|resizeWidth|"
    r"bytes|alt|title|type|href|belowTheFold|topImage|internalRedirect|"
    r"isProcessing|align|height|width)(?:%22|[\"'])\s*[:=]",
    re.I,
)
_MEDIA_HINT = re.compile(
    r"(?:!\[|%7B%22|(?:(?:\A|\.)(?:png|jpe?g|gif|webp|svg))(?:%22|[\"')?#]|$)|"
    r"(?:image|video)/(?:png|jpe?g|gif|webp|svg)\b)",
    re.I,
)


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _append_sentence(results: list[tuple[int, str]], text: str,
                     start: int, end: int) -> None:
    start, end = _trimmed_span(text, start, end)
    if start < end:
        results.append((start, text[start:end]))


def _split_line_sentences(text: str, start: int, end: int,
                          results: list[tuple[int, str]]) -> None:
    """Split one physical line without touching URL/version punctuation."""
    sentence_start = start
    for pos in range(start, end):
        char = text[pos]
        boundary = char in "。！？；"
        if char in ".!?":
            next_pos = pos + 1
            # ASCII punctuation only ends a sentence at whitespace/end.  A
            # period in a domain, filename, version or decimal is preserved.
            boundary = next_pos == end or text[next_pos].isspace()
        if boundary:
            _append_sentence(results, text, sentence_start, pos + 1)
            sentence_start = pos + 1
    _append_sentence(results, text, sentence_start, end)


def sentence_chunks(text: str) -> list[tuple[int, str]]:
    """Return sentence-like slices with exact offsets into ``text``.

    Newlines are boundaries; no normalization, URL decoding, or whitespace
    rewriting is performed before binding offsets.  Leading frontmatter and
    fenced code are structural and therefore produce no candidate slices.
    """
    results: list[tuple[int, str]] = []
    line_start = 0
    in_frontmatter = False
    seen_content = False
    fence = ""
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line_start = offset
        offset += len(raw_line)
        line = raw_line.rstrip("\r\n")
        line_end = line_start + len(line)
        stripped = line.strip()
        if not seen_content and stripped:
            seen_content = True
            if stripped == "---":
                in_frontmatter = True
                continue
        if in_frontmatter:
            if stripped in {"---", "..."}:
                in_frontmatter = False
            continue
        if fence:
            closing = _FENCE_CLOSE.fullmatch(line)
            if closing:
                mark = closing.group("mark")
                if mark[0] == fence[0] and len(mark) >= len(fence):
                    fence = ""
            continue
        opening = _FENCE_OPEN.match(line)
        if opening:
            fence = opening.group("mark")
            continue
        content_start, content_end = _trimmed_span(text, line_start, line_end)
        if content_start < content_end and not text[content_start:].startswith("#"):
            _split_line_sentences(text, content_start, content_end, results)
    return results


def keyword_score(sentence: str) -> int:
    return 2 * len(_NUMBER.findall(sentence)) + min(len(sentence), 220) // 80


def _is_noise(sentence: str) -> bool:
    """Frontmatter/heading/markup lines are structure, not information units."""
    if "\n" in sentence or sentence.startswith(("---", "#", "![", "[![")):
        return True
    if re.match(r"\A[a-zA-Z_]+\s*:", sentence):
        return True
    # Do not turn clipped image markup or encoded media JSON into a fact.  The
    # check is intentionally independent of URL presence, so prose citations
    # such as ``据 https://example.org/report`` remain eligible.
    if _MARKDOWN_IMAGE.search(sentence) or _MARKDOWN_IMAGE_START.search(sentence):
        return True
    if re.fullmatch(r"(?:https?://|https?%3a%2f%2f|www\.)\S+", sentence, re.I):
        return True
    if re.fullmatch(r"(?:<[^>]*>\s*)+", sentence):
        return True  # e.g. an empty <video src=...></video> embed
    without_links = re.sub(r"\[[^\]\n]*\]\([^\)\n]*\)", "", sentence)
    if without_links != sentence and not without_links.strip(" \t-*#>()[]（）,，;；"):
        return True  # a navigation/reference-only line is not an assertion
    media_fields = _MEDIA_JSON_FIELD.findall(sentence)
    if media_fields and (_MEDIA_HINT.search(sentence)
                         or (len(media_fields) >= 2 and "%22" in sentence)):
        return True
    # An isolated opaque machine line is not an attributable information unit.
    # Real case: sentence splitting cuts a percent-encoded URL fragment out of a
    # markdown image link (`.../https%3A%2F%2F...s3.amazonaws.<fragment>.png`).
    # Percent-encoding hides the `/` that would normally exempt a URL, so the
    # fragment reads as a bare token and would otherwise be emitted as a "key
    # fact" -- and then trip the content-safety tripwire downstream.
    return suspicious_machine_line(sentence)


def extract_info_units(norm_text: str, chunk_plan: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """Pure helper: attributable information units with ORIGINAL-text coordinates.

    Exposed for later integration (seed/runtime workers); quote text is the
    exact normalized substring, so each unit can be re-verified later.
    """
    units: list[tuple[int, dict[str, Any]]] = []
    seen_quotes: set[str] = set()
    chunks = chunk_plan["chunks"]
    if not chunks:
        return []
    # Preserve structural context across chunks (especially code/media). Only
    # inspect the bounded read prefix and accept whole sentences contained in
    # an actual chunk, never a clipped fragment or an excluded source range.
    chunk_index = 0
    for offset, sentence in sentence_chunks(norm_text[:chunks[-1]["end"]]):
        end = offset + len(sentence)
        while chunk_index < len(chunks) and chunks[chunk_index]["end"] <= offset:
            chunk_index += 1
        if chunk_index >= len(chunks):
            break
        chunk = chunks[chunk_index]
        if offset < chunk["start"] or end > chunk["end"]:
            continue
        if len(sentence) < 18 or sentence in seen_quotes or _is_noise(sentence):
            continue
        seen_quotes.add(sentence)
        units.append((keyword_score(sentence), {
            "text": sentence,
            "quote": sentence,
            "start": offset,
            "end": end,
            "start_line": norm_text.count("\n", 0, offset) + 1,
            "end_line": norm_text.count("\n", 0, end - 1) + 1,
            "verified": True,
            "kind": "assertion",
            "chunk": chunk["index"],
        }))
    units.sort(key=lambda item: (-item[0], item[1]["start"]))
    return [item[1] for item in units[:limit]]


# ---------------------------------------------------------------------------
# Quality assessment: source-specific, never a generic "no obvious issues"
# ---------------------------------------------------------------------------
def assess_quality(source_type: str, speakers: list[str], norm_text: str,
                   metadata: dict[str, Any] | None) -> list[str]:
    meta = metadata if isinstance(metadata, dict) else {}
    flags: list[str] = []
    cited = bool(normalize_source_list(meta.get("sources") or meta.get("source")))
    numbers = len(_NUMBER.findall(norm_text))
    if source_type in ("ai-synthesis", "oral-case", "unknown"):
        flags.append(f"来源类型为 {source_type}，其中出现的数字与结论未经独立来源核实。"
                     if numbers else
                     f"来源类型为 {source_type}，内容可靠性未经独立来源核实。")
    if source_type == "ai-synthesis" and not cited:
        flags.append("AI 合成/生成内容未标注任何引用来源，事实性陈述不可直接采信。")
    if source_type == "oral-case":
        flags.append("口述/内部案例为当事人转述，结果与数字均为单方陈述，需交叉核实。")
        if speakers:
            flags.append("口述者：" + "、".join(speakers) + "；身份未经核实。")
    if source_type == "dialogue" and not speakers:
        flags.append("对话记录缺少可辨认的说话人标注，角色归属待人工确认。")
    if source_type in ("article", "unknown") and numbers and not cited and not has_citation_markers(norm_text):
        flags.append("正文包含数字/数据但无引用或出处标记，数字按未核实处理。")
    if not norm_text.strip():
        flags.append("源文本为空或不可读，无法进行任何分析。")
    return flags


_SPEAKER_CANDIDATE = re.compile(
    r"\A(?:[-*+]\s*)?(?:\*\*)?([^*\n：:]{1,32}?)(?:\*\*)?\s*[：:](?P<rest>.*)\Z",
    re.S,
)


def _frontmatter_lines(lines: list[str]) -> set[int]:
    """Return 1-based lines inside a leading YAML frontmatter block."""
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None or lines[first].lstrip("\ufeff").strip() != "---":
        return set()
    result: set[int] = set()
    for i in range(first, len(lines)):
        result.add(i + 1)
        if i > first and lines[i].strip() == "---":
            break
    return result


def _parse_speaker_candidate(line: str) -> dict[str, Any] | None:
    """Parse a possible label without deciding whether it is a speaker.

    Deciding from syntax alone is the bug this parser fixes: metadata, URLs and
    ordinary title lines all have the same ``label: value`` shape as dialogue.
    """
    stripped = line.strip()
    if not stripped or stripped == "---" or stripped.startswith("#"):
        return None
    match = _SPEAKER_CANDIDATE.match(stripped)
    if not match:
        return None
    label = match.group(1).strip(" *\t")
    rest = match.group("rest").strip()
    if not label:
        return None
    lowered = label.casefold()
    url = lowered in {"http", "https", "www"} and rest.startswith("//")
    qa = lowered in {"q", "a", "问", "答"}
    unknown = lowered in _UNKNOWN_SPEAKER_LABELS
    metadata = lowered in _METADATA_LABELS
    bold = stripped.startswith("**") and "**" in stripped[2:]
    return {"label": label, "rest": rest, "url": url, "qa": qa,
            "unknown": unknown, "metadata": metadata, "bold": bold}


def _looks_like_dialogue_turn(candidate: dict[str, Any]) -> bool:
    """Return whether a plain label has sentence-shaped turn content.

    Two adjacent plain labels are enough to preserve a short dialogue, but a
    title pair can have the same ``label: value`` syntax. Requiring ordinary
    sentence punctuation for that compact form keeps title/colon prose
    conservative without maintaining a name allowlist. Bold and Q/A labels
    already carry explicit dialogue structure and bypass this check.
    """
    rest = str(candidate.get("rest", "")).strip()
    if not rest:
        return False
    closing = "」』”’\"'）)]】》"
    return bool(re.search(rf"[。！？!?；;.](?:[{re.escape(closing)}])?$", rest))


def _speaker_events(text: str) -> tuple[list[str], dict[int, dict[str, Any]]]:
    """Find conservative speaker events and structural boundaries.

    A plain colon line is accepted only when it participates in a short run of
    labels (or is bold/Q-A formatted). This keeps genuine named dialogue while
    leaving isolated headings and prose labels untrusted. Unknown markers and
    structural lines clear the active speaker so attribution cannot bleed over
    a section boundary.
    """
    lines = normalized_text(text).split("\n")
    frontmatter = _frontmatter_lines(lines)
    candidates: dict[int, dict[str, Any]] = {}
    events: dict[int, dict[str, Any]] = {}
    for line_no, line in enumerate(lines, 1):
        parsed = _parse_speaker_candidate(line)
        if line_no in frontmatter or line.lstrip().startswith("#") or line.strip() == "---":
            events[line_no] = {"kind": "boundary"}
        if parsed is None:
            continue
        # Metadata and URLs are boundaries even outside a well-formed YAML
        # block; they must never activate or inherit a speaker.
        if line_no in frontmatter or parsed["metadata"] or parsed["url"]:
            events[line_no] = {"kind": "boundary"}
            continue
        if parsed["unknown"]:
            events[line_no] = {"kind": "unknown"}
            continue
        candidates[line_no] = parsed

    # Group labels only when every line between them is blank. Ordinary prose,
    # metadata, headings, and other structural events break the run, which
    # prevents a title from activating a later diary paragraph.
    runs: list[list[int]] = []
    for line_no in sorted(candidates):
        previous = runs[-1][-1] if runs else None
        between = lines[previous:line_no - 1] if previous is not None else []
        if (previous is None or line_no - previous > 2
                or any(line.strip() for line in between)
                or any(events.get(i, {}).get("kind") in {"boundary", "unknown"}
                       for i in range(previous + 1, line_no))):
            runs.append([line_no])
        else:
            runs[-1].append(line_no)
    valid: set[int] = set()
    for run in runs:
        run_candidates = [candidates[line_no] for line_no in run]
        labels = [candidate["label"].casefold() for candidate in run_candidates]
        repeated = {label for label in labels if labels.count(label) >= 2}
        # An adjacent/blank-only run of sentence-shaped labels is a bounded
        # structural dialogue signal. This deliberately accepts two-turn
        # conversations while keeping isolated colon headings unknown.
        if len(run) >= 2 and all(_looks_like_dialogue_turn(candidate)
                                 for candidate in run_candidates):
            valid.update(run)
        elif repeated and all(_looks_like_dialogue_turn(candidate)
                              for candidate in run_candidates):
            valid.update(run)
        for line_no in run:
            if candidates[line_no]["bold"] or candidates[line_no]["qa"]:
                valid.add(line_no)
    for line_no, candidate in candidates.items():
        # Structural events always win over candidate classification, even if
        # a future parser extension makes a structural line look label-like.
        if line_no in valid and events.get(line_no, {}).get("kind") not in {"boundary", "unknown"}:
            events[line_no] = {"kind": "speaker", "speaker": candidate["label"]}
        else:
            # An isolated colon line is a structural boundary, not a speaker.
            events[line_no] = {"kind": "boundary"}
    return lines, events


def speaker_map(text: str) -> dict[int, str | None]:
    """Return the verified active speaker for each normalized 1-based line."""
    lines, events = _speaker_events(text)
    del lines  # retained in the helper result for clarity/debugging above
    speakers: dict[int, str | None] = {}
    current: str | None = None
    for line_no in range(1, len(normalized_text(text).split("\n")) + 1):
        event = events.get(line_no)
        if event and event["kind"] == "speaker":
            current = event["speaker"]
        elif event and event["kind"] in {"boundary", "unknown"}:
            current = None
        speakers[line_no] = current
    return speakers


def _explicit_speaker_lines(text: str) -> list[str]:
    lines, events = _speaker_events(text)
    return [lines[line_no - 1] for line_no, event in sorted(events.items())
            if event.get("kind") == "speaker"]


def _speaker_name(line: str) -> str:
    name = re.sub(r"^[#\s]+", "", line).lstrip("*").split("：", 1)[0].split(":", 1)[0]
    return name.strip("*").strip()


def has_citation_markers(text: str) -> bool:
    # A literal mention of 来源 (e.g. 无外部来源) does not prove a citation.
    return bool(_CITATION_MARKER.search(text[:6000]))


def normalize_source_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


# ---------------------------------------------------------------------------
# Topic hints: derived from model extraction and validated, never invented
# ---------------------------------------------------------------------------
def valid_topics(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    topics: list[dict[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title", entry.get("topic_title"))
        if not isinstance(title, str) or not title.strip():
            continue
        content = entry.get("content", entry.get("topic_stub_content", ""))
        topics.append({"title": title.strip()[:64],
                       "content": content.strip() if isinstance(content, str) else ""})
    return topics[:3]


def topic_candidates(cfg: dict[str, Any] | None) -> list[tuple[str, str, tuple[str, ...]]]:
    """Config-driven topic rules; no hardcoded demo corpus (see M0 review)."""
    specs = (cfg or {}).get("heuristic_topics")
    if not isinstance(specs, list):
        return []
    candidates: list[tuple[str, str, tuple[str, ...]]] = []
    for spec in specs:
        if not isinstance(spec, dict) or not spec.get("title"):
            continue
        markers = tuple(str(m) for m in (spec.get("match_any") or []) if str(m).strip())
        candidates.append((str(spec["title"]), str(spec.get("content") or ""), markers))
    return candidates


def infer_topics(title: str, text: str, cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Heuristic fallback hints: explicitly limited, plain pending text only."""
    hay = f"{title}\n{text}"
    topics: list[dict[str, str]] = []
    for title_candidate, content, markers in topic_candidates(cfg):
        if markers and sum(1 for marker in markers if marker in hay) >= 2:
            topics.append({"title": title_candidate, "content": content})
    if not topics:
        # Keep single spaces: collapsing ALL whitespace turned an ordinary title
        # into a space-free token that reads as an opaque machine line
        # ("Amazon Just Killed 50,000 Human Voices" -> "AmazonJustKilled50,000HumanVoices")
        # and tripped the content-safety tripwire.
        short = re.sub(r"\s+", " ", title).strip(" -_")[:32].strip() or "资料待整理专题"
        topics.append({
            "title": short,
            "content": "启发式回退：仅按标题占位，未经语义提取，需人工确认专题边界。",
        })
    return topics[:3]


# ---------------------------------------------------------------------------
# Coverage bookkeeping
# ---------------------------------------------------------------------------
def merge_chunk_plan(chunk_plan: dict[str, Any], failed_chunks: list[int],
                     skipped_chunks: list[int]) -> dict[str, Any]:
    """Coverage = successfully ANALYZED ranges; failures are explicit ranges."""
    error_ranges = [c for c in chunk_plan["chunks"] if c["index"] in failed_chunks]
    skipped = [c for c in chunk_plan["chunks"] if c["index"] in skipped_chunks]
    return {
        "read_ranges": [{"start": c["start"], "end": c["end"]}
                        for c in chunk_plan["chunks"]
                        if c["index"] not in failed_chunks and c["index"] not in skipped_chunks],
        "error_ranges": [{"start": c["start"], "end": c["end"]} for c in error_ranges],
        "excluded_ranges": chunk_plan["excluded_ranges"] + [{"start": c["start"], "end": c["end"]}
                                                           for c in skipped],
        "planned_ranges": [{"start": c["start"], "end": c["end"]} for c in chunk_plan["chunks"]],
        "coverage": "full" if not failed_chunks and not skipped and not chunk_plan["excluded_ranges"] else "partial",
        "total_chars": chunk_plan["total_chars"],
        "read_chars": sum(r["end"] - r["start"] for r in
                          [{"start": c["start"], "end": c["end"]} for c in chunk_plan["chunks"]
                           if c["index"] not in failed_chunks and c["index"] not in skipped_chunks]),
    }


def source_limitations(mode: str, coverage_info: dict[str, Any]) -> list[str]:
    """Mode-specific, honest limitations."""
    out: list[str] = []
    read = coverage_info.get("read_chars", 0)
    total = coverage_info.get("total_chars", 0)
    if mode == "llm":
        out.append(f"分析模式为 LLM 分块语义提取，片段结论由程序在原文中逐字核验；覆盖 {read}/{total} 字符（normalized）。"
                   "核验只证明片段确实出现在原文，不证明陈述为事实。")
    elif mode == "heuristic":
        out.append(f"分析模式为启发式程序规则，不包含语义理解；覆盖 {read}/{total} 字符（normalized）。")
    elif mode == "heuristic-fallback":
        out.append(f"分析模式为 LLM 失败后的启发式回退，不包含语义理解；已分析覆盖 {read}/{total} 字符（normalized）。")
    for entry in coverage_info.get("excluded_ranges", []):
        out.append(f"未读取范围：字符 [{entry['start']}, {entry['end']})。")
    for entry in coverage_info.get("error_ranges", []):
        out.append(f"分析失败范围：字符 [{entry['start']}, {entry['end']})；该范围内无可靠结论。")
    return out


def analysis_fingerprint(coverage: str, excluded_ranges: list[dict[str, int]]) -> str:
    """Stable fingerprint of an analysis run's coverage claim (for reports)."""
    return digest(f"{coverage}\0{excluded_ranges}")[:12]


# ---------------------------------------------------------------------------
# Model chunk-response verification (program side)
# ---------------------------------------------------------------------------
def plain_text(value: str) -> str:
    """Neutralize wikilinks in model/heuristic free text before rendering.

    Only the explicit actual source path is linkable from this producer; pending
    concepts stay literal text. Verification quotes are never passed through
    this function.
    """
    if not isinstance(value, str):
        return value
    return value.replace("[[", "［［").replace("]]", "］］")


def _nearest_speaker_label(norm_text: str, quote_start: int, chunk_start: int) -> str | None:
    """Return the active verified dialogue label at the quote position.

    Attribution must match the active explicit label, including a label on the
    same line as the quote. Structural metadata/headings and unknown markers
    clear the state; they are never returned as speakers.
    """
    del chunk_start  # retained in the callable interface for compatibility
    line_no = norm_text.count("\n", 0, max(0, quote_start)) + 1
    return speaker_map(norm_text).get(line_no)


def _statement_entry(entry: Any) -> dict[str, Any]:
    """Validate one model statement WITHOUT stringifying malformed objects."""
    if isinstance(entry, str):
        text = entry.strip()
        if not text:
            raise SourceAnalysisError("信息单元文本不能为空")
        return {"text": text, "quote": text, "kind": "assertion", "speaker": None}
    if not isinstance(entry, dict):
        raise SourceAnalysisError(f"每条信息单元必须是字符串或对象，收到：{type(entry).__name__}")
    text = entry.get("text")
    if not isinstance(text, str) or not text.strip():
        raise SourceAnalysisError("每条信息单元必须包含非空字符串 text")
    quote = entry.get("quote", text)
    if quote is None:
        quote = text
    if not isinstance(quote, str):
        raise SourceAnalysisError("quote 必须是字符串")
    kind = entry.get("kind", "assertion")
    if not isinstance(kind, str) or kind not in STATEMENT_KINDS:
        raise SourceAnalysisError(f"kind 只能是 {'/'.join(STATEMENT_KINDS)}：{kind!r}")
    speaker = entry.get("speaker")
    if speaker is not None and not isinstance(speaker, str):
        raise SourceAnalysisError("speaker 必须是字符串或 null")
    start_line = entry.get("start_line")
    if start_line is not None and type(start_line) is not int:
        raise SourceAnalysisError("start_line 必须是整数或 null")
    return {"text": text.strip(), "quote": quote, "kind": kind,
            "speaker": speaker.strip() if isinstance(speaker, str) and speaker.strip() else None,
            "start_line": start_line}


def merge_llm_chunk_result(chunk: dict[str, Any], parsed: Any, norm_text: str,
                           flags: list[str], errors: list[str]) -> dict[str, Any]:
    """Program-side verification of one model chunk response.

    Quotes must be located in the ORIGINAL normalized text INSIDE the supplied
    chunk; an invalid, ambiguous or out-of-chunk quote is marked unusable, never
    'verified'. kind is attribution only, never factual verification. Speaker is
    kept per unit and checked against the quoted context.
    """
    if not isinstance(parsed, dict):
        raise SourceAnalysisError("模型响应必须是 JSON 对象")
    # ── Explicit zero contract (chunk_viable) ────────────────────────────
    # A read chunk with no independently useful information MUST say so:
    # chunk_viable=false + nonempty reason + EMPTY key_statements/topics.
    # Compatibility: chunk_viable may be omitted when valid units exist.
    # Missing/malformed key_statements, absent viability with zero units, or
    # a contradictory false+candidates response is an ERROR, never a zero.
    viable = parsed.get("chunk_viable")
    # PRESENCE matters: a present flag must be an EXACT boolean. null/str/int
    # are malformed; only genuine omission is backward compatible.
    if "chunk_viable" in parsed and type(viable) is not bool:
        raise SourceAnalysisError(
            f"chunk_viable 为显式提供时必须是精确布尔值，收到：{viable!r}")
    raw_reason = parsed.get("reason")
    zero_reason = raw_reason.strip() if isinstance(raw_reason, str) and raw_reason.strip() else None
    statements = parsed.get("key_statements", parsed.get("key_facts", []))
    if not isinstance(statements, list):
        raise SourceAnalysisError("key_statements 必须是数组")
    topics_raw = parsed.get("topics")
    if viable is False:
        if not zero_reason:
            raise SourceAnalysisError("chunk_viable=false 必须附非空 reason，否则不是合法零")
        if statements or topics_raw:
            raise SourceAnalysisError("chunk_viable=false 与非空候选相互矛盾，按错误处理")
        limitations = [plain_text(str(x)) for x in parsed.get("limitations", []) if isinstance(x, str)]
        return {"units": [], "limitations": limitations, "topics": [], "summary": "",
                "chunk_outcome": "zero", "zero_reason": zero_reason}
    if viable is None and not statements:
        raise SourceAnalysisError("缺少 chunk_viable 且无任何候选，无法区分合法零与格式错误")
    if viable is True and not statements:
        raise SourceAnalysisError("chunk_viable=true 但无任何候选，不是可接受的零")
    units: list[dict[str, Any]] = []
    for entry in statements:
        try:
            entry = _statement_entry(entry)
        except SourceAnalysisError as exc:
            errors.append(f"第 {chunk['index'] + 1} 块信息单元格式非法，已丢弃：{safe_short(exc)}")
            continue
        text, quote = entry["text"], entry.get("quote", entry["text"])
        unit: dict[str, Any] = {
            "text": text, "quote": quote, "kind": entry["kind"],
            "speaker": entry.get("speaker"), "chunk": chunk["index"], "verified": False,
        }
        try:
            located = locate_quote(norm_text, quote, entry.get("start_line"))
            if located["start"] < chunk["start"] or located["end"] > chunk["end"]:
                raise SourceAnalysisError(
                    f"引用位于所提供片段之外（引用 [{located['start']}, {located['end']})，"
                    f"片段 [{chunk['start']}, {chunk['end']})），按模型幻觉处理")
            unit.update(located)
            unit["verified"] = True
            unit["quote"] = norm_text[located["start"]:located["end"]]
            speaker = unit.get("speaker")
            nearest = _nearest_speaker_label(norm_text, located["start"], chunk["start"])
            if speaker:
                if nearest is None:
                    flags.append(f"第 {chunk['index'] + 1} 块说话人标注「{speaker}」：原文没有可核验的说话人标签，"
                                 f"按未知说话人处理并需人工复核：{text[:40]}")
                    unit["speaker_unverified"] = speaker
                    unit["speaker"] = None  # uncertain prose is never attributed
                elif speaker.casefold() != nearest.casefold():
                    flags.append(f"第 {chunk['index'] + 1} 块说话人标注「{speaker}」与上下文当前"
                                 f"说话人「{nearest}」不符，按未知说话人处理并需人工复核：{text[:40]}")
                    unit["speaker_mismatch"] = nearest
                    unit["speaker"] = None  # untrusted attribution is never persisted
                else:
                    unit["speaker_verified"] = True
            elif nearest is not None:
                # A source label is stronger evidence than an omitted model
                # field; keep the explicit label without guessing on prose.
                unit["speaker"] = nearest
                unit["speaker_verified"] = True
        except SourceAnalysisError as exc:
            unit["unusable_reason"] = str(exc)
            flags.append(f"第 {chunk['index'] + 1} 块引用不可核验，已标记为不可用，不得作为已验证证据：{text[:40]}")
        units.append(unit)
    # Sanitize free-text model output (statements/topics/summary/limitations):
    # no model text may create wikilinks; verification quotes stay verbatim.
    for unit in units:
        unit["text"] = plain_text(unit["text"])
    limitations = [plain_text(str(x)) for x in parsed.get("limitations", []) if isinstance(x, str)]
    for flag in parsed.get("quality_flags", []):
        if isinstance(flag, str) and flag.strip():
            flags.append(f"第 {chunk['index'] + 1} 块质量标记：{plain_text(flag.strip())}")
    topics = valid_topics(parsed.get("topics"))
    for topic in topics:
        topic["title"] = plain_text(topic["title"])
        topic["content"] = plain_text(topic["content"])
    return {"units": units, "limitations": limitations,
            "topics": topics,
            "summary": plain_text(str(parsed.get("summary", "")).strip()),
            "chunk_outcome": "ok", "zero_reason": None}


def safe_short(exc: Exception) -> str:
    return str(exc)[:120]
