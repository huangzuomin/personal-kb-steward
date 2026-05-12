import tempfile
import unittest
from pathlib import Path

from core.index_builder import MANAGED_INDEX_MARKER, generated_index_path, update_index
from core.vault import VaultIndex


class IndexBuilderTests(unittest.TestCase):
    def make_cfg(self, kb: Path) -> dict:
        return {
            "agent": "personal-kb-steward",
            "knowledge_base": str(kb),
            "safety": {
                "backup_dir": str(kb / ".openclaw" / "backups"),
                "operation_log": str(kb / ".openclaw" / "operation-log.jsonl"),
                "manual_review_queue": str(kb / ".openclaw" / "manual-review" / "queue.jsonl"),
            },
        }

    def make_index(self, kb: Path) -> VaultIndex:
        return VaultIndex(root=kb, notes=[], by_rel={}, by_stem={}, by_title={})

    def test_preserves_user_root_index_and_writes_generated_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "wiki" / "topics").mkdir(parents=True)
            user_index = kb / "index.md"
            user_content = "# My Home\n\nThis is my hand-written entry point."
            user_index.write_text(user_content, encoding="utf-8")
            cfg = self.make_cfg(kb)

            update_index(self.make_index(kb), cfg)

            self.assertEqual(user_index.read_text(encoding="utf-8"), user_content)
            generated = generated_index_path(kb)
            self.assertTrue(generated.exists())
            self.assertIn(MANAGED_INDEX_MARKER, generated.read_text(encoding="utf-8"))
            log_text = (kb / ".openclaw" / "operation-log.jsonl").read_text(encoding="utf-8")
            self.assertIn("preserve_user_root_index", log_text)
            self.assertIn("write_generated_index", log_text)

    def test_updates_managed_root_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "wiki" / "topics").mkdir(parents=True)
            user_index = kb / "index.md"
            user_index.write_text(f"{MANAGED_INDEX_MARKER}\n# Old Generated Index\n", encoding="utf-8")
            cfg = self.make_cfg(kb)

            update_index(self.make_index(kb), cfg)

            text = user_index.read_text(encoding="utf-8")
            self.assertIn(MANAGED_INDEX_MARKER, text)
            self.assertIn("# Personal Knowledge Base", text)
            self.assertFalse(generated_index_path(kb).exists())

    def test_creates_managed_root_index_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "wiki" / "topics").mkdir(parents=True)
            cfg = self.make_cfg(kb)

            update_index(self.make_index(kb), cfg)

            text = (kb / "index.md").read_text(encoding="utf-8")
            self.assertIn(MANAGED_INDEX_MARKER, text)
            self.assertIn("# Personal Knowledge Base", text)

    def test_created_directory_readme_has_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            (kb / "wiki" / "seeds").mkdir(parents=True)
            cfg = self.make_cfg(kb)

            update_index(self.make_index(kb), cfg)

            text = (kb / "wiki" / "seeds" / "README.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            self.assertIn("type: run-report", text)
            self.assertIn("sources: []", text)
            self.assertIn("origin:", text)


if __name__ == "__main__":
    unittest.main()
