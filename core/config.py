from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
DEFAULT_PLAN_DIR = ROOT / ".openclaw" / "plans"
DEFAULT_REVIEW_QUEUE_PATH = ROOT / ".openclaw" / "manual-review" / "queue.jsonl"
DEFAULT_PROCESSED_INDEX_PATH = ROOT / ".openclaw" / "processed-index.json"
DEFAULT_RUNS_DIR = ROOT / ".openclaw" / "runs"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def resolve_path(value: str, *, base: Path = ROOT, kb_home: str | None = None) -> Path:
    path = Path(expand_path_expr(value, kb_home=kb_home))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def config_path_expr(cfg: dict[str, Any], dotted_key: str, default: str) -> str:
    current: Any = cfg
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return str(current)


def config() -> dict[str, Any]:
    data = read_json(CONFIG_PATH, {})
    if not data:
        raise SystemExit(f"缺少配置文件：{CONFIG_PATH}")
    return data


def kb_root(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["knowledge_base"])


def state_path(cfg: dict[str, Any]) -> Path:
    return resolve_path(cfg["state_file"], kb_home=str(kb_root(cfg)))


def plan_dir(cfg: dict[str, Any]) -> Path:
    return resolve_path(config_path_expr(cfg, "safety.plans_dir", str(DEFAULT_PLAN_DIR)), kb_home=str(kb_root(cfg)))


def review_queue_path(cfg: dict[str, Any]) -> Path:
    return resolve_path(config_path_expr(cfg, "safety.manual_review_queue", str(DEFAULT_REVIEW_QUEUE_PATH)), kb_home=str(kb_root(cfg)))


def processed_index_path(cfg: dict[str, Any]) -> Path:
    return resolve_path(config_path_expr(cfg, "safety.processed_index", str(DEFAULT_PROCESSED_INDEX_PATH)), kb_home=str(kb_root(cfg)))


def runs_dir(cfg: dict[str, Any]) -> Path:
    return resolve_path(config_path_expr(cfg, "safety.runs_dir", str(DEFAULT_RUNS_DIR)), kb_home=str(kb_root(cfg)))
