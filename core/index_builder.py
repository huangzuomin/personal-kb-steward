from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.vault import VaultIndex


def update_index(index: VaultIndex, cfg: dict[str, Any]) -> None:
    """Updates the root index.md and core directory README.md files."""
    root = index.root
    
    # 1. Ensure core directories have a README.md
    core_dirs = ["seeds", "topics", "concepts", "projects", "cases", "material-packs"]
    for d in core_dirs:
        dir_path = root / "wiki" / d
        if not dir_path.exists():
            continue
        readme_path = dir_path / "README.md"
        if not readme_path.exists():
            readme_path.write_text(f"# {d.title()} Index\n\n- Automatically managed by Knowledge Steward.\n", encoding="utf-8")

    # 2. Build root index.md content
    
    # - 最近更新 (Recent Updates): Get the 3 most recent logs
    log_path = root / "log.md"
    recent_logs = []
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8")
        match = re.search(r"## Recent Runs\n\n(.*?)\n\n## Monthly Archives", log_content, re.DOTALL)
        if match:
            lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
            recent_logs = lines[:3]
            
    recent_updates_section = "\n".join(recent_logs) if recent_logs else "- 暂无更新记录"

    # - 核心入口 (Core Entrances)
    core_entrances = []
    for d in core_dirs:
        if (root / "wiki" / d).exists():
            core_entrances.append(f"- [[wiki/{d}/README]]")
    entrances_section = "\n".join(core_entrances) if core_entrances else "- 暂无入口"

    # - 当前活跃专题 (Active Topics)
    active_topics = []
    for note in index.notes:
        if note.rel.startswith("wiki/topics/") and note.metadata:
            status = note.metadata.get("status", "")
            if status == "growing":
                active_topics.append(f"- [[{note.rel.replace('.md', '')}]]")
    
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

    # Assemble index.md
    index_content = f"""# Personal Knowledge Base

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
    
    index_path = root / "index.md"
    index_path.write_text(index_content, encoding="utf-8")
