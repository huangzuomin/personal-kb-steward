from __future__ import annotations

import datetime as dt
import json


def bullet(items: list[str], empty: str) -> str:
    return "".join(f"- {item}\n" for item in items) if items else f"- {empty}\n"


def frontmatter(item: dict) -> str:
    today = dt.date.today().isoformat()
    return "\n".join([
        "---",
        f"title: {json.dumps(item['title'], ensure_ascii=False)}",
        "type: topic-card",
        f"status: {item['status']}",
        f"stage: {item['stage']}",
        f"created: {today}",
        f"updated: {today}",
        f"sources: {json.dumps(item['sources'], ensure_ascii=False)}",
        f"related: {json.dumps(item.get('related', []), ensure_ascii=False)}",
        f"tags: {json.dumps(['选题卡', '候选选题'], ensure_ascii=False)}",
        f"score: {item['score']}",
        f"confidence: {item['confidence']}",
        f"review_required: {str(bool(item['review_required'])).lower()}",
        "---",
        "",
    ])


def render(item: dict) -> str:
    return (
        frontmatter(item)
        + f"# {item['title']}\n\n"
        + "## 一句话选题\n\n"
        + item["one_sentence_topic"].strip()
        + "\n\n## 选题张力\n\n"
        + item["tension"].strip()
        + "\n\n## 为什么值得写\n\n"
        + bullet(item.get("why_now", []), "价值尚不明确。")
        + "\n## 知识库证据\n\n"
        + bullet(item["sources"], "来源不足。")
        + "\n## 可用角度\n\n"
        + bullet(item.get("angles", []), "暂无可用角度。")
        + "\n## 反方与风险\n\n"
        + bullet(item.get("risks", []), "暂无明确风险。")
        + "\n## 缺口\n\n"
        + bullet(item.get("gaps", []), "暂无明确缺口。")
        + "\n## 推荐等级\n\n"
        + f"{item['score']}\n\n"
        + "## 下一步\n\n"
        + "- 若为 A/B，进入 evidence pack 或 material pack。\n"
        + "- 若为 C，继续积累来源，不升级为正式 topic page。\n"
    )
