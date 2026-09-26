"""B02：标题必须「短而完整」，不能是盲切出来的半句或半词。

全部使用合成样本，不含任何真实个人笔记内容（上游 personal-kb-steward 是 PUBLIC 仓库）。

回归前的现象：模型未提供 title 时走 ``statement[:40]`` 盲切，产出
「…又不让重新学习的成」「…被淘汰，Com」——其中 ``Com`` 是英文单词被切成半截。
"""
from __future__ import annotations

import pytest

from core.atomic_seed import _parse_model_thoughts, _preview_item, _short_title


# ---------------------------------------------------------------- 直接单测

def test_text_within_limit_is_returned_unchanged():
    assert _short_title("一个很短的标题", 40) == "一个很短的标题"


def test_cjk_statement_is_cut_at_a_clause_boundary_not_mid_sentence():
    """B02 原型：盲切会停在「…重新学习的成」，必须停在完整子句。"""
    statement = "在 AI 绘图工具快速迭代的环境下，如何既保持技能不快速过时、又不让重新学习的成本过高？"
    title = _short_title(statement, 40)
    assert len(title) <= 40
    assert title != statement[:40], "不能退化成盲切"
    # 收短位置必须是子句边界：标题之后紧跟标点，而不是半个词
    assert statement[len(title)] in "，、；：。！？"
    assert not title.endswith(("，", "、", "；", "：", "。"))


def test_latin_word_is_never_split():
    """无标点长句回退到词边界：绝不出现 'Com' 这种半截单词。"""
    text = "Completely new pipeline replaces the legacy manual export step for weekly reporting"
    title = _short_title(text, 40)
    if title.endswith("…"):
        return  # 硬切已显式标注，可接受
    nxt = text[len(title):len(title) + 1]
    assert not (title[-1].isalnum() and nxt.isalnum()), f"切在了单词中间：{title!r}"


def test_never_ends_with_dangling_punctuation():
    for text in [
        "笔记中并存两条水墨风格提示词，均以极简禅意自然景观为主题：一条用日出金光渲染巨石与远山",
        "服务器每周巡检，磁盘水位持续上升；需要评估清理策略，并确认备份是否仍然可用",
    ]:
        assert not _short_title(text, 40).endswith(("，", "、", "；", "：", "。"))


def test_weaker_boundary_is_used_when_stronger_one_is_too_early():
    """最近的强边界若太靠前（会让标题失去要点），退而用次级边界。"""
    text = "甲乙丙丁，戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥：这是一个很长的补充说明后面还有很多内容"
    title = _short_title(text, 40)
    assert len(title) > 10
    assert not title.endswith("：")


def test_hard_cut_is_visibly_marked():
    """完全没有边界可依时，硬切必须带省略号，不假装是完整标题。"""
    text = "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十"
    title = _short_title(text, 20)
    assert title.endswith("…")


def test_ellipsis_only_when_actually_shortened():
    assert not _short_title("短标题", 40).endswith("…")


# ------------------------------------------------- 经 _parse_model_thoughts

def _thought(**overrides) -> dict:
    thought = {
        "statement": "在 AI 绘图工具快速迭代的环境下，如何既保持技能不快速过时、又不让重新学习的成本过高？",
        "kind": "assertion",
        "unit_ids": [0],
        "growth_directions": [{"action": "核对原文再落盘", "basis": "标题与正文都来自同一条原文摘录"}],
        "negative_scope": ["不讨论具体工具版本差异"],
    }
    thought.update(overrides)
    return thought


def _units() -> list[dict]:
    return [{"quote": "一段用来定位的原文摘录", "kind": "assertion",
             "identity": "unit-0", "source": "quicknote/a.md"}]


def test_missing_model_title_yields_complete_title():
    """模型没给 title（B02 真实触发路径）：标题必须完整，不是半句。"""
    issues: list[str] = []
    accepted, dropped = _parse_model_thoughts(
        {"thoughts": [_thought()]}, _units(), issues)
    assert dropped == 0 and len(accepted) == 1, issues
    title = accepted[0]["title"]
    statement = _thought()["statement"]
    assert title != statement[:40]
    assert statement[len(title)] in "，、；：。！？"
    assert not title.endswith(("，", "、", "；", "：", "。"))


def test_overlong_model_title_is_shortened_not_discarded():
    """模型给了标题但超过 60 字：收短保留，而不是整条丢弃后去盲切正文。"""
    long_title = "关于在绘图工具快速迭代的环境下既要保持技能不过时又要控制重新学习成本这一长期矛盾的若干观察" * 2
    issues: list[str] = []
    accepted, dropped = _parse_model_thoughts(
        {"thoughts": [_thought(title=long_title)]}, _units(), issues)
    assert dropped == 0 and len(accepted) == 1, issues
    title = accepted[0]["title"]
    assert len(title) <= 60
    assert title.startswith("关于在绘图工具"), title
    assert not title.endswith(("，", "、", "；", "：", "。"))


def test_valid_model_title_is_kept_verbatim():
    issues: list[str] = []
    accepted, dropped = _parse_model_thoughts(
        {"thoughts": [_thought(title="工具迭代与学习成本")]}, _units(), issues)
    assert dropped == 0, issues
    assert accepted[0]["title"] == "工具迭代与学习成本"


# --------------------------------------------------------- _preview_item

def test_preview_item_title_is_not_blind_sliced():
    unit = {"quote": "在 AI 绘图工具快速迭代的环境下，如何既保持技能不快速过时、又不让重新学习的成本过高",
            "kind": "assertion", "identity": "unit-0", "source": "quicknote/a.md"}
    title = _preview_item(unit)["title"]
    assert title != unit["quote"][:40]
    assert unit["quote"][len(title)] in "，、；：。！？"
