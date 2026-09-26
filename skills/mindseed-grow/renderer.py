from __future__ import annotations

import datetime as dt
import json


def card_state(item: dict) -> dict | None:
    """Versioned persistence for atomic seeds: compiled evidence with source
    hashes and coordinates, the original thought statement/kind, exact
    source-information identities and analysis metadata — not body-only."""
    if "thought_units" not in item:
        return None  # legacy topic cards keep their existing contract
    return {
        "version": 1, "type": "seed-card",
        "thought": {"statement": item.get("summary", ""), "kind": item.get("kind", "assertion")},
        "thought_id": item.get("thought_id", ""),
        "statement_sha256": item.get("statement_sha256", ""),
        "thought_units": item.get("thought_units", []),
        "evidence": item.get("evidence", []),
        "analysis": {"analysis_mode": item.get("analysis_mode", "unknown"),
                     "coverage": item.get("coverage", "unknown"),
                     "link_search": item.get("link_search", "not_attempted"),
                     "limited_preview": bool(item.get("limited_preview", False))},
    }


def frontmatter(item: dict) -> str:
    today = dt.date.today().isoformat()
    state = card_state(item)
    lines = [
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
        f"origin: {json.dumps(item.get('origin', {'source_paths': item['sources']}), ensure_ascii=False)}",
        f"cluster_confidence: {item.get('cluster_confidence', 'unknown')}",
        f"seed_terms: {json.dumps(item.get('keywords', []), ensure_ascii=False)}",
        f"schema_version: {item.get('schema_version', 'm0-1')}",
        f"generator_version: {item.get('generator_version', 'pks-m0')}",
        f"analysis_mode: {item.get('analysis_mode', 'unknown')}",
        f"coverage: {item.get('coverage', 'unknown')}",
        f"source_hashes: {json.dumps(item.get('source_hashes', {}), ensure_ascii=False)}",
        f"link_search: {item.get('link_search', 'not_attempted')}",
        f"thought_units: {json.dumps(item.get('thought_units', []), ensure_ascii=False)}",
    ]
    if state is not None:
        lines.append(f"card_state: {json.dumps(state, ensure_ascii=False)}")
    lines += ["---", ""]
    return "\n".join(lines)


def wikilink(rel_path: str) -> str:
    """把相对路径转成 [[wikilink]] 格式。"""
    return f"[[{rel_path}]]"


def bullet(items: list[str], empty: str) -> str:
    return "".join(f"- {item}\n" for item in items) if items else f"- {empty}\n"


def bullet_wikilinks(rel_paths: list[str], empty: str) -> str:
    """输出 [[wikilink]] 格式的双链列表。"""
    return "".join(f"- {wikilink(p)}\n" for p in rel_paths) if rel_paths else f"- {empty}\n"


def render(item: dict) -> str:
    atomic = "thought_units" in item
    head = f"# {item['title']}\n\n"
    if atomic and item.get("analysis_mode") != "llm":
        head += ("> 受限预览：本轮未使用模型做原子提炼，以下仅为可追溯信息单元，"
                 "不能视为 atomic 达标产出。\n\n")
    head += f"## 核心议题\n\n{item['summary'].strip()}\n\n"
    body = (
        "## 来源文件\n\n"
        + bullet_wikilinks(item["sources"], "暂无来源。")
        + "\n## 关键信号\n\n"
        + bullet(item.get("signals", []), "暂无明确关键信号。")
    )
    if atomic and item.get("evidence"):
        rows = []
        for row in item["evidence"]:
            speaker = f" · 说话人：{row['speaker']}" if isinstance(row, dict) and row.get("speaker") else ""
            kind = f" · {row['kind']}" if isinstance(row, dict) and row.get("kind") else ""
            locator = f" · 第 {row['start_line']} 行" if isinstance(row, dict) and row.get("start_line") else ""
            # Display is literal; raw quote bytes persist in card_state evidence.
            quote = row["quote"].replace("[[", "［［").replace("]]", "］］") if isinstance(row, dict) else ""
            rows.append(f"- {quote}（[[{row['source']}]]{locator}{kind}{speaker}）")
        body += "\n## 证据与出处（原文摘录，非独立核实）\n\n" + "\n".join(rows) + "\n"
    body += "\n## 可生长方向\n\n" + bullet(item.get("growth_directions", []), "暂不建议继续生长。")
    if atomic:
        body += ("\n## 卡片边界（暂不扩展到的方向）\n\n"
                 + bullet(item.get("negative_scope", []), "暂无明确边界说明。"))
    body += "\n## 相关链接\n\n" + bullet_wikilinks(item.get("related", []), "暂无可解析相关链接。")
    if atomic:
        status_label = {"not_attempted": "未尝试检索", "no_match": "已检索，无候选",
                        "candidates_found": "已检索，存在候选"}.get(
            item.get("link_search", "not_attempted"), "已检索，存在候选")
        body += ("\n## 关系候选\n\n"
                 + f"- 关系检索状态：{status_label}\n"
                 + bullet(item.get("relation_explanations", []), "暂无关系解释。"))
    body += (
        "\n## 主题关键词（不是待建链接）\n\n"
        + bullet(item.get("keywords", []), "暂无关键词。")
        + "\n## 待创建链接\n\n"
        + bullet(item.get("pending_links", []), "暂无待创建链接。")
        + "\n## 人工复核项\n\n"
        + bullet(item.get("manual_review", []), "暂无明显复核项。")
    )
    return frontmatter(item) + head + body
