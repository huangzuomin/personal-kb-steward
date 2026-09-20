"""Conservative credential tripwires for model input and generated artifacts.

This is not a DLP system or a claim that arbitrary private data is safe. Rules
never rewrite source files, never report the matched value, and never treat a
public IP/domain alone as a credential. Configuration/auth headers are not input
content and must not be passed to this checker.
"""
from __future__ import annotations

import re
from typing import Any


class SensitiveContentError(ValueError):
    """Content needs local inspection before external processing or publication."""


_KEY = r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|password|passwd|secret|client[_-]?secret)"
_KEY_NAME = re.compile(rf"^{_KEY}$", re.I)
_ASSIGNMENT = re.compile(
    rf"(?<![\w-]){_KEY}[\"']?\s*[:=]\s*(?:[\"']([^\"'\r\n]+)[\"']|([^\s,;\"'`]+))", re.I,
)
_TOKEN = re.compile(
    r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    r"AKIA[A-Z0-9]{16}|github_pat_[A-Za-z0-9_]{30,})\b"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")
_BEARER = re.compile(r"\bBearer\s+([A-Za-z0-9._~+/-]{16,}=*)", re.I)
_PLACEHOLDERS = {"...", "…", "redacted", "[redacted]", "<redacted>", "none", "null"}


def _literal_value(value: str) -> bool:
    value = value.strip()
    return bool(value) and not (
        value.casefold() in _PLACEHOLDERS
        or re.fullmatch(r"\*+", value)
        or re.fullmatch(r"<[^<>\r\n]+>", value)
        or re.fullmatch(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%[A-Za-z_][A-Za-z0-9_]*%", value)
    )


def suspicious_machine_line(text: str) -> bool:
    """Detect isolated opaque strings, not hashes, UUIDs, versions or prose."""
    text = text.strip().strip('`')
    if re.fullmatch(r"\.?iZ[A-Za-z0-9]{8,}", text):
        return True
    if not re.fullmatch(r"[\x21-\x7e]{12,128}", text):
        return False
    if re.search(r"[/\\:=]|\.(?:md|png|jpe?g|gif|webp|pdf|json|py|txt)$", text, re.I):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z_-]*v?\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.-]+)?", text):
        return False
    if re.fullmatch(r"[A-Fa-f0-9-]+", text):
        return False
    return all(re.search(p, text) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))


def sensitive_reason(text: str) -> str | None:
    """Return a rule code only; do not return the value or an excerpt."""
    if _PRIVATE_KEY.search(text):
        return "private_key"
    if _TOKEN.search(text):
        return "credential_token"
    if any(_literal_value(m.group(1)) for m in _BEARER.finditer(text)):
        return "bearer_token"
    if any(_literal_value(m.group(1) or m.group(2)) for m in _ASSIGNMENT.finditer(text)):
        return "credential_assignment"
    if any(suspicious_machine_line(line) for line in text.splitlines()):
        return "opaque_machine_line"
    return None


def assert_safe_content(value: Any) -> None:
    """Inspect JSON-like content without mutating it or leaking it in errors."""
    if isinstance(value, str):
        reason = sensitive_reason(value)
        if reason:
            raise SensitiveContentError(
                f"敏感内容检查阻断：{reason}；请在本地复核输入，未输出命中值。"
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            if (isinstance(key, str) and _KEY_NAME.fullmatch(key)
                    and (type(item) in {int, float} or isinstance(item, str) and _literal_value(item))):
                raise SensitiveContentError("敏感内容检查阻断：credential_field；请在本地复核输入，未输出命中值。")
            assert_safe_content(key)
            assert_safe_content(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_safe_content(item)


def safe_error_message(exc: BaseException) -> str:
    """Keep diagnostics useful but omit bodies containing a known tripwire."""
    message = str(exc)
    return f"{type(exc).__name__}: [敏感错误详情已省略]" if sensitive_reason(message) else f"{type(exc).__name__}: {message}"
