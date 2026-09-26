"""Generate M1-source handoff samples: rendered PUBLIC cards + raw mock payloads.

Mocked model output is a FIXTURE, not real-model quality acceptance.
Run via: python -m pytest tests/fixtures/source-quality/_generate_samples.py -q -s
(module-level code executes at import; no tests collected).
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

skill_dir = ROOT / "skills" / "topic-research-compile"
spec = importlib.util.spec_from_file_location("m1_sample_executor", skill_dir / "executor.py")
EXEC = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(skill_dir))
try:
    spec.loader.exec_module(EXEC)
finally:
    sys.path.remove(str(skill_dir))

FIX = ROOT / "tests" / "fixtures" / "source-quality"
OUT = ROOT / "docs" / "iteration-evidence" / "M1-source" / "samples"
OUT.mkdir(parents=True, exist_ok=True)
CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12}, "write": {"sources_dir": "wiki/sources"}}


def note(name, rel):
    raw = (FIX / name).read_bytes()
    text = raw.decode("utf-8")
    from core.vault import parse_frontmatter
    meta, body = parse_frontmatter(text.removeprefix("﻿"))
    import hashlib
    return {"rel": rel, "title": str(meta.get("title") or name), "body": body, "summary": "",
            "metadata": meta, "source_text": text,
            "source_sha256": hashlib.sha256(raw).hexdigest()}


# --- Sample 1: dialogue (real analysis path, heuristic mode over public fixture)
dialogue = note("bold-dialogue.md", "raw/bold-dialogue-sample.md")

# --- Sample 2: uncited report; mock provider echoes the pivotal quote so the
# quote-verification path is exercised (fixture output, NOT a real model).
report = note("uncited-report.md", "raw/uncited-report-sample.md")
REPORT_RAW_RESPONSES = []


def report_provider(cfg, system_prompt, user_payload):
    resp = {
        "summary": "片段讨论市场规模增长与扩张传闻。",
        "key_statements": [
            {"text": "2025年该市场规模增长至520亿元，同比增长18%。",
             "quote": "2025年该市场规模增长至520亿元，同比增长18%。",
             "kind": "assertion"},
            {"text": "据传头部企业正在扩张。",
             "quote": "据传头部企业正在扩张，但文中不做任何引用说明。",
             "kind": "assertion"}
        ],
        "topics": [{"title": "行业规模观察", "content": "数字均无出处，需先核实再引用。"}],
        "limitations": ["样本明示无外部来源；数字不可回溯。"],
        "quality_flags": []
    }
    REPORT_RAW_RESPONSES.append(resp)
    return json.dumps(resp, ensure_ascii=False)


with patch.object(EXEC, "call_chat_completion", report_provider):
    report_result = EXEC.execute({"notes": [report], "config": CFG, "use_llm": True})
    report_payload = EXEC.analyze_note(report, CFG, use_llm=True)

(OUT / "sample-dialogue-heuristic-card.md").write_text(
    EXEC.render({**EXEC.analyze_note(dialogue, CFG, use_llm=False),
                 "sources_dir": "wiki/sources"})[0]["content"], encoding="utf-8")

(OUT / "sample-uncited-report-mock-card.md").write_text(
    EXEC.render({**report_payload, "sources_dir": "wiki/sources"})[0]["content"], encoding="utf-8")
(OUT / "sample-uncited-report-raw-mock-responses.json").write_text(
    json.dumps(REPORT_RAW_RESPONSES, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "sample-uncited-report-structured-payload.json").write_text(
    json.dumps({k: v for k, v in report_payload.items() if k != "info_units"},
               ensure_ascii=False, indent=2, default=str), encoding="utf-8")
(OUT / "sample-uncited-report-info-units.json").write_text(
    json.dumps(report_payload.get("info_units", []), ensure_ascii=False, indent=2),
    encoding="utf-8")
print("samples written to", OUT)
