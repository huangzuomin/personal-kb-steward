from __future__ import annotations

import json
import re
from typing import Any

from core.llm import call_chat_completion
from renderer import render


BOILERPLATE_PATTERNS = (
    "当前位置",
    "责任编辑",
    "来源：",
    "分享到",
    "扫一扫",
    "广告",
    "版权",
    "ICP备案",
)


def clean_body(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in {"---", "```", "```zh"}:
            continue
        if line.startswith(("#", "![", "[![")):
            continue
        if line.startswith("[") and "](" in line and len(line) < 180:
            continue
        if any(marker in line for marker in BOILERPLATE_PATTERNS) and len(line) < 220:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    return "\n".join(lines).strip()


def sentence_chunks(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。！？；.!?])\s*", compact)
    return [part.strip() for part in parts if len(part.strip()) >= 18]


def keyword_score(sentence: str) -> int:
    keywords = [
        "人工智能", "AI", "政策", "规划", "产业", "应用", "数据", "算力",
        "模型", "创新", "治理", "企业", "制造", "财政", "文化", "眼镜",
        "示范", "平台", "目标", "亿元", "2025", "2026", "2027",
    ]
    return sum(2 for word in keywords if word in sentence) + min(len(sentence), 220) // 80


def top_sentences(text: str, limit: int = 5) -> list[str]:
    chunks = sentence_chunks(text)
    ranked = sorted(enumerate(chunks), key=lambda item: (-keyword_score(item[1]), item[0]))
    selected = sorted(ranked[:limit], key=lambda item: item[0])
    return [item[1] for item in selected]


def topic_candidates(cfg: dict[str, Any] | None) -> list[tuple[str, str, tuple[str, ...]]]:
    """Heuristic topic rules, read from config instead of a hardcoded corpus.

    Upstream baked a demo vault into this list (city + agency names) and matched
    it with generic words like 政策/规划/产业, so any document containing two of
    those common words was labelled a "温州 AI 政策" topic regardless of what it
    actually said. Rules now live in `cfg["heuristic_topics"]`; with no config
    the only output is the neutral title-derived stub below.
    """
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
    hay = f"{title}\n{text}"
    topics: list[dict[str, str]] = []
    for title_candidate, content, markers in topic_candidates(cfg):
        if markers and sum(1 for marker in markers if marker in hay) >= 2:
            topics.append({"title": title_candidate, "content": content})
    if not topics:
        short = re.sub(r"\s+", "", title).strip(" -_")[:32] or "资料待整理专题"
        topics.append({
            "title": short,
            "content": "该资料包含可继续整理的事实线索，但需要人工确认专题边界。",
        })
    return topics[:3]


def heuristic_analysis(note: dict[str, Any], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    title = str(note.get("title") or "")
    cleaned = clean_body(str(note.get("body") or ""))
    source_text = cleaned or str(note.get("summary") or "").strip()
    signals = top_sentences(source_text, 5)
    summary = " ".join(signals[:3]).strip()
    if not summary:
        summary = str(note.get("summary") or "").strip() or "待人工补充摘要。"
    if len(summary) > 420:
        summary = summary[:420].rstrip("，。；,; ") + "。"
    return {
        "source_summary": summary,
        "topics": infer_topics(title, source_text, cfg),
        "key_facts": signals,
        "quality_flags": [] if cleaned else ["正文清洗后内容不足，可能需要人工复核。"],
        "analysis_mode": "heuristic",
    }


def target_dirs(cfg: dict[str, Any]) -> dict[str, str]:
    """Write targets must come from config.write, never from hardcoded paths."""
    write = cfg.get("write") if isinstance(cfg, dict) else None
    write = write if isinstance(write, dict) else {}
    return {
        "sources_dir": str(write.get("sources_dir") or "_kb-steward/sources").replace("\\", "/").strip("/"),
    }


def execute(context: dict[str, Any]) -> dict[str, Any]:
    notes = context.get("notes", [])
    cfg = context.get("config", {})
    use_llm = context.get("use_llm", True)
    dirs = target_dirs(cfg)

    created = []
    issues = []
    processed = 0

    if not notes:
        return {"skill": "topic-research-compile", "created": [], "issues": issues, "processed": 0}

    system_prompt = """你是一个专业的行业研究员。请阅读这篇长文调研报告/文章，先忽略网页导航、广告、责任编辑、图片链接等噪音，再提取以下信息：
1. 用 150-300 字撰写结构化摘要，必须覆盖主体、行动、场景、目标/数字或影响，不要只复述文章开头。
2. 提炼 1-3 个适合进入知识库的专题名称。
3. 针对每个专题写一段研究边界或核心关注点。
4. 提取 3-6 条关键事实，优先保留时间、机构、政策目标、产业方向、数字。
5. 标记资料质量问题，例如正文疑似网页导航、信息过短、来源不完整。

返回 JSON 格式：
{
  "source_summary": "...",
  "key_facts": ["..."],
  "quality_flags": ["..."],
  "topics": [
    {
      "topic_title": "...",
      "topic_stub_content": "..."
    }
  ]
}
"""

    for note in notes:
        if not use_llm:
            data = heuristic_analysis(note, cfg)
            issues.append(f"未启用 LLM，已使用启发式结构化整理：{note.get('rel')}")
            pages = render({
                "source_rel": note.get("rel"),
                "source_title": note.get("title"),
                "source_summary": data.get("source_summary", ""),
                "topics": data.get("topics", []),
                "key_facts": data.get("key_facts", []),
                "quality_flags": data.get("quality_flags", []),
                "analysis_mode": data.get("analysis_mode", "heuristic"),
                "sources_dir": dirs["sources_dir"],
            })
            created.extend(pages)
            processed += 1
            continue

        cleaned = clean_body(str(note.get("body") or ""))
        text = f"Title: {note.get('title', '')}\n\n{cleaned[:6000]}"
        try:
            resp = call_chat_completion(cfg, system_prompt, {"text": text})
            data = json.loads(resp)
            
            pages = render({
                "source_rel": note.get("rel"),
                "source_title": note.get("title"),
                "source_summary": data.get("source_summary", ""),
                "key_facts": data.get("key_facts", []),
                "quality_flags": data.get("quality_flags", []),
                "analysis_mode": "llm",
                "sources_dir": dirs["sources_dir"],
                "topics": [
                    {"title": t.get("topic_title", ""), "content": t.get("topic_stub_content", "")}
                    for t in data.get("topics", [])
                ]
            })
            created.extend(pages)
            processed += 1
        except Exception as e:
            data = heuristic_analysis(note, cfg)
            issues.append(f"LLM 提炼失败，已降级为启发式整理 {note.get('rel')}: {e}")
            pages = render({
                "source_rel": note.get("rel"),
                "source_title": note.get("title"),
                "source_summary": data.get("source_summary", ""),
                "topics": data.get("topics", []),
                "key_facts": data.get("key_facts", []),
                "quality_flags": [*data.get("quality_flags", []), "LLM 调用失败，当前为启发式结果。"],
                "analysis_mode": "heuristic-fallback",
                "sources_dir": dirs["sources_dir"],
            })
            created.extend(pages)
            processed += 1

    return {
        "skill": "topic-research-compile",
        "created": created,
        "issues": issues,
        "processed": processed,
        "inputs": [note.get("rel") for note in notes if note.get("rel")],
    }
