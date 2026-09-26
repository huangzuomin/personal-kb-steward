#!/usr/bin/env python3
"""Validate local personal-kb-steward configuration."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.layout import validate_options
from core.config import CARD_PIPELINE_MODES, SEED_GENERATION_MODES
from core.llm_retry import retry_policy
from core.initialization_policy import (
    InitializationPipelineError,
    load_initialization_pipeline,
    validate_initialization_config,
)
CONFIG_PATH = ROOT / "config.json"
ROUTER_PATH = ROOT / "router.json"
WORKFLOWS_PATH = ROOT / "workflows.json"
PUBLIC_ENTRIES = frozenset({
    "organize_kb", "discover_topics", "prepare_writing", "weave_work_memory", "healthcheck",
})


def read_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"缺少文件：{path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def expand_path_expr(value: str, *, kb_home: str | None = None) -> str:
    replacements = {
        "AGENT_HOME": str(ROOT),
        "WORKSPACE_HOME": str(ROOT),
        "KB_HOME": kb_home or os.environ.get("KB_HOME", ""),
    }
    text = os.path.expandvars(os.path.expanduser(str(value)))
    for key, replacement in replacements.items():
        if replacement:
            text = text.replace(f"${{{key}}}", replacement)
            text = text.replace(f"%{key}%", replacement)
    return text


def resolve_path(value: str, *, kb_home: str | None = None) -> Path:
    expanded = expand_path_expr(value, kb_home=kb_home)
    if os.sep == "/":
        expanded = expanded.replace("\\", "/")
    path = Path(expanded)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def path_expr(cfg: dict, dotted_key: str, default: str = "") -> str:
    current = cfg
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return str(current)


def seed_generation_errors(cfg: dict) -> list[str]:
    """seed_generation.mode must be atomic|topic; default only when absent.
    Present invalid types/values are rejected, never coerced. M0 ships the
    configuration seam only, not the atomic generator itself."""
    if "seed_generation" not in cfg:
        return []
    section = cfg.get("seed_generation")
    if not isinstance(section, dict):
        return ["seed_generation 必须是对象"]
    if "mode" not in section:
        return []
    mode = section["mode"]
    if not isinstance(mode, str) or mode not in SEED_GENERATION_MODES:
        return [f"seed_generation.mode 只能是 atomic 或 topic，当前为：{mode!r}"]
    return []


def card_pipeline_errors(cfg: dict) -> list[str]:
    """card_pipeline.mode must be typed|legacy (default only when absent);
    topic_questions must be a bounded nonempty-string list (default empty:
    no configured question => topic stage is disabled, never auto-answered
    from hints); caps must be positive integers. Present invalid types/values
    are rejected, never coerced."""
    if "card_pipeline" not in cfg:
        return []
    section = cfg.get("card_pipeline")
    if not isinstance(section, dict):
        return ["card_pipeline 必须是对象"]
    errors: list[str] = []
    if "mode" in section:
        mode = section["mode"]
        if not isinstance(mode, str) or mode not in CARD_PIPELINE_MODES:
            errors.append(f"card_pipeline.mode 只能是 typed 或 legacy，当前为：{mode!r}")
    if "topic_questions" in section:
        questions = section["topic_questions"]
        if not isinstance(questions, list) or not all(
                isinstance(q, str) and q.strip() for q in questions):
            errors.append("card_pipeline.topic_questions 必须是非空字符串列表")
        elif len(questions) > 1:
            errors.append("card_pipeline.topic_questions 本轮最多支持一个问题；多问题配置必须拆分为多次运行")
    for key in ("related_paths_cap", "topic_source_cap"):
        if key in section:
            value = section[key]
            if type(value) is not int or value < 1:
                errors.append(f"card_pipeline.{key} 必须是正整数：{value!r}")
    return errors


def topic_generation_errors(cfg: dict) -> list[str]:
    """Validate topic budgets and reject an impossible source floor/cap pair."""
    if "topic_generation" not in cfg:
        return []
    section = cfg.get("topic_generation")
    if not isinstance(section, dict):
        return ["topic_generation 必须是对象"]
    errors: list[str] = []
    values: dict[str, int] = {}
    for key, default in (("min_full_sources", 3),
                         ("max_source_chars", 20000),
                         ("max_context_chars", 60000)):
        value = section.get(key, default)
        if type(value) is not int or value < 1:
            errors.append(f"topic_generation.{key} 必须是正整数：{value!r}")
        else:
            values[key] = value
    card = cfg.get("card_pipeline")
    card = card if isinstance(card, dict) else {}
    cap = card.get("topic_source_cap", 6)
    if type(cap) is int and cap >= 1 and "min_full_sources" in values \
            and values["min_full_sources"] > cap:
        errors.append(
            "topic_generation.min_full_sources 不能大于 "
            f"card_pipeline.topic_source_cap（{values['min_full_sources']} > {cap}）"
        )
    return errors


def main() -> int:
    cfg = read_json(CONFIG_PATH)
    router = read_json(ROUTER_PATH)
    workflows = read_json(WORKFLOWS_PATH)

    errors: list[str] = validate_options(cfg)
    errors.extend(seed_generation_errors(cfg))
    errors.extend(card_pipeline_errors(cfg))
    errors.extend(topic_generation_errors(cfg))
    try:
        validate_initialization_config(cfg)
    except InitializationPipelineError as exc:
        errors.append(str(exc))
    try:
        load_initialization_pipeline(lambda entry: workflows.get("entries", {}).get(entry, {}))
    except InitializationPipelineError as exc:
        errors.append(str(exc))
    try:
        retry_policy(cfg.get("llm", {}))
    except ValueError as exc:
        errors.append(f"llm 重试配置无效：{exc}")
    kb_expr = cfg.get("knowledge_base", "")
    if not kb_expr:
        errors.append("knowledge_base 缺失")
        kb = ROOT
    else:
        kb = resolve_path(kb_expr)
    if not kb.exists():
        errors.append(f"knowledge_base 不存在：{kb}")
    state = resolve_path(path_expr(cfg, "state_file"), kb_home=str(kb))
    for key in [
        "safety.plans_dir",
        "safety.runs_dir",
        "safety.processed_index",
        "safety.manual_review_queue",
        "safety.backup_dir",
        "safety.operation_log",
    ]:
        expr = path_expr(cfg, key)
        if not expr:
            errors.append(f"{key} 缺失")
        elif not resolve_path(expr, kb_home=str(kb)).is_relative_to(ROOT.resolve()):
            errors.append(f"{key} should stay under AGENT_HOME: {expr}")
    if cfg.get("safety", {}).get("default_mode") != "dry-run":
        errors.append("safety.default_mode 必须是 dry-run")
    if not cfg.get("safety", {}).get("require_apply_flag_for_writes"):
        errors.append("必须启用 require_apply_flag_for_writes")
    clustering = cfg.get("clustering", {})
    if clustering.get("mode") != "dynamic":
        errors.append("clustering.mode must be dynamic")
    if clustering.get("allow_fixed_theme_rules"):
        errors.append("clustering.allow_fixed_theme_rules must be false")

    entries = set(workflows.get("entries", {}))
    user_entries = cfg.get("routing", {}).get("user_entries", [])
    if not isinstance(user_entries, list) or not all(isinstance(item, str) for item in user_entries):
        errors.append("routing.user_entries 必须是字符串列表")
        user_entries = []
    configured_entries = set(user_entries)
    if configured_entries != PUBLIC_ENTRIES:
        errors.append(
            "routing.user_entries 必须恰好包含五个公共入口；"
            f"缺失：{sorted(PUBLIC_ENTRIES - configured_entries)}；"
            f"非公共入口：{sorted(configured_entries - PUBLIC_ENTRIES)}"
        )
    if len(user_entries) != len(configured_entries):
        errors.append("routing.user_entries 不得重复")
    if not configured_entries.issubset(entries):
        errors.append(f"公共入口引用未定义 workflow：{sorted(configured_entries - entries)}")

    for route in router.get("routes", []):
        if route.get("entry") not in entries:
            errors.append(f"router entry 未定义：{route.get('entry')}")
        if not route.get("primary_skill"):
            errors.append(f"router route 缺 primary_skill：{route}")

    required = set(cfg.get("knowledge_model", {}).get("required_frontmatter", []))
    if "stage" not in required:
        errors.append("required_frontmatter 必须包含 stage")
    if "sources" not in required:
        errors.append("required_frontmatter 必须包含 sources")

    if errors:
        print("配置校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("配置校验通过")
    print(f"知识库：{kb.resolve() if kb.exists() else kb}")
    print(f"用户入口：{', '.join(sorted(configured_entries))}")
    print(f"knowledge_base expr: {kb_expr}")
    print(f"knowledge_base path: {kb.resolve() if kb.exists() else kb}")
    print(f"state_file path: {state}")
    print("default mode: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
