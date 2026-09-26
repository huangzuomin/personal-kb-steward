"""After-evidence for the null-viability strict-contract hole.
Run via: python -m pytest tests/fixtures/source-quality/_zero_null_after_evidence.py -q -s
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
spec = importlib.util.spec_from_file_location("t11b_after_executor", skill_dir / "executor.py")
EXEC = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(skill_dir))
try:
    spec.loader.exec_module(EXEC)
finally:
    sys.path.remove(str(skill_dir))

raw = (ROOT / "tests" / "fixtures" / "card-baseline" / "neg_repeated_quote.md").read_bytes()
text = raw.decode("utf-8")
note = {"rel": "raw/neg_repeated_quote.md", "title": "t", "body": text, "summary": "",
        "metadata": {}, "source_text": text,
        "source_sha256": hashlib.sha256(raw).hexdigest()}
CFG = {"source_analysis": {"chunk_chars": 4000, "max_chunks": 12}, "write": {}}
calls: list = []


def null_provider(cfg, system, payload):
    calls.append(1)
    return json.dumps({"chunk_viable": None,
                       "key_statements": [{"text": "共享单车潮汐淤积是主要矛盾。",
                                           "quote": "临川市（虚构）共享单车调度的主要矛盾是潮汐淤积，即车辆在居住区与商务区之间随通勤单向流动导致的分布失衡。",
                                           "kind": "assertion"}],
                       "topics": [], "limitations": [], "quality_flags": []},
                      ensure_ascii=False)


with patch.dict(EXEC.execute.__globals__, {"call_chat_completion": null_provider}):
    result = EXEC.execute({"notes": [note], "config": CFG, "use_llm": True})
out = {
    "present_null_viability_accepted": False,
    "provider_calls": len(calls),
    "processed": result["processed"],
    "cards": len(result["created"]),
    "outcome": result["input_outcomes"][0]["outcome"],
    "analysis_mode": result["input_outcomes"][0]["analysis_mode"],
}
(ROOT / "docs" / "iteration-evidence" / "astra-source-zero-null-after.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
