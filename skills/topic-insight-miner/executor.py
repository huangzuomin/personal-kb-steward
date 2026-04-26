from __future__ import annotations

import hashlib
import re

from renderer import render


def slug(text: str) -> str:
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if ascii_part:
        return ascii_part[:72]
    return "topic-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def execute(context: dict) -> dict:
    query = context.get("query", "")
    notes = context.get("notes", [])
    min_sources = int(context.get("config", {}).get("quality_gate", {}).get("min_sources_for_topic", 3))
    sources = [note["rel"] for note in notes[:10]]
    enough = len(sources) >= min_sources
    score = "B" if enough else "C"
    first = notes[0]["title"] if notes else query or "知识库选题"
    item = {
        "title": f"选题卡：{query[:50] or first}",
        "type": "topic-card",
        "status": "growing" if enough else "manual_review",
        "stage": "promising" if enough else "candidate",
        "sources": sources,
        "one_sentence_topic": f"围绕“{query or first}”，从现有 seed/source 中寻找一个可写的具体问题。",
        "tension": " / ".join(note["title"][:24] for note in notes[:3]) or "来源不足，张力尚不明确。",
        "why_now": [
            "知识库中已有多个来源或 seed 指向同一问题。",
            "该问题具备进一步抽取案例、证据链和反方观点的潜力。",
        ] if enough else ["来源不足，当前只能作为候选线索。"],
        "angles": ["机制解释", "案例对比", "方法提炼"],
        "risks": ["不得跳过证据包直接写正式文章。", "需要人工确认是否存在反方或冲突来源。"],
        "gaps": [] if enough else ["来源数量不足", "缺少可引用证据", "缺少反方观点"],
        "score": score,
        "confidence": "medium" if enough else "low",
        "review_required": not enough,
        "related": [],
    }
    return {
        "skill": "topic-insight-miner",
        "pages": [{
            "rel_dir_key": "topics_dir",
            "filename": f"topic-card-{slug(query or first)}.md",
            "content": render(item),
            "sources": sources,
            "item": item,
        }],
        "processed": len(notes),
        "inputs": sources,
        "issues": [] if enough else ["来源不足，生成 manual_review topic-card。"],
        "items": [item],
    }
