from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _load_env() -> None:
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


_load_env()


class LLMError(RuntimeError):
    pass


def mock_skill_response(skill: str, task: str, documents: list[dict[str, str]]) -> dict[str, Any]:
    sources = [doc["path"] for doc in documents[:5]]
    title_seed = task.strip() or (documents[0]["title"] if documents else skill)
    type_by_skill = {
        "mindseed-grow": "seed-card",
        "topic-insight-miner": "topic-card",
        "writing-material-pack": "material-pack",
    }
    stage_by_skill = {
        "mindseed-grow": "seed",
        "topic-insight-miner": "candidate",
        "writing-material-pack": "assembling",
    }
    return {
        "items": [
            {
                "title": f"LLM Preview: {title_seed[:48]}",
                "type": type_by_skill.get(skill, "run-report"),
                "status": "manual_review" if not sources else "growing",
                "stage": "needs_context" if not sources else stage_by_skill.get(skill, "growing"),
                "sources": sources,
                "summary": "Mock LLM output for runtime verification. Replace with a real provider by setting API configuration.",
                "signals": [doc["title"] for doc in documents[:3]],
                "related": [],
                "pending_links": [],
                "confidence": "low",
                "review_required": True,
                "manual_review": ["Mock output; human review required before apply."],
            }
        ]
    }


def call_chat_completion(cfg: dict[str, Any], system_prompt: str, user_payload: dict[str, Any]) -> str:
    llm_cfg = cfg.get("llm", {})
    base_url = os.environ.get("OPENAI_BASE_URL") or llm_cfg.get("base_url") or "https://api.openai.com/v1"
    model = os.environ.get("OPENAI_MODEL") or llm_cfg.get("model")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_key_env = llm_cfg.get("api_key_env")
    if not api_key and api_key_env:
        api_key = os.environ.get(str(api_key_env))
    if not model:
        raise LLMError("Missing LLM model. Set OPENAI_MODEL or llm.model.")
    if not api_key:
        raise LLMError("Missing API key. Set OPENAI_API_KEY or llm.api_key_env.")

    body = {
        "model": model,
        "temperature": float(llm_cfg.get("temperature", 0.2)),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(llm_cfg.get("timeout_seconds", 60))) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"LLM connection error: {exc}") from exc
    return payload["choices"][0]["message"]["content"]
