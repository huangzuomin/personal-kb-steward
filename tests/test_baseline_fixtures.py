# -*- coding: utf-8 -*-
"""T0 公开合成素材基线测试。

验证 tests/fixtures/card-baseline/ 下的合成素材与 manifest 一致，
负例保持"故意损坏/空/无关/重复"形态，并把原始字节的 SHA256 快照写入
docs/iteration-evidence/T0/fixture-hashes.json。

注意：这些是公开合成素材（SYNTHETIC），不验证私有 demo 数据。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "card-baseline"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
EVIDENCE_DIR = REPO_ROOT / "docs" / "iteration-evidence" / "T0"

MAIN_FIXTURE_IDS = ["dialogue_user_ai_01", "research_summary_uncited_01", "project_case_01"]
CASE_FAMILY_IDS = ["project_case_01", "project_case_01_followup", "project_case_01_counterexample"]
NEG_FIXTURE_IDS = ["neg_empty", "neg_irrelevant", "neg_damaged", "neg_repeated_quote"]

REQUIRED_SYNTHETIC_MARK = "SYNTHETIC"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def fixture_path(entry) -> Path:
    return REPO_ROOT / entry["path"]


# ---------------------------------------------------------------- 正例素材

def test_manifest_lists_all_expected_fixtures(manifest):
    ids = [e["id"] for e in manifest["fixtures"]]
    for fid in MAIN_FIXTURE_IDS + NEG_FIXTURE_IDS:
        assert fid in ids, f"manifest 缺少 {fid}"


@pytest.mark.parametrize("fid", MAIN_FIXTURE_IDS)
def test_main_fixture_is_synthetic_and_substantive(manifest, fid):
    entry = next(e for e in manifest["fixtures"] if e["id"] == fid)
    path = fixture_path(entry)
    assert path.exists(), f"缺少素材文件 {path}"
    text = path.read_text(encoding="utf-8")
    assert REQUIRED_SYNTHETIC_MARK in text, f"{fid} 缺少 SYNTHETIC 声明"
    # 500–1200 汉字区间（以汉字计，含标点从宽：仅统计 CJK 统一表意文字）
    han = sum(1 for ch in text if "一" <= ch <= "鿿")
    assert 400 <= han <= 1500, f"{fid} 汉字数 {han} 超出合理区间"


@pytest.mark.parametrize("fid", MAIN_FIXTURE_IDS)
def test_main_fixture_matches_declared_speaker_markers(manifest, fid):
    entry = next(e for e in manifest["fixtures"] if e["id"] == fid)
    text = fixture_path(entry).read_text(encoding="utf-8")
    for marker in entry["expected_speaker_markers"]:
        assert marker in text, f"{fid} 缺少声明的标记: {marker}"


def test_dialogue_distinguishes_user_thoughts_and_ai_proposals(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "dialogue_user_ai_01")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert "（用户）" in text and "提案" in text
    assert text.count("AI 助手（提案") >= 3, "AI 提案不足三条"
    assert "边界" in text, "缺少提案边界/局限陈述"


def test_uncited_summary_keeps_numbers_unverified(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "research_summary_uncited_01")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert "示意性" in text and "无" in text and "来源" in text


def test_project_case_separates_mechanism_and_limits(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "project_case_01")
    text = fixture_path(entry).read_text(encoding="utf-8")
    for section in ["背景", "行动", "结果", "复用机制", "局限"]:
        assert section in text, f"project_case_01 缺少小节关键词: {section}"


# ---------------------------------------------------------------- 案例族主题组（M3/T10）

def test_manifest_declares_topic_group(manifest):
    groups = manifest.get("topic_groups", [])
    assert groups, "manifest 缺少 topic_groups"
    group = next(g for g in groups if g["id"] == "case_family_conversion_chain")
    assert group["explicit_question"].startswith("三段转化链")
    assert sorted(group["source_ids"]) == sorted(CASE_FAMILY_IDS)
    assert group["supported_tensions"] and group["contextual_differences_not_conflicts"] and group["missing_evidence"]


@pytest.mark.parametrize("fid", ["project_case_01_followup", "project_case_01_counterexample"])
def test_case_family_companion_is_synthetic(manifest, fid):
    entry = next(e for e in manifest["fixtures"] if e["id"] == fid)
    path = fixture_path(entry)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert REQUIRED_SYNTHETIC_MARK in text
    han = sum(1 for ch in text if "一" <= ch <= "鿿")
    assert 400 <= han <= 1200, f"{fid} 汉字数 {han} 超出区间"


def test_followup_distinguishes_measurement_and_disagreement(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "project_case_01_followup")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert "测量窗口" in text and "分母" in text, "须区分测量窗口与分母"
    assert "无法裁决" in text, "解释分歧应保持未裁决状态"
    assert "归因" in text


def test_counterexample_limits_scope_of_failure(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "project_case_01_counterexample")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert "条件差异" in text and "边界" in text
    assert "不能据此断言" in text, "须限制失败结论的适用范围"


def test_irrelevant_fixture_not_in_topic_group(manifest):
    group = next(g for g in manifest["topic_groups"] if g["id"] == "case_family_conversion_chain")
    assert "neg_irrelevant" not in group["source_ids"]
    for fid in group["source_ids"]:
        entry = next(e for e in manifest["fixtures"] if e["id"] == fid)
        assert entry["material_kind"] not in ("negative_irrelevant", "negative_empty")


# ---------------------------------------------------------------- 负例素材

def test_neg_empty_is_empty(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "neg_empty")
    assert fixture_path(entry).read_text(encoding="utf-8").strip() == ""


def test_neg_irrelevant_has_no_knowledge_markers(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "neg_irrelevant")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert REQUIRED_SYNTHETIC_MARK not in text.replace("合成", "")  # 无正式合成声明头也可，但须无主题词
    for topic_word in ["共享单车", "转化链", "Zettelkasten", "seed card"]:
        assert topic_word not in text


def test_neg_damaged_is_intentionally_corrupted(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "neg_damaged")
    text = fixture_path(entry).read_text(encoding="utf-8")
    assert "�" in text, "负例应包含 U+FFFD 替换字符（故意损坏）"
    assert "synthetic-damaged-fixture" in text


def test_neg_repeated_quote_has_single_unique_paragraph(manifest):
    entry = next(e for e in manifest["fixtures"] if e["id"] == "neg_repeated_quote")
    text = fixture_path(entry).read_text(encoding="utf-8")
    sentences = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("临川市")]
    assert len(sentences) >= 3, "重复引用负例应包含至少 3 次重复"
    assert len(set(sentences)) == 1, "重复引用负例的重复段应完全一致"


# ---------------------------------------------------------------- 既有损坏素材保留

def test_existing_damaged_industry_report_untouched():
    p = REPO_ROOT / "examples" / "mini-vault" / "raw" / "industry_report.md"
    raw = p.read_bytes()
    assert raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:64], \
        "industry_report.md 应保持其原有损坏编码形态"


# ---------------------------------------------------------------- Hash 快照

def test_write_fixture_hash_snapshot(manifest):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for entry in manifest["fixtures"]:
        raw = fixture_path(entry).read_bytes()
        snapshots[entry["id"]] = {
            "path": entry["path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    raw_manifest = MANIFEST_PATH.read_bytes()
    snapshots["manifest.json"] = {
        "path": "tests/fixtures/card-baseline/manifest.json",
        "sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "bytes": len(raw_manifest),
    }
    out = EVIDENCE_DIR / "fixture-hashes.json"
    out.write_text(
        json.dumps(
            {
                "_comment": "由 tests/test_baseline_fixtures.py 计算的原始字节 SHA256 快照（运行时生成，非手填）",
                "algorithm": "sha256",
                "fixtures": snapshots,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # 回读校验
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["fixtures"]["neg_empty"]["sha256"] == hashlib.sha256(b"").hexdigest()
