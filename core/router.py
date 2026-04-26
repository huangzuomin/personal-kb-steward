from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import read_json


ROOT = Path(__file__).resolve().parents[1]
ROUTER_PATH = ROOT / "router.json"
WORKFLOWS_PATH = ROOT / "workflows.json"


def load_router() -> dict[str, Any]:
    return read_json(ROUTER_PATH, {"routes": [], "default_entry": "organize_kb"})


def route_item(task: str, router: dict[str, Any] | None = None) -> dict[str, Any] | None:
    router = router or read_json(ROUTER_PATH, {"routes": [], "default": "mindseed-grow"})
    low = task.lower()
    for item in router.get("routes", []):
        for keyword in item.get("match_any", []):
            if keyword.lower() in low:
                return item
    default_entry = router.get("default_entry")
    for item in router.get("routes", []):
        if item.get("entry") == default_entry:
            return item
    return None


def default_entry_skill(router: dict[str, Any]) -> str:
    default_entry = router.get("default_entry")
    for item in router.get("routes", []):
        if item.get("entry") == default_entry:
            return item.get("primary_skill") or item.get("skill") or "mindseed-grow"
    return "mindseed-grow"


def route(task: str) -> str:
    router = read_json(ROUTER_PATH, {"routes": [], "default": "mindseed-grow"})
    item = route_item(task, router)
    if item:
        return item.get("primary_skill") or item.get("skill") or "mindseed-grow"
    return router.get("default") or router.get("default_skill") or default_entry_skill(router)


def workflow_for_entry(entry: str) -> dict[str, Any]:
    workflows = read_json(WORKFLOWS_PATH, {"entries": {}})
    return workflows.get("entries", {}).get(entry, {})
