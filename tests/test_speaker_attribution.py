"""Focused regressions for source/seed speaker attribution.

These fixtures are synthetic and deliberately mix frontmatter, URLs, ordinary
colon headings, explicit dialogue, Q/A roles, and an unknown transition.
"""
from __future__ import annotations

import hashlib

from core import atomic_seed
from core import source_analysis as sa
from core.claims import normalized_text


TEXT = """---
creation date: 2026-09-21
tags: [diary]
source: https://example.invalid/entry
---
# 温州秘境：制作地图故事
日记正文没有明确说话人，应保持未知。

失落的世界：东湖
另一段日记正文也没有明确说话人。

主持人：现在进入第一个问题？
记者：请说明这项工作的边界。
主持人：谢谢你的回答。

问：问方的内容？
答：答方的内容。

张三：第一句明确发言。
张三后续未标注的内容仍属于张三。
未知：这一段没有可辨认的说话人。
未知转场后的普通叙述仍然没有说话人。
"""


def test_source_parser_ignores_metadata_urls_and_plain_headings():
    norm = normalized_text(TEXT)
    assert sa._nearest_speaker_label(norm, norm.index("日记正文"), 0) is None
    assert sa._nearest_speaker_label(norm, norm.index("另一段"), 0) is None
    assert sa._nearest_speaker_label(norm, norm.index("请说明"), 0) == "记者"
    assert sa._nearest_speaker_label(norm, norm.index("问方"), 0) == "问"
    assert sa._nearest_speaker_label(norm, norm.index("答方"), 0) == "答"
    assert sa._nearest_speaker_label(norm, norm.index("张三后续"), 0) == "张三"
    assert sa._nearest_speaker_label(norm, norm.index("未知转场"), 0) is None


def test_short_dialogue_and_run_boundaries_are_preserved():
    for text, first, second in (
        ("主持人：请介绍变化。\n记者：目前只做辅助工具。\n", "主持人", "记者"),
        ("张三：新工具仍要验证。\n李四：需要保留人工审核。\n", "张三", "李四"),
        ("Alice: First statement.\nBob: Second statement.\n", "Alice", "Bob"),
    ):
        mapped = sa.speaker_map(text)
        assert mapped[1] == first
        assert mapped[2] == second

    # A nonblank prose line between labels is a boundary. It must not be
    # mistaken for the same compact conversation run.
    separated = "主持人：请介绍变化。\n普通正文，没有说话人。\n记者：目前只做辅助工具。\n"
    assert all(value is None for value in sa.speaker_map(separated).values())


def test_source_merge_drops_unverifiable_model_speaker_and_keeps_swapped_detection():
    norm = normalized_text(TEXT)
    chunk = {"index": 0, "start": 0, "end": len(norm)}
    flags: list[str] = []
    errors: list[str] = []
    parsed = {
        "chunk_viable": True,
        "key_statements": [
            {"text": "未知正文", "quote": "日记正文没有明确说话人，应保持未知。",
             "speaker": "用户"},
            {"text": "主持人问题", "quote": "现在进入第一个问题？", "speaker": "主持人"},
            {"text": "错配回答", "quote": "请说明这项工作的边界。", "speaker": "主持人"},
        ],
        "topics": [],
    }
    result = sa.merge_llm_chunk_result(chunk, parsed, norm, flags, errors)
    units = {u["text"]: u for u in result["units"]}
    assert units["未知正文"]["speaker"] is None
    assert units["主持人问题"]["speaker"] == "主持人"
    assert units["错配回答"]["speaker"] is None
    assert units["错配回答"]["speaker_mismatch"] == "记者"
    assert any("原文没有可核验的说话人标签" in flag for flag in flags)


def test_atomic_seed_ignores_frontmatter_headings_and_unknown_transition():
    sha = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()
    note = {"rel": "quicknote/synthetic.md", "source_text": TEXT,
            "source_sha256": sha, "body": TEXT}
    units = atomic_seed.information_units(note)
    by_quote = {u["quote"]: u for u in units}
    assert by_quote["日记正文没有明确说话人，应保持未知。"]["speaker"] is None
    assert by_quote["另一段日记正文也没有明确说话人。"]["speaker"] is None
    assert by_quote["主持人：现在进入第一个问题？"]["speaker"] == "主持人"
    assert by_quote["记者：请说明这项工作的边界。"]["speaker"] == "记者"
    assert by_quote["未知转场后的普通叙述仍然没有说话人。"]["speaker"] is None
