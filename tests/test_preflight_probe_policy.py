"""T9 per-apply probe policy: one probe per parent per apply, refreshed each apply,
cleanup failure reported (not ignored), and existing-target writability checks."""
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from core import apply_preflight
from scripts import personal_kb_steward as steward
from tests import test_object_plans as fixtures


@pytest.fixture
def case():
    instance = fixtures.ObjectPlanTests()
    instance.setUp()
    yield instance
    instance.doCleanups()


def plan(rid, pages):
    return {"run_id": rid, "task": "probe policy", "entry": "discover_topics",
            "primary_skill": "topic-research-compile", "planned_pages": list(pages), "manual_review": []}


class ProbeCounter:
    def __init__(self):
        self.writes = 0
        self.parents = []

    def __call__(self, probe):
        self.writes += 1
        self.parents.append(probe.parent)


def apply_plan_with_probes(case, plan_obj, counter):
    real_write, real_delete = apply_preflight._write_probe, apply_preflight._delete_probe

    def counting_write(probe):
        counter(probe)
        real_write(probe)

    with patch.object(apply_preflight, "_write_probe", side_effect=counting_write), \
         patch.object(apply_preflight, "_delete_probe", side_effect=real_delete):
        return steward.command_apply_plan(case.cfg, str(case.persist(plan_obj)))


def test_hundred_pages_in_one_parent_probe_once_and_second_apply_probes_again(case):
    pages = [case.page(f"wiki/topics/p{i}.md") for i in range(100)]
    first = ProbeCounter()
    assert apply_plan_with_probes(case, plan("probe-one-parent", pages), first) == 0
    assert first.writes == 1
    assert all(p.name == "topics" for p in first.parents)
    assert not list((case.root / "wiki/topics").glob(".write-check-*"))

    second = ProbeCounter()
    more = [case.page(f"wiki/topics/q{i}.md") for i in range(5)]
    assert apply_plan_with_probes(case, plan("probe-refresh", more), second) == 0
    assert second.writes == 1  # a new apply refreshes the probe, no cross-apply cache


def test_two_parents_probe_exactly_twice_within_one_apply(case):
    pages = [case.page(f"wiki/topics/t{i}.md") for i in range(60)]
    pages += [case.page(f"wiki/sources/s{i}.md") for i in range(60)]
    counter = ProbeCounter()
    assert apply_plan_with_probes(case, plan("probe-two-parents", pages), counter) == 0
    assert counter.writes == 2
    assert {p.name for p in counter.parents} == {"topics", "sources"}


def test_probe_write_failure_rejects_apply_without_any_target_mutation(case, capsys):
    def denied(probe):
        raise PermissionError("目标目录不可写：simulated directory write denial")

    with patch.object(apply_preflight, "_write_probe", side_effect=denied):
        with pytest.raises(PermissionError):
            steward.command_apply_plan(
                case.cfg, str(case.persist(plan("probe-denied", [case.page("wiki/topics/x.md")]))))
    record = json.loads((case.root / ".openclaw/runs/probe-denied.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed" and record["created"] == [] and not record["write_started"]
    assert not (case.root / "wiki/topics/x.md").exists()
    assert "目标目录不可写" in record["error"]


def test_probe_cleanup_failure_is_reported_not_ignored(case):
    def stuck(probe):
        raise PermissionError("simulated probe deletion denial")

    with patch.object(apply_preflight, "_write_probe", side_effect=apply_preflight._write_probe), \
         patch.object(apply_preflight, "_delete_probe", side_effect=stuck):
        with pytest.raises(PermissionError, match="无法删除"):
            steward.command_apply_plan(
                case.cfg, str(case.persist(plan("probe-stuck", [case.page("wiki/topics/x.md")]))))
    leftovers = list((case.root / "wiki/topics").glob(".write-check-*"))
    assert leftovers  # residual probe is kept and named by the diagnostics
    assert not (case.root / "wiki/topics/x.md").exists()
    record = json.loads((case.root / ".openclaw/runs/probe-stuck.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed" and "无法删除" in record["error"]
    for leftover in leftovers:
        leftover.unlink()


def test_probe_create_and_cleanup_are_real_with_no_leftovers(tmp_path):
    prober = apply_preflight.ParentWriteProber("owned-attempt")
    prober.probe_parent(tmp_path)
    assert tmp_path.exists() and not list(tmp_path.glob(".write-check-*"))
    prober.probe_parent(tmp_path)  # dedup: still no leftovers, one probe total


def test_probe_name_collision_never_touches_unowned_file(tmp_path):
    planted = tmp_path / ".write-check-owned-attempt-0.tmp"
    planted.write_bytes(b"SENTINEL-NOT-OURS")
    prober = apply_preflight.ParentWriteProber("owned-attempt")
    with pytest.raises(PermissionError, match="已被占用"):
        prober.probe_parent(tmp_path)
    assert planted.read_bytes() == b"SENTINEL-NOT-OURS"  # unowned file preserved


def test_partial_probe_write_failure_cleans_owned_file_and_preserves_cause(tmp_path):
    real_write = apply_preflight.os.write

    def failing_write(fd, data):
        raise OSError("simulated partial probe write failure")

    with patch.object(apply_preflight.os, "write", side_effect=failing_write):
        with pytest.raises(PermissionError, match="探针已清理"):
            apply_preflight.ParentWriteProber("owned-attempt").probe_parent(tmp_path)
    assert not list(tmp_path.glob(".write-check-*"))  # owned leftover cleaned up
    assert real_write  # reference keeps original symbol resolvable for reviewers


def test_partial_probe_write_failure_with_denied_cleanup_reports_both(tmp_path):
    def failing_write(fd, data):
        raise OSError("simulated partial probe write failure")

    def stuck(probe):
        raise PermissionError("simulated cleanup denial")

    with patch.object(apply_preflight.os, "write", side_effect=failing_write), \
         patch.object(apply_preflight, "_delete_probe", side_effect=stuck):
        with pytest.raises(PermissionError, match="写入失败且无法清理") as excinfo:
            apply_preflight.ParentWriteProber("owned-attempt").probe_parent(tmp_path)
    assert isinstance(excinfo.value.__cause__, OSError)  # original cause preserved


def test_missing_update_target_race_creates_nothing_and_fails_apply(case):
    """Simulate the target disappearing between preflight's exists() check and
    the writability probe: no file may be (re)created, apply must fail."""
    target = case.root / "wiki/topics/a.md"
    target.write_text(case.content("Old", None, 3), encoding="utf-8")
    real_check = apply_preflight.ParentWriteProber.check_existing_target

    def disappears(self, path):
        if path.exists():
            path.unlink()
        return real_check(self, path)

    with patch.object(apply_preflight.ParentWriteProber, "check_existing_target", disappears):
        with pytest.raises(FileNotFoundError, match="消失"):
            steward.command_apply_plan(
                case.cfg, str(case.persist(plan("race-update", [case.page(operation="update", content=case.content("New"))]))))
    assert not target.exists()  # not recreated by the writability check
    record = json.loads((case.root / ".openclaw/runs/race-update.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed" and record["created"] == []


def test_existing_readonly_update_target_rejected_before_any_write(case):
    target = case.root / "wiki/topics/a.md"
    target.write_text(case.content("Old", None, 3), encoding="utf-8")
    before = target.read_bytes()
    os.chmod(target, stat.S_IREAD)
    try:
        with pytest.raises(PermissionError, match="只读"):
            steward.command_apply_plan(
                case.cfg, str(case.persist(plan("readonly-update", [case.page(operation="update", content=case.content("New"))]))))
    finally:
        os.chmod(target, stat.S_IWRITE)
    assert target.read_bytes() == before
    record = json.loads((case.root / ".openclaw/runs/readonly-update.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed" and record["created"] == [] and not record["write_started"]


def test_writable_update_target_still_applies(case):
    target = case.root / "wiki/topics/a.md"
    target.write_text(case.content("Old", None, 3), encoding="utf-8")
    pages = [case.page(operation="update", content=case.content("New"))]
    counter = ProbeCounter()
    assert apply_plan_with_probes(case, plan("writable-update", pages), counter) == 0
    assert counter.writes == 1
    assert "New" in target.read_text(encoding="utf-8")
