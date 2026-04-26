from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def load_executor(root: Path, skill_name: str):
    skill_dir = root / "skills" / skill_name
    path = skill_dir / "executor.py"
    if not path.exists():
        raise FileNotFoundError(f"Skill executor not found: {path}")
    module_name = "personal_kb_steward_skill_" + skill_name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load executor: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(skill_dir))
    previous_renderer = sys.modules.pop("renderer", None)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("renderer", None)
        if previous_renderer is not None:
            sys.modules["renderer"] = previous_renderer
        try:
            sys.path.remove(str(skill_dir))
        except ValueError:
            pass
    if not hasattr(module, "execute"):
        raise RuntimeError(f"Skill executor missing execute(context): {path}")
    return module.execute


def execute_skill(root: Path, skill_name: str, context: dict[str, Any]) -> dict[str, Any]:
    executor = load_executor(root, skill_name)
    result = executor(context)
    result.setdefault("skill", skill_name)
    result.setdefault("pages", [])
    result.setdefault("issues", [])
    result.setdefault("inputs", [])
    result.setdefault("processed", 0)
    return result
