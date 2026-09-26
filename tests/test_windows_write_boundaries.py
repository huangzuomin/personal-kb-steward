"""T9 native Windows boundary evidence: junction aliases into raw/protected
paths and outside the test vault, including not-yet-existing targets.

Junction evidence here is REAL (mklink /J needs no privilege on Windows).
Symlink evidence is explicitly UNVERIFIED on this host: where a test needs a
true symlink it attempts creation and, on OSError, records that the symlink
guard could not be exercised — a skip is never claimed as a pass.

Guard layering found in the codebase (documented, not weakened):
- plans produced via write_execution_plan are identity-checked at persist time
  (bind_plan_objects -> _current rejects vault escapes and writes through
  symlinks for knowledge paths);
- command_apply_plan re-validates object writes before any page write.
The preflight layer must independently reject aliases for targets that are not
knowledge paths (hand-written plan JSON), which is what the root-level alias
tests below exercise.
"""
import json
import os
import subprocess

import pytest

from core.config import sha256_text
from core.knowledge_objects import ObjectIdentityError
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


@pytest.fixture
def case():
    instance = fixtures.ObjectPlanTests()
    instance.setUp()
    yield instance
    instance.doCleanups()


def make_junction(link, target):
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return link


def plan(rid, pages):
    return {"run_id": rid, "task": "native boundary", "entry": "discover_topics",
            "primary_skill": "topic-research-compile", "planned_pages": list(pages), "manual_review": []}


def raw_page(rel_path):
    content = "planted"
    return {"skill": "topic-research-compile", "operation": "create", "rel_path": rel_path,
            "sources": [], "content": content, "content_sha256": sha256_text(content),
            "review_required": False, "confidence": "medium"}


PROTECTED_FILES = ("raw/a.md",)


def snap_protected(case):
    """Byte snapshots of the protected input files, taken BEFORE the operation."""
    return {rel: (case.root / rel).read_bytes() for rel in PROTECTED_FILES}


def assert_protected_untouched(case, before):
    """Compare against the pre-operation snapshot; detects in-place mutation."""
    for rel, original in before.items():
        assert (case.root / rel).exists(), f"protected input {rel} was removed"
        assert (case.root / rel).read_bytes() == original, f"protected input {rel} was modified"


def test_snapshot_helper_detects_mutation(case):
    """Regression for the evidence defect: the helper must fail when a
    protected file is modified between snapshot and check."""
    before = snap_protected(case)
    target = case.root / "raw/a.md"
    target.write_bytes(original := target.read_bytes() + b"TAMPERED")
    with pytest.raises(AssertionError, match="was modified"):
        assert_protected_untouched(case, before)
    target.write_bytes(original[:-len(b"TAMPERED")])
    assert_protected_untouched(case, before)  # restored: passes again


def apply_rejected(case, plan_obj):
    """Reject may land at plan persist (identity layer) or at apply (preflight
    or object-write validation); in every case nothing may be written."""
    try:
        path = case.persist(plan_obj)
    except ObjectIdentityError:
        return
    with pytest.raises((ObjectIdentityError, SystemExit, PermissionError)):
        steward.command_apply_plan(case.cfg, str(path))


def hand_written_plan_file(case, rid, pages):
    plan_dir = case.root / ".openclaw/plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = plan_dir / f"{rid}.json"
    steward.write_json(path, plan(rid, pages))
    return path


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_knowledge_target_under_junction_aliasing_raw_is_rejected_before_writes(case):
    before = snap_protected(case)
    alias = make_junction(case.root / "wiki/topics/raw-alias", case.root / "raw")
    try:
        apply_rejected(case, plan("junction-raw-create",
                                  [case.page("wiki/topics/raw-alias/brand-new.md")]))
        assert not (case.root / "raw/brand-new.md").exists()
        assert_protected_untouched(case, before)
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_knowledge_target_under_junction_aliasing_raw_survives_hand_written_plan(case):
    """A plan JSON that never passed persist must still be rejected by the
    apply channel (object-write validation), with zero writes."""
    alias = make_junction(case.root / "wiki/topics/raw-alias", case.root / "raw")
    try:
        before = snap_protected(case)
        path = hand_written_plan_file(case, "junction-raw-json",
                                      [raw_page("wiki/topics/raw-alias/brand-new.md")])
        with pytest.raises((ObjectIdentityError, SystemExit, PermissionError)):
            steward.command_apply_plan(case.cfg, str(path))
        assert not (case.root / "raw/brand-new.md").exists()
        assert_protected_untouched(case, before)
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_nontarget_root_junction_aliasing_raw_is_rejected_before_any_write(case):
    """Root-level alias, non-knowledge rel_path: no identity layer applies, so
    preflight itself must reject. Demonstrated gap at baseline; guard added."""
    alias = make_junction(case.root / "raw-alias", case.root / "raw")
    try:
        before = snap_protected(case)
        path = hand_written_plan_file(case, "junction-root-raw",
                                      [raw_page("raw-alias/planted.md")])
        with pytest.raises((SystemExit, PermissionError)):
            steward.command_apply_plan(case.cfg, str(path))
        assert not (case.root / "raw/planted.md").exists()
        assert_protected_untouched(case, before)
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_uppercase_root_junction_aliasing_quicknote_is_rejected_before_any_write(case):
    alias = make_junction(case.root / "QUICKNOTE-ALIAS", case.root / "quicknote")
    try:
        path = hand_written_plan_file(case, "junction-root-quicknote",
                                      [raw_page("QUICKNOTE-ALIAS/planted.md")])
        with pytest.raises((SystemExit, PermissionError)):
            steward.command_apply_plan(case.cfg, str(path))
        assert not (case.root / "quicknote/planted.md").exists()
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_root_junction_outside_vault_is_rejected_and_outside_stays_empty(case):
    outside = case.root.parent / f"t9-outside-{os.getpid()}"
    outside.mkdir(parents=True, exist_ok=True)
    try:
        alias = make_junction(case.root / "outside-alias", outside)
        try:
            path = hand_written_plan_file(case, "junction-root-outside",
                                          [raw_page("outside-alias/escaped.md")])
            with pytest.raises((SystemExit, PermissionError)):
                steward.command_apply_plan(case.cfg, str(path))
            assert not (outside / "escaped.md").exists()
            assert not list(outside.iterdir())
        finally:
            os.rmdir(alias)
    finally:
        outside.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_dangling_junction_to_missing_outside_path_is_rejected(case):
    outside_missing = case.root.parent / f"t9-missing-{os.getpid()}"
    assert not outside_missing.exists()
    alias = make_junction(case.root / "dangling-alias", outside_missing)
    try:
        path = hand_written_plan_file(case, "junction-root-dangling",
                                      [raw_page("dangling-alias/gone.md")])
        with pytest.raises((SystemExit, PermissionError, OSError)):
            steward.command_apply_plan(case.cfg, str(path))
        assert not outside_missing.exists()
    finally:
        os.rmdir(alias)


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_not_yet_existing_target_in_clean_directory_still_applies(case):
    page = case.page("wiki/topics/brand-new-legit.md")
    path = case.persist(plan("clean-create-still-applies", [page]))
    assert steward.command_apply_plan(case.cfg, str(path)) == 0
    assert (case.root / "wiki/topics/brand-new-legit.md").exists()


@pytest.mark.skipif(os.name != "nt", reason="Native Windows junction contract")
def test_true_symlink_guard_evidence_or_explicit_unverified(case):
    alias = case.root / "raw-sym-alias"
    try:
        alias.symlink_to(case.root / "raw", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("UNVERIFIED: symlink privilege unavailable on this host; "
                    "junction evidence covered by sibling tests, symlink guard not exercised")
    try:
        before = snap_protected(case)
        path = hand_written_plan_file(case, "symlink-root-raw",
                                      [raw_page("raw-sym-alias/planted.md")])
        with pytest.raises((SystemExit, PermissionError)):
            steward.command_apply_plan(case.cfg, str(path))
        assert not (case.root / "raw/planted.md").exists()
        assert_protected_untouched(case, before)
    finally:
        os.rmdir(alias)
