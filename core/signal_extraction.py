"""Verbatim seed excerpts with body-line provenance and conservative type filtering.

Line numbers are 1-based in the supplied body, NOT full-file line numbers after
frontmatter removal. This is a small conservative reader, not a full Markdown
parser, semantic assertion extractor or secrecy guarantee.
"""
from __future__ import annotations

import re
import ipaddress
from dataclasses import dataclass

from .content_safety import sensitive_reason, suspicious_machine_line

_ROUTINE = re.compile(r"^(?:每日例程|晨间日记|今日打卡|习惯追踪|暂无|无内容|daily routine|habit tracker)[:：\s]*$", re.I)
_FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_CONFIG = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{2,}\s*=\s*\S+(?:\s*#.*)?$")
_NGINX = re.compile(r"^(?:(?:server|location)\b.*\{|(?:listen|proxy_pass|server_name)\s+[^。！？]+;|[{}];?)$")
_COMMAND = re.compile(r"^(?:\$\s+)?(?:sudo\s+)?(curl|ssh|scp|acme\.sh|cd|systemctl|docker|git|npm|make|screen|nano)\s+(.+)$", re.I)
_COMMAND_ARG = re.compile(r"(?:^|\s)(?:[-/~.]\S*|https?://\S+|\d{1,3}(?:\.\d{1,3}){3}\b|\S+=\S+)")
_SUBCOMMANDS = {
    "git": {"clone", "commit", "push", "pull", "checkout", "switch", "status", "diff"},
    "docker": {"run", "compose", "build", "exec", "pull", "ps"},
    "npm": {"install", "run", "ci", "test"},
    "systemctl": {"start", "stop", "restart", "enable", "status"},
    "make": {"run", "install", "test", "build"},
}


@dataclass(frozen=True)
class SignalExcerpt:
    text: str
    body_line: int


def _unquote(line: str) -> str:
    while line.startswith('>'):
        line = line[1:].lstrip()
    return line


def non_signal_kind(line: str) -> str | None:
    if sensitive_reason(line):
        return "sensitive"
    if re.fullmatch(r"`+[^`]+`+", line):
        return "code"
    if (re.fullmatch(r"https?://\S+", line)
            or re.fullmatch(r"!?\[[^\]]*\]\([^\r\n]+\)", line)
            or re.fullmatch(r"\S+\.(?:png|jpe?g|gif|webp|svg)", line, re.I)):
        return "reference"
    try:
        ipaddress.ip_address(line.strip('[]'))
    except ValueError:
        pass
    else:
        return "reference"
    if _CONFIG.fullmatch(line) or _NGINX.fullmatch(line):
        return "configuration"
    command = _COMMAND.match(line)
    if command:
        name, args = command.groups()
        if (_COMMAND_ARG.search(args)
                or args.split()[0].lower() in _SUBCOMMANDS.get(name.lower(), set())):
            return "procedure"
    if suspicious_machine_line(line):
        return "machine"
    return None


def signal_excerpts(body: str, *, limit: int = 3) -> list[SignalExcerpt]:
    if limit <= 0:
        return []
    result: list[SignalExcerpt] = []
    seen: set[str] = set()
    fence_char = ''
    fence_length = 0
    for body_line, raw in enumerate(body.splitlines(), 1):
        line = _unquote(raw.strip())
        # List-contained fences use the same conservative skip state. Never let
        # a shorter fence, a different delimiter or closing info text end it.
        fence_line = re.sub(r"^(?:[-*+] |\d+[.)] )", "", line).strip()
        fence = _FENCE.match(fence_line)
        if fence_char:
            if (fence and fence.group(1)[0] == fence_char
                    and len(fence.group(1)) >= fence_length and not fence.group(2).strip()):
                fence_char, fence_length = '', 0
            continue
        if fence:
            fence_char, fence_length = fence.group(1)[0], len(fence.group(1))
            continue
        if not line or re.match(r"^(?:#{1,6}\s|[-*_]{3,}$|[-*+]\s+\[[ xX]\])", line):
            continue
        line = re.sub(r"^(?:[-*+] |\d+[.)、]\s*)", "", line).strip()
        if _ROUTINE.fullmatch(line) or non_signal_kind(line):
            continue
        for sentence in re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+", line):
            sentence = sentence.strip()
            if (8 <= len(sentence) <= 240 and re.search(r"[\w\u4e00-\u9fff]", sentence)
                    and sentence not in seen and not non_signal_kind(sentence)):
                seen.add(sentence)
                result.append(SignalExcerpt(sentence, body_line))
                if len(result) >= limit:
                    return result
    return result


def signal_sentences(body: str, *, limit: int = 3) -> list[str]:
    return [excerpt.text for excerpt in signal_excerpts(body, limit=limit)]
