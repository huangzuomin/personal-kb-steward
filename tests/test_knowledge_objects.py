import hashlib
import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from core.knowledge_objects import ObjectIdentityError, identity_from_metadata, new_object_id
from core.vault import build_index


class KnowledgeObjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = {
            "knowledge_base": str(self.root),
            "scan": {"include_dirs": ["wiki", "raw"], "exclude_dirs": [], "extensions": [".md"]},
            "write": {"log_file": "log.md"},
        }

    def note(self, path, object_id=None, revision=1, extra=""):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        identity = f"object_id: {object_id}\nrevision: {revision}\n" if object_id else ""
        target.write_text(f"---\n{identity}title: Shared title\ntype: topic-page\n{extra}---\n# Body\n", encoding="utf-8")
        return target

    def test_ids_are_opaque_and_unique(self):
        ids = {new_object_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)
        for object_id in ids:
            self.assertEqual(UUID(object_id[3:]).version, 4)
            self.assertTrue(object_id.startswith("kb:"))

    def test_legacy_scan_never_mints_or_changes_files(self):
        target = self.note("wiki/topics/legacy.md", extra="id: existing-user-id\n")
        before = target.read_bytes()
        index = build_index(self.cfg)
        self.assertEqual(index.objects.legacy_paths, ["wiki/topics/legacy.md"])
        self.assertIsNone(index.by_rel["wiki/topics/legacy.md"].object_id)
        self.assertIsNone(index.by_rel["wiki/topics/legacy.md"].revision)
        self.assertEqual(index.objects.issues, [])
        self.assertEqual(index.objects.by_id, {})
        self.assertEqual(target.read_bytes(), before)

    def test_rename_changes_path_not_identity_or_revision(self):
        object_id = new_object_id()
        old = self.note("wiki/topics/旧名称.md", object_id, 3, "canonical_path: obsolete.md\n")
        old_bytes = old.read_bytes()
        index = build_index(self.cfg)
        self.assertEqual(index.by_object_id[object_id].revision, 3)
        new = old.with_name("新名称.md")
        old.rename(new)
        index = build_index(self.cfg)
        obj = index.objects.get(object_id)
        self.assertEqual(obj.object_id, object_id)
        self.assertEqual(obj.revision, 3)
        self.assertEqual(obj.canonical_path, "wiki/topics/新名称.md")
        self.assertEqual(obj.content_sha256, hashlib.sha256(old_bytes).hexdigest())
        self.assertEqual(index.by_object_id[object_id].canonical_path, obj.canonical_path)

    def test_same_titles_do_not_collide(self):
        first, second = new_object_id(), new_object_id()
        self.note("wiki/topics/a.md", first)
        self.note("wiki/concepts/a.md", second)
        index = build_index(self.cfg)
        self.assertEqual(len(index.objects.by_id), 2)
        self.assertEqual(index.objects.issues, [])

    def test_duplicate_id_is_reported_not_last_writer_wins(self):
        object_id = new_object_id()
        self.note("wiki/topics/a.md", object_id)
        self.note("wiki/topics/b.md", object_id)
        index = build_index(self.cfg)
        self.assertNotIn(object_id, index.by_object_id)
        self.assertEqual(index.objects.duplicates[object_id], ["wiki/topics/a.md", "wiki/topics/b.md"])
        self.assertEqual(index.objects.issues[0]["kind"], "duplicate_object_id")
        with self.assertRaises(ObjectIdentityError):
            index.objects.get(object_id)

    def test_overlapping_scan_dirs_do_not_manufacture_duplicate_ids(self):
        object_id = new_object_id()
        self.note("wiki/topics/a.md", object_id)
        self.cfg["scan"]["include_dirs"] = ["wiki", "wiki/topics"]
        index = build_index(self.cfg)
        self.assertEqual(index.objects.issues, [])
        self.assertIn(object_id, index.objects.by_id)

    def test_invalid_id_and_revision_are_visible_to_lint(self):
        self.note("wiki/topics/a.md", "not-an-id")
        self.note("wiki/topics/b.md", new_object_id(), "0")
        index = build_index(self.cfg)
        self.assertEqual(len(index.objects.issues), 2)
        self.assertEqual({item["kind"] for item in index.objects.issues}, {"invalid_object_identity"})
        with self.assertRaises(ObjectIdentityError):
            index.objects.require_valid()

    def test_duplicate_identity_keys_are_not_silently_overwritten(self):
        self.note("wiki/topics/a.md", new_object_id(), extra="revision: 2\n")
        index = build_index(self.cfg)
        self.assertEqual(index.objects.by_id, {})
        self.assertEqual(index.objects.issues[0]["kind"], "invalid_object_identity")

    def test_raw_and_generated_readme_are_not_objects(self):
        raw = self.note("raw/source.md", extra="revision: source-edition-2\n")
        self.note("wiki/topics/README.md", new_object_id())
        before = raw.read_bytes()
        index = build_index(self.cfg)
        self.assertEqual(index.objects.by_id, {})
        self.assertEqual(index.objects.legacy_paths, [])
        self.assertIsNone(index.by_rel["raw/source.md"].object_id)
        self.assertEqual(before, raw.read_bytes())

    def test_scalar_validation_is_strict(self):
        object_id = new_object_id()
        for value in (0, -1, True, False, 1.0, "1.0", "-1", "01", "", None):
            with self.subTest(value=value), self.assertRaises(ObjectIdentityError):
                identity_from_metadata({"object_id": object_id, "revision": value})
        self.assertEqual(identity_from_metadata({"object_id": object_id, "revision": "2"}), (object_id, 2))
        for meta in ({"revision": 1}, {"object_id": object_id}, {"object_id": "kb:" + str(UUID(int=0)), "revision": 1}):
            with self.subTest(meta=meta), self.assertRaises(ObjectIdentityError):
                identity_from_metadata(meta)


if __name__ == "__main__":
    unittest.main()
