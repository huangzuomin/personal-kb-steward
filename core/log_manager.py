from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.markdown import bullet, frontmatter
from core.vault import VaultIndex


def write_run_log(index: VaultIndex, cfg: dict[str, Any], operations: list[dict[str, Any]], task: str) -> list[str]:
    """Writes detailed run logs for each operation and updates monthly/root logs.
    Returns the list of paths to the created run logs."""
    now = datetime.now(timezone.utc)
    yyyy = now.strftime("%Y")
    yyyy_mm = now.strftime("%Y-%m")
    ts = now.strftime("%Y-%m-%d-%H%M")
    
    logs_dir = index.root / "logs" / yyyy
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    run_log_paths = []
    
    for op in operations:
        skill = op.get("skill", "unknown")
        # 1. Create run log
        run_log_name = f"{ts}-{skill}.md"
        run_log_path = logs_dir / run_log_name
        rel_run_log = f"logs/{yyyy}/{run_log_name}"
        
        status = "success" if not op.get("issues") else "has_issues"
        
        lines = [
            "---",
            "type: run-log",
            "agent: personal-kb-steward",
            f"skill: {skill}",
            f"created: {now.isoformat()}",
            f"status: {status}",
            "---",
            f"# Run Log: {skill} ({ts})",
            "",
            "## Input",
            f"- Task: {task}",
            f"- Processed: {op.get('processed', 0)}",
            "",
            "## Created",
            bullet(op.get("created", []), "None"),
            "",
            "## Issues / Errors",
            bullet(op.get("issues", []), "None"),
            ""
        ]
        
        run_log_path.write_text("\n".join(lines), encoding="utf-8")
        run_log_paths.append(rel_run_log)
        
    if not run_log_paths:
        return []

    # 2. Update monthly log
    monthly_log_name = f"{yyyy_mm}.md"
    monthly_log_path = logs_dir / monthly_log_name
    rel_monthly_log = f"logs/{yyyy}/{monthly_log_name}"
    
    if not monthly_log_path.exists():
        monthly_log_path.write_text(f"# {yyyy_mm} 知识库运行日志\n\n## Summary\n\n运行次数：0\n新建页面：0\n错误次数：0\n\n## Runs\n\n", encoding="utf-8")
        
    monthly_content = monthly_log_path.read_text(encoding="utf-8")
    
    # Update stats
    run_count = int(re.search(r"运行次数：(\d+)", monthly_content).group(1)) if re.search(r"运行次数：(\d+)", monthly_content) else 0
    created_count = int(re.search(r"新建页面：(\d+)", monthly_content).group(1)) if re.search(r"新建页面：(\d+)", monthly_content) else 0
    error_count = int(re.search(r"错误次数：(\d+)", monthly_content).group(1)) if re.search(r"错误次数：(\d+)", monthly_content) else 0
    
    run_count += 1
    for op in operations:
        created_count += len(op.get("created", []))
        if op.get("issues"):
            error_count += 1
            
    monthly_content = re.sub(r"运行次数：\d+", f"运行次数：{run_count}", monthly_content)
    monthly_content = re.sub(r"新建页面：\d+", f"新建页面：{created_count}", monthly_content)
    monthly_content = re.sub(r"错误次数：\d+", f"错误次数：{error_count}", monthly_content)
    
    # Append runs
    run_links = "\n".join(f"- [[{p.replace('.md', '')}]]" for p in run_log_paths)
    monthly_content += f"{run_links}\n"
    
    monthly_log_path.write_text(monthly_content, encoding="utf-8")
    
    # 3. Update root log.md
    root_log_path = index.root / "log.md"
    if not root_log_path.exists():
        root_log_path.write_text("# Knowledge Base Log\n\n## Recent Runs\n\n## Monthly Archives\n\n", encoding="utf-8")
        
    root_log_content = root_log_path.read_text(encoding="utf-8")
    
    # Parse existing runs
    recent_runs_match = re.search(r"## Recent Runs\n\n(.*?)\n\n## Monthly Archives", root_log_content, re.DOTALL)
    existing_runs = []
    if recent_runs_match:
        existing_runs = [line for line in recent_runs_match.group(1).splitlines() if line.strip()]
        
    # Prepend new run
    ts_pretty = now.strftime("%Y-%m-%d %H:%M")
    summary = f"新增 {sum(len(op.get('created', [])) for op in operations)} 项, {sum(len(op.get('issues', [])) for op in operations)} 问题"
    
    # Create the single log entry summarizing this execution
    # Alternatively, create an entry for each operation. Let's do one per execution to not flood the logs too much.
    main_log_link = run_log_paths[0].replace('.md', '') if run_log_paths else ""
    new_entry = f"- {ts_pretty} [[{main_log_link}]]：{summary}"
    
    existing_runs.insert(0, new_entry)
    existing_runs = existing_runs[:30] # Keep max 30
    
    runs_text = "\n".join(existing_runs)
    
    # Parse existing monthly archives
    archives_match = re.search(r"## Monthly Archives\n\n(.*)", root_log_content, re.DOTALL)
    existing_archives = []
    if archives_match:
        existing_archives = [line for line in archives_match.group(1).splitlines() if line.strip()]
        
    archive_link = f"- [[{rel_monthly_log.replace('.md', '')}]]"
    if archive_link not in existing_archives:
        existing_archives.append(archive_link)
        
    archives_text = "\n".join(sorted(set(existing_archives), reverse=True))
    
    new_root_content = f"# Knowledge Base Log\n\n## Recent Runs\n\n{runs_text}\n\n## Monthly Archives\n\n{archives_text}\n"
    root_log_path.write_text(new_root_content, encoding="utf-8")
    
    return run_log_paths
