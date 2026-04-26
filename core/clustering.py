from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "when", "why",
    "how", "use", "using", "about", "into", "your", "http", "https", "www",
    "com", "org", "net", "source", "content", "article", "articles", "read",
    "more", "new", "best", "image", "google", "gmail", "markdown",
    "一个", "一种", "这个", "那个", "如何", "什么", "以及", "进行", "关于",
    "使用", "可以", "需要", "生成", "整理", "资料", "内容", "来源",
}


@dataclass
class ClusterInput:
    path: str
    title: str
    content: str


def text_tokens(text: str) -> list[str]:
    items: list[str] = []
    for item in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,8}", text):
        low = item.lower()
        if low not in STOPWORDS and not low.isdigit():
            items.append(low)
    return items


def slug_for(parts: list[str]) -> str:
    raw = "-".join(parts) or "cluster"
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").lower()
    if ascii_part:
        return ascii_part[:64]
    return "cluster-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


# ── LLM 语义聚类 ──────────────────────────────────────────────────────────────

_CLUSTER_SYSTEM_PROMPT = """\
你是一个个人知识库的语义聚类引擎。
给定一批笔记碎片（title + content），请将它们归入 2-5 个语义主题集群。

输出规则：
- 必须返回纯 JSON，不要包含任何 Markdown 代码块或多余文字。
- 顶层字段为 "clusters"，值为数组。
- 每个 cluster 必须包含：
  - title（str）：语义化中文主题名，例如"地方媒体AI转型困境"，不要用词频词拼接
  - reasoning（str）：一句话解释这批笔记为何属于同一主题
  - sources（list[str]）：属于该集群的笔记路径列表（必须从输入路径中选取，不得新造）
  - confidence（str）：high / medium / low
- 同一笔记可以归入多个集群。
- 不要生成没有来源支撑的集群。
- 不要使用"AI"、"内容"、"整理"等单独的宽泛词作为 title。
"""


def _llm_cluster(inputs: list[ClusterInput], cfg: dict, max_clusters: int) -> list[dict] | None:
    """调用 LLM 进行语义聚类，失败返回 None。"""
    try:
        import json
        from .llm import LLMError, call_chat_completion
        from .json_contract import extract_json
    except ImportError:
        return None

    docs = [
        {"path": inp.path, "title": inp.title, "content": inp.content[:800]}
        for inp in inputs
    ]
    payload = {
        "task": "semantic_clustering",
        "max_clusters": max_clusters,
        "notes": docs,
    }
    try:
        raw = call_chat_completion(cfg, _CLUSTER_SYSTEM_PROMPT, payload)
        data = extract_json(raw)
    except (LLMError, Exception):
        return None

    raw_clusters = data.get("clusters", [])
    if not isinstance(raw_clusters, list) or not raw_clusters:
        return None

    valid_paths = {inp.path for inp in inputs}
    result = []
    for c in raw_clusters[:max_clusters]:
        sources = [s for s in c.get("sources", []) if s in valid_paths]
        if not sources:
            continue
        title = str(c.get("title", "")).strip()
        if not title:
            continue
        result.append({
            "slug": slug_for(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", title)[:3]),
            "title": title,
            "reasoning": str(c.get("reasoning", "")),
            "tags": ["LLM聚类", title[:20]],
            "terms": re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", title)[:4],
            "confidence": c.get("confidence", "medium"),
            "sources": sources,
            "llm_clustered": True,
        })
    return result if result else None


# ── 词频 Fallback ─────────────────────────────────────────────────────────────

def _heuristic_cluster(inputs: list[ClusterInput], max_clusters: int) -> tuple[list[dict], list[str]]:
    """原词频聚类，作为 LLM 失败时的 fallback。"""
    if not inputs:
        return [], []
    per_doc: dict[str, list[str]] = {}
    global_counts: Counter[str] = Counter()
    for item in inputs:
        tokens = text_tokens(item.title + "\n" + item.content[:3000])
        weighted = text_tokens(item.title) * 2 + tokens
        counts = Counter(weighted)
        top = [token for token, _ in counts.most_common(8)]
        per_doc[item.path] = top
        global_counts.update(set(top))

    anchors = [token for token, count in global_counts.most_common(max_clusters * 2) if count >= 1][:max_clusters]
    if not anchors:
        anchors = [inputs[0].title[:24] or "未命名议题"]

    grouped: dict[str, list[ClusterInput]] = defaultdict(list)
    for item in inputs:
        tokens = per_doc[item.path]
        anchor = next((token for token in anchors if token in tokens), anchors[0])
        grouped[anchor].append(item)

    clusters: list[dict] = []
    for anchor, docs in grouped.items():
        local = Counter()
        for doc in docs:
            local.update(per_doc[doc.path])
        terms = [term for term, _ in local.most_common(4)]
        title_terms = terms[:3] or [anchor]
        clusters.append({
            "slug": slug_for(title_terms),
            "title": "动态议题：" + " / ".join(title_terms),
            "reasoning": "词频启发式聚类（LLM 不可用），请人工确认主题是否准确。",
            "tags": ["词频聚类（fallback）", *title_terms[:3]],
            "terms": terms,
            "confidence": "low",
            "sources": [doc.path for doc in docs],
            "llm_clustered": False,
        })

    clusters.sort(key=lambda c: (-len(c["sources"]), c["title"]))
    unmatched = [c["sources"][0] for c in clusters if c["confidence"] == "low"]
    return clusters[:max_clusters], unmatched


# ── 公开入口 ──────────────────────────────────────────────────────────────────

def cluster_inputs(
    inputs: list[ClusterInput],
    max_clusters: int = 5,
    cfg: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """
    语义聚类入口。
    先尝试 LLM；失败时 fallback 到词频聚类（confidence: low）。
    返回 (clusters, unmatched_low_confidence_sources)。
    """
    if not inputs:
        return [], []

    if cfg:
        llm_result = _llm_cluster(inputs, cfg, max_clusters)
        if llm_result is not None:
            unmatched = [c["sources"][0] for c in llm_result if c.get("confidence") == "low"]
            return llm_result, unmatched

    return _heuristic_cluster(inputs, max_clusters)
