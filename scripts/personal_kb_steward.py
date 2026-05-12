#!/usr/bin/env python3
"""Personal knowledge-base steward runtime."""
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
from core.finalizer import make_finalize_plan
from core.initializer import make_initialization_plan as build_initialization_plan, split_existing_pages
from core.skill_executor import execute_skill
from core.safety import (
    append_operation_log,
    backup_root,
    operation_log_path,
    recovery_hint,
    safe_delete_file,
    safe_write_text,
    user_next_step,
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
    return f"寰呭垱寤猴細{target}"
def readable_filename(title: str, fallback: str = "未命名页面") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title).strip()
    cleaned = re.sub(r"[：:，,。；;、/\\\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if cleaned.lower().startswith("seed-"):
        cleaned = cleaned[5:].strip("-")
    return cleaned[:80] or fallback
def canonical_link_target(index: VaultIndex, target: str) -> str | None:
    return resolve_link(index, target)
def safe_wikilink(index: VaultIndex, target: str) -> str:
    resolved = canonical_link_target(index, target)
    if not resolved:
        return pending_link(target)
    return wikilink(resolved)
def link_list(items: list[str], empty: str = "鏆傛棤") -> str:
    return bullet([pending_link(item) for item in items], empty)
def safe_link_list(index: VaultIndex, items: list[str], empty: str = "鏆傛棤") -> str:
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
        query_terms = ["ai", "鏂伴椈", "濯掍綋", "娓╁窞", "鐭ヨ瘑"]
    scored: list[tuple[int, Note]] = []
    for note in index.notes:
        if not note.rel.startswith(prefixes):
            continue
        score = score_note(note, query_terms)
        if score:
            scored.append((score, note))
    return [note for _, note in sorted(scored, key=lambda x: (-x[0], x[1].rel))[:limit]]
def query_results(index: VaultIndex, query: str, limit: int = 12, prefixes: tuple[str, ...] = ("raw/", "quicknote/", "inbox/", "wiki/seeds/", "wiki/topics/")) -> list[dict[str, Any]]:
    return [
        {
            "path": note.rel,
            "title": note.title,
            "sources": note_sources(note) or [note.rel],
            "summary": note_summary(note, 180),
        }
        for note in select_notes(index, query, limit=limit, prefixes=prefixes)
    ]
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
    manual_reviews = []
    for page in result.get("pages", []):
        rel_dir = cfg["write"][page["rel_dir_key"]]
        rel = write_page(index, cfg, rel_dir, f"{Path(page['filename']).stem}-{run_id()}.md", page["content"])
        created.append(rel)
        issues.extend(validate_markdown(index, page["content"], page.get("sources", [])))
    for page in result.get("created", []):
        target = page.get("target")
        content = page.get("content")
        if not target or not isinstance(content, str):
            continue
        assert_safe_rel_write(cfg, target)
        target_path = Path(target)
        rel = write_page(index, cfg, target_path.parent.as_posix(), target_path.name, content)
        created.append(rel)
        review = page.get("manual_review")
        review_sources = []
        if review:
            review = dict(review)
            review.setdefault("target", rel)
            review_sources = list(review.get("sources", []))
            manual_reviews.append(review)
            inputs.extend(review_sources)
        issues.extend(validate_markdown(index, content, review_sources))
    return {
        "skill": result.get("skill"),
        "created": created,
        "processed": int(result.get("processed", 0)),
        "inputs": sorted(set(inputs)),
        "issues": issues,
        "items": result.get("items", []),
        "manual_reviews": manual_reviews,
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
            "origin": page.get("origin") or page.get("item", {}).get("origin") or {"source_paths": page.get("sources", [])},
            "content_sha256": sha256_text(content),
            "content": content,
            "review_required": bool(page.get("item", {}).get("review_required", False)),
            "confidence": page.get("item", {}).get("confidence"),
        })
    for page in result.get("created", []):
        target = page.get("target")
        content = page.get("content")
        if not target or not isinstance(content, str):
            continue
        assert_safe_rel_write(cfg, target)
        review = page.get("manual_review") or {}
        sources = list(
            page.get("sources")
            or review.get("sources", [])
            or page.get("origin", {}).get("source_paths", [])
        )
        review_required = bool(review) or bool(page.get("review_required", False))
        pages.append({
            "skill": result.get("skill") or page.get("skill"),
            "operation": "create",
            "rel_path": Path(target).as_posix(),
            "target": Path(target).as_posix(),
            "sources": sources,
            "origin": page.get("origin") or {"source_paths": sources},
            "content_sha256": sha256_text(content),
            "content": content,
            "review_required": review_required,
            "confidence": page.get("confidence") or ("low" if review_required else None),
            "manual_review": review,
            "analysis_mode": page.get("analysis_mode"),
        })
    return pages
def mvp_executor_plan(
    index: VaultIndex,
    cfg: dict[str, Any],
    task: str,
    skill: str,
    changed: list[Note],
    processed_index: dict[str, Any],
    plan_run_id: str,
    *,
    use_llm: bool = False,
) -> dict[str, Any] | None:
    if skill not in MVP_EXECUTOR_SKILLS:
        return None
    if skill == "mindseed-grow":
        candidates_all = [
            n for n in changed
            if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
        ]
        notes = unprocessed_notes(processed_index, candidates_all, skill)[: cfg["scan"]["max_files_per_run"]]
        context = {"config": cfg, "notes": executor_notes(notes)}
    elif skill == "topic-research-compile":
        candidates_all = [n for n in changed if n.rel.startswith("raw/")]
        notes = unprocessed_notes(processed_index, candidates_all, skill)[: cfg["scan"]["max_files_per_run"]]
        context = {"config": cfg, "notes": executor_notes(notes), "use_llm": use_llm}
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
    raise RuntimeError(f"鏃犳硶鐢熸垚鍞竴鏂囦欢鍚嶏細{path}")
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
            issues.append(f"鍙岄摼闈炶鑼冿細{target} -> {resolved}")
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
def work_memory_candidate(note: Note) -> bool:
    text = note.title + "\n" + note.body[:1500]
    patterns = ["会议", "周报", "项目", "复盘", "决定", "决策", "待办", "行动项", "课程", "上课", "开会", "产品优化"]
    return any(p in text for p in patterns)
def raw_coverage_report(index: VaultIndex) -> dict[str, Any]:
    raw_files = sorted(note.rel for note in index.notes if note.rel.startswith("raw/"))
    coverage: dict[str, list[str]] = {rel: [] for rel in raw_files}
    for note in index.notes:
        if not note.rel.startswith("wiki/"):
            continue
        for source in note_sources(note):
            if source in coverage:
                coverage[source].append(note.rel)
    missing = [rel for rel, pages in coverage.items() if not pages]
    return {
        "raw_total": len(raw_files),
        "covered": len(raw_files) - len(missing),
        "missing": missing,
        "coverage": {rel: pages for rel, pages in coverage.items() if pages},
    }
def planned_raw_coverage(raw_files: list[str], pages: list[dict[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, list[str]] = {rel: [] for rel in raw_files}
    for page in pages:
        rel_path = str(page.get("rel_path") or "")
        for source in page.get("sources", []):
            if source in coverage:
                coverage[source].append(rel_path)
    missing = [rel for rel, targets in coverage.items() if not targets]
    return {
        "raw_total": len(raw_files),
        "covered": len(raw_files) - len(missing),
        "missing": missing,
    }
def weak_topic_stub(note: Note) -> bool:
    if note.metadata.get("type") != "topic-page":
        return False
    title = str(note.metadata.get("title") or note.title)
    body = note.body
    return title.startswith("Topic from ") or "Mock stub content" in body or body.count("待补充") >= 2
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
    mock_content = []
    weak_topics = []
    low_confidence_active = []
    processed_schema_error = load_processed_index(cfg).get("_schema_error")
    for note in index.notes:
        if note.rel.startswith("wiki/") and not note.metadata:
            missing_meta.append(note.rel)
        status = str(note.metadata.get("status", "")).strip()
        if status and status not in legal_status and status in legal_stage:
            stage_migrations.append({"file": note.rel, "current_status": status, "suggested_status": "growing", "suggested_stage": status})
        elif status and status not in legal_status:
            status_issues.append({"file": note.rel, "status": status})
        sources = note_sources(note)
        if note.rel.startswith("wiki/") and note.metadata and note.path.name != "README.md":
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
        if note.rel.startswith("wiki/") and any(marker in note.body for marker in BLOCKED_APPLY_MARKERS):
            mock_content.append(note.rel)
        if weak_topic_stub(note):
            weak_topics.append(note.rel)
        confidence = str(note.metadata.get("confidence", "")).strip().lower()
        if note.rel.startswith("wiki/") and confidence == "low" and status == "active":
            low_confidence_active.append(note.rel)
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
    raw_coverage = raw_coverage_report(index)
    risk_buckets = {
        "P0": [],
        "P1": [],
        "P2": [],
        "P3": [],
    }
    for item in source_issues:
        risk_buckets["P1"].append({"kind": "source_issue", **item})
    for item in mock_content:
        risk_buckets["P0"].append({"kind": "mock_content_applied", "file": item})
    if processed_schema_error:
        risk_buckets["P0"].append({"kind": "processed_index_schema_error", "message": processed_schema_error})
    for item in raw_coverage["missing"]:
        risk_buckets["P1"].append({"kind": "raw_coverage_missing", "file": item})
    for item in weak_topics:
        risk_buckets["P1"].append({"kind": "weak_topic_stub", "file": item})
    for item in low_confidence_active:
        risk_buckets["P1"].append({"kind": "low_confidence_marked_active", "file": item})
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
    risk_count = sum(len(items) for items in risk_buckets.values())
    health_score = max(0, 100 - len(risk_buckets["P0"]) * 10 - len(risk_buckets["P1"]) * 3 - len(risk_buckets["P2"]) - min(len(risk_buckets["P3"]), 20))
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
        "mock_content": mock_content[:100],
        "weak_topic_stubs": weak_topics[:100],
        "low_confidence_active": low_confidence_active[:100],
        "processed_index_schema_error": processed_schema_error,
        "raw_coverage": {
            "raw_total": raw_coverage["raw_total"],
            "covered": raw_coverage["covered"],
            "missing": raw_coverage["missing"][:100],
        },
        "duplicate_titles": duplicates,
        "orphans": orphans[:100],
        "backlog": backlog,
    }
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
            kind = "妗堜緥" if any(x in line for x in ["妗堜緥", "FT", "NYT", "BBC", "CBC", "DeepSeek", "娓╁窞", "椤圭洰"]) else "浜嬪疄绾跨储"
            items.append({"source": note.rel, "kind": kind, "text": line})
    return items[:30]
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
    append_operation_log(cfg, {
        "operation": "write_dry_run_plan",
        "run_id": plan.get("run_id"),
        "plan_path": str(path),
        "mode": plan.get("mode", "dry-run"),
        "planned_pages": len(plan.get("planned_pages", [])),
        "next_step": "请审阅 plan；确认无误后再运行 apply-plan。",
    })
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


def make_execution_plan(
    cfg: dict[str, Any],
    task: str,
    scheduled: bool = False,
    use_llm: bool = False,
    mock_llm: bool = False,
    include_all: bool = False,
) -> dict[str, Any]:
    plan_run_id = run_id()
    index = build_index(cfg)
    state = load_state(cfg)
    changed = changed_notes(index, state)
    input_scope = index.notes if include_all else changed
    processed_index = load_processed_index(cfg)
    router = load_router()
    routed = route_item(task, router) or {}
    entry = routed.get("entry") or router.get("default_entry") or "organize_kb"
    workflow = workflow_for_entry(entry)
    primary_skill = routed.get("primary_skill") or workflow.get("primary_skill") or route(task)
    pipeline = workflow.get("pipeline") or [primary_skill]
    lint = healthcheck(index, cfg) if entry == "healthcheck" or scheduled else None
    mindseed_inputs = [
        n for n in input_scope
        if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
    ]
    mindseed_unprocessed = unprocessed_notes(processed_index, mindseed_inputs, "mindseed-grow")
    work_memory_inputs = [n for n in input_scope if n.rel.startswith(("quicknote/", "inbox/")) and work_memory_candidate(n)]
    work_memory_unprocessed = unprocessed_notes(processed_index, work_memory_inputs, "work-memory-weave")
    raw_inputs = [n for n in input_scope if n.rel.startswith("raw/")]
    raw_unprocessed = unprocessed_notes(processed_index, raw_inputs, "raw-ingest-router")
    raw_blocked = [n.rel for n in input_scope if n.rel.startswith("raw/") and not raw_seed_allowed(n, cfg)]
    actions: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    raw_init_guard = (
        not scheduled
        and entry == "organize_kb"
        and len(raw_inputs) >= 3
    )

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
                "reason": "沉淀 router 判定为调研报告的长文。",
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
            "estimated_inputs": len(mindseed_unprocessed) if primary_skill == "mindseed-grow" else len(input_scope),
            "skipped_already_processed": (len(mindseed_inputs) - len(mindseed_unprocessed)) if primary_skill == "mindseed-grow" else 0,
        })

    if raw_blocked and scheduled:
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
    if raw_init_guard:
        manual_review.append({
            "type": "wrong_entry_for_initialization",
            "risk": "high",
            "reason": "organize_kb 不能用于 raw 全量初始化；请改用 init-kb 分批 pipeline。",
            "items": [n.rel for n in raw_inputs[:20]],
        })
    for action in actions:
        action["risk"] = classify_action_risk(action)
    planned_pages: list[dict[str, Any]] = []
    primary_input_scope = input_scope
    if primary_skill == "mindseed-grow":
        primary_input_scope = [note for note in input_scope if not note.rel.startswith("raw/")]
    plan_executor_result = None if raw_init_guard else mvp_executor_plan(
        index,
        cfg,
        task,
        primary_skill,
        primary_input_scope,
        processed_index,
        plan_run_id,
        use_llm=use_llm and not mock_llm,
    ) if not scheduled else None
    if plan_executor_result:
        planned_pages = plan_executor_result.get("planned_pages", [])
        for action in actions:
            if action.get("operation") == "run_primary_skill" and action.get("skill") == primary_skill:
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

    raw_compile_result: dict[str, Any] | None = None
    if not scheduled and primary_skill == "mindseed-grow" and raw_unprocessed and not raw_init_guard:
        raw_compile_result = mvp_executor_plan(
            index,
            cfg,
            task,
            "topic-research-compile",
            input_scope,
            processed_index,
            plan_run_id,
            use_llm=use_llm and not mock_llm,
        )
        raw_pages = raw_compile_result.get("planned_pages", []) if raw_compile_result else []
        if raw_pages:
            planned_pages.extend(raw_pages)
            actions.append({
                "operation": "run_follow_up_skill",
                "entry": "organize_kb",
                "skill": "topic-research-compile",
                "risk": classify_action_risk({"operation": "run_follow_up_skill", "risk": "medium"}),
                "reason": "raw/ long-form inputs are routed to topic-research-compile instead of mindseed-grow.",
                "pipeline_declared": pipeline,
                "pipeline_executed_now": ["topic-research-compile"],
                "execution_mode": "plan_preview",
                "estimated_inputs": len(raw_unprocessed),
                "planned_inputs": len(raw_compile_result.get("inputs", [])),
                "planned_pages": len(raw_pages),
            })
        elif raw_blocked:
            manual_review.append({
                "type": "raw_input_blocked",
                "risk": "medium",
                "reason": "raw/ inputs were excluded from mindseed-grow, but topic-research-compile produced no planned_pages.",
                "items": raw_blocked[:20],
            })
        if raw_compile_result and raw_compile_result.get("issues"):
            manual_review.append({
                "type": "planned_executor_issues",
                "risk": "medium",
                "reason": "topic-research-compile produced review issues; inspect planned pages before apply-plan.",
                "items": raw_compile_result.get("issues", [])[:20],
            })
    for page in planned_pages:
        if str(page.get("rel_path", "")).startswith("wiki/sources/") and not page_has_blocked_placeholder(page):
            page["review_required"] = False
            page["confidence"] = "high"
    review_pages = [p for p in planned_pages if page_requires_manual_review(p)]
    if review_pages:
        manual_review.append({
            "type": "planned_pages_require_review",
            "risk": "medium",
            "reason": "plan contains review_required or low-confidence pages; approve the queue before review apply-approved.",
            "items": [p.get("rel_path") for p in review_pages[:20]],
        })

    llm_result: dict[str, Any] | None = None
    if use_llm and not scheduled:
        input_notes = select_llm_input_notes(index, cfg, task, primary_skill, input_scope, processed_index)
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
        "pipeline_executed_now": [
            item["skill"]
            for item in actions
            if item.get("operation") in {"run_primary_skill", "run_follow_up_skill"}
        ],
        "knowledge_base": str(index.root),
        "scan_scope": "all" if include_all else "changed",
        "changed_files": len(changed),
        "candidate_files": len(input_scope),
        "changed_file_sample": [n.rel for n in changed[:30]],
        "actions": actions,
        "planned_pages": planned_pages,
        "plan_quality": {
            "duplicate_targets": duplicate_page_targets(planned_pages),
            "blocked_placeholder_pages": [p.get("rel_path") for p in planned_pages if page_has_blocked_placeholder(p)],
            "raw_coverage": planned_raw_coverage([n.rel for n in raw_inputs], planned_pages),
        },
        "llm_runtime": llm_result,
        "manual_review": manual_review,
        "apply_instruction": "请审阅 plan；无人工审核项时运行 apply-plan，有人工审核项时先 review approve 再运行 review apply-approved。",
    }


def print_plan_summary(plan: dict[str, Any], path: Path, queued: int) -> None:
    print(f"璁″垝鏂囦欢锛{path}")
    print(f"鍏ュ彛锛{plan.get('entry')}")
    print(f"Primary skill锛{plan.get('primary_skill')}")
    print(f"鎵弿鑼冨洿锛{plan.get('scan_scope', 'changed')}")
    print(f"鍙樻洿鏂囦欢浼拌锛{plan.get('changed_files')}")
    if plan.get("scan_scope") == "all":
        print(f"鍊欓€夋枃浠舵€绘暟锛{plan.get('candidate_files')}")
    batching = plan.get("batching") or {}
    if batching:
        print(
            "鍒濆鍖栨壒娆★細"
            + f"raw {batching.get('raw_batches', 0)} 鎵癸紝"
            + f"quicknote/inbox {batching.get('quicknote_batches', 0)} 鎵癸紝"
            + f"本批后剩余 {batching.get('remaining_after_current', 0)} 个输入\n"
        )
    print(f"璁″垝鍔ㄤ綔锛{len(plan.get('actions', []))}")
    estimated = sum(int(action.get("estimated_inputs", 0)) for action in plan.get("actions", []))
    if estimated:
        print(f"棰勮澶勭悊杈撳叆锛{estimated}")
    print(f"浜哄伐纭椤癸細{len(plan.get('manual_review', []))}")
    quality = plan.get("plan_quality") or {}
    if quality.get("duplicate_targets"):
        print(f"閲嶅鐩爣璺緞锛{len(quality.get('duplicate_targets', {}))}")
    blocked = quality.get("blocked_placeholder_pages") or []
    if blocked:
        print(f"mock/鍗犱綅椤甸潰锛{len(blocked)}")
    raw_cov = quality.get("raw_coverage") or {}
    if raw_cov.get("raw_total"):
        print(f"raw 瑕嗙洊锛{raw_cov.get('covered', 0)}/{raw_cov.get('raw_total', 0)}")
    if quality.get("pdf_needs_extraction"):
        print(f"PDF 寰呮娊鍙栵細{len(quality.get('pdf_needs_extraction', []))}")
    llm = plan.get("llm_runtime")
    if llm:
        mode = "mock" if llm.get("mock") else "provider"
        print(f"LLM runtime锛{mode}锛宨tems={len(llm.get('items', []))}锛宱k={llm.get('ok')}")
    planned = plan.get("planned_pages", [])
    if planned:
        print(f"璁″垝钀界洏椤甸潰锛{len(planned)}")
        print(f"搴旂敤鍛戒护锛歱ython scripts\\personal_kb_steward.py apply-plan {path}")
        # 鈹€鈹€ Plan Diff 棰勮 鈹€鈹€
        for pp in planned[:5]:
            print()
            print("鈹€" * 60)
            print(f"  skill: {pp.get('skill', '')}")
            print(f"  璺緞: {pp.get('target', '')}")
            content = pp.get('content', '')
            preview_lines = content.split('\n')[:20]
            print("  鍓?0琛?")
            for pline in preview_lines:
                print(f"    {pline}")
            print("鈹€" * 60)
        if len(planned) > 5:
            print(f"  ... 杩樻湁 {len(planned) - 5} 涓〉闈㈡湭灞曠ず")
    if queued:
        print(f"宸插啓鍏ヤ汉宸ョ‘璁ら槦鍒楋細{queued}")
    print(f"当前为 dry-run；{plan.get('apply_instruction')}")


def write_report(index: VaultIndex, cfg: dict[str, Any], operations: list[dict[str, Any]], lint: dict[str, Any] | None, label: str) -> str:
    created = [item for op in operations for item in op.get("created", [])]
    inputs = sorted({item for op in operations for item in op.get("inputs", [])})
    issues = [item for op in operations for item in op.get("issues", [])]
    title = f"知识库管家运行报告 {run_id()}"
    content = (
        frontmatter(title, "run-report", "compiled", inputs, tags=["运行报告"], confidence="high", stage="compiled", origin={"source_paths": inputs, "operation": "run-report"})
        + f"# {title}\n\n"
        + f"## 任务\n\n{label}\n\n"
        + "## 处理概览\n\n"
        + f"- 新建/更新页面：{len(created)}\n"
        + f"- 发现问题：{len(issues) + (lint or {}).get('risk_count', 0)}\n\n"
        + "## 输入文件\n\n"
        + bullet(inputs, "没有输入文件。")
        + "\n"
        + "## 新建/更新页面\n\n"
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
    schema_error = load_processed_index(cfg).get("_schema_error")
    changed = changed_notes(index, state)
    print(f"智能体：{cfg['agent_name_cn']}（{cfg['agent']}）")
    print(f"鐭ヨ瘑搴擄細{index.root}")
    print(f"绗旇鏁伴噺锛{len(index.notes)}")
    print(f"鑷笂娆¤繍琛屽悗鐨勫彉鏇达細{len(changed)}")
    print(f"Processed index 鏉ユ簮璁板綍锛{len(processed)}")
    if schema_error:
        print(f"Processed index schema 閿欒锛{schema_error}")
    print(f"涓婃杩愯锛{state.get('last_run', '浠庢湭杩愯')}")
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
        print(f"鎶ュ憡锛{report}")
    return 0


def command_run(cfg: dict[str, Any], apply: bool = False, use_llm: bool = True, include_all: bool = False) -> int:
    if apply:
        print("安全执行模型已收口：run --apply 不再直接写入知识库。")
    plan = make_execution_plan(cfg, "姣忔棩鐭ヨ瘑鐢熼暱", scheduled=True, include_all=include_all)
    path = write_execution_plan(cfg, plan)
    queued = write_manual_review_queue(cfg, plan)
    print_plan_summary(plan, path, queued)
    return 0


def command_task(
    cfg: dict[str, Any],
    task: str,
    apply: bool = False,
    use_llm: bool = False,
    mock_llm: bool = False,
    include_all: bool = False,
) -> int:
    if apply:
        print("安全执行模型已收口：task --apply 不再直接写入知识库。")
    plan = make_execution_plan(cfg, task, use_llm=use_llm or mock_llm, mock_llm=mock_llm, include_all=include_all)
    path = write_execution_plan(cfg, plan)
    queued = write_manual_review_queue(cfg, plan)
    print_plan_summary(plan, path, queued)
    if apply:
        print("请审阅 plan 后执行上方 apply-plan 命令；如包含人工审核项，请先 review approve 后运行 review apply-approved。")
    return 0


def command_plan(
    cfg: dict[str, Any],
    task: str,
    use_llm: bool = False,
    mock_llm: bool = False,
    include_all: bool = False,
) -> int:
    plan = make_execution_plan(cfg, task, use_llm=use_llm or mock_llm, mock_llm=mock_llm, include_all=include_all)
    path = write_execution_plan(cfg, plan)
    queued = write_manual_review_queue(cfg, plan)
    print_plan_summary(plan, path, queued)
    return 0


def command_init_kb(
    cfg: dict[str, Any],
    *,
    batch_size: int = 6,
    use_llm: bool = True,
    no_llm: bool = False,
    apply: bool = False,
    max_batches: int = 20,
) -> int:
    applied_batches = 0
    limit = max(1, max_batches)
    for batch_index in range(limit):
        plan = build_initialization_plan(cfg, plan_run_id=run_id(), stamp=stamp(), executor_plan_fn=mvp_executor_plan, page_requires_manual_review=page_requires_manual_review, duplicate_page_targets=duplicate_page_targets, page_has_blocked_placeholder=page_has_blocked_placeholder, planned_raw_coverage=planned_raw_coverage, batch_size=batch_size, use_llm=use_llm and not no_llm, include_all=True)
        path = write_execution_plan(cfg, plan)
        queued = write_manual_review_queue(cfg, plan)
        print_plan_summary(plan, path, queued)
        if not apply:
            return 0
        if not plan.get("planned_pages"):
            print("init-kb：没有新的 planned_pages，初始化批处理结束。")
            return 0
        blocking_review = [item for item in plan.get("manual_review", []) if item.get("type") == "planned_pages_require_review"]
        if blocking_review:
            print("init-kb --apply 暂停：当前计划仍包含需要人工审核的页面。")
            return 1
        command_apply_plan(cfg, str(path))
        applied_batches += 1
        remaining = int(plan.get("batching", {}).get("remaining_after_current", 0) or 0)
        if remaining <= 0:
            print(f"init-kb --apply 完成：已应用 {applied_batches} 个批次。")
            return 0
        print(f"init-kb --apply：已应用第 {batch_index + 1} 批，剩余输入约 {remaining} 个。")
    print(f"init-kb --apply 已达到批次数上限 {limit}，请重新运行以继续。")
    return 0


def command_finalize_kb(cfg: dict[str, Any], *, apply: bool = False) -> int:
    plan = make_finalize_plan(cfg, plan_run_id=run_id(), stamp=stamp())
    path = write_execution_plan(cfg, plan)
    queued = write_manual_review_queue(cfg, plan)
    print_plan_summary(plan, path, queued)
    if apply and plan.get("planned_pages"):
        return command_apply_plan(cfg, str(path))
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
        raise SystemExit(f"鎵句笉鍒?plan锛{ref}")
    raise SystemExit(f"plan 寮曠敤涓嶅敮涓€锛{ref}")


def fail_apply_plan(cfg: dict[str, Any], run_id_value: str, plan_path: Path | None, root: Path | None, created: list[dict[str, Any]], exc: BaseException) -> None:
    cfg["_run_id"] = run_id_value
    failed_manifest = {
        "run_id": run_id_value,
        "failed_at": stamp(),
        "plan_path": str(plan_path) if plan_path else "",
        "knowledge_base": str(root) if root else "",
        "created": created,
        "backup_dir": str(backup_root(cfg) / run_id_value),
        "operation_log": str(operation_log_path(cfg)),
        "recovery_hint": recovery_hint(cfg, run_id_value),
        "next_step": user_next_step(exc),
        "status": "failed",
        "error": str(exc),
    }
    manifest_path = write_run_manifest(cfg, failed_manifest)
    append_operation_log(cfg, {
        "operation": "apply_plan_failed",
        "run_id": run_id_value,
        "error": str(exc),
        "next_step": user_next_step(exc),
        "manifest_path": str(manifest_path),
    })
    print(f"apply-plan 澶辫触锛{exc}", file=sys.stderr)
    print(f"涓嬩竴姝ワ細{user_next_step(exc)}", file=sys.stderr)
    print(recovery_hint(cfg, run_id_value), file=sys.stderr)
    print(f"澶辫触 run manifest锛{manifest_path}", file=sys.stderr)


def assert_safe_rel_write(cfg: dict[str, Any], rel_path: str) -> None:
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise SystemExit(f"鎷掔粷涓嶅畨鍏ㄧ洰鏍囪矾寰勶細{rel_path}")
    first = rel.parts[0] if rel.parts else ""
    if first in set(cfg.get("safety", {}).get("protected_dirs", [])):
        raise SystemExit(f"鎷掔粷鍐欏叆鍙椾繚鎶ょ洰褰曪細{rel_path}")


def page_requires_manual_review(page: dict[str, Any]) -> bool:
    review_required = page.get("review_required", False)
    if isinstance(review_required, str):
        review_required = review_required.strip().lower() in {"1", "true", "yes", "y"}
    confidence = str(page.get("confidence", "")).strip().lower()
    return bool(review_required) or confidence == "low"
BLOCKED_APPLY_MARKERS = (
    "Mock summary for dry-run",
    "Mock stub content",
)
BLOCKED_HEURISTIC_MARKERS = (
    "鍒嗘瀽妯″紡锛歨euristic",
    "鍒嗘瀽妯″紡锛歨euristic-fallback",
)
def page_has_blocked_placeholder(page: dict[str, Any]) -> bool:
    content = str(page.get("content") or "")
    if any(marker in content for marker in BLOCKED_APPLY_MARKERS):
        return True
    if page.get("skill") == "topic-research-compile" and any(marker in content for marker in BLOCKED_HEURISTIC_MARKERS):
        return True
    if page.get("skill") == "topic-research-compile" and str(page.get("rel_path", "")).startswith("wiki/topics/"):
        weak_markers = ["待补充", "（待补充", "Topic from"]
        if sum(content.count(marker) for marker in weak_markers) >= 2:
            return True
    return False
def duplicate_page_targets(pages: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(page.get("rel_path") or "") for page in pages)
    return {rel: count for rel, count in counts.items() if rel and count > 1}
def preflight_apply_pages(
    cfg: dict[str, Any],
    root: Path,
    pages: list[dict[str, Any]],
    *,
    allow_reviewed: bool = False,
) -> list[tuple[dict[str, Any], Path]]:
    targets: list[tuple[dict[str, Any], Path]] = []
    duplicates = duplicate_page_targets(pages)
    if duplicates:
        details = ", ".join(f"{rel} x{count}" for rel, count in sorted(duplicates.items())[:10])
        raise SystemExit(f"plan 鍐呭瓨鍦ㄩ噸澶嶇洰鏍囪矾寰勶紝鎷掔粷 apply-plan锛{details}")
    for page in pages:
        rel_path = page.get("rel_path")
        if not rel_path:
            raise SystemExit("plan 页面缺少 rel_path，不能安全写入。")
        if page_has_blocked_placeholder(page):
            raise SystemExit(f"plan 椤甸潰鍖呭惈 mock 鎴栧急鍗犱綅鍐呭锛屾嫆缁?apply-plan锛{rel_path}")
        if page_requires_manual_review(page) and not allow_reviewed:
            raise SystemExit(f"plan 椤甸潰闇€瑕佷汉宸ュ鏍革紝鎷掔粷鐩存帴 apply-plan锛{rel_path}")
        assert_safe_rel_write(cfg, rel_path)
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise SystemExit(f"鎷掔粷瓒婄晫鍐欏叆锛{target}")
        operation = str(page.get("operation") or "create")
        if operation == "update" and not target.exists():
            raise SystemExit(f"鏇存柊鐩爣涓嶅瓨鍦紝鎷掔粷 apply-plan锛{rel_path}")
        if operation != "update" and target.exists():
            raise SystemExit(f"鐩爣宸插瓨鍦紝鎷掔粷瑕嗙洊锛{rel_path}")
        content = page.get("content")
        content_hash = page.get("content_sha256")
        if not isinstance(content, str) or not content_hash:
            raise SystemExit(f"plan 椤甸潰缂哄皯 content 鎴?content_sha256锛{rel_path}")
        if sha256_text(content) != content_hash:
            raise SystemExit(f"plan 鍐呭 hash 涓嶅尮閰嶏細{rel_path}")
        parent = target.parent
        if parent.exists():
            probe = parent / f".write-check-{run_id()}.tmp"
            try:
                probe.write_text("ok", encoding="utf-8")
            except OSError as exc:
                raise PermissionError(f"鐩爣鐩綍涓嶅彲鍐欙細{parent}") from exc
            finally:
                try:
                    if probe.exists():
                        probe.unlink()
                except OSError:
                    pass
        targets.append((page, target))
    return targets
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
def reconcile_created_pages(root: Path, created: list[dict[str, Any]]) -> dict[str, Any]:
    rels = [str(item.get("rel_path") or "") for item in created]
    unique_rels = sorted(set(rel for rel in rels if rel))
    missing = []
    hash_mismatch = []
    for item in created:
        rel = str(item.get("rel_path") or "")
        if not rel:
            continue
        target = root / rel
        if not target.exists():
            missing.append(rel)
        elif item.get("sha256") and sha256_file(target) != item.get("sha256"):
            hash_mismatch.append(rel)
    duplicate_created = {rel: count for rel, count in Counter(rels).items() if rel and count > 1}
    return {
        "created_count": len(created),
        "unique_created_count": len(unique_rels),
        "duplicate_created": duplicate_created,
        "missing": missing,
        "hash_mismatch": hash_mismatch,
        "ok": len(created) == len(unique_rels) and not missing and not hash_mismatch,
    }
def command_apply_plan(cfg: dict[str, Any], ref: str, *, allow_reviewed: bool = False) -> int:
    created: list[dict[str, Any]] = []
    plan_path: Path | None = None
    root: Path | None = None
    try:
        plan_path = resolve_plan_ref(cfg, ref)
        try:
            plan = read_json(plan_path, {})
        except json.JSONDecodeError as exc:
            raise SystemExit(f"plan JSON 解析失败：{plan_path}。{user_next_step(exc)}") from exc
        pages = plan.get("planned_pages", [])
        if not pages:
            raise SystemExit("该 plan 没有 planned_pages，不能 apply-plan。请先重新生成 dry-run plan。")
        ensure_dirs(cfg)
        root = kb_root(cfg)
        apply_run_id = str(plan.get("run_id") or run_id())
        cfg["_run_id"] = apply_run_id
        skipped_existing: list[str] = []
        if plan.get("entry") == "init_kb":
            pages, skipped_existing = split_existing_pages(cfg, pages)
        if not pages and skipped_existing:
            print(f"apply-plan：{len(skipped_existing)} 个目标已存在，初始化计划无需重复写入。")
            return 0
        append_operation_log(cfg, {
            "operation": "apply_plan_start",
            "run_id": apply_run_id,
            "plan_path": str(plan_path),
            "knowledge_base": str(root),
            "planned_pages": len(pages),
            "skipped_existing_pages": skipped_existing,
            "backup_dir": str(backup_root(cfg) / apply_run_id),
        })
        targets = preflight_apply_pages(cfg, root, pages, allow_reviewed=allow_reviewed)
        append_operation_log(cfg, {
            "operation": "apply_plan_preflight_ok",
            "run_id": apply_run_id,
            "targets": [str(target) for _, target in targets],
            "skipped_existing_pages": skipped_existing,
        })
        for page, target in targets:
            rel_path = page["rel_path"]
            safe_write_text(
                cfg,
                target,
                page["content"],
                run_id=apply_run_id,
                operation="apply_plan_update_page" if page.get("operation") == "update" else "apply_plan_create_page",
                reason="Apply reviewed plan page; original raw/quicknote/inbox files are protected.",
            )
            created.append({
                "rel_path": rel_path,
                "sha256": sha256_file(target),
                "skill": page.get("skill"),
                "operation": page.get("operation", "create"),
                "sources": page.get("sources", []),
                "origin": page.get("origin") or {"source_paths": page.get("sources", [])},
            })

        reconcile = reconcile_created_pages(root, created)
        if not reconcile["ok"]:
            raise SystemExit(f"apply-plan 钀界洏鏍￠獙澶辫触锛{json.dumps(reconcile, ensure_ascii=False)}")

        index = build_index(cfg)
        operations_by_skill: dict[str, dict[str, Any]] = {}
        for item in created:
            skill = item.get("skill") or plan.get("primary_skill")
            op = operations_by_skill.setdefault(skill, {
                "skill": skill,
                "operation": "apply-plan",
                "created": [],
                "inputs": set(),
                "source_outputs": {},
                "issues": [],
            })
            op["created"].append(item["rel_path"])
            item_sources = item.get("sources", [])
            op["inputs"].update(item_sources)
            for source in item_sources:
                op["source_outputs"].setdefault(source, []).append(item["rel_path"])
        operations = []
        for op in operations_by_skill.values():
            inputs = sorted(op["inputs"])
            op["inputs"] = inputs
            op["processed"] = len(inputs)
            operations.append(op)
        write_run_log(index, cfg, operations, plan.get("task", "apply-plan"))
        update_processed_index(index, cfg, operations)
        save_state(cfg, build_index(cfg), operations)
        update_index(build_index(cfg), cfg)
        manifest = {
            "run_id": apply_run_id,
            "applied_at": stamp(),
            "plan_path": str(plan_path),
            "knowledge_base": str(root),
            "created": created,
            "skipped_existing_pages": skipped_existing,
            "backup_dir": str(backup_root(cfg) / apply_run_id),
            "operation_log": str(operation_log_path(cfg)),
            "recovery_hint": recovery_hint(cfg, apply_run_id),
            "reconcile": reconcile,
            "status": "applied",
        }
        manifest_path = write_run_manifest(cfg, manifest)
        append_operation_log(cfg, {
            "operation": "apply_plan_complete",
            "run_id": apply_run_id,
            "created": [item["rel_path"] for item in created],
            "skipped_existing_pages": skipped_existing,
            "manifest_path": str(manifest_path),
        })
        created_count = sum(1 for item in created if item.get("operation") != "update")
        updated_count = sum(1 for item in created if item.get("operation") == "update")
        print(f"宸插簲鐢?plan锛{plan_path}")
        print(f"鍐欏叆椤甸潰锛{len(created)}锛屾柊寤猴細{created_count}锛屾洿鏂帮細{updated_count}")
        if skipped_existing:
            print(f"璺宠繃宸插瓨鍦ㄩ〉闈細{len(skipped_existing)}")
        print(f"run manifest锛{manifest_path}")
        print(f"澶囦唤鐩綍锛{backup_root(cfg) / apply_run_id}")
        print(f"鎿嶄綔鏃ュ織锛{operation_log_path(cfg)}")
        print(f"鍥炴粴鍛戒护锛歱ython scripts\\personal_kb_steward.py rollback {apply_run_id}")
        return 0
    except (Exception, SystemExit) as exc:
        failed_run_id = str(locals().get("apply_run_id") or Path(ref).stem or "apply-plan-error")
        fail_apply_plan(cfg, failed_run_id, plan_path, root, created, exc)
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
        raise SystemExit(f"鎵句笉鍒?run manifest锛{ref}")
    raise SystemExit(f"run 寮曠敤涓嶅敮涓€锛{ref}")


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
            skipped.append(f"涓嶅瓨鍦細{rel_path}")
            continue
        if sha256_file(target) != item.get("sha256"):
            skipped.append(f"hash 宸插彉鍖栵紝璺宠繃锛{rel_path}")
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
    print(f"宸插洖婊?run锛{manifest.get('run_id')}")
    print(f"鍒犻櫎椤甸潰锛{len(removed)}")
    print(f"鍒犻櫎鍓嶅浠界洰褰曪細{backup_root(cfg) / rollback_run_id}")
    print(f"鎿嶄綔鏃ュ織锛{operation_log_path(cfg)}")
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
        print(f"浜哄伐纭闃熷垪锛{target}")
        print(format_queue_summary(items))
        if not filtered:
            print("  (鏃犲尮閰嶈褰?")
            return 0
        print()
        for i, item in enumerate(filtered, 1):
            print(format_list_item(item, i))
        return 0

    elif sub == "show":
        item = find_item(items, args.id)
        if not item:
            print(f"鏈壘鍒?ID锛{args.id}")
            return 1
        print(format_show_item(item))
        return 0

    elif sub == "approve":
        reason = getattr(args, "reason", "") or ""
        if approve_item(items, args.id, reason):
            save_queue(target, items)
            print(f"宸叉壒鍑嗭細{args.id}")
            return 0
        print(f"鏈壘鍒板緟纭椤癸細{args.id}")
        return 1

    elif sub == "reject":
        reason = getattr(args, "reason", "") or ""
        if reject_item(items, args.id, reason):
            save_queue(target, items)
            print(f"宸叉嫆缁濓細{args.id}")
            return 0
        print(f"鏈壘鍒板緟纭椤癸細{args.id}")
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
        run_ids = sorted({str(item.get("run_id", "")).strip() for item in to_apply if item.get("run_id")})
        if not run_ids:
            print("已批准项缺少 run_id，无法定位对应 plan。")
            return 1
        applied = 0
        for rid in run_ids:
            related = [item for item in items if item.get("run_id") == rid]
            pending = [item for item in related if item.get("status") == "pending"]
            rejected = [item for item in related if item.get("status") == "rejected"]
            if pending or rejected:
                print(f"跳过 run {rid}：仍有 pending={len(pending)} rejected={len(rejected)} 的审核项。")
                continue
            command_apply_plan(cfg, rid, allow_reviewed=True)
            now = stamp()
            for item in related:
                if item.get("status") == "approved":
                    item["status"] = "applied"
                    item["applied_at"] = now
                    applied += 1
        if applied:
            save_queue(target, items)
        print(f"已应用审核通过项：{applied} 项")
        return 0 if applied else 1

    else:
        print(f"鏈煡 review 瀛愬懡浠わ細{sub}")
        return 2


def command_processed(cfg: dict[str, Any]) -> int:
    target = processed_index_path(cfg)
    data = load_processed_index(cfg)
    processed = data.get("processed", {})
    skill_counts: Counter[str] = Counter()
    for record in processed.values():
        for skill in record.get("skills", {}):
            skill_counts[skill] += 1
    print(f"Processed index锛{target}")
    print(f"鏉ユ簮璁板綍锛{len(processed)}")
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
    run_parser.add_argument("--apply", action="store_true", help="鎵ц鍐欏叆锛涢粯璁ゅ彧鐢熸垚 dry-run plan")
    run_parser.add_argument("--all", action="store_true", help="鍒濆鏁寸悊妯″紡锛氭壂鎻忓叏閮ㄧ瑪璁帮紝鑰屼笉鍙湅鏈疆鍙樻洿")
    sub.add_parser("lint")
    health = sub.add_parser("healthcheck")
    health.add_argument("--write", action="store_true", help="写入健康检查报告")
    plan = sub.add_parser("plan")
    plan.add_argument("--llm", action="store_true", help="鍔犺浇 SKILL.md 骞惰皟鐢?LLM Skill Runtime")
    plan.add_argument("--mock-llm", action="store_true", help="浣跨敤 mock LLM 杩愯 Skill Runtime")
    plan.add_argument("--all", action="store_true", help="鍒濆鏁寸悊妯″紡锛氭壂鎻忓叏閮ㄧ瑪璁帮紝鑰屼笉鍙湅鏈疆鍙樻洿")
    plan.add_argument("text", nargs="+")
    task = sub.add_parser("task")
    task.add_argument("--apply", action="store_true", help="鎵ц鍐欏叆锛涢粯璁ゅ彧鐢熸垚 dry-run plan")
    task.add_argument("--llm", action="store_true", help="鍔犺浇 SKILL.md 骞惰皟鐢?LLM Skill Runtime锛涗粎 dry-run plan 鐢熸晥")
    task.add_argument("--mock-llm", action="store_true", help="浣跨敤 mock LLM 杩愯 Skill Runtime锛涗粎 dry-run plan 鐢熸晥")
    task.add_argument("--all", action="store_true", help="鍒濆鏁寸悊妯″紡锛氭壂鎻忓叏閮ㄧ瑪璁帮紝鑰屼笉鍙湅鏈疆鍙樻洿")
    task.add_argument("text", nargs="+")
    init_kb = sub.add_parser("init-kb", help="鍒嗘壒鍒濆鍖栫煡璇嗗簱锛岀敓鎴?pipeline plan")
    init_kb.add_argument("--batch-size", type=int, default=6, help="姣忔壒 raw 闀挎枃鏁伴噺锛岄粯璁?6")
    init_kb.add_argument("--no-llm", action="store_true", help="不调用 LLM，使用启发式整理并标记质量风险")
    init_kb.add_argument("--apply", action="store_true", help="鎸夋壒娆＄敓鎴愬苟搴旂敤鍒濆鍖栬鍒掞紝鐩村埌鏃犳柊澧為〉鎴栬揪鍒版壒娆℃暟涓婇檺")
    init_kb.add_argument("--max-batches", type=int, default=20, help="--apply 鏈€澶氳繛缁鐞嗙殑鎵规鏁帮紝榛樿 20")
    finalize = sub.add_parser("finalize-kb", help="璺?source-note 鑱氬悎骞惰ˉ related 閾炬帴")
    finalize.add_argument("--apply", action="store_true", help="搴旂敤 finalize 璁″垝")
    apply_plan = sub.add_parser("apply-plan")
    apply_plan.add_argument("ref", help="plan 鏂囦欢璺緞銆乺un_id 鎴栧敮涓€鐗囨")
    rollback = sub.add_parser("rollback")
    rollback.add_argument("ref", help="run manifest 璺緞銆乺un_id 鎴栧敮涓€鐗囨")
    # 鈹€鈹€ review 瀛愬懡浠ょ粍 鈹€鈹€
    review_parser = sub.add_parser("review", help="浜哄伐纭闃熷垪绠＄悊")
    review_sub = review_parser.add_subparsers(dest="review_command")
    review_list = review_sub.add_parser("list", help="鍒楀嚭闃熷垪")
    review_list.add_argument("--all", action="store_true", help="鏄剧ず鎵€鏈夌姸鎬侊紙鍖呮嫭宸插鐞嗭級")
    review_list.add_argument("--type", help="按类型过滤")
    review_list.add_argument("--risk", help="按风险等级过滤（P0/P1/P2/P3）")
    review_show = review_sub.add_parser("show", help="鏄剧ず鍗曟潯璇︽儏")
    review_show.add_argument("id", help="璁板綍 ID 鎴栧墠缂€")
    review_approve = review_sub.add_parser("approve", help="鎵瑰噯璁板綍")
    review_approve.add_argument("id", help="璁板綍 ID 鎴栧墠缂€")
    review_approve.add_argument("--reason", default="", help="鎵瑰噯鐞嗙敱")
    review_reject = review_sub.add_parser("reject", help="鎷掔粷璁板綍")
    review_reject.add_argument("id", help="璁板綍 ID 鎴栧墠缂€")
    review_reject.add_argument("--reason", default="", help="鎷掔粷鐞嗙敱")
    review_batch = review_sub.add_parser("batch-approve", help="鎵归噺鎵瑰噯")
    review_batch.add_argument("--risk", help="只批准指定风险等级")
    review_batch.add_argument("--type", help="只批准指定类型")
    review_apply = review_sub.add_parser("apply-approved", help="执行所有已批准项")
    sub.add_parser("processed")
    args = parser.parse_args(argv)
    cfg = config()
    if args.command == "status":
        return command_status(cfg)
    if args.command == "run":
        return command_run(cfg, apply=args.apply, include_all=args.all)
    if args.command == "lint":
        return command_lint(cfg, write=False)
    if args.command == "healthcheck":
        return command_lint(cfg, write=args.write)
    if args.command == "plan":
        return command_plan(cfg, " ".join(args.text), use_llm=args.llm, mock_llm=args.mock_llm, include_all=args.all)
    if args.command == "task":
        return command_task(cfg, " ".join(args.text), apply=args.apply, use_llm=args.llm, mock_llm=args.mock_llm, include_all=args.all)
    if args.command == "init-kb":
        return command_init_kb(cfg, batch_size=args.batch_size, no_llm=args.no_llm, apply=args.apply, max_batches=args.max_batches)
    if args.command == "finalize-kb":
        return command_finalize_kb(cfg, apply=args.apply)
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
