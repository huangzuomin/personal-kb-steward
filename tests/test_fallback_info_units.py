"""B12 regressions for bounded heuristic source extraction.

These tests exercise only the pure source-analysis helpers.  They keep the
normalized source text as the sole coordinate system and use synthetic media
markup to reproduce the chunk-boundary noise seen in the local diagnostic.
"""
from __future__ import annotations

from core import source_analysis as sa
from core.claims import normalized_text


def _units(text: str, *, chunk_chars: int = 4000, limit: int = 20):
    norm = normalized_text(text)
    plan = sa.plan_chunks(norm, chunk_chars, 8)
    return norm, sa.extract_info_units(norm, plan, limit=limit)


def test_newline_separates_heading_frontmatter_and_first_prose():
    text = (
        "---\n"
        "title: 一段不会成为事实的 frontmatter 标题\n"
        "sources: https://example.invalid/meta\n"
        "---\n"
        "# 页面标题\n"
        "\n"
        "标题后的正文是一段足够长的自然语言陈述，用于验证换行边界。\n"
    )
    norm, units = _units(text)

    quotes = [unit["quote"] for unit in units]
    assert any("标题后的正文" in quote for quote in quotes)
    assert all("frontmatter" not in quote for quote in quotes)
    assert all(not quote.startswith("#") for quote in quotes)
    for unit in units:
        assert unit["quote"] == norm[unit["start"]:unit["end"]]
        assert unit["text"] == unit["quote"]


def test_fenced_code_is_not_an_information_unit():
    text = (
        "页面说明是一段真实的自然语言，用来确认代码块不会吞掉相邻正文。\n"
        "```json\n"
        '{"srcNoWatermark": null, "imageSize": 1456, "type": "image/png"}\n'
        "这不是可归因的事实，只是代码内容。\n"
        "```\n"
        "代码之后的正文仍然是一段可核验的自然语言陈述。\n"
    )
    _, units = _units(text)

    quotes = [unit["quote"] for unit in units]
    assert any("页面说明" in quote for quote in quotes)
    assert any("代码之后" in quote for quote in quotes)
    assert all("srcNoWatermark" not in quote for quote in quotes)
    assert all("这不是可归因" not in quote for quote in quotes)


def test_media_json_fragment_split_across_chunks_is_not_a_fact():
    media = (
        "![媒体](https://journaliststoolbox.substack.com/p/%7B%22src%22:%22"
        "https://substack-post-media.s3.amazonaws.com/public/images/"
        "45df3b87-8e9a-4ff5-9473-f168724a6d19_1600x300.png%22,%22"
        "srcNoWatermark%22:null,%22fullscreen%22:null,%22imageSize%22:null,"
        "%22height%22:273,%22width%22:1456,%22resizeWidth%22:null,"
        "%22bytes%22:196690,%22alt%22:%22%22,%22type%22:%22image/png%22%7D)"
    )
    text = (
        "前置文字用于把媒体行切在 chunk 边界附近，确保测试覆盖跨块片段。"
        + ("补充前置" * 16)
        + media
        + "\n媒体之后的正文是一段需要保留的自然语言信息，日期为 2025 年。\n"
    )
    _, units = _units(text, chunk_chars=200)

    quotes = [unit["quote"] for unit in units]
    assert any("媒体之后的正文" in quote for quote in quotes), quotes
    assert all("srcNoWatermark" not in quote for quote in quotes)
    assert all("png%22" not in quote for quote in quotes)
    assert all("image/png" not in quote for quote in quotes)


def test_normal_citation_url_sentence_is_preserved():
    text = (
        "研究团队在 2025 年发布了这项结果，完整说明见 "
        "https://example.com/research/2025-report ，这句话本身仍是自然语言。\n"
    )
    _, units = _units(text)

    assert any("完整说明见 https://example.com/research/2025-report" in unit["quote"]
               for unit in units)


def test_dates_decimals_versions_stay_in_one_sentence():
    text = "版本 v1.2.3 于 2025-09-22 发布，小数 3.14 仍然保留在同一句中。"
    _, units = _units(text)

    assert [unit["quote"] for unit in units] == [text]


def test_duplicate_sentence_is_deduplicated_after_newline_split():
    sentence = "同一条自然语言陈述重复出现，用于验证去重逻辑仍然正常。"
    text = f"{sentence}\n{sentence}\n另一条独立陈述也足够长，可以作为对照。"
    _, units = _units(text)

    quotes = [unit["quote"] for unit in units]
    assert quotes.count(sentence) == 1
    assert any("另一条独立陈述" in quote for quote in quotes)


def test_fence_context_survives_chunk_boundaries_and_different_fence_markers():
    body = (
        "# 原始资料\n````text\n"
        + "代码块内的伪陈述绝不能被当成知识事实而输出，尽管它看起来像自然语言。\n" * 12
        + "~~~\n错误类型的关闭标记之后仍然属于代码块，这一句也不是真实事实。\n"
        + "```\n长度不足的关闭标记之后仍然属于代码块，这一句也不是真实事实。\n"
        + "````\n代码之外的真实正文足够长，应该被作为信息单元保留并可回到原文。\n"
    )
    norm, units = _units(body, chunk_chars=200)
    assert [u["text"] for u in units] == [
        "代码之外的真实正文足够长，应该被作为信息单元保留并可回到原文。"]
    for unit in units:
        assert norm[unit["start"]:unit["end"]] == unit["quote"]


def test_short_encoded_media_fragment_and_url_only_line_are_not_facts():
    norm, units = _units(
        "png%22,%22srcNoWatermark%22:nu\n"
        "https%3A%2F%2Fexample.com%2Fimages%2Fclip.png\n"
        "有完整语义的正文仍然需要被保留，不能与编码媒体片段一并消失。\n")
    assert len(units) == 1
    assert units[0]["quote"] == norm[units[0]["start"]:units[0]["end"]]
    assert units[0]["text"].startswith("有完整语义")


def test_navigation_and_empty_html_embeds_are_not_assertions():
    _, units = _units(
        '[查看完整提示](https://example.com/redirect/long-identifier)\n'
        '- [工具](https://example.com/tools)（[示例](https://example.com/demo)）\n'
        '<video controls="" src="blob:https://example.com/video-id"></video>\n'
        '根据[研究报告](https://example.com/report)，这一段具有实际陈述的正文仍然需要保留。\n')
    assert len(units) == 1
    assert units[0]["text"].startswith("根据[研究报告]")
