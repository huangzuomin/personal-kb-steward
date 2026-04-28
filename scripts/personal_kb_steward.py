#!/usr/bin/env python3
"""个人知识库管家运行时。

设计原则：
- 原始资料只读。
- 先建立索引，再生成派生知识。
- 所有来源和双链必须可解析。
- 不确定内容进入 manual_review。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MVP_EXECUTOR_SKILLS = {
    "mindseed-grow",
    "topic-insight-miner",
    "writing-evidence-harvester",
    "knowledge-gap-finder",
    "writing-material-pack",
    "raw-ingest-router",
    "topic-research-compile",
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from core.skill_runtime import run_skill_runtime
from core.log_manager import write_run_log
from core.index_builder import update_index
from core.skill_executor import execute_skill
from core.safety import (
    append_operation_log,
    backup_root,
    operation_log_path,
    recovery_hint,
    safe_delete_file,
    safe_write_text,
)
from core.config import (
    config,
    kb_root,
    plan_dir,
    processed_index_path,
    read_json,
    resolve_path,
    review_queue_path,
    runs_dir,
    sha256_file,
    sha256_text,
    state_path,
    write_json,
)
from core.vault import Note, VaultIndex, build_index
from core.state import (
    changed_notes,
    is_processed,
    load_processed_index,
    load_state,
    save_state as save_state_core,
    unprocessed_notes,
    update_processed_index as update_processed_index_core,
)
from core.review_queue import (
    load_queue,
    save_queue,
    append_item,
    find_item,
    filter_items,
    pending_items,
    approved_items,
    approve_item,
    reject_item,
    batch_approve,
    format_list_item,
    format_show_item,
    format_queue_summary,
)
from core.router import load_router, route, route_item, workflow_for_entry
from core.markdown import bullet, frontmatter, note_summary, slug

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "when", "why",
    "how", "use", "using", "about", "into", "your", "http", "https", "www",
    "com", "org", "net", "source", "content", "article", "articles", "read",
    "more", "new", "best", "image", "google", "gmail", "markdown", "md",
    "一个", "一种", "这个", "那个", "如何", "什么", "以及", "进行", "关于",
    "使用", "可以", "需要", "生成", "整理", "资料", "内容", "来源"
}

def stamp() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def run_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def ensure_dirs(cfg: dict[str, Any]) -> None:
    root = kb_root(cfg)
    for key, rel in cfg["write"].items():
        if key.endswith("_dir"):
            (root / rel).mkdir(parents=True, exist_ok=True)
    state_path(cfg).parent.mkdir(parents=True, exist_ok=True)


def save_state(cfg: dict[str, Any], index: VaultIndex, operations: list[dict[str, Any]]) -> None:
    save_state_core(cfg, index, operations, stamp())


def update_processed_index(index: VaultIndex, cfg: dict[str, Any], operations: list[dict[str, Any]]) -> None:
    update_processed_index_core(index, cfg, operations, stamp())


def wikilink(rel: str) -> str:
    return f"[[{rel}]]"


def pending_link(target: str) -> str:
    return f"待创建：{target}"


def canonical_link_target(index: VaultIndex, target: str) -> str | None:
    return resolve_link(index, target)


def safe_wikilink(index: VaultIndex, target: str) -> str:
    resolved = canonical_link_target(index, target)
    if not resolved:
        return pending_link(target)
    return wikilink(resolved)


def link_list(items: list[str], empty: str = "暂无") -> str:
    return bullet([pending_link(item) for item in items], empty)


def safe_link_list(index: VaultIndex, items: list[str], empty: str = "暂无") -> str:
    return bullet([safe_wikilink(index, item) for item in items], empty)


def extract_wikilinks(text: str) -> list[str]:
    return re.findall(r"\[\[([^\]|#]+)", text)


def resolve_link(index: VaultIndex, target: str) -> str | None:
    clean = target.strip()
    if clean in index.by_rel:
        return clean
    as_path = clean.replace("\\", "/")
    if as_path in index.by_rel:
        return as_path
    stem = Path(clean).stem
    matches = index.by_stem.get(stem, [])
    if len(matches) == 1:
        return matches[0].rel
    title_matches = index.by_title.get(clean.lower(), [])
    if len(title_matches) == 1:
        return title_matches[0].rel
    return None


def normalize_source(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            if isinstance(item, str):
                items.append(item)
            elif isinstance(item, dict) and item.get("path"):
                items.append(str(item["path"]))
        return items
    return []


def note_sources(note: Note) -> list[str]:
    return normalize_source(note.metadata.get("sources") or note.metadata.get("source"))


def tokens(text: str) -> list[str]:
    items = []
    for item in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,12}", text):
        low = item.lower()
        if low not in STOPWORDS:
            items.append(low)
    return items


def score_note(note: Note, query_terms: list[str]) -> int:
    hay = (note.title + "\n" + note.body[:6000]).lower()
    return sum(3 if term in note.title.lower() else 1 for term in query_terms if term.lower() in hay)


def select_notes(index: VaultIndex, query: str, limit: int = 12, prefixes: tuple[str, ...] = ("raw/", "quicknote/", "inbox/", "wiki/seeds/", "wiki/topics/")) -> list[Note]:
    query_terms = tokens(query)
    if not query_terms:
        query_terms = ["ai", "新闻", "媒体", "温州", "知识"]
    scored: list[tuple[int, Note]] = []
    for note in index.notes:
        if not note.rel.startswith(prefixes):
            continue
        score = score_note(note, query_terms)
        if score:
            scored.append((score, note))
    return [note for _, note in sorted(scored, key=lambda x: (-x[0], x[1].rel))[:limit]]


def llm_documents(notes: list[Note], max_chars: int) -> list[dict[str, str]]:
    docs = []
    for note in notes:
        docs.append({
            "path": note.rel,
            "title": note.title,
            "type": str(note.metadata.get("type") or ""),
            "status": str(note.metadata.get("status") or ""),
            "stage": str(note.metadata.get("stage") or ""),
            "content": note.body[:max_chars],
        })
    return docs


def executor_notes(notes: list[Note]) -> list[dict[str, Any]]:
    return [
        {
            "rel": note.rel,
            "title": note.title,
            "body": note.body,
            "summary": note_summary(note, 180),
            "metadata": note.metadata,
        }
        for note in notes
    ]


def apply_executor_pages(index: VaultIndex, cfg: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    created = []
    issues = list(result.get("issues", []))
    inputs = list(result.get("inputs", []))
    for page in result.get("pages", []):
        rel_dir = cfg["write"][page["rel_dir_key"]]
        rel = write_page(index, cfg, rel_dir, f"{Path(page['filename']).stem}-{run_id()}.md", page["content"])
        created.append(rel)
        issues.extend(validate_markdown(index, page["content"], page.get("sources", [])))
    return {
        "skill": result.get("skill"),
        "created": created,
        "processed": int(result.get("processed", 0)),
        "inputs": sorted(set(inputs)),
        "issues": issues,
        "items": result.get("items", []),
    }


def planned_pages_from_executor_result(cfg: dict[str, Any], result: dict[str, Any], plan_run_id: str) -> list[dict[str, Any]]:
    pages = []
    for page in result.get("pages", []):
        rel_dir = cfg["write"][page["rel_dir_key"]]
        filename = f"{Path(page['filename']).stem}-{plan_run_id}.md"
        rel_path = (Path(rel_dir) / filename).as_posix()
        content = page["content"]
        pages.append({
            "skill": result.get("skill"),
            "operation": "create",
            "rel_path": rel_path,
            "sources": page.get("sources", []),
            "content_sha256": sha256_text(content),
            "content": content,
            "review_required": bool(page.get("item", {}).get("review_required", False)),
            "confidence": page.get("item", {}).get("confidence"),
        })
    return pages


def mvp_executor_plan(index: VaultIndex, cfg: dict[str, Any], task: str, skill: str, changed: list[Note], processed_index: dict[str, Any], plan_run_id: str) -> dict[str, Any] | None:
    if skill not in MVP_EXECUTOR_SKILLS:
        return None
    if skill == "mindseed-grow":
        candidates_all = [
            n for n in changed
            if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
        ]
        notes = unprocessed_notes(processed_index, candidates_all, skill)[: cfg["scan"]["max_files_per_run"]]
        context = {"config": cfg, "notes": executor_notes(notes)}
    elif skill == "topic-insight-miner":
        notes = select_notes(index, task, limit=8, prefixes=("wiki/seeds/", "wiki/topics/", "raw/"))
        context = {"config": cfg, "query": task, "notes": executor_notes(notes)}
    else:
        notes = select_notes(index, task, limit=12)
        items = evidence_items(notes, task)
        context = {
            "config": cfg,
            "query": task,
            "notes": executor_notes(notes),
            "evidence_items": items,
            "timeline": sorted({d for n in notes for d in extract_dates(n.body)}),
            "related": [],
        }
    result = execute_skill(ROOT, skill, context)
    return {
        "skill": skill,
        "inputs": result.get("inputs", []),
        "processed": result.get("processed", 0),
        "issues": result.get("issues", []),
        "planned_pages": planned_pages_from_executor_result(cfg, result, plan_run_id),
    }


def select_llm_input_notes(
    index: VaultIndex,
    cfg: dict[str, Any],
    task: str,
    skill: str,
    changed: list[Note],
    processed_index: dict[str, Any],
) -> list[Note]:
    if skill == "mindseed-grow":
        candidates = [
            n for n in changed
            if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
        ]
        return unprocessed_notes(processed_index, candidates, skill)[:5]
    if skill == "work-memory-weave":
        candidates = [n for n in changed if n.rel.startswith(("quicknote/", "inbox/")) and work_memory_candidate(n)]
        return unprocessed_notes(processed_index, candidates, skill)[:5]
    if skill == "topic-insight-miner":
        return select_notes(index, task, limit=8, prefixes=("wiki/seeds/", "wiki/topics/", "wiki/sources/", "wiki/work-memory/", "raw/"))
    if skill == "writing-material-pack":
        return select_notes(index, task, limit=8, prefixes=("wiki/topics/", "wiki/evidence/", "wiki/gaps/", "wiki/claim-checks/", "wiki/seeds/", "raw/"))
    return select_notes(index, task, limit=6)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    base = path.with_suffix("")
    suffix = path.suffix
    for i in range(2, 200):
        candidate = Path(f"{base}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法生成唯一文件名：{path}")


def write_page(index: VaultIndex, cfg: dict[str, Any], rel_dir: str, filename: str, content: str) -> str:
    path = unique_path(index.root / rel_dir / filename)
    safe_write_text(
        cfg,
        path,
        content,
        run_id=str(cfg.get("_run_id") or run_id()),
        operation="create_page",
        reason="Create derived knowledge page; original source files are not modified.",
    )
    return path.relative_to(index.root).as_posix()


def source_quality(index: VaultIndex, sources: list[str]) -> tuple[bool, list[str]]:
    issues = []
    if not sources:
        issues.append("缺少来源")
    for source in sources:
        if source.endswith("/") or source in {"raw", "raw/", "wiki", "wiki/"}:
            issues.append(f"来源过粗：{source}")
        elif source not in index.by_rel:
            issues.append(f"来源不存在：{source}")
    return not issues, issues


def validate_markdown(index: VaultIndex, content: str, sources: list[str]) -> list[str]:
    issues = []
    _, source_issues = source_quality(index, sources)
    issues.extend(source_issues)
    for target in extract_wikilinks(content):
        resolved = resolve_link(index, target)
        if not resolved and target not in sources:
            issues.append(f"双链无法解析：{target}")
        elif resolved and target != resolved:
            issues.append(f"双链非规范：{target} -> {resolved}")
    if "Manual synthesis required" in content or "No explicit" in content:
        issues.append("存在英文占位内容")
    return issues


def raw_seed_allowed(note: Note, cfg: dict[str, Any]) -> bool:
    if not note.rel.startswith("raw/"):
        return True
    markers = cfg["scan"].get("seed_markers", ["#seed", "#随手记", "#待生长"])
    max_chars = int(cfg["scan"].get("raw_seed_max_chars", 2000))
    text = note.title + "\n" + note.body[: max_chars + 200]
    return len(note.body) <= max_chars or any(marker in text for marker in markers)


def existing_note_by_title(index: VaultIndex, type_: str, title: str, prefix: str) -> Note | None:
    for note in index.by_title.get(title.strip().lower(), []):
        if note.rel.startswith(prefix) and note.metadata.get("type") == type_:
            return note
    return None


def seed_card_for_cluster(index: VaultIndex, cfg: dict[str, Any], cluster: dict[str, Any], notes: list[Note]) -> dict[str, Any]:
    sources = [note.rel for note in notes[:10]]
    ok, issues = source_quality(index, sources)
    confidence = cluster.get("confidence") or ("high" if len(sources) >= 5 else "medium" if len(sources) >= 2 else "low")
    if confidence == "low":
        issues.append("动态聚类置信度低，需要人工判断是否值得生长。")
    status = "seed" if ok and confidence != "low" else "manual_review"
    title = cluster["title"]
    existing = existing_note_by_title(index, "seed-card", title, cfg["write"]["seed_dir"])
    if existing:
        return {
            "skill": "mindseed-grow",
            "created": [],
            "processed": len(notes),
            "inputs": sources,
            "issues": [f"已存在相近 seed，跳过新建：{existing.rel}"],
        }
    content = (
        frontmatter(title, "seed-card", status, sources, tags=cluster.get("tags", ["动态聚类"]), confidence=confidence, stage="seed" if status == "seed" else "needs_context")
        + f"# {title}\n\n"
        + "## 核心议题\n\n"
        + f"这张种子卡来自本轮输入的动态议题聚类，而不是预设主题规则。它聚合与“{title}”相关的资料，用于后续生长为专题页、证据包或写作材料包。\n\n"
        + "## 聚类锚点\n\n"
        + bullet(cluster.get("terms", []), "暂无明确锚点")
        + "\n"
        + "## 来源文件\n\n"
        + "".join(f"- {safe_wikilink(index, src)}\n" for src in sources)
        + "\n## 关键信号\n\n"
        + "".join(f"- {note.title}：{note_summary(note, 120)}\n" for note in notes[:6])
        + "\n## 可生长方向\n\n"
        + "- 提炼一个更窄的研究问题。\n"
        + "- 抽取案例、时间线、观点分歧和证据缺口。\n"
        + "- 若来源充足，可升级为 topic page。\n\n"
        + "## 人工复核项\n\n"
        + ("- 暂无明显复核项。\n" if not issues else "".join(f"- {item}\n" for item in issues))
    )
    created = write_page(index, cfg, cfg["write"]["seed_dir"], f"seed-{cluster['slug']}-{run_id()}.md", content)
    return {"skill": "mindseed-grow", "created": [created], "processed": len(notes), "inputs": sources, "issues": issues}


def skill_mindseed_grow(index: VaultIndex, cfg: dict[str, Any], changed: list[Note], explicit_notes: list[Note] | None = None) -> dict[str, Any]:
    processed_index = load_processed_index(cfg)
    raw_skipped = [n.rel for n in changed if n.rel.startswith("raw/") and not raw_seed_allowed(n, cfg)]
    candidates_all = [
        n for n in changed
        if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
    ]
    if explicit_notes:
        for en in explicit_notes:
            if en not in candidates_all:
                candidates_all.append(en)
                if en.rel in raw_skipped:
                    raw_skipped.remove(en.rel)
    already_processed = [n.rel for n in candidates_all if is_processed(processed_index, n, "mindseed-grow")]
    candidates = unprocessed_notes(processed_index, candidates_all, "mindseed-grow")
    if not candidates:
        issues = [f"已跳过 raw 长文或未标记资料：{item}" for item in raw_skipped[:20]]
        issues.extend(f"输入未变化，跳过：{item}" for item in already_processed[:20])
        return {"skill": "mindseed-grow", "created": [], "processed": 0, "inputs": [], "issues": issues}
    limited = candidates[: cfg["scan"]["max_files_per_run"]]
    result = apply_executor_pages(index, cfg, execute_skill(ROOT, "mindseed-grow", {
        "config": cfg,
        "notes": executor_notes(limited),
    }))
    result["issues"].extend(f"已跳过 raw 长文或未标记资料：{item}" for item in raw_skipped[:20])
    result["issues"].extend(f"输入未变化，跳过：{item}" for item in already_processed[:20])
    return result


def work_memory_candidate(note: Note) -> bool:
    text = note.title + "\n" + note.body[:1500]
    patterns = ["会议", "周报", "项目", "复盘", "决定", "决策", "待办", "行动项", "课程", "上课", "开会", "产品优化"]
    return any(p in text for p in patterns)


def extract_lines(text: str, patterns: list[str], limit: int = 10) -> list[str]:
    out = []
    for line in text.splitlines():
        clean = line.strip(" -*\t")
        if clean and any(p.lower() in clean.lower() for p in patterns):
            out.append(clean[:220])
    return out[:limit]


def extract_dates(text: str) -> list[str]:
    dates = re.findall(r"20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", text)
    return sorted(set(dates))[:20]


def extract_people_orgs(text: str) -> tuple[list[str], list[str]]:
    people = []
    orgs = []
    for line in text.splitlines():
        clean = line.strip(" -*\t")
        if any(key in clean for key in ["参会", "参与", "负责人", "对接", "汇报"]):
            people.append(clean[:160])
        if any(key in clean for key in ["公司", "部门", "团队", "中心", "频道", "新闻网", "机构"]):
            orgs.append(clean[:160])
    return people[:8], orgs[:8]


def skill_work_memory_weave(index: VaultIndex, cfg: dict[str, Any], changed: list[Note], explicit_notes: list[Note] | None = None) -> dict[str, Any]:
    processed_index = load_processed_index(cfg)
    candidates_all = [n for n in changed if n.rel.startswith(("quicknote/", "inbox/")) and work_memory_candidate(n)]
    if explicit_notes:
        for en in explicit_notes:
            if en not in candidates_all:
                candidates_all.append(en)
    already_processed = [n.rel for n in candidates_all if is_processed(processed_index, n, "work-memory-weave")]
    candidates = unprocessed_notes(processed_index, candidates_all, "work-memory-weave")
    created = []
    issues = []
    inputs = []
    for note in candidates[: cfg["scan"]["max_files_per_run"]]:
        inputs.append(note.rel)
        decisions = extract_lines(note.body, ["决定", "决策", "结论", "确认"])
        actions = extract_lines(note.body, ["待办", "行动", "推进", "跟进", "优化", "制作", "上课", "开会"])
        risks = extract_lines(note.body, ["风险", "阻塞", "问题", "困难", "缺少", "延期", "不确定"])
        dates = extract_dates(note.body)
        people, orgs = extract_people_orgs(note.body)
        note_issues = []
        if not dates:
            note_issues.append(f"缺少明确日期：{note.rel}")
        if not actions:
            note_issues.append(f"缺少明确行动项：{note.rel}")
        issues.extend(note_issues)
        title = f"工作记忆：{note.title}"
        content = (
            frontmatter(title, "work-memory", "growing" if not note_issues else "manual_review", [note.rel], tags=["工作记忆"], confidence="medium", stage="active" if not note_issues else "needs_context")
            + f"# {title}\n\n"
            + "## 来源文件\n\n"
            + f"- {safe_wikilink(index, note.rel)}\n\n"
            + "## 项目/事项\n\n"
            + f"- {note.title}\n\n"
            + "## 时间线\n\n"
            + bullet(dates, "未识别到明确日期，需人工复核。")
            + "\n## 关键决策\n\n"
            + bullet(decisions, "未识别到明确决策。")
            + "\n## 行动项\n\n"
            + bullet(actions, "未识别到明确行动项。")
            + "\n## 人物/组织\n\n"
            + "### 人物\n\n"
            + bullet(people, "未识别到明确人物。")
            + "\n### 组织\n\n"
            + bullet(orgs, "未识别到明确组织。")
            + "\n## 风险与阻塞\n\n"
            + bullet(risks, "需要人工确认哪些事项仍然有效。")
            + "\n## 下次回看\n\n"
            + "- 检查行动项是否闭环。\n"
            + "- 检查决策是否仍然有效。\n"
            + "\n## 人工复核项\n\n"
            + bullet(note_issues, "暂无明确复核项。")
        )
        created.append(write_page(index, cfg, cfg["write"]["work_memory_dir"], f"work-memory-{slug(note.title)}-{run_id()}.md", content))
    issues.extend(f"输入未变化，跳过：{item}" for item in already_processed[:20])
    return {"skill": "work-memory-weave", "created": created, "processed": len(candidates), "inputs": inputs, "issues": issues}


def healthcheck(index: VaultIndex, cfg: dict[str, Any]) -> dict[str, Any]:
    legal_status = set(cfg["knowledge_model"]["statuses"])
    legal_stage = set(cfg["knowledge_model"].get("workflow_stages", []))
    duplicates = {title: [n.rel for n in notes] for title, notes in index.by_title.items() if len(notes) > 1}
    broken = []
    missing_meta = []
    source_issues = []
    status_issues = []
    stage_migrations = []
    noncanonical_links = []
    placeholders = []
    for note in index.notes:
        if note.rel.startswith("wiki/") and not note.metadata:
            missing_meta.append(note.rel)
        status = str(note.metadata.get("status", "")).strip()
        if status and status not in legal_status and status in legal_stage:
            stage_migrations.append({"file": note.rel, "current_status": status, "suggested_status": "growing", "suggested_stage": status})
        elif status and status not in legal_status:
            status_issues.append({"file": note.rel, "status": status})
        sources = note_sources(note)
        if note.rel.startswith("wiki/") and note.metadata:
            _, issues = source_quality(index, sources)
            source_issues.extend({"file": note.rel, "issue": item} for item in issues)
        for target in extract_wikilinks(note.body):
            resolved = resolve_link(index, target)
            if not resolved:
                broken.append({"file": note.rel, "target": target})
            elif target != resolved:
                noncanonical_links.append({"file": note.rel, "target": target, "suggested": resolved})
        if "Manual synthesis required" in note.body or "No explicit" in note.body:
            placeholders.append(note.rel)
    inbound = Counter()
    for note in index.notes:
        for target in extract_wikilinks(note.body):
            resolved = resolve_link(index, target)
            if resolved:
                inbound[Path(resolved).stem] += 1
    orphans = [n.rel for n in index.notes if n.rel.startswith("wiki/") and inbound[n.path.stem] == 0 and n.path.name != "README.md"]
    root = index.root
    backlog = {
        "quicknote": len(list((root / "quicknote").glob("*.md"))) if (root / "quicknote").exists() else 0,
        "inbox": len(list((root / "inbox").glob("*.md"))) if (root / "inbox").exists() else 0,
        "raw": len(list((root / "raw").glob("*.md"))) if (root / "raw").exists() else 0,
    }
    risk_buckets = {
        "P0": [],
        "P1": [],
        "P2": [],
        "P3": [],
    }
    for item in source_issues:
        risk_buckets["P1"].append({"kind": "source_issue", **item})
    for item in broken:
        risk_buckets["P1"].append({"kind": "broken_link", **item})
    for item in noncanonical_links:
        risk_buckets["P2"].append({"kind": "noncanonical_link", **item})
    for item in status_issues:
        risk_buckets["P2"].append({"kind": "status_issue", **item})
    for item in stage_migrations:
        risk_buckets["P2"].append({"kind": "stage_migration", **item})
    for item in missing_meta:
        risk_buckets["P2"].append({"kind": "missing_metadata", "file": item})
    for item in placeholders:
        risk_buckets["P3"].append({"kind": "placeholder", "file": item})
    for item in orphans:
        risk_buckets["P3"].append({"kind": "orphan", "file": item})
    for key, count in backlog.items():
        if count:
            risk_buckets["P3"].append({"kind": "backlog", "folder": key, "count": count})
    risk_count = len(broken) + len(missing_meta) + len(source_issues) + len(status_issues) + len(placeholders) + len(noncanonical_links)
    health_score = max(0, 100 - len(risk_buckets["P1"]) * 2 - len(risk_buckets["P2"]) - min(len(risk_buckets["P3"]), 20))
    return {
        "skill": "kb-lint-healthcheck",
        "total_notes": len(index.notes),
        "risk_count": risk_count,
        "health_score": health_score,
        "risk_buckets": {key: value[:100] for key, value in risk_buckets.items()},
        "broken_links": broken[:100],
        "missing_metadata": missing_meta[:100],
        "source_issues": source_issues[:100],
        "status_issues": status_issues[:100],
        "stage_migrations": stage_migrations[:100],
        "noncanonical_links": noncanonical_links[:100],
        "placeholder_pages": placeholders[:100],
        "duplicate_titles": duplicates,
        "orphans": orphans[:100],
        "backlog": backlog,
    }


def topic_question(seed: Note) -> str:
    title = seed.title.replace("Seed:", "").strip()
    if "新闻" in title or "媒体" in title:
        return f"{title}中最值得解释的转型张力是什么？"
    if "温州" in title or "雁荡" in title:
        return f"{title}如何从地方素材变成可持续的文化知识资产？"
    if "规范" in title or "信源" in title:
        return f"{title}为什么难以形成统一标准？"
    return f"{title}背后有哪些值得继续研究的问题？"


def skill_topic_insight_miner(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    seed_notes = select_notes(index, query, limit=8, prefixes=("wiki/seeds/", "wiki/topics/", "raw/"))
    return apply_executor_pages(index, cfg, execute_skill(ROOT, "topic-insight-miner", {
        "config": cfg,
        "query": query,
        "notes": executor_notes(seed_notes),
    }))


def evidence_items(notes: list[Note], query: str) -> list[dict[str, str]]:
    query_terms = tokens(query)
    items = []
    for note in notes:
        lines = []
        for line in note.body.splitlines():
            clean = line.strip(" -*#\t")
            if len(clean) < 12:
                continue
            if any(term.lower() in clean.lower() for term in query_terms):
                lines.append(clean[:220])
        if not lines:
            lines = [note_summary(note, 180)]
        for line in lines[:3]:
            kind = "案例" if any(x in line for x in ["案例", "FT", "NYT", "BBC", "CBC", "DeepSeek", "温州", "项目"]) else "事实线索"
            items.append({"source": note.rel, "kind": kind, "text": line})
    return items[:30]


def skill_evidence_harvester(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=12)
    sources = [n.rel for n in notes]
    items = evidence_items(notes, query)
    timeline = sorted({d for n in notes for d in extract_dates(n.body)})
    # 优先走 executor.py（Jinja2 模板驱动）
    try:
        result = apply_executor_pages(index, cfg, execute_skill(ROOT, "writing-evidence-harvester", {
            "config": cfg,
            "query": query,
            "notes": executor_notes(notes),
            "evidence_items": items,
            "timeline": timeline,
        }))
        result["sources"] = sources
        result["items"] = items
        return result
    except FileNotFoundError:
        pass
    # fallback：规则式提取（注明降级）
    title = f"证据包：{query[:60] or '未命名主题'}"
    status = "compiled" if len(items) >= 5 else "manual_review"
    content = (
        frontmatter(title, "evidence-pack", status, sources, tags=["证据包"], confidence="medium" if status == "compiled" else "low", stage="compiled" if status == "compiled" else "insufficient")
        + f"# {title}\n\n"
        + "## 来源范围\n\n"
        + bullet([safe_wikilink(index, src) for src in sources], "没有找到可用来源。")
        + "\n## 证据条目\n\n"
        + "".join(f"- **{item['kind']}**｜{safe_wikilink(index, item['source'])}｜{item['text']}\n" for item in items)
        + "\n## 时间线线索\n\n"
        + bullet(timeline, "暂未识别到明确时间线。")
        + "\n## 反方与限制\n\n"
        + "- 需要人工确认来源可信度和上下文。\n"
        + "- 需要进一步区分事实、观点和推断。\n"
    )
    issues = validate_markdown(index, content, sources)
    issues.append("executor 未找到，使用 heuristic fallback 生成 evidence-pack。")
    created = write_page(index, cfg, cfg["write"]["evidence_dir"], f"evidence-{slug(query, 'topic')}-{run_id()}.md", content)
    return {"skill": "writing-evidence-harvester", "created": [created], "processed": len(items), "issues": issues, "sources": sources, "items": items}


def skill_material_pack(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    # Step 1: 先跑 evidence harvester（现在走 executor.py）
    evidence = skill_evidence_harvester(index, cfg, query)
    notes = select_notes(index, query, limit=12)
    sources = evidence.get("sources", [])
    items = evidence.get("items", [])
    timeline = sorted({d for n in notes for d in extract_dates(n.body)})
    # Step 2: material-pack 走 executor.py（Jinja2 驱动）
    result = apply_executor_pages(index, cfg, execute_skill(ROOT, "writing-material-pack", {
        "config": cfg,
        "query": query,
        "notes": executor_notes(notes),
        "evidence_items": items,
        "timeline": timeline,
        "related": evidence.get("created", []),
    }))
    result["created"].extend(evidence.get("created", []))
    result["issues"].extend(evidence.get("issues", []))
    result["inputs"] = sorted(set(result.get("inputs", []) + sources))
    return result


def skill_gap_finder(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=10)
    sources = [n.rel for n in notes]
    items = evidence_items(notes, query)
    timeline = sorted({d for n in notes for d in extract_dates(n.body)})
    # 优先走 executor.py（Jinja2 模板驱动）
    try:
        result = apply_executor_pages(index, cfg, execute_skill(ROOT, "knowledge-gap-finder", {
            "config": cfg,
            "query": query,
            "notes": executor_notes(notes),
            "evidence_items": items,
            "timeline": timeline,
        }))
        return result
    except FileNotFoundError:
        pass
    # fallback：规则式提取
    gaps = []
    if not any(item["kind"] == "案例" for item in items):
        gaps.append("缺少具体案例")
    if not any(extract_dates(n.body) for n in notes):
        gaps.append("缺少清晰时间线")
    if len(sources) < 3:
        gaps.append("来源数量不足")
    gaps.extend(["缺少反方观点", "缺少可直接引用的关键段落"])
    title = f"知识缺口报告：{query[:60] or '未命名主题'}"
    content = (
        frontmatter(title, "gap-report", "growing" if sources else "manual_review", sources, tags=["知识缺口"], confidence="medium", stage="open")
        + f"# {title}\n\n"
        + "## 已有证据\n\n"
        + bullet([safe_wikilink(index, src) for src in sources], "暂无可用来源。")
        + "\n## 缺口清单\n\n"
        + bullet(gaps, "暂未识别到明显缺口。")
        + "\n## 推荐补充路径\n\n"
        + "- 查找一手来源。\n- 补充反方材料。\n- 为关键事实寻找可引用段落。\n"
    )
    created = write_page(index, cfg, cfg["write"]["gaps_dir"], f"gap-{slug(query, 'topic')}-{run_id()}.md", content)
    return {"skill": "knowledge-gap-finder", "created": [created], "processed": len(gaps), "issues": ["executor 未找到，使用 heuristic fallback。"]}


def skill_claim_checker(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=10)
    sources = [n.rel for n in notes]
    claims = re.split(r"[。；;\n]", query)
    claims = [c.strip() for c in claims if len(c.strip()) > 6] or [query]
    rows = []
    for claim in claims[:10]:
        terms = tokens(claim)
        support = [n.rel for n in notes if score_note(n, terms) > 0][:5]
        level = "medium" if len(support) >= 2 else "weak" if support else "unsupported"
        rows.append((claim, level, support))
    title = f"观点证据校验：{query[:50] or '未命名论断'}"
    content = frontmatter(title, "claim-check", "compiled", sources, tags=["证据校验"], confidence="medium", stage="checking") + f"# {title}\n\n"
    for claim, level, support in rows:
        content += f"## {claim}\n\n- 证据等级：{level}\n- 支持来源：\n"
        content += bullet([safe_wikilink(index, src) for src in support], "暂无来源支持，不能写成结论。")
        content += "\n"
    created = write_page(index, cfg, cfg["write"]["claims_dir"], f"claim-check-{slug(query, 'claim')}-{run_id()}.md", content)
    return {"skill": "claim-evidence-checker", "created": [created], "processed": len(rows), "issues": []}


def skill_case_bank(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=12)
    items = [item for item in evidence_items(notes, query) if item["kind"] == "案例"]
    sources = sorted(set(item["source"] for item in items))
    title = f"案例库条目：{query[:60] or '未命名主题'}"
    content = (
        frontmatter(title, "case-story", "compiled" if items else "manual_review", sources, tags=["案例库"], confidence="medium" if items else "low", stage="draft" if items else "needs_context")
        + f"# {title}\n\n"
        + "## 案例条目\n\n"
        + bullet([f"{safe_wikilink(index, item['source'])}｜{item['text']}" for item in items], "暂未识别到足够明确的案例。")
        + "\n## 可说明的观点\n\n"
        + "- 需要人工把案例与具体论点绑定。\n\n"
        + "## 风险与限制\n\n"
        + "- 案例上下文需回到原文确认。\n"
    )
    created = write_page(index, cfg, cfg["write"]["cases_dir"], f"case-story-{slug(query, 'case')}-{run_id()}.md", content)
    return {"skill": "case-story-bank-builder", "created": [created], "processed": len(items), "issues": []}


def skill_project_review(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=10, prefixes=("wiki/work-memory/", "quicknote/", "inbox/"))
    sources = [n.rel for n in notes]
    title = f"项目复盘提炼：{query[:60] or '未命名项目'}"
    content = (
        frontmatter(title, "project-review", "growing" if sources else "manual_review", sources, tags=["项目复盘"], confidence="medium" if sources else "low", stage="draft")
        + f"# {title}\n\n"
        + "## 项目背景\n\n"
        + bullet([f"{safe_wikilink(index, n.rel)}｜{note_summary(n, 120)}" for n in notes], "缺少项目来源。")
        + "\n## 决策节点\n\n"
        + bullet([line for n in notes for line in extract_lines(n.body, ["决定", "决策", "确认"])], "未识别到明确决策节点。")
        + "\n## 可复用方法\n\n"
        + "- 需要人工确认哪些经验可迁移。\n\n"
        + "## 下次检查清单\n\n"
        + "- 目标是否明确。\n- 关键决策是否记录。\n- 行动项是否闭环。\n"
    )
    created = write_page(index, cfg, cfg["write"]["reviews_dir"], f"project-review-{slug(query, 'project')}-{run_id()}.md", content)
    return {"skill": "project-review-synthesizer", "created": [created], "processed": len(notes), "issues": []}


def skill_topic_compile(index: VaultIndex, cfg: dict[str, Any], query: str) -> dict[str, Any]:
    notes = select_notes(index, query, limit=15)
    sources = [n.rel for n in notes]
    seed_links = [n.rel for n in notes if n.rel.startswith("wiki/seeds/")]
    raw_links = [n.rel for n in notes if n.rel.startswith("raw/")]
    existing_topics = [n.rel for n in notes if n.rel.startswith("wiki/topics/")]
    status = "compiled" if len(sources) >= 3 else "manual_review"
    title = f"专题页：{query[:60] or '未命名专题'}"
    content = (
        frontmatter(title, "topic-page", status, sources, tags=["专题沉淀"], confidence="medium" if status == "compiled" else "low", stage="compiled" if status == "compiled" else "needs_context")
        + f"# {title}\n\n"
        + "## 主题边界\n\n"
        + f"{query}\n\n"
        + "## 双链索引\n\n"
        + "### 来源\n\n"
        + safe_link_list(index, raw_links, "暂无可解析 raw 来源。")
        + "\n### 已有种子\n\n"
        + safe_link_list(index, seed_links, "暂无相关 seed。")
        + "\n### 相关专题\n\n"
        + safe_link_list(index, existing_topics, "暂无已有相关专题。")
        + "\n### 概念页\n\n"
        + "- 待创建：从本专题中拆分稳定概念。\n\n"
        + "### 来源笔记\n\n"
        + "- 待创建：为高价值来源生成 source-note。\n\n"
        + "### 待创建链接\n\n"
        + "- 待创建概念和来源笔记必须先落盘，再写成双链。\n\n"
        + "## 来源地图\n\n"
        + bullet([f"{safe_wikilink(index, n.rel)}｜{n.title}" for n in notes], "来源不足。")
        + "\n## 已知事实\n\n"
        + bullet([f"{safe_wikilink(index, item['source'])}｜{item['text']}" for item in evidence_items(notes, query)[:12]], "暂未抽取到足够事实。")
        + "\n## 概念与关系\n\n"
        + "- 待进一步拆分为 concept page。\n\n"
        + "## 冲突与问题\n\n"
        + "- 需要检查是否存在来源冲突。\n\n"
        + "## 下一步\n\n"
        + "- 生成 evidence pack。\n- 识别知识缺口。\n"
    )
    created = write_page(index, cfg, cfg["write"]["topics_dir"], f"topic-{slug(query, 'topic')}-{run_id()}.md", content)
    return {"skill": "topic-research-compile", "created": [created], "processed": len(notes), "issues": validate_markdown(index, content, sources)}


def merge_ops(skill: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    created = []
    issues = []
    inputs = []
    processed = 0
    for op in operations:
        created.extend(op.get("created", []))
        issues.extend(op.get("issues", []))
        inputs.extend(op.get("inputs", []))
        processed += int(op.get("processed", 0))
    return {"skill": skill, "created": created, "processed": processed, "inputs": sorted(set(inputs)), "issues": issues}


def classify_action_risk(action: dict[str, Any]) -> str:
    if action.get("operation") in {"delete", "move", "rename", "merge", "rewrite_raw"}:
        return "high"
    if action.get("writes_to_raw"):
        return "high"
    if action.get("source_scope") == "raw_default":
        return "medium"
    return action.get("risk", "low")


def plan_filename(plan: dict[str, Any]) -> str:
    safe_entry = slug(str(plan.get("entry") or "task"), "entry")
    return f"{plan['run_id']}-{safe_entry}.json"


def write_execution_plan(cfg: dict[str, Any], plan: dict[str, Any]) -> Path:
    target_dir = plan_dir(cfg)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / plan_filename(plan)
    write_json(path, plan)
    return path


def write_manual_review_queue(cfg: dict[str, Any], plan: dict[str, Any]) -> int:
    items = plan.get("manual_review", [])
    if not items:
        return 0
    target = review_queue_path(cfg)
    for item in items:
        record = {
            "run_id": plan.get("run_id"),
            "entry": plan.get("entry"),
            "task": plan.get("task"),
            **item,
        }
        append_item(target, record)
    return len(items)


def make_execution_plan(cfg: dict[str, Any], task: str, scheduled: bool = False, use_llm: bool = False, mock_llm: bool = False) -> dict[str, Any]:
    plan_run_id = run_id()
    index = build_index(cfg)
    state = load_state(cfg)
    changed = changed_notes(index, state)
    processed_index = load_processed_index(cfg)
    router = load_router()
    routed = route_item(task, router) or {}
    entry = routed.get("entry") or router.get("default_entry") or "organize_kb"
    workflow = workflow_for_entry(entry)
    primary_skill = routed.get("primary_skill") or workflow.get("primary_skill") or route(task)
    pipeline = workflow.get("pipeline") or [primary_skill]
    lint = healthcheck(index, cfg) if entry == "healthcheck" or scheduled else None
    mindseed_inputs = [
        n for n in changed
        if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
    ]
    mindseed_unprocessed = unprocessed_notes(processed_index, mindseed_inputs, "mindseed-grow")
    work_memory_inputs = [n for n in changed if n.rel.startswith(("quicknote/", "inbox/")) and work_memory_candidate(n)]
    work_memory_unprocessed = unprocessed_notes(processed_index, work_memory_inputs, "work-memory-weave")
    raw_inputs = [n for n in changed if n.rel.startswith("raw/")]
    raw_unprocessed = unprocessed_notes(processed_index, raw_inputs, "raw-ingest-router")
    raw_blocked = [n.rel for n in changed if n.rel.startswith("raw/") and not raw_seed_allowed(n, cfg)]
    actions: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []

    if scheduled:
        actions.extend([
            {
                "operation": "run_primary_skill",
                "entry": "organize_kb",
                "skill": "raw-ingest-router",
                "risk": "low",
                "reason": "自动分类并分发长文报告与记录。",
                "estimated_inputs": len(raw_unprocessed),
            },
            {
                "operation": "run_primary_skill",
                "entry": "organize_kb",
                "skill": "mindseed-grow",
                "risk": "low",
                "reason": "每日整理入口，处理 quicknote/inbox 以及 router 判定的碎片。",
                "estimated_inputs": len(mindseed_unprocessed),
                "skipped_already_processed": len(mindseed_inputs) - len(mindseed_unprocessed),
            },
            {
                "operation": "run_primary_skill",
                "entry": "weave_work_memory",
                "skill": "work-memory-weave",
                "risk": "low",
                "reason": "每日工作记忆入口，处理 quicknote/inbox 以及 router 判定的工作记录。",
                "estimated_inputs": len(work_memory_unprocessed),
                "skipped_already_processed": len(work_memory_inputs) - len(work_memory_unprocessed),
            },
            {
                "operation": "run_primary_skill",
                "entry": "organize_kb",
                "skill": "topic-research-compile",
                "risk": "medium",
                "reason": "沉淀 router 判定为调研报告的长文（如果有）。",
                "estimated_inputs": 0,
            },
            {
                "operation": "write_run_report",
                "entry": "healthcheck",
                "skill": "kb-lint-healthcheck",
                "risk": "low",
                "reason": "每日运行报告和健康摘要。",
                "estimated_risks": (lint or {}).get("risk_count", 0),
            },
        ])
    elif entry == "healthcheck":
        actions.append({
            "operation": "write_report",
            "entry": entry,
            "skill": primary_skill,
            "risk": "low",
            "target": cfg["write"]["reports_dir"],
            "reason": "生成健康检查报告，不修改知识内容。",
            "estimated_risks": (lint or {}).get("risk_count", 0),
        })
    else:
        actions.append({
            "operation": "run_primary_skill",
            "entry": entry,
            "skill": primary_skill,
            "risk": "low",
            "target": workflow.get("writes_by_default", []),
            "reason": workflow.get("description") or "执行入口 primary skill。",
            "pipeline_declared": pipeline,
            "pipeline_executed_now": [primary_skill],
            "estimated_inputs": len(mindseed_unprocessed) if primary_skill == "mindseed-grow" else len(changed),
            "skipped_already_processed": (len(mindseed_inputs) - len(mindseed_unprocessed)) if primary_skill == "mindseed-grow" else 0,
        })

    if raw_blocked and (scheduled or primary_skill == "mindseed-grow"):
        manual_review.append({
            "type": "raw_input_blocked",
            "risk": "medium",
            "reason": "raw 默认不应进入 mindseed-grow；需要用户指定、短文本或 seed 标记。",
            "items": raw_blocked[:20],
        })
    if lint and lint.get("risk_count", 0):
        manual_review.append({
            "type": "health_risks_detected",
            "risk": "medium",
            "reason": "健康检查发现风险，修复前需要 plan/apply 或人工确认。",
            "risk_count": lint.get("risk_count", 0),
        })

    for action in actions:
        action["risk"] = classify_action_risk(action)

    planned_pages: list[dict[str, Any]] = []
    plan_executor_result = mvp_executor_plan(index, cfg, task, primary_skill, changed, processed_index, plan_run_id) if not scheduled else None
    if plan_executor_result:
        planned_pages = plan_executor_result.get("planned_pages", [])
        for action in actions:
            if action.get("operation") == "run_primary_skill":
                action["execution_mode"] = "plan_preview"
                action["planned_pages"] = len(planned_pages)
                action["planned_inputs"] = len(plan_executor_result.get("inputs", []))
        if plan_executor_result.get("issues"):
            manual_review.append({
                "type": "planned_executor_issues",
                "risk": "medium",
                "reason": "MVP Skill executor produced review issues; inspect planned pages before apply-plan.",
                "items": plan_executor_result.get("issues", [])[:20],
            })

    llm_result: dict[str, Any] | None = None
    if use_llm and not scheduled:
        input_notes = select_llm_input_notes(index, cfg, task, primary_skill, changed, processed_index)
        docs = llm_documents(input_notes, int(cfg["scan"].get("max_source_chars", 6000)))
        llm_result = run_skill_runtime(ROOT, cfg, primary_skill, task, docs, mock=mock_llm)
        for action in actions:
            if action.get("operation") == "run_primary_skill":
                action["execution_mode"] = "llm_skill_runtime"
                action["llm_skill_path"] = llm_result.get("skill_path")
                action["llm_items"] = len(llm_result.get("items", []))
                action["llm_ok"] = llm_result.get("ok")
        if llm_result.get("issues"):
            manual_review.append({
                "type": "llm_runtime_issues",
                "risk": "medium",
                "reason": "LLM Skill Runtime returned validation or provider issues; review before apply.",
                "items": llm_result.get("issues", [])[:20],
            })

    return {
        "run_id": plan_run_id,
        "created_at": stamp(),
        "mode": "dry-run",
        "task": task,
        "entry": entry,
        "primary_skill": primary_skill,
        "pipeline_declared": pipeline,
        "pipeline_executed_now": [item["skill"] for item in actions if item.get("operation") == "run_primary_skill"],
        "knowledge_base": str(index.root),
        "changed_files": len(changed),
        "changed_file_sample": [n.rel for n in changed[:30]],
        "actions": actions,
        "planned_pages": planned_pages,
        "llm_runtime": llm_result,
        "manual_review": manual_review,
        "apply_instruction": "重新运行相同命令并添加 --apply 才会写入知识库。",
    }


def print_plan_summary(plan: dict[str, Any], path: Path, queued: int) -> None:
    print(f"计划文件：{path}")
    print(f"入口：{plan.get('entry')}")
    print(f"Primary skill：{plan.get('primary_skill')}")
    print(f"变更文件估计：{plan.get('changed_files')}")
    print(f"计划动作：{len(plan.get('actions', []))}")
    estimated = sum(int(action.get("estimated_inputs", 0)) for action in plan.get("actions", []))
    if estimated:
        print(f"预计处理输入：{estimated}")
    print(f"人工确认项：{len(plan.get('manual_review', []))}")
    llm = plan.get("llm_runtime")
    if llm:
        mode = "mock" if llm.get("mock") else "provider"
        print(f"LLM runtime：{mode}，items={len(llm.get('items', []))}，ok={llm.get('ok')}")
    planned = plan.get("planned_pages", [])
    if planned:
        print(f"计划落盘页面：{len(planned)}")
        print(f"应用命令：python scripts\\personal_kb_steward.py apply-plan {path}")
        # ── Plan Diff 预览 ──
        for pp in planned[:5]:
            print()
            print("─" * 60)
            print(f"  skill: {pp.get('skill', '')}")
            print(f"  路径: {pp.get('target', '')}")
            content = pp.get('content', '')
            preview_lines = content.split('\n')[:20]
            print("  前20行:")
            for pline in preview_lines:
                print(f"    {pline}")
            print("─" * 60)
        if len(planned) > 5:
            print(f"  ... 还有 {len(planned) - 5} 个页面未展示")
    if queued:
        print(f"已写入人工确认队列：{queued}")
    print("当前为 dry-run；添加 --apply 才会写入知识库。")


def write_report(index: VaultIndex, cfg: dict[str, Any], operations: list[dict[str, Any]], lint: dict[str, Any] | None, label: str) -> str:
    created = [item for op in operations for item in op.get("created", [])]
    issues = [item for op in operations for item in op.get("issues", [])]
    title = f"知识库管家运行报告 {run_id()}"
    content = (
        frontmatter(title, "run-report", "compiled", [str(index.root)], tags=["运行报告"], confidence="high", stage="compiled")
        + f"# {title}\n\n"
        + f"## 任务\n\n{label}\n\n"
        + "## 处理概览\n\n"
        + f"- 新建页面：{len(created)}\n"
        + f"- 发现问题：{len(issues) + (lint or {}).get('risk_count', 0)}\n\n"
        + "## 新建页面\n\n"
        + bullet(created, "没有新建页面。")
        + "\n## 质量问题\n\n"
        + bullet(issues, "本次操作未发现生成层面的质量问题。")
    )
    if lint:
        content += (
            "\n## 健康检查摘要\n\n"
            + f"- 健康评分：{lint.get('health_score', '未计算')}\n"
            + f"- 总笔记数：{lint['total_notes']}\n"
            + f"- 风险数：{lint['risk_count']}\n"
            + f"- 断链：{len(lint['broken_links'])}\n"
            + f"- 来源问题：{len(lint['source_issues'])}\n"
            + f"- 缺元数据：{len(lint['missing_metadata'])}\n"
            + f"- 状态迁移建议：{len(lint.get('stage_migrations', []))}\n"
            + f"- 非规范双链：{len(lint.get('noncanonical_links', []))}\n"
        )
        buckets = lint.get("risk_buckets", {})
        content += (
            "\n## 风险分级\n\n"
            + f"- P0：{len(buckets.get('P0', []))}\n"
            + f"- P1：{len(buckets.get('P1', []))}\n"
            + f"- P2：{len(buckets.get('P2', []))}\n"
            + f"- P3：{len(buckets.get('P3', []))}\n"
        )
    rel = write_page(index, cfg, cfg["write"]["reports_dir"], f"kb-steward-{run_id()}.md", content)
    return rel


def command_status(cfg: dict[str, Any]) -> int:
    index = build_index(cfg)
    state = load_state(cfg)
    processed = load_processed_index(cfg).get("processed", {})
    changed = changed_notes(index, state)
    print(f"智能体：{cfg['agent_name_cn']}（{cfg['agent']}）")
    print(f"知识库：{index.root}")
    print(f"笔记数量：{len(index.notes)}")
    print(f"自上次运行后的变更：{len(changed)}")
    print(f"Processed index 来源记录：{len(processed)}")
    print(f"上次运行：{state.get('last_run', '从未运行')}")
    return 0


def command_lint(cfg: dict[str, Any], write: bool = False) -> int:
    ensure_dirs(cfg)
    if write:
        cfg["_run_id"] = run_id()
    index = build_index(cfg)
    lint = healthcheck(index, cfg)
    print(json.dumps(lint, ensure_ascii=False, indent=2))
    if write:
        op = {"skill": "kb-lint-healthcheck", "created": [], "processed": len(index.notes), "issues": []}
        report = write_report(index, cfg, [op], lint, "知识库健康检查")
        op["created"].append(report)
        write_run_log(index, cfg, [op], "知识库健康检查")
        save_state(cfg, build_index(cfg), [op])
        print(f"报告：{report}")
    return 0


def command_run(cfg: dict[str, Any], apply: bool = False, use_llm: bool = True) -> int:
    if not apply:
        plan = make_execution_plan(cfg, "每日知识生长", scheduled=True)
        path = write_execution_plan(cfg, plan)
        queued = write_manual_review_queue(cfg, plan)
        print_plan_summary(plan, path, queued)
        return 0
    ensure_dirs(cfg)
    cfg["_run_id"] = run_id()
    index = build_index(cfg)
    state = load_state(cfg)
    changed = changed_notes(index, state)
    
    # ── 1. raw-ingest-router (长文自动分类) ──
    raw_inputs = [n for n in changed if n.rel.startswith("raw/")]
    processed_index = load_processed_index(cfg)
    raw_unprocessed = unprocessed_notes(processed_index, raw_inputs, "raw-ingest-router")
    
    routing_map = {"seed": [], "work_memory": [], "research_report": [], "unclear": []}
    operations = []
    
    if raw_unprocessed:
        print(f"路由分类 {len(raw_unprocessed)} 篇 raw 长文...")
        router_result = execute_skill(ROOT, "raw-ingest-router", {
            "config": cfg,
            "notes": executor_notes(raw_unprocessed),
            "use_llm": use_llm
        })
        routing_map = router_result.get("routing_map", routing_map)
        
        # 将 router 自己的运行也作为一条 operation，只记录 issues，它本身没有 created 实体页面
        operations.append({
            "skill": "raw-ingest-router",
            "created": [],
            "processed": router_result.get("processed", 0),
            "issues": router_result.get("issues", [])
        })
        
        # unclear 的文件进入 manual review
        for note in routing_map.get("unclear", []):
            append_item(review_queue_path(cfg), {
                "run_id": run_id(),
                "entry": "organize_kb",
                "task": "自动分类长文",
                "type": "unclear_raw_note",
                "risk": "P2",
                "reason": "长文类型不明或难以分类，建议手动处理",
                "sources": [note.get("rel", "")] 
            })

    # 将 map 里的 dict 转换回 Note 对象
    def _to_notes(dict_list: list[dict]) -> list[Note]:
        return [n for n in raw_unprocessed if any(n.rel == d.get("rel") for d in dict_list)]

    seed_notes = _to_notes(routing_map.get("seed", []))
    work_notes = _to_notes(routing_map.get("work_memory", []))
    research_notes = _to_notes(routing_map.get("research_report", []))

    # ── 2. mindseed-grow ──
    operations.append(skill_mindseed_grow(index, cfg, changed, explicit_notes=seed_notes))
    
    # ── 3. work-memory-weave ──
    operations.append(skill_work_memory_weave(index, cfg, changed, explicit_notes=work_notes))
    
    # ── 4. topic-research-compile ──
    if research_notes:
        print(f"提取 {len(research_notes)} 篇调研报告...")
        compile_result = execute_skill(ROOT, "topic-research-compile", {
            "config": cfg,
            "notes": executor_notes(research_notes),
            "use_llm": use_llm
        })
        # topic-research-compile 会输出页面
        topic_op = apply_executor_pages(index, cfg, compile_result)
        # 将新生成的 source-note / topic-page 包含需要人工确认的标记进入 queue
        for pp in compile_result.get("planned_pages", []):
            if pp.get("manual_review"):
                append_item(review_queue_path(cfg), {
                    "run_id": run_id(),
                    "entry": "organize_kb",
                    "task": "长文专题沉淀",
                    **pp["manual_review"]
                })
        operations.append(topic_op)

    lint = healthcheck(index, cfg)
    report = write_report(index, cfg, operations, lint, "每日知识生长")
    operations.append({"skill": "run-report", "created": [report], "processed": 1, "issues": []})
    write_run_log(index, cfg, operations, "每日知识生长")
    update_processed_index(index, cfg, operations)
    save_state(cfg, build_index(cfg), operations)
    update_index(build_index(cfg), cfg)
    print(f"变更文件：{len(changed)}")
    for op in operations:
        print(f"{op['skill']}：新建 {len(op.get('created', []))}，问题 {len(op.get('issues', []))}")
    return 0


def execute_task_apply(cfg: dict[str, Any], task: str) -> int:
    ensure_dirs(cfg)
    cfg["_run_id"] = run_id()
    index = build_index(cfg)
    state = load_state(cfg)
    changed = changed_notes(index, state)
    skill = route(task)
    if skill == "mindseed-grow":
        op = skill_mindseed_grow(index, cfg, changed)
    elif skill == "work-memory-weave":
        op = skill_work_memory_weave(index, cfg, changed)
    elif skill == "kb-lint-healthcheck":
        return command_lint(cfg, write=True)
    elif skill == "topic-insight-miner":
        op = skill_topic_insight_miner(index, cfg, task)
    elif skill == "writing-evidence-harvester":
        op = skill_evidence_harvester(index, cfg, task)
    elif skill == "writing-material-pack":
        op = skill_material_pack(index, cfg, task)
    elif skill == "knowledge-gap-finder":
        op = skill_gap_finder(index, cfg, task)
    elif skill == "claim-evidence-checker":
        op = skill_claim_checker(index, cfg, task)
    elif skill == "case-story-bank-builder":
        op = skill_case_bank(index, cfg, task)
    elif skill == "project-review-synthesizer":
        op = skill_project_review(index, cfg, task)
    elif skill == "topic-research-compile":
        op = skill_topic_compile(index, cfg, task)
    else:
        op = {"skill": skill, "created": [], "processed": 0, "issues": [f"未实现的 skill：{skill}"]}
    report = write_report(index, cfg, [op], None, task)
    op2 = {"skill": "run-report", "created": [report], "processed": 1, "issues": []}
    write_run_log(index, cfg, [op, op2], task)
    update_index(index, cfg)
    update_processed_index(index, cfg, [op])
    save_state(cfg, build_index(cfg), [op, op2])
    print(f"任务：{task}")
    print(f"路由技能：{skill}")
    print(f"新建页面：{len(op.get('created', [])) + 1}")
    if op.get("issues"):
        print("问题：")
        for issue in op["issues"]:
            print(f"- {issue}")
    return 0


def command_task(cfg: dict[str, Any], task: str, apply: bool = False, use_llm: bool = False, mock_llm: bool = False) -> int:
    if not apply:
        plan = make_execution_plan(cfg, task, use_llm=use_llm or mock_llm, mock_llm=mock_llm)
        path = write_execution_plan(cfg, plan)
        queued = write_manual_review_queue(cfg, plan)
        print_plan_summary(plan, path, queued)
        return 0
    if route(task) in MVP_EXECUTOR_SKILLS:
        plan = make_execution_plan(cfg, task, use_llm=use_llm or mock_llm, mock_llm=mock_llm)
        path = write_execution_plan(cfg, plan)
        queued = write_manual_review_queue(cfg, plan)
        print_plan_summary(plan, path, queued)
        print("MVP Skill 已升级为 apply-plan 落盘；请审阅 plan 后执行上方 apply-plan 命令。")
        return 0
    return execute_task_apply(cfg, task)


def command_plan(cfg: dict[str, Any], task: str, use_llm: bool = False, mock_llm: bool = False) -> int:
    plan = make_execution_plan(cfg, task, use_llm=use_llm or mock_llm, mock_llm=mock_llm)
    path = write_execution_plan(cfg, plan)
    queued = write_manual_review_queue(cfg, plan)
    print_plan_summary(plan, path, queued)
    return 0


def resolve_plan_ref(cfg: dict[str, Any], ref: str) -> Path:
    path = Path(ref)
    if path.exists():
        return path.resolve()
    base = plan_dir(cfg)
    candidate = base / ref
    if candidate.exists():
        return candidate.resolve()
    matches = list(base.glob(f"*{ref}*.json"))
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise SystemExit(f"找不到 plan：{ref}")
    raise SystemExit(f"plan 引用不唯一：{ref}")


def assert_safe_rel_write(cfg: dict[str, Any], rel_path: str) -> None:
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"拒绝不安全目标路径：{rel_path}")
    first = rel.parts[0] if rel.parts else ""
    if first in set(cfg.get("safety", {}).get("protected_dirs", [])):
        raise SystemExit(f"拒绝写入受保护目录：{rel_path}")


def write_run_manifest(cfg: dict[str, Any], manifest: dict[str, Any]) -> Path:
    target = runs_dir(cfg) / f"{manifest['run_id']}.json"
    safe_write_text(
        cfg,
        target,
        json.dumps(manifest, ensure_ascii=False, indent=2),
        run_id=str(cfg.get("_run_id") or manifest["run_id"]),
        operation="write_run_manifest",
        reason="Persist run manifest with backup if an earlier manifest exists.",
    )
    return target


def command_apply_plan(cfg: dict[str, Any], ref: str) -> int:
    plan_path = resolve_plan_ref(cfg, ref)
    plan = read_json(plan_path, {})
    pages = plan.get("planned_pages", [])
    if not pages:
        raise SystemExit("该 plan 没有 planned_pages，不能 apply-plan。")
    ensure_dirs(cfg)
    root = kb_root(cfg)
    apply_run_id = str(plan.get("run_id") or run_id())
    cfg["_run_id"] = apply_run_id
    created: list[dict[str, Any]] = []
    try:
        append_operation_log(cfg, {
            "operation": "apply_plan_start",
            "run_id": apply_run_id,
            "plan_path": str(plan_path),
            "knowledge_base": str(root),
            "planned_pages": len(pages),
            "backup_dir": str(backup_root(cfg) / apply_run_id),
        })
        for page in pages:
            rel_path = page["rel_path"]
            assert_safe_rel_write(cfg, rel_path)
            target = (root / rel_path).resolve()
            if not str(target).startswith(str(root)):
                raise SystemExit(f"拒绝越界写入：{target}")
            if target.exists():
                raise SystemExit(f"目标已存在，拒绝覆盖：{rel_path}")
            if sha256_text(page["content"]) != page["content_sha256"]:
                raise SystemExit(f"plan 内容 hash 不匹配：{rel_path}")
            safe_write_text(
                cfg,
                target,
                page["content"],
                run_id=apply_run_id,
                operation="apply_plan_create_page",
                reason="Apply reviewed plan page; original raw/quicknote/inbox files are protected.",
            )
            created.append({
                "rel_path": rel_path,
                "sha256": sha256_file(target),
                "skill": page.get("skill"),
                "sources": page.get("sources", []),
            })

        index = build_index(cfg)
        op = {
            "skill": plan.get("primary_skill"),
            "created": [item["rel_path"] for item in created],
            "processed": len({src for item in created for src in item.get("sources", [])}),
            "inputs": sorted({src for item in created for src in item.get("sources", [])}),
            "issues": [],
        }
        write_run_log(index, cfg, [op], plan.get("task", "apply-plan"))
        update_processed_index(index, cfg, [op])
        save_state(cfg, build_index(cfg), [op])
        update_index(build_index(cfg), cfg)
        manifest = {
            "run_id": apply_run_id,
            "applied_at": stamp(),
            "plan_path": str(plan_path),
            "knowledge_base": str(root),
            "created": created,
            "backup_dir": str(backup_root(cfg) / apply_run_id),
            "operation_log": str(operation_log_path(cfg)),
            "recovery_hint": recovery_hint(cfg, apply_run_id),
            "status": "applied",
        }
        manifest_path = write_run_manifest(cfg, manifest)
        append_operation_log(cfg, {
            "operation": "apply_plan_complete",
            "run_id": apply_run_id,
            "created": [item["rel_path"] for item in created],
            "manifest_path": str(manifest_path),
        })
        print(f"已应用 plan：{plan_path}")
        print(f"新建页面：{len(created)}")
        print(f"run manifest：{manifest_path}")
        print(f"备份目录：{backup_root(cfg) / apply_run_id}")
        print(f"操作日志：{operation_log_path(cfg)}")
        print(f"回滚命令：python scripts\\personal_kb_steward.py rollback {apply_run_id}")
        return 0
    except (Exception, SystemExit) as exc:
        failed_manifest = {
            "run_id": apply_run_id,
            "failed_at": stamp(),
            "plan_path": str(plan_path),
            "knowledge_base": str(root),
            "created": created,
            "backup_dir": str(backup_root(cfg) / apply_run_id),
            "operation_log": str(operation_log_path(cfg)),
            "recovery_hint": recovery_hint(cfg, apply_run_id),
            "status": "failed",
            "error": str(exc),
        }
        manifest_path = write_run_manifest(cfg, failed_manifest)
        append_operation_log(cfg, {
            "operation": "apply_plan_failed",
            "run_id": apply_run_id,
            "error": str(exc),
            "manifest_path": str(manifest_path),
        })
        print(f"apply-plan 失败：{exc}", file=sys.stderr)
        print(recovery_hint(cfg, apply_run_id), file=sys.stderr)
        print(f"失败 run manifest：{manifest_path}", file=sys.stderr)
        raise


def resolve_run_manifest(cfg: dict[str, Any], ref: str) -> Path:
    path = Path(ref)
    if path.exists():
        return path.resolve()
    candidate = runs_dir(cfg) / f"{ref}.json"
    if candidate.exists():
        return candidate.resolve()
    matches = list(runs_dir(cfg).glob(f"*{ref}*.json"))
    if len(matches) == 1:
        return matches[0].resolve()
    if not matches:
        raise SystemExit(f"找不到 run manifest：{ref}")
    raise SystemExit(f"run 引用不唯一：{ref}")


def command_rollback(cfg: dict[str, Any], ref: str) -> int:
    manifest_path = resolve_run_manifest(cfg, ref)
    manifest = read_json(manifest_path, {})
    root = kb_root(cfg)
    rollback_run_id = f"rollback-{manifest.get('run_id') or run_id()}"
    cfg["_run_id"] = rollback_run_id
    removed = []
    skipped = []
    append_operation_log(cfg, {
        "operation": "rollback_start",
        "run_id": rollback_run_id,
        "target_run_id": manifest.get("run_id"),
        "manifest_path": str(manifest_path),
    })
    for item in manifest.get("created", []):
        rel_path = item["rel_path"]
        assert_safe_rel_write(cfg, rel_path)
        target = (root / rel_path).resolve()
        if not target.exists():
            skipped.append(f"不存在：{rel_path}")
            continue
        if sha256_file(target) != item.get("sha256"):
            skipped.append(f"hash 已变化，跳过：{rel_path}")
            continue
        safe_delete_file(
            cfg,
            target,
            run_id=rollback_run_id,
            operation="rollback_delete_created_page",
            reason="Rollback deletes a generated page only after backing it up.",
        )
        removed.append(rel_path)
    manifest["status"] = "rolled_back"
    manifest["rolled_back_at"] = stamp()
    manifest["removed"] = removed
    manifest["skipped"] = skipped
    manifest["rollback_backup_dir"] = str(backup_root(cfg) / rollback_run_id)
    manifest["operation_log"] = str(operation_log_path(cfg))
    write_json(manifest_path, manifest)
    append_operation_log(cfg, {
        "operation": "rollback_complete",
        "run_id": rollback_run_id,
        "target_run_id": manifest.get("run_id"),
        "removed": removed,
        "skipped": skipped,
    })
    print(f"已回滚 run：{manifest.get('run_id')}")
    print(f"删除页面：{len(removed)}")
    print(f"删除前备份目录：{backup_root(cfg) / rollback_run_id}")
    print(f"操作日志：{operation_log_path(cfg)}")
    if skipped:
        print("跳过：")
        for item in skipped:
            print(f"- {item}")
    return 0


def command_review(cfg: dict[str, Any], args: Any) -> int:
    target = review_queue_path(cfg)
    items = load_queue(target)
    sub = getattr(args, "review_command", None) or "list"

    if sub == "list":
        show_all = getattr(args, "all", False)
        type_filter = getattr(args, "type", None)
        risk_filter = getattr(args, "risk", None)
        filtered = items if show_all else pending_items(items)
        if type_filter:
            filtered = filter_items(filtered, item_type=type_filter)
        if risk_filter:
            filtered = filter_items(filtered, risk=risk_filter)
        print(f"人工确认队列：{target}")
        print(format_queue_summary(items))
        if not filtered:
            print("  (无匹配记录)")
            return 0
        print()
        for i, item in enumerate(filtered, 1):
            print(format_list_item(item, i))
        return 0

    elif sub == "show":
        item = find_item(items, args.id)
        if not item:
            print(f"未找到 ID：{args.id}")
            return 1
        print(format_show_item(item))
        return 0

    elif sub == "approve":
        reason = getattr(args, "reason", "") or ""
        if approve_item(items, args.id, reason):
            save_queue(target, items)
            print(f"已批准：{args.id}")
            return 0
        print(f"未找到待确认项：{args.id}")
        return 1

    elif sub == "reject":
        reason = getattr(args, "reason", "") or ""
        if reject_item(items, args.id, reason):
            save_queue(target, items)
            print(f"已拒绝：{args.id}")
            return 0
        print(f"未找到待确认项：{args.id}")
        return 1

    elif sub == "batch-approve":
        risk_filter = getattr(args, "risk", None)
        type_filter = getattr(args, "type", None)
        count = batch_approve(items, risk=risk_filter, item_type=type_filter)
        if count:
            save_queue(target, items)
        print(f"批量批准：{count} 项")
        return 0

    elif sub == "apply-approved":
        to_apply = approved_items(items)
        if not to_apply:
            print("无已批准待应用项。")
            return 0
        # 已批准项的操作依赖于关联的 plan；目前标记为 applied
        applied = 0
        for item in to_apply:
            item["status"] = "applied"
            item["applied_at"] = stamp()
            applied += 1
        save_queue(target, items)
        print(f"已标记为 applied：{applied} 项")
        print("提示：相关操作需要通过 apply-plan 命令执行对应的 plan 文件。")
        return 0

    else:
        print(f"未知 review 子命令：{sub}")
        return 2


def command_processed(cfg: dict[str, Any]) -> int:
    target = processed_index_path(cfg)
    data = load_processed_index(cfg)
    processed = data.get("processed", {})
    skill_counts: Counter[str] = Counter()
    for record in processed.values():
        for skill in record.get("skills", {}):
            skill_counts[skill] += 1
    print(f"Processed index：{target}")
    print(f"来源记录：{len(processed)}")
    if not skill_counts:
        print("暂无已处理记录。")
        return 0
    for skill, count in sorted(skill_counts.items()):
        print(f"- {skill}: {count}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="个人知识库管家")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--apply", action="store_true", help="执行写入；默认只生成 dry-run plan")
    sub.add_parser("lint")
    health = sub.add_parser("healthcheck")
    health.add_argument("--write", action="store_true", help="写入健康检查报告")
    plan = sub.add_parser("plan")
    plan.add_argument("--llm", action="store_true", help="加载 SKILL.md 并调用 LLM Skill Runtime")
    plan.add_argument("--mock-llm", action="store_true", help="使用 mock LLM 运行 Skill Runtime")
    plan.add_argument("text", nargs="+")
    task = sub.add_parser("task")
    task.add_argument("--apply", action="store_true", help="执行写入；默认只生成 dry-run plan")
    task.add_argument("--llm", action="store_true", help="加载 SKILL.md 并调用 LLM Skill Runtime；仅 dry-run plan 生效")
    task.add_argument("--mock-llm", action="store_true", help="使用 mock LLM 运行 Skill Runtime；仅 dry-run plan 生效")
    task.add_argument("text", nargs="+")
    apply_plan = sub.add_parser("apply-plan")
    apply_plan.add_argument("ref", help="plan 文件路径、run_id 或唯一片段")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("ref", help="run manifest 路径、run_id 或唯一片段")
    # ── review 子命令组 ──
    review_parser = sub.add_parser("review", help="人工确认队列管理")
    review_sub = review_parser.add_subparsers(dest="review_command")
    review_list = review_sub.add_parser("list", help="列出队列")
    review_list.add_argument("--all", action="store_true", help="显示所有状态（包括已处理）")
    review_list.add_argument("--type", help="按类型过滤")
    review_list.add_argument("--risk", help="按风险等级过滤（P0/P1/P2/P3）")
    review_show = review_sub.add_parser("show", help="显示单条详情")
    review_show.add_argument("id", help="记录 ID 或前缀")
    review_approve = review_sub.add_parser("approve", help="批准记录")
    review_approve.add_argument("id", help="记录 ID 或前缀")
    review_approve.add_argument("--reason", default="", help="批准理由")
    review_reject = review_sub.add_parser("reject", help="拒绝记录")
    review_reject.add_argument("id", help="记录 ID 或前缀")
    review_reject.add_argument("--reason", default="", help="拒绝理由")
    review_batch = review_sub.add_parser("batch-approve", help="批量批准")
    review_batch.add_argument("--risk", help="只批准指定风险等级")
    review_batch.add_argument("--type", help="只批准指定类型")
    review_apply = review_sub.add_parser("apply-approved", help="执行所有已批准项")
    sub.add_parser("processed")
    args = parser.parse_args(argv)
    cfg = config()
    if args.command == "status":
        return command_status(cfg)
    if args.command == "run":
        return command_run(cfg, apply=args.apply)
    if args.command == "lint":
        return command_lint(cfg, write=False)
    if args.command == "healthcheck":
        return command_lint(cfg, write=args.write)
    if args.command == "plan":
        return command_plan(cfg, " ".join(args.text), use_llm=args.llm, mock_llm=args.mock_llm)
    if args.command == "task":
        return command_task(cfg, " ".join(args.text), apply=args.apply, use_llm=args.llm, mock_llm=args.mock_llm)
    if args.command == "apply-plan":
        return command_apply_plan(cfg, args.ref)
    if args.command == "rollback":
        return command_rollback(cfg, args.ref)
    if args.command == "review":
        return command_review(cfg, args)
    if args.command == "processed":
        return command_processed(cfg)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
