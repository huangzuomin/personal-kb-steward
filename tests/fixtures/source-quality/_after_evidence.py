"""T10 after-evidence: canonical neg_damaged.md through the source executor.
Run via: python -m pytest tests/test_text_integrity_gates.py -q (tests) plus
python -m pytest tests/fixtures/source-quality/_after_evidence.py -q -s
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

skill_dir = ROOT / "skills" / "topic-research-compile"
spec = importlib.util.spec_from_file_location("t10_after_executor", skill_dir / "executor.py")
EXEC = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(skill_dir))
try:
    spec.loader.exec_module(EXEC)
finally:
    sys.path.remove(str(skill_dir))

raw = (ROOT / "tests" / "fixtures" / "card-baseline" / "neg_damaged.md").read_bytes()
text = raw.decode("utf-8")
note = dict(rel="raw/neg_damaged.md", title="损坏的公开合成输入", body=text, summary="",
            metadata={}, source_text=text, source_sha256=hashlib.sha256(raw).hexdigest())
calls: list = []


def provider(*args, **kwargs):
    calls.append(1)
    return "{}"


with patch.dict(EXEC.execute.__globals__, {"call_chat_completion": provider}):
    result = EXEC.execute({"notes": [note], "config": {"source_analysis": {"chunk_chars": 4000,
                                                                "max_chunks": 12},
                                              "write": {}}, "use_llm": True})
out = {"provider_calls": len(calls), "processed": result.get("processed"),
       "created_count": len(result.get("created", [])),
       "issues": result.get("issues")}
(ROOT / "docs" / "iteration-evidence" / "astra-damaged-text-after.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
