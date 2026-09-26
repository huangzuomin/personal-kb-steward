"""After-evidence for the explicit useful-content zero contract.
Run via: python -m pytest tests/fixtures/source-quality/_zero_after_evidence.py -q -s
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import importlib.util

skill_dir = ROOT / "skills" / "topic-research-compile"
spec = importlib.util.spec_from_file_location("t11_after_executor", skill_dir / "executor.py")
EXEC = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(skill_dir))
try:
    spec.loader.exec_module(EXEC)
finally:
    sys.path.remove(str(skill_dir))

CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12},
       "write": {"sources_dir": "wiki/sources"}}


def canonical(name):
    raw = (ROOT / "tests" / "fixtures" / "card-baseline" / f"{name}.md").read_bytes()
    text = raw.decode("utf-8")
    return {"rel": f"raw/{name}.md", "title": name, "body": text, "summary": "",
            "metadata": {}, "source_text": text,
            "source_sha256": hashlib.sha256(raw).hexdigest()}


out = {}
# Case 1: explicit chunk_viable=false zero over canonical neg_irrelevant
calls = []


def zero_provider(cfg, system, payload):
    calls.append(1)
    return json.dumps({"chunk_viable": False, "reason": "无可沉淀的独立信息",
                       "key_statements": [], "topics": [], "limitations": [],
                       "quality_flags": []}, ensure_ascii=False)


with patch.dict(EXEC.execute.__globals__, {"call_chat_completion": zero_provider}):
    result = EXEC.execute({"notes": [canonical("neg_irrelevant")],
                           "config": CFG, "use_llm": True})
out["neg_irrelevant_explicit_zero"] = {
    "calls": len(calls), "processed": result["processed"], "cards": len(result["created"]),
    "issues": result["issues"], "input_outcomes": result["input_outcomes"]}

# Case 2: root's ORIGINAL before-probe response (source_viable, no chunk_viable,
# empty candidates) -> malformed/empty, fallback partial, processed 0
calls2 = []


def old_provider(cfg, system, payload):
    calls2.append(1)
    return json.dumps({"summary": "日常闲聊，无可沉淀的独立信息。", "key_statements": [],
                       "topics": [], "limitations": [], "quality_flags": [],
                       "source_viable": False, "reason": "无可沉淀的独立信息"},
                      ensure_ascii=False)


with patch.dict(EXEC.execute.__globals__, {"call_chat_completion": old_provider}):
    result = EXEC.execute({"notes": [canonical("neg_irrelevant")],
                           "config": CFG, "use_llm": True})
out["neg_irrelevant_old_contract_response"] = {
    "calls": len(calls2), "processed": result["processed"], "cards": len(result["created"]),
    "card_analysis_mode": (result["created"][0]["analysis_mode"] if result["created"] else None),
    "input_outcomes": result["input_outcomes"]}

(ROOT / "docs" / "iteration-evidence" / "astra-negative-source-after.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("after evidence written")
