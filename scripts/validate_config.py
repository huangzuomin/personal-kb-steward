#!/usr/bin/env python3
"""Validate local personal-kb-steward configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
ROUTER_PATH = ROOT / "router.json"
WORKFLOWS_PATH = ROOT / "workflows.json"


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
    path = Path(expand_path_expr(value, kb_home=kb_home))
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


def main() -> int:
    cfg = read_json(CONFIG_PATH)
    router = read_json(ROUTER_PATH)
    workflows = read_json(WORKFLOWS_PATH)

    errors: list[str] = []
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
        elif not str(resolve_path(expr, kb_home=str(kb))).startswith(str(ROOT)):
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
    configured_entries = set(cfg.get("routing", {}).get("user_entries", []))
    if configured_entries != entries:
        errors.append(f"routing.user_entries 与 workflows.entries 不一致：{configured_entries} != {entries}")

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
    print(f"用户入口：{', '.join(sorted(entries))}")
    print(f"knowledge_base expr: {kb_expr}")
    print(f"knowledge_base path: {kb.resolve() if kb.exists() else kb}")
    print(f"state_file path: {state}")
    print("default mode: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
