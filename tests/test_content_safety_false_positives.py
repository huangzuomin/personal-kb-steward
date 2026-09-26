"""回归：启发式产出不得把普通内容变成「不透明机器行」而整批死掉。

真实故障（2026-09-22，真库）：`init-kb --batch-size 3` 抛
`SensitiveContentError: opaque_machine_line`，**整批中止**，14 篇 raw 受影响。
逐条查证后确认**两处都是误报**，根因都在无 LLM 的启发式路径的**产出侧**：

1. `infer_topics` 回退分支 `re.sub(r"\\s+", "", title)` **删掉标题所有空格**：
   "Amazon Just Killed 50,000 Human Voices" → "AmazonJustKilled50,000HumanVoices"
   —— 无空格 + 大小写 + 数字 + 逗号，正好命中 `suspicious_machine_line`。
   （`assert_safe_content(note)` 先过是因为它按**行**判，原标题带空格。）

2. `sentence_chunks` 对 `.`/`!`/`?` **无条件断句**，把 markdown 图片链接切碎：
   `!` 被单独切出后，`[](https://substackcdn.` 不再以 `![` 开头，绕过噪音过滤；
   残留的 URL 片段（`%3A%2F%2F` 藏掉了 `/`）读起来像裸 token，直接命中
   `opaque_machine_line`。修法：ASCII 句末符仅在**后接空白或文末**时才断句。
   （换行仍不是边界 —— 那是另一处已知局限，见本文件末尾的用例。）

3. 单篇命中不得整批死掉。分流口径：真凭据类规则（`private_key` /
   `credential_token` / `bearer_token` / `credential_assignment` /
   `credential_field`）**仍然中止整轮**（安全事件，不能降级成「跳过一篇」）；
   只有高误报的 `opaque_machine_line` 记为 blocked 输入并继续
   （在 `input_outcomes` 里可见，不写页面、不计 processed）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from core import source_analysis as sa  # noqa: E402
from core.content_safety import (SensitiveContentError, assert_safe_content,  # noqa: E402
                                 sensitive_reason, suspicious_machine_line)
from core.vault import parse_frontmatter  # noqa: E402


def _load_source_executor():
    skill_dir = ROOT / "skills" / "topic-research-compile"
    spec = importlib.util.spec_from_file_location("src_executor_safety_test",
                                                 skill_dir / "executor.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(skill_dir))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(skill_dir))
    return module


_SRC_EXEC = _load_source_executor()

# 真实故障样本：markdown 图片链接 + 百分号编码 URL
REAL_BODY = (
    "Overview 切换按钮。\n\n"
    "![](https://substackcdn.example/image/fetch/w_1456,c_limit,f_auto,q_auto:good/"
    "https%3A%2F%2Fpost-media.s3.amazonaws.example/Ab3xY9K2mQ7wZ4nP8rT5vL1sD6fG0hJ%2FkL9.png)\n\n"
    "音频概览目前仅提供英文版本，其他语言将在后续更新中逐步开放支持，请留意官方说明。\n"
)
REAL_TITLE = "Amazon Just Killed 50,000 Human Voices"


def _note(title: str, body: str, rel: str = "raw/剪藏/样本.md") -> dict:
    text = f"---\ntitle: {title}\n---\n{body}"
    meta, parsed = parse_frontmatter(text)
    return {
        "rel": rel,
        "title": title,
        "body": parsed,
        "summary": "",
        "metadata": meta,
        "source_text": text,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


class InferTopicsTests(unittest.TestCase):
    def test_fallback_title_keeps_spaces(self):
        """回退专题标题必须保留单空格，不能塌成无空格 token。"""
        topics = sa.infer_topics(REAL_TITLE, "", {})
        title = topics[0]["title"]
        self.assertIn(" ", title)
        self.assertFalse(suspicious_machine_line(title))
        self.assertIsNone(sensitive_reason(title))

    def test_fallback_title_is_readable_and_bounded(self):
        """空白折叠成单空格，首尾不留空白，长度有界。"""
        topics = sa.infer_topics("  --  Short  Title  --  ", "", {})
        self.assertEqual(topics[0]["title"], "Short Title")
        long_topics = sa.infer_topics("A" * 10 + " " + "B" * 40, "", {})
        self.assertLessEqual(len(long_topics[0]["title"]), 32)

    def test_empty_title_still_falls_back(self):
        topics = sa.infer_topics("", "", {})
        self.assertEqual(topics[0]["title"], "资料待整理专题")


class ExtractInfoUnitsTests(unittest.TestCase):
    def test_percent_encoded_url_fragment_is_not_an_information_unit(self):
        plan = sa.plan_chunks(REAL_BODY, 4000, 8)
        units = sa.extract_info_units(REAL_BODY, plan)
        for unit in units:
            self.assertFalse(
                suspicious_machine_line(unit["text"]),
                f"不透明机器行被当成信息单元：len={len(unit['text'])}")
        self.assertIsNone(sensitive_reason(json.dumps(units, ensure_ascii=False)))

    def test_standalone_prose_sentence_survives(self):
        """修复不能把正常句子一起过滤掉（散文自成一句时必须保留）。"""
        body = (
            "音频概览目前仅提供英文版本，其他语言将在后续更新中逐步开放支持。\n\n"
            "![](https://substackcdn.example/image/fetch/w_1456,c_limit,f_auto,"
            "q_auto:good/https%3A%2F%2Fpost-media.s3.amazonaws.example/"
            "Ab3xY9K2mQ7wZ4nP8rT5vL1sD6fG0hJ%2FkL9.png)\n"
        )
        plan = sa.plan_chunks(body, 4000, 8)
        units = sa.extract_info_units(body, plan)
        self.assertTrue(any("音频概览" in u["text"] for u in units), units)
        for unit in units:
            self.assertFalse(suspicious_machine_line(unit["text"]))


class SentenceChunksTests(unittest.TestCase):
    """切句不得在 URL/文件名/小数内部断开，也不得把行粘在一起。"""

    def test_dots_inside_urls_and_filenames_do_not_split(self):
        text = "见 ![](https://substackcdn.example/a.png) 说明。"
        parts = [s for _, s in sa.sentence_chunks(text)]
        self.assertTrue(any("substackcdn.example" in s for s in parts),
                        f"URL 被从 '.' 处切碎：{parts}")

    def test_ascii_terminator_needs_following_space(self):
        parts = [s for _, s in sa.sentence_chunks("Version 1.2.3 released. Next line here.")]
        self.assertIn("Version 1.2.3 released.", parts)
        self.assertIn("Next line here.", parts)

    def test_cjk_terminators_always_split(self):
        parts = [s for _, s in sa.sentence_chunks("甲；乙！丙？丁。")]
        self.assertEqual(parts, ["甲；", "乙！", "丙？", "丁。"])

    def test_heading_prefixed_prose_line_survives_newline_boundary(self):
        """标题与正文按换行分界，正文仍以原文片段进入信息单元。"""
        text = "# 标题\n\n这一行是真实散文，长度足够构成一个可抽取的信息单元。\n"
        plan = sa.plan_chunks(text, 4000, 8)
        units = sa.extract_info_units(text, plan)
        self.assertTrue(units, "标题后的正文不应因换行与标题粘连而静默丢失")
        self.assertTrue(any("这一行是真实散文" in u["quote"] for u in units), units)
        for unit in units:
            self.assertEqual(unit["quote"], text[unit["start"]:unit["end"]])


class SafetyTripClassificationTests(unittest.TestCase):
    """真凭据 → 中止；启发式误报 → 只拦这一篇。"""

    def test_credential_reasons_are_hard(self):
        for reason in ("private_key", "credential_token", "bearer_token",
                       "credential_assignment", "credential_field"):
            self.assertTrue(_SRC_EXEC._is_hard_safety_trip(
                SensitiveContentError("x", reason)), reason)

    def test_opaque_machine_line_is_not_hard(self):
        self.assertFalse(_SRC_EXEC._is_hard_safety_trip(
            SensitiveContentError("x", "opaque_machine_line")))

    def test_real_credential_in_output_aborts_the_run(self):
        """真凭据出现在产出里必须中止，不能被降级成「跳过一篇」。"""
        note = _note("正常标题", "这是一段足够长的正常中文正文，用于构成可抽取的信息单元。")
        original = _SRC_EXEC.analyze_note

        def leaky(n, cfg, use_llm):
            data = original(n, cfg, use_llm)
            return {**data, "unused_field": "api_key=sk-secret1234567890abcd"}

        _SRC_EXEC.analyze_note = leaky
        try:
            with self.assertRaises(SensitiveContentError):
                _SRC_EXEC.execute({"notes": [note], "config": {"write": {}},
                                   "use_llm": False})
        finally:
            _SRC_EXEC.analyze_note = original


class HeuristicOutputSafetyTests(unittest.TestCase):
    def test_analyze_note_output_passes_content_safety(self):
        """端到端：真实故障样本走一遍启发式分析，产出必须能过敏感检查。"""
        note = _note(REAL_TITLE, REAL_BODY)
        data = _SRC_EXEC.analyze_note(note, {"write": {}}, use_llm=False)
        assert_safe_content(data)  # 修复前这里抛 opaque_machine_line

    def test_executor_blocks_one_input_without_killing_the_batch(self):
        """单篇产出命中 → 记为 blocked 并继续，不得让整批抛异常。"""
        good = _note("正常标题", "这是一段足够长的正常中文正文，用于构成可抽取的信息单元。")
        bad = _note("命中样本", REAL_BODY, rel="raw/剪藏/命中.md")
        original = _SRC_EXEC.analyze_note
        real_data = original(bad, {"write": {}}, use_llm=False)

        def fake(note, cfg, use_llm):
            if note.get("rel") == bad["rel"]:
                return {**real_data, "source_summary": "ok", "key_facts": [],
                        "facts_display": [], "info_units": [], "topics": [],
                        "poison": "Ab3xY9K2mQ7wZ4nP8rT5vL1sD6fG0hJ%2FkL9"}
            return original(note, cfg, use_llm)

        _SRC_EXEC.analyze_note = fake
        try:
            result = _SRC_EXEC.execute({"notes": [bad, good], "config": {"write": {}},
                                        "use_llm": False})
        finally:
            _SRC_EXEC.analyze_note = original

        outcomes = {o.get("rel"): o for o in result.get("input_outcomes", [])}
        # 注意：outcome() 的字段名是 "outcome"（不是 "status"）。
        self.assertEqual(outcomes[bad["rel"]]["outcome"], "blocked")
        self.assertTrue(any("敏感检查" in i for i in result.get("issues", [])))
        # 好料不受牵连：仍被分析（不得因同批有一篇命中而整批 blocked）
        good_outcome = outcomes[good["rel"]]["outcome"]
        self.assertNotEqual(good_outcome, "blocked")


if __name__ == "__main__":
    unittest.main()
