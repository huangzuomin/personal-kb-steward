# T6/T8 B — topic, stage outcomes and repeat/apply lifecycle

NOT DISPATCHED. After A2 and independent typed-update helper acceptance. Resume same integrator. Root owns design and acceptance. Same private-data/no-live-provider/no-network/no-subagent/no-install/no-commit restrictions. Preserve others. Reuse accepted generators and helper; no duplicate writer/identity implementation.

Owned integration files: core/card_pipeline.py, initializer/finalizer/executor adapters, new core/stage_ledger.py and optional core/pipeline_history.py, core/state.py, minimal CLI <=1700 lines, focused additions to core/review_runs.py/core/review_queue.py only for page-level reviewed lifecycle, config validator/example, integration tests. Request a narrow source/seed executor ownership addition only if their per-input results lack necessary signals. Do not alter generator semantic contracts/prompts. Source and seed failure/zero/partial must remain distinct.

## Update hook

Use accepted core/typed_card_updates.prepare_typed_updates for every NEW source/concept/case/topic proposal before plan binding (with exact page.item candidates retained). Its managed region/semantic key state starts at initial creation, not retrofitted after first apply. Seed keeps accepted prepare_seed_updates. No adoption of old typed cards or legacy cards. Changed new-system source files yield reviewed replacement of the source-card generated region. Failed/ambiguous updates remain blocked with per-input outcomes; they must not be swallowed by split_existing_pages or marked processed. Existing object identity and generation-time base survive binding. Do not fabricate fresh object IDs yourself.

## Topic

Add topic to shared discover_cards/default init/finalize. Research question comes from an explicit configured question or persisted source topic hint (clearly a proposal). Use existing Retriever to bound relevant eligible original sources; no synthetic theme guessed from filenames or generic concatenation. Question/config/selection decisions appear in stage ledger. No configured/proposed meaningful question => skipped/not_configured; do not spend a model call. Min 3 specifically cited usable originals for full; below min may yield explicitly limited stub. Concept/case no floor. Reject impossible max_sources < min_sources settings before any provider call. Keep shared-origin limitations, quote/state validation and same review/apply authority. Explicit case skill remains case only.

## Stages / pending intake

Every relevant invocation exposes source, seed, concept, case and topic stage results (case-only command may declare only case). status executed/skipped/blocked/error, reason code, input/attempted/succeeded/output counts, analysis mode; preserve errors and zero_output/no_inputs/not_configured/insufficient_evidence/partial_input/model_error/unchanged_inputs/pending_review/review_rejected explicitly. Display reason text in Chinese without claiming generation when no model ran. Valid zero is distinguishable from provider/malformed-output failure.

Important observed bug: initializer currently starts from changed_notes(index, global_state), then unprocessed_notes. A successful sibling apply saves a GLOBAL file snapshot, so a failed/unapproved input can disappear from the next changed-only run even though its processed entry is absent. New typed intake must select pending eligible raw/quick inputs from per-input source/version outcome state, not only global changed_notes. Preserve explicit --all behavior while keeping failed units retryable.

## No repeated model calls on unchanged inputs

Fingerprint each stage before calling a model: canonical selected original hashes AND upstream-card hashes, question/type, relevant non-secret config/provider model settings, actual generator/prompt/schema version or code hashes, bounded retrieval context as supplied. Never hash or persist credentials. Input order independent. Cached result must not survive a change to any actual model input or generator contract.

Prefer using existing saved plan/run evidence as the generation receipt rather than introducing another unreviewed write authority. Save each stage fingerprint/outcome/candidate target set in the plan at the normal plan-save boundary. On next invocation:
- matching still-pending plan => zero provider calls, pending_review with existing plan reference; do not count applied/processed or duplicate its proposals;
- matching reviewed and successfully applied output set, hashes/identity intact => skipped/unchanged_inputs, no pages/no revisions;
- matching valid zero-output saved result => skipped/zero_output, no provider call; this is successful generation with no card, not an applied card;
- matching rejected result => skipped/review_rejected with review reference; do not silently resubmit as a new run;
- matching partial review => expose remaining pending/rejected/failed pages truthfully; do not mark the whole stage/input as applied;
- prior provider/schema/write failure => retryable, never reused as successful outcome;
- changed actual inputs/config/version => fresh generation; if existing derived card manually changed, do not overwrite; update helper decides safe update vs blocked.

Use existing state/plan path helpers and safe writer. No mutation during plain collector/discovery reads. If a safe durable receipt needs a new file, justify in report and route its mutation via existing save-plan/apply lifecycle. Receipt corruption/missing output invalidates hit with visible reason, never suppresses work as success. Do not use file existence or stable title as cache proof. User may explicitly request regeneration via narrowly validated option; normal repeat is no-call. No hidden retry loop.

## Per-input review/apply

Plan carries per-input attempted/outcome and exact candidate target mapping. Record processed success only for source versions whose required candidates actually applied successfully (or explicit valid-zero disposition). Partial approve/reject must not mark remaining cards or inputs completed; successful sibling inputs should not be needlessly regenerated. A generated preview/partial source is not full successful compilation. Source zero/seed zero states must be tracked without inventing page writes.

Recheck page-level review authority against exact run and content hash before subset apply. Approving one queue item must never authorize a different page or a whole run. Rejected pages must not be written; surviving pages cannot contain future-sibling wikilinks. Retain run-level non-page blockers where applicable. Keep current T9 preflight/path/probe restrictions. Apply failures retain written-file evidence; do not claim all-or-nothing transaction or automatically retry writes.

## Required evidence

Actual plan -> saved plan -> page review -> apply, in isolated synthetic vaults: first generation/apply; identical repeat with provider sentinel that fails if called; same pending plan repeat; valid zero repeat; full rejection repeat; partial approval with pending sibling; provider failure and next normal invocation recovery; 3 batches including repeated input; cumulative source evidence; source revision update; manual outside-text/YAML preservation and ambiguous manual edit block. Compare all-at-once vs split-batch normalized semantic identities/sources/evidence (ignore random IDs/timestamps across fresh vaults). Verify stable same-vault IDs/revisions and all original bytes unchanged. Test own cases plus affected review/state/initializer/finalizer/plan-object checks; full suite only after all workers freeze.

Report command paths, stage states and model-call counts, remaining limitations; stop for Astra acceptance. Engineering completion does not establish real-model semantics.
