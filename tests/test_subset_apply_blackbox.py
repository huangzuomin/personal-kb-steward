"""B3 desired same-plan subset review/apply acceptance tests.

These tests deliberately require the page-scoped queue contract.  The plan
and pages come from the real public producer path; only the provider seam is
mocked.  The current BEFORE implementation still emits one aggregate review
record, so this module is expected to fail at the exact authority assertion
until the B3 integrator supplies the page-scoped records and writer.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.page_review_scope import (
    PAGE_REVIEW_SCOPE,
    PAGE_REVIEW_TYPE,
    page_review_records,
)
from core.vault import build_index, parse_frontmatter
from scripts import personal_kb_steward as steward
from tests import public_round_support as round_support
from tests.test_card_pipeline_integration import make_cfg


SOURCE_IDS = ("project_case_01", "project_case_01_followup")
_AUTHORITY_FIELDS = (
    "schema_version",
    "type",
    "scope",
    "run_id",
    "review_key",
    "target",
    "rel_path",
    "canonical_path",
    "operation",
    "object_id",
    "revision",
    "base_revision",
    "base_sha256",
    "base_object_id",
    "content_sha256",
)


def _prepare_real_two_output_plan(
    root: Path, run_id: str
) -> tuple[dict, dict, Path, bytes, dict[str, bytes], object, object]:
    """Generate two actual source pages and save one bound parent plan."""
    cfg = make_cfg(root)
    originals: dict[str, bytes] = {}
    pages: list[dict] = []
    provider_log = round_support.CallLog()
    provider = round_support.make_offline_provider(provider_log)
    for fixture_id in SOURCE_IDS:
        fixture = round_support.load_fixture(fixture_id)
        raw_path = root / fixture["rel"]
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(fixture["text"].encode("utf-8"))
        originals[fixture["rel"]] = raw_path.read_bytes()
        index = build_index(cfg)
        note = index.by_rel[fixture["rel"]]
        with patch("core.llm.call_chat_completion", provider):
            generated = steward.mvp_executor_plan(
                index,
                cfg,
                "B3 subset blackbox source output",
                "topic-research-compile",
                [note],
                {},
                f"{run_id}-{fixture_id}",
                use_llm=True,
            )
        assert generated.get("planned_pages"), generated.get("issues")
        pages.extend(generated["planned_pages"])

    plan = {
        "run_id": run_id,
        "entry": "init_kb",
        "task": "B3 subset blackbox",
        "primary_skill": "topic-research-compile",
        "planned_pages": pages,
        "manual_review": [{
            "type": "planned_pages_require_review",
            "risk": "medium",
            "reason": "B3 acceptance requires exact page-scoped approval rows.",
            "items": [page["rel_path"] for page in pages],
        }],
    }
    plan_path = steward.write_execution_plan(cfg, plan)
    steward.write_manual_review_queue(cfg, plan)
    plan_bytes = plan_path.read_bytes()

    # This is the authority gate.  It intentionally rejects the current
    # aggregate queue instead of rewriting it into page rows in the test.
    queue = _queue_for(cfg, run_id)
    records = page_review_records(plan)
    _assert_exact_page_authority(queue, records)

    assert len(provider_log.calls) == len(SOURCE_IDS), provider_log.calls
    assert all(
        page.get("object_id") and page.get("revision") == 1
        for page in plan["planned_pages"]
    )
    return cfg, plan, plan_path, plan_bytes, originals, provider_log, provider


def _queue_for(cfg: dict, run_id: str) -> list[dict]:
    return [
        item
        for item in steward.load_queue(steward.review_queue_path(cfg))
        if item.get("run_id") == run_id
    ]


def _review(cfg: dict, provider: object, args: SimpleNamespace) -> int:
    """Keep every review/apply probe on the public offline provider seam."""
    with patch("core.llm.call_chat_completion", provider):
        return steward.command_review(cfg, args)


def _assert_exact_page_authority(queue: list[dict], records: list[dict]) -> None:
    expected_by_target = {record["target"]: record for record in records}
    assert len(queue) == len(records) == 2, (
        "B3 requires one real page authority record per saved target; "
        f"observed {len(queue)} queue row(s): {queue!r}"
    )
    assert {item.get("type") for item in queue} == {PAGE_REVIEW_TYPE}
    assert {item.get("scope") for item in queue} == {PAGE_REVIEW_SCOPE}
    assert {item.get("target") for item in queue} == set(expected_by_target)
    assert all(item.get("status") == "pending" for item in queue)
    assert all(isinstance(item.get("id"), str) and item["id"] for item in queue)
    for item in queue:
        expected = expected_by_target[item["target"]]
        for field in _AUTHORITY_FIELDS:
            assert item.get(field) == expected[field], (
                f"page authority mismatch for {item['target']}: {field}"
            )


def _target_snapshots(root: Path, targets: list[str]) -> dict[str, dict | None]:
    snapshots: dict[str, dict | None] = {}
    for target in targets:
        path = root / target
        if not path.exists():
            snapshots[target] = None
            continue
        metadata, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        snapshots[target] = {
            "bytes": path.read_bytes(),
            "object_id": metadata.get("object_id"),
            "revision": metadata.get("revision"),
        }
    return snapshots


def _expected_snapshot(plan: dict, target: str) -> dict:
    page = next(page for page in plan["planned_pages"] if page["rel_path"] == target)
    return {
        "bytes": page["content"].encode("utf-8"),
        "object_id": page["object_id"],
        "revision": str(page["revision"]),
    }


def _assert_immutable_parent(
    plan_path: Path,
    plan_bytes: bytes,
    root: Path,
    originals: dict[str, bytes],
) -> None:
    assert plan_path.read_bytes() == plan_bytes
    assert {rel: (root / rel).read_bytes() for rel in originals} == originals


def test_subset_approve_one_then_remaining_and_unchanged_reapply(tmp_path: Path):
    """Approve one target, then the remainder, with exact no-op reapply."""
    run_id = "b3-desired-approve-pending"
    cfg, plan, plan_path, plan_bytes, originals, provider_log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    queue = _queue_for(cfg, run_id)
    targets = [page["rel_path"] for page in plan["planned_pages"]]
    queue_by_target = {item["target"]: item for item in queue}
    first, second = (queue_by_target[target] for target in targets)

    assert _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="approve",
            id=first["id"],
            reason="B3 desired approve first page",
        ),
    ) == 0
    assert _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    ) == 0

    after_first = _target_snapshots(tmp_path, targets)
    assert after_first[targets[0]] == _expected_snapshot(plan, targets[0])
    assert after_first[targets[1]] is None
    statuses = {item["target"]: item["status"] for item in _queue_for(cfg, run_id)}
    assert statuses == {targets[0]: "applied", targets[1]: "pending"}
    _assert_immutable_parent(plan_path, plan_bytes, tmp_path, originals)

    assert _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="approve",
            id=second["id"],
            reason="B3 desired approve remaining page",
        ),
    ) == 0
    assert _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    ) == 0

    after_second = _target_snapshots(tmp_path, targets)
    assert after_second[targets[0]] == after_first[targets[0]]
    assert after_second[targets[1]] == _expected_snapshot(plan, targets[1])
    assert all(item["status"] == "applied" for item in _queue_for(cfg, run_id))
    _assert_immutable_parent(plan_path, plan_bytes, tmp_path, originals)

    before_reapply = after_second
    assert _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    ) == 0
    assert _target_snapshots(tmp_path, targets) == before_reapply
    assert len(provider_log.calls) == 2
    _assert_immutable_parent(plan_path, plan_bytes, tmp_path, originals)


def test_subset_approve_one_reject_one_writes_only_approved_and_reapply_is_noop(
    tmp_path: Path,
):
    """A rejected sibling never writes, and an unchanged apply is a no-op."""
    run_id = "b3-desired-approve-reject"
    cfg, plan, plan_path, plan_bytes, originals, provider_log, provider = (
        _prepare_real_two_output_plan(tmp_path, run_id)
    )
    queue = _queue_for(cfg, run_id)
    targets = [page["rel_path"] for page in plan["planned_pages"]]
    queue_by_target = {item["target"]: item for item in queue}
    first, second = (queue_by_target[target] for target in targets)

    assert _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="approve",
            id=first["id"],
            reason="B3 desired approve page",
        ),
    ) == 0
    assert _review(
        cfg,
        provider,
        SimpleNamespace(
            review_command="reject",
            id=second["id"],
            reason="B3 desired reject sibling",
        ),
    ) == 0
    assert _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    ) == 0

    expected = _expected_snapshot(plan, targets[0])
    observed = _target_snapshots(tmp_path, targets)
    assert observed[targets[0]] == expected
    assert observed[targets[1]] is None
    statuses = {item["target"]: item["status"] for item in _queue_for(cfg, run_id)}
    assert statuses == {targets[0]: "applied", targets[1]: "rejected"}
    _assert_immutable_parent(plan_path, plan_bytes, tmp_path, originals)

    before_reapply = observed
    assert _review(
        cfg,
        provider,
        SimpleNamespace(review_command="apply-approved", run_id=run_id),
    ) == 0
    assert _target_snapshots(tmp_path, targets) == before_reapply
    assert len(provider_log.calls) == 2
    _assert_immutable_parent(plan_path, plan_bytes, tmp_path, originals)
