from __future__ import annotations

import hashlib
import re

from core.clustering import ClusterInput, cluster_inputs
from renderer import render
from core.seed_quality import seed_item, signal_sentences


def safe_filename(title: str) -> str:
    """把 seed 标题转成面向人的中文文件名，保留中文语义。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', title).strip()
    cleaned = re.sub(r"[：:，,。；;、/\\\s]+", "-", cleaned).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if cleaned.lower().startswith("seed-"):
        cleaned = cleaned[5:].strip("-")
    return cleaned[:80] or "未命名种子卡"


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
        [ClusterInput(n["rel"], n["title"], "\n".join(signal_sentences(n.get("body", ""), limit=6))) for n in notes],
        max_clusters=max_clusters,
        cfg=cfg if context.get("use_llm", True) else None,
    )
    pages = []
    for cluster in clusters:
        item = seed_item(cluster, notes, cfg)
        if not item["sources"]:
            continue
        pages.append({"rel_dir_key": "seed_dir", "filename": f"{safe_filename(item['title'])}.md",
                      "content": render(item), "sources": item["sources"], "item": item})
    return {"skill": "mindseed-grow", "pages": pages, "processed": len(notes),
            "inputs": [n["rel"] for n in notes],
            "issues": [f"动态聚类置信度低：{s}" for s in low_confidence],
            "items": [page["item"] for page in pages]}
