# -*- coding: utf-8 -*-
"""GP003 Phase 3：case 卡 limitation 责任划界（MERGE_DOUBLE_COUNTS_UPSTREAM 修复）。

契约：模型侧 provenance_map[].limitations = additional limitations only
（不得复制/改写/概括 upstream_source_analysis 已列出的限制）；
系统继续强制继承全部上游限制 ⇒ final = upstream + genuinely new，各一条。
禁止语义相似度去重——重复从生产源头（prompt 契约）避免；
模型若仍违规复述，normalize 保留之（诚实边界，见报告）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import case_generation as casegen
from scripts.evaluate_public_baseline import build_cfg, prepare_vault
from tests.test_case_generation import full_response, load_note

CASE1_REL = "tests/fixtures/concept-case/case_source_01.md"
DIRECTIVE_MARKER = "upstream_source_analysis"
U1 = "照片数量口径不一：48张与51幅，差异未解释"
U2 = "稿件为自媒体转载，转引链条较长，原始出处核对受限"
NEW1 = "案例生成时的来源覆盖窗口未包含影像链接内容（组合阶段新发现）"
UPSTREAM_META = {"source_kind": "article", "limitations": [U1, U2], "speakers": []}


def _spy_provider(response):
    payloads = []

    def provider(cfg, system_prompt, payload):
        payloads.append(payload)
        return json.dumps(response, ensure_ascii=False)

    provider.payloads = payloads
    return provider


def _notes():
    note = load_note("case_source_01.md")
    note["metadata"] = dict(note.get("metadata") or {})
    note["metadata"]["upstream_analysis"] = dict(UPSTREAM_META)
    return [note]


@pytest.fixture
def case_cfg(tmp_path: Path):
    root = tmp_path / "vault"
    prepare_vault(root)  # 隔离目录；generate_cases 本身不落盘
    return build_cfg(root)


def _response_with(limitations):
    response = json.loads(json.dumps(full_response()))
    response["provenance_map"] = [
        {"rel": CASE1_REL, "provenance": "合成来源", "limitations": list(limitations)}]
    return response


def test_payload_carries_additional_only_limitations_contract(case_cfg):
    """RED 核心：provenance_map.limitations 的契约必须明确 additional-only。"""
    spy = _spy_provider(_response_with([NEW1]))
    casegen.generate_cases(_notes(), case_cfg, call_provider=spy, now="2026-09-25")
    assert spy.payloads, "provider 未被调用"
    contract = json.dumps(
        spy.payloads[0].get("output_contract", {}).get("provenance_map"),
        ensure_ascii=False)
    assert DIRECTIVE_MARKER in contract, (
        "provenance_map.limitations 契约必须引用 upstream_source_analysis 并声明 "
        "additional-only（当前模型会复述上游已列出的限制）")
    assert "additional" in contract.lower() or "不得复制" in contract


def test_upstream_plus_genuinely_new_each_once(case_cfg):
    """合规模型（只输出真正新增）⇒ final = upstream + new，各一条。"""
    spy = _spy_provider(_response_with([NEW1]))
    out = casegen.generate_cases(_notes(), case_cfg, call_provider=spy, now="2026-09-25")
    item = out["items"][0]
    entry = next(e for e in item["provenance_map"] if "case_source_01" in e["rel"])
    lims = entry["limitations"]
    assert lims.count(U1) == 1, lims
    assert lims.count(U2) == 1, lims
    assert lims.count(NEW1) == 1, lims
    assert len(lims) == 3, lims


def test_upstream_inherited_when_model_omits(case_cfg):
    """模型不输出 limitations ⇒ 上游限制仍全部强制继承（继承逻辑不可删）。"""
    spy = _spy_provider(_response_with([]))
    out = casegen.generate_cases(_notes(), case_cfg, call_provider=spy, now="2026-09-25")
    item = out["items"][0]
    entry = next(e for e in item["provenance_map"] if "case_source_01" in e["rel"])
    lims = entry["limitations"]
    assert lims.count(U1) == 1 and lims.count(U2) == 1, lims


def test_model_cannot_delete_upstream_limitations(case_cfg):
    """模型试图输出与上游矛盾的空/覆盖信息 ⇒ 上游限制仍然全部在场。"""
    spy = _spy_provider(_response_with(["与上游无关的全新限制"]))
    out = casegen.generate_cases(_notes(), case_cfg, call_provider=spy, now="2026-09-25")
    item = out["items"][0]
    entry = next(e for e in item["provenance_map"] if "case_source_01" in e["rel"])
    lims = entry["limitations"]
    assert U1 in lims and U2 in lims, "上游限制不可被模型删除"
    assert "与上游无关的全新限制" in lims, "模型真正新增的限制应被保留"
