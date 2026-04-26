from __future__ import annotations

import hashlib
import re

from core.clustering import ClusterInput, cluster_inputs
from renderer import render


def slug(text: str) -> str:
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if ascii_part:
        return ascii_part[:72]
    return "seed-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def execute(context: dict) -> dict:
    notes = context.get("notes", [])
    cfg = context.get("config", {})
    max_clusters = int(cfg.get("clustering", {}).get("max_clusters", 5))
    clusters, low_confidence = cluster_inputs(
        [ClusterInput(n["rel"], n["title"], n.get("body", "")) for n in notes],
        max_clusters=max_clusters,
        cfg=cfg,
    )
    pages = []
    issues = []
    for cluster in clusters:
        confidence = cluster.get("confidence", "low")
        review = confidence == "low"
        manual_review = []
        if review:
            manual_review.append("动态聚类置信度低，需要人工确认是否值得生长。")
        item = {
            "title": cluster["title"],
            "type": "seed-card",
            "status": "manual_review" if review else "seed",
            "stage": "needs_context" if review else "seed",
            "sources": cluster["sources"],
            "summary": (
                f"[LLM语义聚类] " if cluster.get("llm_clustered") else "[词频聚类·fallback] "
            ) + (
                cluster.get("reasoning") or
                f"这张 seed-card 来自本轮输入的动态议题聚类，聚类锚点为：{' / '.join(cluster.get('terms', []))}。"
            ),
            "signals": [f"{n['title']}：{n.get('summary', '')}" for n in notes if n["rel"] in cluster["sources"]][:6],
            "growth_directions": [
                "提炼一个更窄的研究问题。",
                "抽取案例、时间线、观点分歧和证据缺口。",
                "来源充足后再交给 topic-insight-miner。",
            ],
            "related": [],
            "pending_links": cluster.get("terms", [])[:3],
            "tags": cluster.get("tags", ["动态聚类"]),
            "confidence": confidence,
            "review_required": review,
            "manual_review": manual_review,
        }
        pages.append({
            "rel_dir_key": "seed_dir",
            "filename": f"seed-{cluster['slug']}.md",
            "content": render(item),
            "sources": item["sources"],
            "item": item,
        })
    issues.extend(f"动态聚类置信度低：{source}" for source in low_confidence)
    return {
        "skill": "mindseed-grow",
        "pages": pages,
        "processed": len(notes),
        "inputs": [n["rel"] for n in notes],
        "issues": issues,
        "items": [page["item"] for page in pages],
    }
