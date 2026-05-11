import json
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import personal_kb_steward as steward  # noqa: E402
from core.vault import build_index  # noqa: E402


class SourceTraceabilityTests(unittest.TestCase):
    def make_cfg(self, kb: Path) -> dict:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
        cfg["knowledge_base"] = str(kb)
        cfg["state_file"] = str(kb / ".state.json")
        cfg["safety"]["plans_dir"] = str(kb / ".openclaw" / "plans")
        cfg["safety"]["runs_dir"] = str(kb / ".openclaw" / "runs")
        cfg["safety"]["processed_index"] = str(kb / ".openclaw" / "processed-index.json")
        cfg["safety"]["manual_review_queue"] = str(kb / ".openclaw" / "manual-review" / "queue.jsonl")
        cfg["safety"]["backup_dir"] = str(kb / ".openclaw" / "backups")
        cfg["safety"]["operation_log"] = str(kb / ".openclaw" / "operation-log.jsonl")
        return cfg

    def test_query_results_include_source_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "quicknote" / "source.md").write_text(
                "# AI newsroom\n\nAI newsroom source trace test.",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            index = build_index(cfg)

            results = steward.query_results(index, "AI newsroom")

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0]["path"], "quicknote/source.md")
            self.assertIn("quicknote/source.md", results[0]["sources"])

    def test_healthcheck_reports_raw_coverage_and_mock_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            (kb / "wiki" / "sources").mkdir(parents=True)
            (kb / "raw" / "a.md").write_text("# A\n\nalpha", encoding="utf-8")
            (kb / "raw" / "b.md").write_text("# B\n\nbeta", encoding="utf-8")
            (kb / "wiki" / "sources" / "source-a.md").write_text(
                "---\n"
                "title: Source A\n"
                "type: source-note\n"
                "status: active\n"
                "stage: compiled\n"
                "sources: [\"raw/a.md\"]\n"
                "confidence: high\n"
                "---\n"
                "# Source A\n\nMock summary for dry-run.\n",
                encoding="utf-8",
            )
            cfg = self.make_cfg(kb)
            index = build_index(cfg)

            lint = steward.healthcheck(index, cfg)

            self.assertEqual(lint["raw_coverage"]["raw_total"], 2)
            self.assertEqual(lint["raw_coverage"]["covered"], 1)
            self.assertIn("raw/b.md", lint["raw_coverage"]["missing"])
            p0_kinds = {item["kind"] for item in lint["risk_buckets"]["P0"]}
            p1_kinds = {item["kind"] for item in lint["risk_buckets"]["P1"]}
            self.assertIn("mock_content_applied", p0_kinds)
            self.assertIn("raw_coverage_missing", p1_kinds)

    def test_healthcheck_reports_processed_index_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "quicknote").mkdir()
            (kb / "inbox").mkdir()
            (kb / "raw").mkdir()
            cfg = self.make_cfg(kb)
            bad_index = kb / ".openclaw" / "processed-index.json"
            bad_index.parent.mkdir(parents=True)
            bad_index.write_text(json.dumps({"records": {"raw/a.md": {}}}), encoding="utf-8")
            index = build_index(cfg)

            lint = steward.healthcheck(index, cfg)

            self.assertIn("processed-index schema mismatch", lint["processed_index_schema_error"])
            p0_kinds = {item["kind"] for item in lint["risk_buckets"]["P0"]}
            self.assertIn("processed_index_schema_error", p0_kinds)


if __name__ == "__main__":
    unittest.main()
