from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.markdown import frontmatter
from core.safety import append_operation_log, safe_write_text
from core.vault import VaultIndex


MANAGED_INDEX_MARKER = "<!-- managed-by: personal-kb-steward:index-builder -->"


def generated_index_path(root: Path) -> Path:
    return root / ".openclaw" / "generated-index.md"


# Key -> section label for the generated index. Values are resolved through
# `config.write`, so a customised layout never produces links into a tree that
# does not exist.
INDEXED_DIR_KEYS = {
    "seed_dir": "seeds",
    "topics_dir": "topics",
    "concepts_dir": "concepts",
    "cases_dir": "cases",
    "materials_dir": "material-packs",
}
# Upstream layout, used only when config.write omits a key entirely.
LEGACY_INDEX_DIRS = {
    "seeds": "wiki/seeds", "topics": "wiki/topics", "concepts": "wiki/concepts",
    "cases": "wiki/cases", "material-packs": "wiki/material-packs",
}


def indexed_dirs(cfg: dict[str, Any]) -> dict[str, str]:
    """Relative dirs for the index, taken from `config.write` (never hardcoded).

    A missing `write` section falls back to the upstream layout rather than
    yielding nothing: an empty result would silently stop creating READMEs.
    """
    write = cfg.get("write") if isinstance(cfg, dict) else None
    write = write if isinstance(write, dict) else {}
    resolved: dict[str, str] = {}
    for key, label in INDEXED_DIR_KEYS.items():
        value = str(write.get(key) or LEGACY_INDEX_DIRS[label]).replace("\\", "/").strip("/")
        if value:
            resolved[label] = value
    return resolved


def update_index(index: VaultIndex, cfg: dict[str, Any]) -> None:
    """Updates managed index files without overwriting a user-owned root index.md."""
    root = index.root
    run_id = str(cfg.get("_run_id") or datetime.now(timezone.utc).strftime("index-%Y%m%d-%H%M%S"))
    dirs = indexed_dirs(cfg)

    # 1. Ensure core directories have a README.md
    for label, rel_dir in dirs.items():
        dir_path = root / rel_dir
        if not dir_path.exists():
            continue
        readme_path = dir_path / "README.md"
        if not readme_path.exists():
            title = f"{label.title()} Index"
            content = (
                frontmatter(
                    title,
                    "run-report",
                    "compiled",
                    [],
                    tags=["managed-index"],
                    confidence="high",
                    stage="compiled",
                    origin={"source_paths": [], "operation": "index-builder"},
                )
                + f"# {title}\n\n"
                + "- Automatically managed by Knowledge Steward.\n"
            )
            safe_write_text(
                cfg,
                readme_path,
                content,
                run_id=run_id,
                operation="create_index_readme",
                reason="Create missing managed directory README before updating the knowledge-base index.",
            )

    # 2. Build root index.md content
    
    # - 最近更新 (Recent Updates): Get the 3 most recent logs
    log_path = root / "log.md"
    recent_logs = []
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8")
        match = re.search(r"## Recent Runs\n\n(.*?)\n\n## Monthly Archives", log_content, re.DOTALL)
        if match:
            lines = [
                re.sub(r"\[\[([^\]]+)\]\]", r"`\1`", line.strip())
                for line in match.group(1).splitlines()
                if line.strip()
            ]
            recent_logs = lines[:3]
            
    recent_updates_section = "\n".join(recent_logs) if recent_logs else "- 暂无更新记录"

    # - 核心入口 (Core Entrances)
    core_entrances = []
    for label, rel_dir in dirs.items():
        if (root / rel_dir).exists():
            core_entrances.append(f"- [[{rel_dir}/README.md]]")
    entrances_section = "\n".join(core_entrances) if core_entrances else "- 暂无入口"

    # - 当前活跃专题 (Active Topics)
    topics_dir = dirs.get("topics", "")
    topics_prefix = f"{topics_dir}/" if topics_dir else None
    active_topics = []
    for note in index.notes:
        if topics_prefix and note.rel.startswith(topics_prefix) and note.metadata:
            status = note.metadata.get("status", "")
            if status == "growing":
                active_topics.append(f"- [[{note.rel}]]")
    
    # Only keep up to 10 active topics to avoid bloat
    active_topics = active_topics[:10]
    active_topics_section = "\n".join(active_topics) if active_topics else "- 暂无活跃专题"

    # - 待人工确认 (Pending Manual Review)
    review_queue_path_str = cfg.get("safety", {}).get("manual_review_queue", "")
    if review_queue_path_str:
        review_queue_path_str = review_queue_path_str.replace("${AGENT_HOME}", str(Path(__file__).resolve().parents[1]))
    review_queue_path = Path(review_queue_path_str) if review_queue_path_str else root / ".openclaw" / "manual-review" / "queue.jsonl"
    pending_count = 0
    if review_queue_path.exists():
        content = review_queue_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if '"status": "pending"' in line or '"status":"pending"' in line:
                pending_count += 1
                
    review_section = f"- [[.openclaw/manual-review/queue.jsonl]] ({pending_count} 项待处理)"
    if pending_count > 0:
        review_section = f"- Manual review queue: {pending_count} pending item(s)"
    if pending_count == 0:
        review_section = "- 暂无待处理项"

    # - 健康状态 (Health Status)
    # Find latest lint report
    reports_dir = root / "outputs"
    latest_report = None
    if reports_dir.exists():
        reports = list(reports_dir.glob("kb-steward-*.md"))
        if reports:
            reports.sort(key=lambda p: p.name, reverse=True)
            latest_report = reports[0]
            
    health_section = f"- [[outputs/{latest_report.name.replace('.md', '')}]]" if latest_report else "- 暂无健康报告"

    if latest_report:
        health_section = f"- [[outputs/{latest_report.name}]]"

    # Assemble index.md
    index_content = f"""{MANAGED_INDEX_MARKER}
# Personal Knowledge Base

## 最近更新

{recent_updates_section}

## 核心入口

{entrances_section}

## 当前活跃专题

{active_topics_section}

## 待人工确认

{review_section}

## 健康状态

{health_section}
"""
    
    root_index_path = root / "index.md"
    index_path = root_index_path
    operation = "write_root_index"
    reason = "Update generated knowledge-base index; existing managed file is backed up first."
    if root_index_path.exists() and MANAGED_INDEX_MARKER not in root_index_path.read_text(encoding="utf-8-sig", errors="replace"):
        index_path = generated_index_path(root)
        operation = "write_generated_index"
        reason = "Root index.md appears user-owned; write generated index to .openclaw/generated-index.md instead."
        append_operation_log(cfg, {
            "operation": "preserve_user_root_index",
            "run_id": run_id,
            "target": "index.md",
            "generated_target": ".openclaw/generated-index.md",
            "reason": reason,
        })
    safe_write_text(
        cfg,
        index_path,
        index_content,
        run_id=run_id,
        operation=operation,
        reason=reason,
    )
