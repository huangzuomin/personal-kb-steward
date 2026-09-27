"""Agent-CLI transport backend: run a headless coding agent in read-only
mode and take its stdout as the provider response.

The agent replaces the single-shot chat-completion call with a tool-using
run: it receives the same system prompt and JSON payload as the API path,
but may Read the full source files (document entries carry ``abs_path``)
and Grep the vault before answering. The agent gets NO write tools — its
entire effect on the world is stdout text, so every filesystem mutation
still goes through the Python dry-run -> review -> apply chain.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import kb_root
from .content_safety import assert_safe_content, sensitive_reason
from .llm import LLMError

ROOT = Path(__file__).resolve().parents[1]
PROMPT_TMP_DIR = ROOT / ".openclaw" / "tmp"

# args template placeholders. "{stdin}" is an explicit marker meaning the
# prompt is piped to the process stdin; it is the default whenever
# "{prompt_file}" does not appear in the template (both never appear
# together — see call_agent_cli).
KNOWN_PLACEHOLDERS = frozenset({"{cwd}", "{prompt_file}", "{stdin}"})

DEFAULT_TIMEOUT_SECONDS = 900.0


def _agent_section(cfg: dict[str, Any]) -> dict[str, Any]:
    llm_cfg = cfg.get("llm", {})
    agent = llm_cfg.get("agent") if isinstance(llm_cfg, dict) else None
    if not isinstance(agent, dict):
        raise LLMError("llm.backend=agent 需要配置 llm.agent 对象")
    return agent


def build_prompt(system_prompt: str, user_payload: dict[str, Any], workspace: str) -> str:
    """Compose the full prompt: contract, payload, environment, output rules."""
    payload_text = json.dumps(user_payload, ensure_ascii=False, indent=1)
    return (
        f"{system_prompt}\n\n"
        "== 用户载荷（JSON）==\n"
        f"{payload_text}\n\n"
        "== 运行环境 ==\n"
        f"知识库根目录（工作目录）：{workspace}\n"
        "documents 中每个条目的 abs_path 是原文绝对路径。content 被截断时必须用 Read 读取全文后再分析；"
        "允许用 Grep/Glob 在知识库内检索，交叉核验事实、数字与链接目标是否真实存在。\n\n"
        "== 输出要求 ==\n"
        "完成分析与核验后，只输出一个 JSON 对象：第一个字符必须是 { ，最后一个字符必须是 } 。"
        "禁止输出 Markdown 代码块标记、解释文字、计划或日志。JSON 结构必须符合用户载荷中的 output_contract。"
    )


def _write_prompt_file(prompt: str) -> Path:
    PROMPT_TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = PROMPT_TMP_DIR / f"agent-prompt-{os.getpid()}-{int(time.time() * 1000)}.txt"
    path.write_text(prompt, encoding="utf-8")
    return path


def _resolve_command(command: str) -> str:
    """Resolve through PATH including Windows .cmd/.exe shims."""
    resolved = shutil.which(command)
    if resolved is None:
        raise LLMError(
            f"agent CLI 未找到：{command}（请确认已安装并在 PATH 中，"
            f"或在 llm.agent.command 里写绝对路径）")
    return resolved


def _build_argv(agent: dict[str, Any], workspace: str, prompt_file: Path) -> tuple[list[str], bool]:
    """Expand the args template. Returns (argv, stdin_mode)."""
    command = str(agent.get("command", "")).strip()
    if not command:
        raise LLMError("llm.agent.command 未配置")
    template = agent.get("args", [])
    if not isinstance(template, list) or not all(isinstance(a, str) for a in template):
        raise LLMError("llm.agent.args 必须是字符串数组")
    has_prompt_file = "{prompt_file}" in template
    has_stdin_marker = "{stdin}" in template
    if has_prompt_file and has_stdin_marker:
        raise LLMError("llm.agent.args 不能同时包含 {prompt_file} 和 {stdin}")
    argv = [_resolve_command(command)]
    for part in template:
        stripped = part.strip()
        if stripped == "{cwd}":
            argv.append(workspace)
        elif stripped == "{prompt_file}":
            argv.append(str(prompt_file))
        elif stripped == "{stdin}":
            continue
        elif part.startswith("{") and part.endswith("}"):
            raise LLMError(f"llm.agent.args 含未知占位符：{part}（支持 {sorted(KNOWN_PLACEHOLDERS)}）")
        else:
            argv.append(part)
    stdin_mode = not has_prompt_file
    return argv, stdin_mode


def run_llm_probe(cfg: dict[str, Any], backend: str | None = None) -> tuple[bool, list[str]]:
    """Connectivity probe behind the CLI ``llm-check`` command. Optionally
    overrides llm.backend on a config copy (never persists). Returns
    (ok, output lines to print)."""
    from .config import llm_backend as resolve_backend
    from .json_contract import extract_json
    from .llm import llm_generate

    if backend:
        cfg = json.loads(json.dumps(cfg, ensure_ascii=False))
        cfg.setdefault("llm", {})["backend"] = backend
    try:
        active = resolve_backend(cfg)
    except ValueError as exc:
        return False, [f"配置无效：{exc}"]
    llm_cfg = cfg.get("llm", {})
    if not isinstance(llm_cfg, dict):
        llm_cfg = {}
    if active == "api":
        base_url = os.environ.get("OPENAI_BASE_URL") or llm_cfg.get("base_url", "")
        model = os.environ.get("OPENAI_MODEL") or os.environ.get("LLM_MODEL") or llm_cfg.get("model", "")
        lines = [f"后端：api（{base_url or '未配置 base_url'}，模型 {model or '未配置 model'}）"]
    else:
        agent = llm_cfg.get("agent", {})
        if not isinstance(agent, dict):
            agent = {}
        lines = [f"后端：agent（{agent.get('command')}，工作目录 {kb_root(cfg)}）"]
    payload = {
        "task": "connectivity_probe",
        "instruction": '这是连通性探针。只返回 {"ok": true} 这个 JSON 对象，不要任何其他文本。',
        "output_contract": {"required": {"ok": "boolean，必须为 true"}},
    }
    started = time.monotonic()
    try:
        raw = llm_generate(cfg, "你是连通性探针。严格按用户载荷中的指令输出。", payload)
        data = extract_json(raw)
    except (LLMError, ValueError) as exc:
        lines.append(f"失败：{exc}")
        return False, lines
    except json.JSONDecodeError as exc:
        lines.append(f"失败：返回内容不是合法 JSON：{exc}")
        return False, lines
    elapsed = time.monotonic() - started
    if isinstance(data, dict) and data.get("ok") is True:
        lines.append(f"通过：{elapsed:.1f}s，返回 {len(raw)} 字符")
        return True, lines
    lines.append(f"失败：返回了 JSON 但 ok != true：{str(data)[:200]}")
    return False, lines


def call_agent_cli(cfg: dict[str, Any], system_prompt: str, user_payload: dict[str, Any]) -> str:
    """Same signature and return contract as llm.call_chat_completion:
    returns the raw response text (expected to contain the JSON)."""
    assert_safe_content(system_prompt)
    assert_safe_content(user_payload)
    agent = _agent_section(cfg)
    workspace = str(kb_root(cfg))
    prompt = build_prompt(system_prompt, user_payload, workspace)
    prompt_file = _write_prompt_file(prompt)
    try:
        argv, stdin_mode = _build_argv(agent, workspace, prompt_file)
        try:
            timeout_value = agent.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
            if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
                raise ValueError("timeout_seconds must be a finite number")
            timeout = float(timeout_value)
            if timeout <= 0:
                raise ValueError("timeout_seconds must be positive")
        except ValueError as exc:
            raise LLMError(f"llm.agent.timeout_seconds 配置无效：{exc}") from None

        env = os.environ.copy()
        env_extra = agent.get("env", {})
        if isinstance(env_extra, dict):
            env.update({str(k): str(v) for k, v in env_extra.items()})

        try:
            proc = subprocess.run(
                argv,
                cwd=workspace,
                env=env,
                input=prompt.encode("utf-8") if stdin_mode else None,
                capture_output=True,
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            raise LLMError(f"agent CLI 超时（>{timeout:g}s）：{agent.get('command')}") from None
        except FileNotFoundError:
            raise LLMError(f"agent CLI 未找到：{agent.get('command')}") from None
        except OSError as exc:
            detail = str(exc)
            if sensitive_reason(detail):
                detail = "[agent launch detail omitted: sensitive content]"
            raise LLMError(f"agent CLI 启动失败：{detail}") from None

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            detail = (stderr or stdout).strip()[-500:]
            if sensitive_reason(detail):
                detail = "[agent error body omitted: sensitive content]"
            raise LLMError(
                f"agent CLI 退出码 {proc.returncode}：{detail or '(无输出)'}")
        if not stdout.strip():
            raise LLMError("agent CLI 无 stdout 输出（分析未产生结果）")
        assert_safe_content(stdout)
        return stdout
    finally:
        try:
            prompt_file.unlink(missing_ok=True)
        except OSError:
            pass
