# Final minimum closure — Claude CLI coding work order

User direction: focus on stable generation at the approved demo's minimum quality; do not over-engineer. Existing cards are out of scope. Astra plans, dispatches and independently accepts; you implement only the remaining reproduced failures.

Workspace: this isolated .pks-iteration checkout. Other agents' changes are present and must be preserved. The preceding Luna receipt/subset checkpoint will be handed over before this work is dispatched. No implementation owner runs concurrently after that handoff.

Read the latest M3-integration/checkpoint-B2-B3-joint report if present, the current failing test output referenced by Astra, and only the relevant functions. Do not replay the project's full history or redesign its architecture.

Dispatch snapshot: Luna is stopped after 45 passed / 3 failed in `.execution/pytest-luna-B2-B3-joint-focused.log`. Three-input-wave now passes. Remaining failures are positive-growth immediate unchanged repeat (three additional calls/updates) and the two producer-recovery task/init cases. The latter currently stop at old queue-status assertions; the processed-index assertions behind them must also remain meaningful and pass. Start from these concrete failures, not hypothetical cases.

## Deliver the smallest working closure

1. The existing tests/test_derived_three_input_waves.py and tests/test_derived_positive_growth.py must finish with zero provider calls/no planned writes on the final unchanged repeat. Stable object identity, accumulated evidence and normalized all-at-once equivalence must remain intact. New raw material may legitimately trigger evaluation; do not restore the rejected zero-call-during-new-input assumption.
2. Typed receipts must recognize exact output evidence across approved subsets and retain per-input required-target completeness. Reuse core.plan_output_evidence; do not add another execution/receipt ledger. Preserve pending/rejected decisions and the ability to continue the same saved plan.
3. Fix the actual default task/init processing-completion regression exposed by tests/test_producer_recovery.py. Existing task selectors still use core.state.unprocessed_notes, so fully completed inputs must remain visible in the existing processed index. Keep the existing state writer. Only advance an input after its required outputs are verified; a source producing multiple cards is not complete after one. For an old path with no per-input receipt, conservative full-parent completion is acceptable. Prefer a small completion calculation at the existing reconcile/update_processed_index seam over a new recovery framework.
4. Adjust producer-recovery test assertions only where the intentional page-scoped contract changes observable shape: exact page rows applied, genuine non-page rows reviewed, successful subset manifest with exact parent linkage. Preserve current bytes/hash/identity and processed-source assertions. Do not weaken tests to hide an implementation defect.

Allowed production files: core/pipeline_history.py, core/apply_execution.py, and the existing apply/state-update seam in scripts/personal_kb_steward.py. A small existing-core helper may be used only if necessary to keep CLI <=1700 lines; no broad refactor or new subsystem. Preserve public APIs/monkeypatch seams. Tests/test_producer_recovery.py may receive the narrowly described contract alignment. Existing independent growth, three-wave and subset tests are read/run only.

Use the established Python: C:/Users/zooma/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe. Set PYTHONUTF8=1 and PYTHONIOENCODING=utf-8. Use a fresh .execution/pytest-claude-final-* basetemp and preserve failed output.

First reproduce the remaining reported failure; then run the three-wave, positive-growth, receipt-subset, subset blackbox and producer-recovery modules. Add at most a focused regression for a concrete uncovered bug, not a new adversarial test matrix. Stop for a bounded handoff after the fix and focused run, even if a remaining concern needs Astra's decision. Astra runs the final whole-suite check and real-model content review.

No private vault/demo, original workspace data, config.json, .env or credential access; no network/live model/install/commit/push/delete/true-vault execution. No subagents or unrelated process skills. Normal Claude permission controls remain enabled. Do not touch other files or replace previous evidence.

Report docs/iteration-evidence/M3-integration/final-minimum-closure.md: changed files, exact commands/exits, evidence paths, remaining concrete blockers. Distinguish implementation from root acceptance; keep final response compact.

## Astra implementation direction after diagnosis

Final dispatch split: Claude CLI owns only the cumulative-cohort comparison in core/pipeline_history.py and its small report. public_runner_finish owns the existing apply_execution/CLI state-update seam and narrowly aligned producer_recovery tests. This supersedes the combined ownership above; no overlapping production edits.

You have read enough context. Implement now; do not continue broad exploration or create debugging harnesses.

- Repeat defect: do NOT remove retrieval_context from fingerprints or omit hashes of actually supplied context. A cumulative input wave needs to exclude its previous verified own discovery cohort before retrieval even when the current original/upstream set has grown. In derived_cohort_paths, allow a previous cohort whose original and upstream snapshots are an exact subset of the current snapshots, while semantic/config/generator contract still match. Keep newest-single-cohort selection, exact output proof and current-target integrity. Unrelated external cards and incompatible source versions remain visible/invalidate. This is a small compatibility comparison, not a new lineage system. Run existing derived edges/lifecycle tests along with growth to guard external-context invalidation.
- Processed state: use the current apply writer's existing reconcile -> build_index -> update_processed_index phase. For a subset, compute completed operations from previously verified/observed parent outputs plus the current reconciled created records, checked against the exact parent target catalog. A typed file input may advance only when all its required targets are proved (including the existing verified NOOP case). A no-receipt legacy plan advances only after all parent writes are proved. Reuse existing state writing; no extra ledger, post-apply retry service or duplicate page writer. Put the narrow calculation in the existing core/apply_execution.py if needed for CLI line budget.
- Align only the intended producer-recovery queue/manifest shape assertions; retain processed outputs/bytes/identity checks. Preserve prior code changes and all failure evidence.

If this concrete approach conflicts with actual code, state the specific conflict in the handoff instead of expanding the design. Finish a patch and the focused run, then stop.
