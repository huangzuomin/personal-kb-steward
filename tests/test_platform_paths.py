"""Cross-platform path/newline contracts; no network shares are contacted."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import resolve_path
from core.safety import safe_write_text
from scripts import validate_config as validator
from tests.test_review_guards import isolated_config


class PlatformPathTests(unittest.TestCase):
    def test_config_resolvers_agree_for_chinese_paths_and_mixed_separators(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(validator, "ROOT", root):
                for value in ("知识库/专题", "知识库\\专题", "child/../知识库"):
                    with self.subTest(value=value):
                        self.assertEqual(resolve_path(value, base=root), validator.resolve_path(value))

    def test_page_writes_preserve_utf8_bom_and_crlf_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = isolated_config(root)
            for i, text in enumerate(("中文\n", "中文\r\n", "\ufeff---\r\ntitle: 知识\r\n---\r\n正文\r\n")):
                with self.subTest(text=text):
                    target = root / f"wiki/中文/{i}.md"
                    safe_write_text(cfg, target, text, run_id=f"newline-{i}", operation="test", reason="newline contract")
                    self.assertEqual(target.read_bytes(), text.encode("utf-8"))

    @unittest.skipUnless(os.name == "nt", "Windows native drive/junction contract")
    def test_native_drive_and_junction_containment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "agent"
            root.mkdir()
            outside = root.parent / "outside"
            outside.mkdir()
            alias = root / "junction"
            with patch.object(validator, "ROOT", root):
                value = str(root / "中文" / "nested")
                self.assertTrue(Path(value).drive)
                self.assertEqual(resolve_path(value), validator.resolve_path(value))
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(outside)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                try:
                    self.assertFalse(validator.resolve_path(str(alias / "backups")).is_relative_to(root.resolve()))
                finally:
                    alias.rmdir()
