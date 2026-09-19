from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_contract import extract_json, validate_contract
from .llm import LLMError, call_chat_completion, mock_skill_response
from .renderer import render_previews
from .skill_loader import build_system_prompt, load_skill
from .validator import canonicalize_related_links, validate_skill_items


def run_skill_runtime(
    root: Path,
    cfg: dict[str, Any],
    skill_name: str,
    task: str,
    documents: list[dict[str, str]],
    *,
    mock: bool = False,
) -> dict[str, Any]:
    spec = load_skill(root, skill_name)
    contract = {
        "top_level": "items",
        "required_item_keys": [
            "title",
            "type",
            "status",
            "stage",
            "sources",
            "summary",
            "confidence",
            "review_required",
        ],
        "required_item_types": {
            "title": "string（单行）",
            "type": "string，固定 topic-card" if skill_name == "topic-insight-miner" else "string，遵循当前 Skill 的页面类型",
            "status": "string",
            "stage": "string",
            "sources": "array<string>，必须是本次提供文档的完整相对路径",
            "summary": "string",
            "confidence": "string，low|medium|high",
            "review_required": "boolean",
        },
        "optional_item_types": {
            "one_sentence_topic": "string",
            "tension": "string",
            "why_now": "array<string>",
            "signals": "array<string>",
            "angles": "array<string>",
            "risks": "array<string>",
            "gaps": "array<string>",
            "manual_review": "array<string>",
            "score": "string",
            "related": "array<string>，只能填本次提供文档的链接，禁止编造",
            "pending_links": "array<string>，想引但知识库中不存在的目标写这里",
        },
        "type_rules": [
            "array<string> 字段必须返回 JSON 数组，每项一个短句；禁止把整段文字塞进数组或写成单个字符串。",
            "没有内容的可选字段请省略；数组可用 []，字符串可用空字符串，不要混用类型。",
        ],
        "forbidden": ["source", "full_article", "draft_article"],
    }
    payload = {
        "task": task,
        "skill": skill_name,
        "output_contract": contract,
        "documents": documents,
    }
    try:
        if mock:
            data = mock_skill_response(skill_name, task, documents)
            raw_text = json.dumps(data, ensure_ascii=False)
        else:
            raw_text = call_chat_completion(cfg, build_system_prompt(spec, contract), payload)
            data = extract_json(raw_text)
    except (LLMError, json.JSONDecodeError, FileNotFoundError, KeyError) as exc:
        return {
            "enabled": True,
            "mock": mock,
            "skill": skill_name,
            "skill_path": str(spec.path) if "spec" in locals() else "",
            "ok": False,
            "issues": [str(exc)],
            "items": [],
            "previews": [],
        }

    issues = validate_contract(data)
    if not issues:
        canonicalize_related_links(data, documents)
        issues.extend(validate_skill_items(data, documents))
    return {
        "enabled": True,
        "mock": mock,
        "skill": skill_name,
        "skill_path": str(spec.path),
        "ok": not issues,
        "issues": issues,
        "items": data.get("items", []) if isinstance(data, dict) else [],
        "previews": render_previews(data) if not issues else [],
        "raw_chars": len(raw_text),
    }
