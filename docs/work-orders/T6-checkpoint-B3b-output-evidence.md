# B3b — read-only per-target applied evidence helper

Independent foundation pulled forward while B2 intake is active. This is NOT B3 production integration or partial-apply authorization. Owner: public_runner_finish. Allowed ONLY new core/plan_output_evidence.py, tests/test_plan_output_evidence.py and docs/iteration-evidence/M3-integration/checkpoint-B3b.md/json. Preserve others. No edits to pipeline_history/review_runs/CLI/runner/semantic generators. Public/synthetic only; no private/config/env/native/network/install/commit. Stop at bounded handoff.

Implement one reusable read API:

`verified_plan_outputs(index, cfg, plan_path, plan_sha256, target_catalog) -> {verified, observed_failed, conflicts, manifest_paths}`

`target_catalog` maps canonical relative target -> expected {content_sha256, object_id, revision, canonical_path}; use only already-bound page identity. `verified[target]` includes these same exact fields plus evidence manifest/run refs. `observed_failed` retains separately the individually verified outputs from failed attempts. `conflicts` are structured reasons, never silently repaired.

This helper READS only. It neither writes cards/queue/receipts nor grants approval, creates IDs, skips run guards or retries anything. Caller must still validate review authority and refuse conflicts. Actual B3 integration waits B2 acceptance.

Input/audit contract:
- Re-read the saved parent plan bytes and require exact supplied plan_sha256 and actual plan.run_id. Require each expected catalog tuple to match its corresponding bound saved page (hash/content/identity/revision/operation as applicable); no caller-fabricated target proof.
- Current ordinary applied manifest links through exact `plan_path` + `plan_sha256`, run_id==parent run.
- Future subset manifest links through EXACT `parent_plan_path` + `parent_plan_sha256` + `parent_run_id`, plus `subset_hash` and `selected_targets` map of the exact approved target/content tuples. Validate required presence/types/matching membership, do not trust mere name prefix. Root/integrator will preserve this contract in both success and failure manifests; coordinate proposal changes through handoff before assuming another schema.
- Scan normal canonical run manifests and retained immutable attempt records so late reporting failures do not erase actual mutation facts. Deduplicate identical event/target facts; never replace a prior observation with a later status just by sorted filename.
- For successful batch require status=applied and real reconcile.ok=true. For failed batch, no fabricated successful whole-batch reconcile: a created item can establish only its own observed mutation if write_started is exactly true, content_verified is exactly true, expected/observed SHA-256 and recorded identity match the bound parent page. Retain failed batch status.
- For every verified target, re-read current bytes, check hash and exact metadata object_id/revision against the expected tuple. Use strict ints (bool not int); reject missing/forged hash, identity, target traversal/escape, malformed matching records and conflicting facts. Resolve confinement before opening target bytes. Queue status, file presence alone or a proposed page never establishes completion.
- Ignore valid unrelated parent plans/runs. Relevant malformed or contradictory evidence is a visible conflict; verify candidates may remain in output but caller must not authorize through conflicts.
- Ordinary old failure manifests lacking the new parent/hash linkage are retained diagnostics where relevant, never promoted to verified proof. A NOOP receipt is a separate generation proof handled by B2, not invented as an applied write by this helper.

Tests isolated public tiny actual bound plans + normal write_observed_page/save_run_manifest where useful: ordinary success; two linked subset successes union; individually verified first target in failedtwo-pageattempt without whole-batchsuccess; latefailed event preserves previous actual evidence; unrelated run ignored; stale/current edit/falsequeue-only/no currentfile blocks; plan/hash/run/target/identity/revision forgery (bool included); matching conflicting records visible; out-of-root path notread. Preserve originals. Focused tests only, no full suite.

Deliver compact helper API/example, exact tests and limitations. This module does not by itself pass subset review. Integration owner remains topic_integration_finish after B2.