# B2/B3 joint receipt closure — prepared, not dispatched

Owner after the derived lifecycle checkpoint: topic_integration_finish. Root owns acceptance. Preserve other owners' changes; public/synthetic only; no live/native model, network, private vault, config.json, credentials, installation, commits or full suite during edits.

Prerequisites: bounded B2-derived checkpoint and bounded B3 writer checkpoint. Do not start while either interface is still changing. Existing B3a/B3b helper acceptance is the foundation, not permission to weaken evidence checks.

Allowed production files: core/pipeline_history.py and narrowly required card_pipeline receipt transport. New tests/test_receipt_subset_integration.py and own M3-integration/checkpoint-B2-B3-joint.md/json reports. Do not edit the writer, queue, independent blackbox/positive-growth tests or semantic generators; report a demonstrated foreign-module defect to root.

## Required behavior

1. A saved page-scoped plan remains the generation authority across several reviewed subsets. Read verified_plan_outputs using the full bound parent-plan target catalog and exact saved parent hash. Select per-input required_targets only after obtaining full-plan evidence. Combine separately verified successful manifests and individually observed writes from failed attempts without claiming the failed attempt succeeded.
2. Evaluate page review state for the exact required targets of this input/stage. A pending or rejected unrelated sibling must not relabel a fully applied input. A rejected required target remains rejected; an unapproved required target remains pending; both reuse the saved generation result with zero provider calls. Genuine non-page blockers remain effective. Malformed/missing/forged authorities or conflicting evidence fail closed, never authorize writes or claim completion.
3. An input is unchanged/completed only when every required output has exact current byte hash/object identity/revision proof (or the existing verified updater NOOP snapshot). One source producing two seeds must not become completed after one seed is applied. An input producing an explicit valid zero remains distinguishable from failure and rejection.
4. Once every required target has been applied across subsets, the immediately repeated unchanged production entry makes zero calls and proposes no writes. A real changed model, generator contract, original, upstream or external related context still invalidates appropriately.
5. Derived cohort exclusion uses the same exact output evidence across subsets, preserves canonical producer identity across initialize/finalize, and chooses one historical discovery cohort. Do not union unrelated historical outputs or hide changed external cards.
6. Keep the processed index truthful. The writer intentionally leaves subset processed_index unadvanced pending this integration. Receipts may be the authoritative lifecycle completion source if that is the established design; document that choice and prove all public selectors use it rather than adding a false broad source.outputs completion. Report any remaining selector that needs writer/owner coordination.

## Minimum actual-flow evidence

- One source -> two atomic seeds: approve/apply first, leave second pending; source stays incomplete, immediate intake makes zero provider calls and points to saved plan; approve/apply second, final immediate intake zero calls/no pages and completed closure.
- Two unrelated source inputs in one plan: one applied, other rejected or pending; exact per-input dispositions, no sibling contamination and no calls on unchanged repeat.
- Actual second write failure: first exact observed write retained, first page authority reconciled, explicit safe remainder applied under its own protected subset identity; union proves completion, no replay of first, failed manifest preserved.
- Derived concept/case/topic split subsets: no forged full completion; after complete union, initialize/finalize repeat zero calls and stable IDs/revisions/bytes.
- Removed page row, changed target bytes, parent hash mismatch, tampered subset metadata all remain blocked; no aggregate fallback.

Use existing actual save/review/apply fixtures and mock only the provider. Keep original bytes and parent plan immutable. Run the new module plus targeted existing source/seed/derived receipt and subset blackbox tests, with a unique basetemp. No full suite. Deliver FINAL checkpoint with exact file list, command/exit/log paths, unresolved failures and lifecycle decisions; do not claim semantic/live/release acceptance.
