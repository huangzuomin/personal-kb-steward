# M2/M3 integration — One reviewable card pipeline

Owner: Claude integration executor; Astra designs, dispatches and independently accepts. NOT dispatched yet. Start only after source/seed/generator interfaces and reports are available. Other workers share this checkout; preserve their changes.

## Scope and inputs

Read AGENTS.md, docs/card-contracts.md, accepted M1/M2 reports and the iteration plan. Public/synthetic fixtures only. Stay in checkout; no parent/private vault, live config.json/.env, credentials, model/network calls, subagents, installs, commits or pushes. Preserve T9 preflight. Do not modify original/legacy cards.

Own core/initializer.py, core/finalizer.py, core/skill_executor.py, necessary core/card_contracts.py registration, core/config.py, scripts/validate_config.py, config.example.json, small CLI adapters, new core/card_pipeline.py and core/stage_ledger.py, skills/case-story-bank-builder/executor.py and schema.json, workflow/router registration if needed. Source generator is frozen after acceptance; request narrow ownership transfer for needed persistence fixes. Source/seed and concept/case/topic implementations remain shared modules, not reimplemented here. Main CLI <=1700 lines: move new orchestration into core, keep the CLI thin.

Tests owned: tests/test_card_pipeline_integration.py, tests/test_cross_batch_promotion.py, tests/test_stage_ledger.py, tests/test_demo_pipeline.py. Existing initialization/finalization tests may be minimally adapted for explicit legacy configuration only; keep new default behavior separately asserted. Evidence docs/iteration-evidence/M2-integration and M3-integration.

## Target behavior

1. Default new flow can discover concept/case candidates without users naming every card or supplying markers. Single-source concepts/cases are valid if supported. An unrelated batch or empty evidence yields zero, with reason. Retain explicit old aggregation rules without representing their generic output as baseline-qualified new cards.
2. Reuse exact full source snapshots and information units. Subsequent promotion selects persisted source-note objects whose original-source hashes still match, coverage is full, and source evidence is usable. Partial/error/unknown snapshots cannot silently become complete promotion evidence. Limitations persist; full coverage and matched quotes do not mean factual verification. Never retrieve approved demo/old cards as substitute model outputs.
3. Source information units/claims and coverage must survive rendering and reload in an explicit versioned Markdown-owned field. Do not infer authoritative evidence by parsing display paraphrases. Recheck original bytes via captured index at generation; never silently refresh mismatching stored source hashes. Source/seed downstream input adapter must preserve speaker attribution and uncertainty.
4. Initialization compiles its pending source batch and processes quicknotes; downstream discovery reads eligible persisted sources, including earlier batches. Finalize and case skill delegate to the same generators/pipeline. Newly planned but not yet approved source pages are not authoritative persisted inputs. Return all stage outcomes so a second invocation's purpose is clear.
5. Write only via existing plan binding -> review -> apply. Every page carries original-source and upstream-note retrieval hashes, generation-time update base, review flags and structured provenance. Do not use direct writers or invent object IDs. A rejected page must not leave broken wikilinks in any applied sibling: only link already-existing targets; future candidates stay pending plain paths until a later reviewed linking update.
6. Preserve manual content/custom frontmatter on updates. Confirmed object identity plus exact thought/mechanism evidence keys govern reuse; similar title alone never merges. Unchanged sources/candidate content yield no duplicate and no revision increment. New evidence to an existing confirmed object uses reviewed updates. Ambiguous matches get explicit manual review instead of silent duplicates/collapse.
7. Cross-batch discovery operates on the cumulative eligible set, not only current batch. Deterministic tests compare normalized type/semantic keys, source hashes, claims/evidence, relation targets and quality state for all-at-once versus split batches. Different fresh-vault object IDs and timestamps are irrelevant; rerun in same vault preserves IDs. Do not call a stable filename proof of semantic identity.
8. Stage ledger records executed/skipped/blocked/error, reason, input/output counts and model mode. Reasons include no_inputs, zero_output, not_configured, insufficient_evidence, partial_input, model_error. Failed generation must not count as processed success. Correctly separate attempted inputs from successfully handled inputs, including mixed success/failure batches and partial approval.
9. Validate budgets and impossible min/max source settings before calls. Topics require at least 3 specific original sources by default, with shared-origin dependence surfaced; 1-2 sources can only form an explicitly limited stub. Concepts/cases have no inherited topic floor. No-model execution is blocked/limited and never claims model semantic success.
10. T7 topic generator joins this pipeline when accepted, retaining existing Retriever/claims/review infrastructure. Do not fork a second synthesis writeback authority.

## Checkpoints and acceptance

A: source-note reload/evidence eligibility + concept/case adapters + isolated actual init/finalize/case-skill -> persisted plan -> review -> apply tests. Stop for Astra review before the larger cross-batch work.
B: topic integration + stage ledger + exact rerun/update behavior + manual preservation. Report real default flow invocation and stage reasons.
C: isolated >=3 batches with a repeated source, one simulated provider failure and subsequent recovery; raw files unchanged, review rejection leaves no dangling links, processed does not advance failed units, identities stable. No real model calls in worker tests.

Return compact report.md/report.json with files, public artifacts, exact commands/exit codes, stage ledger, pending limitations. Include full logs locally. A passing helper test or a worker done message is not pipeline/product acceptance.

## Integration review notes fixed by Astra

Persistence seam: all new typed cards use frontmatter `card_state: {version: 1, type: ..., analysis: {...}}`; source-note includes `info_units`, other types include compiled `claims` and their exact identity fields. Source hash is original raw bytes, while claims offsets use BOM/CRLF-normalized original text. Qualify persisted source-note state against original snapshots before discovery.

Additional focused ownership: core/state.py if necessary to consume per-input outcomes without changing legacy semantics; new core/executor_adapters.py if needed to move existing CLI conversion/orchestration while keeping scripts/personal_kb_steward.py <=1700 lines. No broad CLI rewrite. Preserve verified T9 boundary code.

Current `split_existing_pages` skips any create target that exists. For NEW typed source cards this must not discard a changed-source regeneration: prepare reviewed source updates preserving object_id, base hash/revision, manual body and custom keys. Unchanged original snapshot => no duplicate/revision churn. Changed original => old stored source analysis remains ineligible until refreshed through review/apply; never silently bind old analysis to new hash. Do not adopt/repair legacy cards in this iteration. Test changed source -> source update -> downstream candidate update in same vault.

Source/seed task failures must be reconciled per input, not by generic nonzero output count. The existing state updater derives one operation_status for all inputs; demonstrate a mixed batch and reviewer subset apply behaves correctly before changing that contract.

Topic question routing: use an explicit user/task research question where supplied; otherwise derive a clearly proposed question from persisted source topic hints and disclose it as a proposed research frame. Use existing Retriever for relevant eligible source selection, not all-source concatenation. A generic label alone must not make unrelated source notes count toward topic sufficiency. No extra user form is required. Empty/no coherent question -> skipped/no_inputs or insufficient_evidence with a concrete reason; never fake a complete topic simply to hit five types.

## Checkpoint B/C clarification: stable runs with a stochastic model

Unchanged reruns must not rely solely on a mock provider returning identical wording. Record a stage-input fingerprint (eligible upstream object/original hashes, generator/prompt/schema version, relevant config and explicit/proposed question) using existing state/review lifecycle. With unchanged inputs and already reviewed/applied output, skip generation with a concrete unchanged_inputs reason and zero model calls. Do not preemptively cache an unapproved proposal as applied success; rejected/subset-approved outcomes must stay explicit. New input/evidence/version invalidates the appropriate stage and permits a reviewed update. Tests must assert provider-call count on unchanged reruns, in addition to no extra revision/card.

For updates to NEW typed sources/cards, distinguish generated body from preserved manual additions. Never display stale generated facts under a newly rebound source hash; a prior generated section may be retained only as clearly versioned history with its original provenance. Existing legacy cards remain outside repair/adoption. If safely separating manual edits is ambiguous, block that update for review instead of overwriting. This is a scope limit, not permission for automatic legacy migration.
