from __future__ import annotations

import http.client
import json
import math
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .content_safety import assert_safe_content, sensitive_reason
from .llm_retry import is_transient_error, retry_policy


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
    # Scan content, not configuration/authentication. Do this before constructing
    # the request and scan the returned text before callers can log or render it.
    assert_safe_content(system_prompt)
    assert_safe_content(user_payload)
    llm_cfg = cfg.get("llm", {})
    try:
        policy = retry_policy(llm_cfg)
    except ValueError as exc:
        raise LLMError(f"Invalid LLM retry configuration: {exc}") from None
    base_url = os.environ.get("OPENAI_BASE_URL") or llm_cfg.get("base_url") or "https://api.openai.com/v1"
    model = os.environ.get("OPENAI_MODEL") or os.environ.get("LLM_MODEL") or llm_cfg.get("model")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_key_env = llm_cfg.get("api_key_env")
    if not api_key and api_key_env:
        api_key = os.environ.get(str(api_key_env))
    if not model:
        raise LLMError("Missing LLM model. Set OPENAI_MODEL (legacy LLM_MODEL is also accepted) or llm.model.")
    if not api_key:
        raise LLMError("Missing API key. Set OPENAI_API_KEY or llm.api_key_env.")

    try:
        timeout_value = llm_cfg.get("timeout_seconds", 300)
        if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
            raise ValueError("timeout_seconds must be a finite number")
        timeout_seconds = float(timeout_value)
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
    except ValueError as exc:
        raise LLMError(f"Invalid LLM retry/timeout configuration: {exc}") from exc

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
    started = time.monotonic()
    deadline = started + policy.retry_budget_seconds

    for attempt in range(1, policy.max_attempts + 1):
        # Preserve the configured socket timeout for the first attempt when
        # the budget permits it. Later attempts use the remaining budget.
        remaining = (
            policy.retry_budget_seconds
            if attempt == 1 else deadline - time.monotonic()
        )
        if remaining <= 0:
            raise LLMError(
                f"LLM retry budget exhausted before attempt {attempt} "
                f"of {policy.max_attempts}"
            ) from None
        try:
            timeout = min(timeout_seconds, remaining)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw_response = response.read()
            try:
                payload = json.loads(raw_response.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise LLMError("Invalid LLM response JSON; no retry attempted") from None
            break
        except urllib.error.HTTPError as exc:
            if not is_transient_error(exc):
                detail = _http_error_detail(exc, api_key)
                raise LLMError(
                    f"LLM HTTP error {exc.code} on attempt {attempt}/"
                    f"{policy.max_attempts}: {detail}"
                ) from None
            if attempt >= policy.max_attempts:
                detail = _http_error_detail(exc, api_key)
                raise LLMError(
                    f"LLM HTTP error {exc.code} after {attempt} attempts: {detail}"
                ) from None
            _close_http_error(exc)
        except (urllib.error.URLError, OSError,
                http.client.IncompleteRead, socket.timeout) as exc:
            if not is_transient_error(exc):
                detail = _connection_error_detail(exc, api_key)
                raise LLMError(
                    f"LLM connection error on attempt {attempt}/"
                    f"{policy.max_attempts}: {detail}"
                ) from None
            if attempt >= policy.max_attempts:
                detail = _connection_error_detail(exc, api_key)
                raise LLMError(
                    f"LLM connection error after {attempt} attempts: {detail}"
                ) from None

        remaining = deadline - time.monotonic()
        delay = policy.delay_seconds()
        if remaining <= delay:
            raise LLMError(
                f"LLM retry budget exhausted after {attempt} attempts "
                f"(budget {policy.retry_budget_seconds:g}s)"
            ) from None
        if delay:
            time.sleep(delay)
    else:  # pragma: no cover - the loop either returns or raises above
        raise LLMError(f"LLM provider failed after {policy.max_attempts} attempts") from None

    content = _response_content(payload)
    assert_safe_content(content)
    return content


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise LLMError("Invalid LLM response shape: expected an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMError("Invalid LLM response shape: missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict) or "content" not in message:
        raise LLMError("Invalid LLM response shape: missing message content")
    content = message["content"]
    if not isinstance(content, str):
        raise LLMError("Invalid LLM response shape: content must be text")
    return content


def _close_http_error(exc: urllib.error.HTTPError) -> None:
    try:
        exc.close()
    except Exception:
        pass


def _http_error_detail(exc: urllib.error.HTTPError, api_key: str) -> str:
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except Exception:
        detail = ""
    finally:
        _close_http_error(exc)
    if sensitive_reason(detail) or (api_key and api_key in detail):
        return "[provider error body omitted: sensitive content]"
    return detail


def _connection_error_detail(exc: BaseException, api_key: str) -> str:
    reason = getattr(exc, "reason", exc)
    detail = str(reason)
    if sensitive_reason(detail) or (api_key and api_key in detail):
        return "[provider connection detail omitted: sensitive content]"
    return detail or type(reason).__name__
