# -*- coding: utf-8 -*-
"""GP003 Phase 2：Result 区职责划界（CASE_SCHEMA_RESPONSIBILITY_OVERLAP 修复）。

产品裁决：Result 的正式载体 = result.figures（每条关键结果事实一次）；
组合层不再用 figures 语句拼接机械 summary；判断与证据层保持完整证据链。
"""
from __future__ import annotations

from tests.test_case_generation import CLAIM_RATE, CLAIM_SALES, parse_card_state, run

NEEDLES = ("4%升至11%", "3200元")   # 两条 figure statement 的独有子串


def _result_section(content: str) -> str:
    start = content.index("## 结果")
    nxt = content.find("\n## ", start + 1)
    return content[start:nxt if nxt != -1 else len(content)]


def test_result_section_renders_each_figure_once():
    out, _ = run()
    content = out["pages"][0]["content"]
    section = _result_section(content)
    for needle in NEEDLES:
        count = section.count(needle)
        assert count == 1, (
            f"Result 区内同一结果事实出现 {count} 次（期望 1）：{needle} —— "
            "机械 summary 与 figures 列表的职责重叠（CASE_SCHEMA_RESPONSIBILITY_OVERLAP）")


def test_composed_summary_is_no_longer_mechanical_join():
    out, _ = run()
    cand = out["items"][0]
    assert cand["result"]["summary"] == "", (
        f"组合层不得再用 figures 语句拼接 summary（实测：{cand['result']['summary'][:60]}…）")


def test_judgment_evidence_layer_preserved():
    out, _ = run()
    content = out["pages"][0]["content"]
    assert "## 判断与证据" in content
    judgment_section = content[content.index("## 判断与证据"):]
    for needle in NEEDLES:
        assert judgment_section.count(needle) == 1, (
            "证据层的结论陈述 + 逐字引文必须完整保留")


def test_frontmatter_claims_preserved():
    out, _ = run()
    content = out["pages"][0]["content"]
    state = parse_card_state(content)
    statements = [c["statement"] for c in state.get("claims", [])]
    for needle in NEEDLES:
        assert any(needle in s for s in statements), (
            "frontmatter 机器可读 claims 不得为视觉去重而删除")
