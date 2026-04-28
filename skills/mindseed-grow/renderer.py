from __future__ import annotations

import datetime as dt
import json


def frontmatter(item: dict) -> str:
    today = dt.date.today().isoformat()
    return "\n".join([
        "---",
        f"title: {json.dumps(item['title'], ensure_ascii=False)}",
        "type: seed-card",
        f"status: {item['status']}",
        f"stage: {item['stage']}",
        f"created: {today}",
        f"updated: {today}",
        f"sources: {json.dumps(item['sources'], ensure_ascii=False)}",
        f"related: {json.dumps(item.get('related', []), ensure_ascii=False)}",
        f"tags: {json.dumps(item.get('tags', ['动态聚类', 'seed']), ensure_ascii=False)}",
        f"confidence: {item['confidence']}",
        f"review_required: {str(bool(item['review_required'])).lower()}",
        "---",
        "",
    ])


def wikilink(rel_path: str) -> str:
    """把相对路径转成 [[wikilink]] 格式。"""
    return f"[[{rel_path}]]"


def bullet(items: list[str], empty: str) -> str:
    return "".join(f"- {item}\n" for item in items) if items else f"- {empty}\n"


def bullet_wikilinks(rel_paths: list[str], empty: str) -> str:
    """输出 [[wikilink]] 格式的双链列表。"""
    return "".join(f"- {wikilink(p)}\n" for p in rel_paths) if rel_paths else f"- {empty}\n"


def render(item: dict) -> str:
    return (
        frontmatter(item)
        + f"# {item['title']}\n\n"
        + "## 核心议题\n\n"
        + item["summary"].strip()
        + "\n\n## 来源文件\n\n"
        + bullet_wikilinks(item["sources"], "暂无来源。")
        + "\n## 关键信号\n\n"
        + bullet(item.get("signals", []), "暂无明确关键信号。")
        + "\n## 可生长方向\n\n"
        + bullet(item.get("growth_directions", []), "暂不建议继续生长。")
        + "\n## 相关链接\n\n"
        + bullet_wikilinks(item.get("related", []), "暂无可解析相关链接。")
        + "\n## 待创建链接\n\n"
        + bullet(item.get("pending_links", []), "暂无待创建链接。")
        + "\n## 人工复核项\n\n"
        + bullet(item.get("manual_review", []), "暂无明显复核项。")
    )
