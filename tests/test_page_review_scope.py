"""B3a pure page-review scope tests using only synthetic bound plans."""
from __future__ import annotations

import hashlib

import pytest

from core.page_review_scope import (
    PAGE_REVIEW_TYPE,
    PageReviewScopeError,
    page_review_records,
    select_page_review,
)
from core.plan_objects import bind_plan_objects
from core.vault import VaultIndex, parse_frontmatter


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _page(target: str, title: str, *, links: list[str] | None = None,
          operation: str = "create", object_id: str | None = None,
          revision: int = 1, base_revision: int | None = None,
          base_sha256: str | None = None) -> dict:
    links = links or []
    link_text = "\n".join(f"- [[{link}]]" for link in links)
    content = (f"---\ntitle: {title}\ntype: topic-page\n---\n"
               f"# {title}\n\n{link_text}\n")
    page = {
        "operation": operation,
        "rel_path": target,
        "target": target,
        "canonical_path": target,
        "object_id": object_id or f"kb:{title}",
        "revision": revision,
        "content": content,
        "content_sha256": _sha(content),
    }
    if operation == "update":
        page["base_revision"] = base_revision
        page["base_sha256"] = base_sha256 or ("a" * 64)
    return page


def _plan(*pages: dict, run_id: str = "b3a-run") -> dict:
    return {"run_id": run_id, "planned_pages": list(pages)}


def _queue(record: dict, status: str, item_id: str) -> dict:
    return {**record, "id": item_id, "status": status}


def _applied(record: dict) -> dict:
    return {
        "canonical_path": record["target"],
        "content_sha256": record["content_sha256"],
        "object_id": record["object_id"],
        "revision": record["revision"],
    }


@pytest.fixture
def three_page_plan():
    return _plan(
        _page("wiki/a.md", "A", links=["wiki/b.md"]),
        _page("wiki/b.md", "B", operation="update", object_id="kb:b",
              revision=2, base_revision=1),
        _page("wiki/c.md", "C", object_id="kb:c"),
    )


def test_page_review_records_require_bound_pages_and_exact_content_hash(three_page_plan):
    records = page_review_records(three_page_plan)
    assert len(records) == 3
    assert all(record["type"] == PAGE_REVIEW_TYPE for record in records)
    assert all(record["scope"] == "page" for record in records)
    assert records[1]["operation"] == "update"
    assert records[1]["base_revision"] == 1
    assert records[1]["base_object_id"] is None
    assert records[0]["review_key"] == _sha(
        "b3a-run\x00wiki/a.md\x00" + records[0]["content_sha256"])


@pytest.mark.parametrize("mutator", [
    lambda plan: plan["planned_pages"][0].update(content_sha256="0" * 64),
    lambda plan: plan["planned_pages"][0].update(operation="replace"),
    lambda plan: plan["planned_pages"][0].update(canonical_path="wiki/alias.md"),
])
def test_records_reject_forged_hash_unknown_operation_and_target(mutator, three_page_plan):
    mutator(three_page_plan)
    with pytest.raises(PageReviewScopeError):
        page_review_records(three_page_plan)


def test_records_reject_duplicate_targets_and_duplicate_object_ids():
    duplicate_target = _plan(_page("wiki/a.md", "A"), _page("wiki/a.md", "A2"))
    with pytest.raises(PageReviewScopeError, match="target"):
        page_review_records(duplicate_target)
    duplicate_object = _plan(_page("wiki/a.md", "A", object_id="kb:same"),
                             _page("wiki/b.md", "B", object_id="kb:same"))
    with pytest.raises(PageReviewScopeError, match="object_id"):
        page_review_records(duplicate_object)


def test_update_base_object_id_is_part_of_exact_review_identity(three_page_plan):
    page = three_page_plan["planned_pages"][1]
    page["base_object_id"] = "kb:b"
    record = page_review_records(three_page_plan)[1]
    assert record["base_object_id"] == "kb:b"
    forged = _queue(record, "approved", "q-b")
    forged["base_object_id"] = "kb:other"
    result = select_page_review(three_page_plan, [forged])
    assert result["selected_targets"] == []
    assert any(c["kind"] == "stale_or_forged_page_record"
               for c in result["conflicts"])


def test_real_bind_plan_objects_output_is_accepted(tmp_path):
    plan = _plan(_page("wiki/bound.md", "Bound"), run_id="bound-api")
    bind_plan_objects(VaultIndex(tmp_path, [], {}, {}, {}), plan)
    page = plan["planned_pages"][0]
    metadata, _ = parse_frontmatter(page["content"])
    assert metadata["object_id"] == page["object_id"]
    assert metadata["revision"] == "1"
    record = page_review_records(plan)[0]
    assert record["object_id"] == page["object_id"]
    assert record["revision"] == 1


def test_one_approved_page_keeps_pending_and_rejected_siblings_visible(three_page_plan):
    plan = _plan(_page("wiki/a.md", "A"),
                 three_page_plan["planned_pages"][1],
                 three_page_plan["planned_pages"][2])
    records = page_review_records(plan)
    result = select_page_review(
        plan,
        [_queue(records[0], "approved", "q-a"),
         _queue(records[1], "pending", "q-b"),
         _queue(records[2], "rejected", "q-c")],
    )
    assert result["selected_targets"] == ["wiki/a.md"]
    assert result["selected_review_ids"] == ["q-a"]
    assert result["pending_targets"] == ["wiki/b.md"]
    assert result["rejected_targets"] == ["wiki/c.md"]
    assert result["authorized_target_hashes"] == {
        "wiki/a.md": records[0]["content_sha256"]}
    assert result["can_apply_subset"] is True
    assert result["can_apply_all"] is False


def test_all_exactly_approved_pages_are_selectable(three_page_plan):
    records = page_review_records(three_page_plan)
    result = select_page_review(
        three_page_plan,
        [_queue(record, "approved", f"q-{record['target']}") for record in records],
    )
    assert result["selected_targets"] == ["wiki/a.md", "wiki/b.md", "wiki/c.md"]
    assert result["pending_targets"] == []
    assert result["rejected_targets"] == []
    assert result["can_apply_subset"] is True
    assert result["can_apply_all"] is True


def test_non_page_pending_record_blocks_subset_without_becoming_page_authority(three_page_plan):
    records = page_review_records(three_page_plan)
    result = select_page_review(
        three_page_plan,
        [_queue(records[0], "approved", "q-a"),
         {"id": "aggregate", "run_id": "b3a-run",
          "type": "planned_pages_require_review", "status": "pending"}],
    )
    assert result["selected_targets"] == ["wiki/a.md"]
    assert result["run_blockers"]
    assert result["authorized_targets"] == {}
    assert result["can_apply_subset"] is False
    assert result["legacy_aggregate_records"][0]["id"] == "aggregate"


def test_foreign_same_target_history_is_ignored_but_never_authorizes_current_run():
    plan = _plan(_page("wiki/isolated.md", "Isolated"))
    record = page_review_records(plan)[0]
    foreign = _queue(record, "approved", "q-previous")
    foreign["run_id"] = "previous-run"
    foreign_only = select_page_review(plan, [foreign])
    assert foreign_only["selected_targets"] == []
    assert foreign_only["target_states"]["wiki/isolated.md"] == "pending"
    assert foreign_only["conflicts"] == []
    assert foreign_only["can_apply_subset"] is False

    current = _queue(record, "approved", "q-current")
    mixed = select_page_review(plan, [current, foreign])
    assert mixed["selected_targets"] == ["wiki/isolated.md"]
    assert mixed["can_apply_subset"] is True


@pytest.mark.parametrize("field", ["revision", "schema_version"])
def test_boolean_authority_fields_do_not_match_integer_fields(field, three_page_plan):
    record = page_review_records(three_page_plan)[0]
    forged = _queue(record, "approved", "forged-bool")
    forged[field] = True
    result = select_page_review(three_page_plan, [forged])
    assert result["selected_targets"] == []
    assert any(c["kind"] == "stale_or_forged_page_record"
               for c in result["conflicts"])


def test_duplicate_queue_id_fails_closed_across_pages_and_runs(three_page_plan):
    records = page_review_records(three_page_plan)
    same_run = select_page_review(
        three_page_plan,
        [_queue(records[1], "approved", "same-queue-id"),
         _queue(records[2], "approved", "same-queue-id")],
    )
    assert same_run["selected_targets"] == []
    assert same_run["selected_review_ids"] == []
    assert same_run["can_apply_subset"] is False
    assert {c["kind"] for c in same_run["conflicts"]} >= {"duplicate_queue_id"}

    foreign = _queue(records[2], "approved", "cross-run-id")
    foreign["run_id"] = "previous-run"
    cross_run = select_page_review(
        three_page_plan,
        [_queue(records[1], "approved", "cross-run-id"), foreign],
    )
    assert cross_run["selected_targets"] == []
    assert cross_run["can_apply_subset"] is False
    assert any(c["kind"] == "duplicate_queue_id" for c in cross_run["conflicts"])


def test_forged_target_or_hash_never_authorizes_a_page(three_page_plan):
    records = page_review_records(three_page_plan)
    forged_hash = _queue(records[0], "approved", "forged-hash")
    forged_hash["content_sha256"] = "0" * 64
    result = select_page_review(three_page_plan, [forged_hash])
    assert result["selected_pages"] == []
    assert any(c["kind"] == "stale_or_forged_page_record" for c in result["conflicts"])


def test_changed_content_after_review_fails_closed(three_page_plan):
    records = page_review_records(three_page_plan)
    three_page_plan["planned_pages"][0]["content"] += "changed after review\n"
    with pytest.raises(PageReviewScopeError, match="content_sha256"):
        select_page_review(three_page_plan, [_queue(records[0], "approved", "q-a")])


def test_duplicate_scope_records_are_conflict_even_when_both_approved(three_page_plan):
    record = page_review_records(three_page_plan)[0]
    result = select_page_review(
        three_page_plan,
        [_queue(record, "approved", "q-a1"), _queue(record, "approved", "q-a2")],
    )
    assert result["selected_targets"] == []
    assert result["target_states"]["wiki/a.md"] == "conflict"
    assert any(c["kind"] == "duplicate_page_scope_records"
               for c in result["conflicts"])


def test_approved_one_page_cannot_turn_legacy_aggregate_into_page_authority(three_page_plan):
    records = page_review_records(three_page_plan)
    result = select_page_review(
        three_page_plan,
        [_queue(records[0], "approved", "q-a"),
         {"id": "aggregate", "run_id": "b3a-run",
          "type": "planned_pages_require_review", "status": "approved"}],
    )
    assert result["selected_targets"] == ["wiki/a.md"]
    assert result["pending_targets"] == ["wiki/b.md", "wiki/c.md"]
    assert result["legacy_aggregate_records"]
    assert result["legacy_run_only"] is False
    assert result["can_apply_all"] is False


def test_old_run_only_aggregate_is_reported_and_selects_nothing(three_page_plan):
    result = select_page_review(
        three_page_plan,
        [{"id": "aggregate", "run_id": "b3a-run",
          "type": "planned_pages_require_review", "status": "approved"}],
    )
    assert result["selected_pages"] == []
    assert result["legacy_run_only"] is True
    assert result["mode"] == "legacy_run"
    assert result["can_apply_subset"] is False


def test_future_pending_or_rejected_sibling_link_is_dependency_blocker(three_page_plan):
    records = page_review_records(three_page_plan)
    result = select_page_review(
        three_page_plan,
        [_queue(records[0], "approved", "q-a"),
         _queue(records[1], "pending", "q-b")],
    )
    assert result["dependency_blockers"]
    assert result["can_apply_subset"] is False


@pytest.mark.parametrize("link, sibling_pages", [
    ("shared", [("wiki/one/shared.md", "One"), ("wiki/two/shared.md", "Two")]),
    ("Shared", [("wiki/left.md", "Shared"), ("wiki/right.md", "Shared")]),
])
def test_ambiguous_planned_sibling_link_is_a_visible_blocker(link, sibling_pages):
    plan = _plan(
        _page("wiki/source.md", "Source", links=[link]),
        *[_page(target, title, object_id=f"kb:sibling-{index}")
          for index, (target, title) in enumerate(sibling_pages, start=1)],
    )
    records = page_review_records(plan)
    result = select_page_review(
        plan,
        [_queue(records[0], "approved", "q-source")]
        + [_queue(record, "pending", f"q-{index}")
           for index, record in enumerate(records[1:], start=1)],
    )
    assert any(c["kind"] == "ambiguous_planned_sibling_link"
               for c in result["dependency_blockers"])
    assert result["can_apply_subset"] is False


def test_applied_sibling_requires_actual_output_mapping(three_page_plan):
    records = page_review_records(three_page_plan)
    queue = [_queue(records[0], "approved", "q-a"),
             _queue(records[1], "applied", "q-b")]
    no_trust = select_page_review(three_page_plan, queue)
    assert no_trust["verified_applied_targets"] == []
    assert any(c["kind"] == "unverified_applied_sibling_link"
               for c in no_trust["dependency_blockers"])
    assert no_trust["can_apply_subset"] is False

    verified = select_page_review(
        three_page_plan, queue,
        applied_outputs={"wiki/b.md": _applied(records[1])},
    )
    assert verified["verified_applied_targets"] == ["wiki/b.md"]
    assert verified["dependency_blockers"] == []
    assert verified["can_apply_subset"] is True

    mismatch = _applied(records[1])
    mismatch["content_sha256"] = "0" * 64
    bad = select_page_review(three_page_plan, queue,
                             applied_outputs={"wiki/b.md": mismatch})
    assert any(c["kind"] == "applied_output_mismatch" for c in bad["conflicts"])
    assert bad["dependency_blockers"]
    assert bad["can_apply_subset"] is False


def test_unknown_same_run_page_record_is_a_visible_conflict(three_page_plan):
    records = page_review_records(three_page_plan)
    unknown = _queue(records[0], "approved", "q-unknown")
    unknown["target"] = "wiki/ghost.md"
    result = select_page_review(
        three_page_plan,
        [_queue(records[0], "approved", "q-a"), unknown],
    )
    assert result["selected_targets"] == ["wiki/a.md"]
    assert any(c["kind"] == "unknown_page_target" for c in result["conflicts"])
    assert result["authorized_targets"] == {}
    assert result["can_apply_subset"] is False
