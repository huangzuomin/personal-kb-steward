# T6 A2 — thin typed generation adapters and actual review/apply

NOT DISPATCHED. Resume integration session after A1 acceptance and M2 canonical statement handoff. Use previous exploration; do not redesign framework. Same private-data/no-model/no-subagent/no-commit restrictions. Root owns ledger/workorders. Preserve other agents.

Own core/card_pipeline.py (extend accepted collector, no rewrite), initializer.py, finalizer.py, skill_executor.py only if necessary, config.py + validator/example for small pipeline mode config, new optional core/executor_adapters.py, minimal CLI edits <=1700 lines, NEW case skill executor/schema, tests/test_card_pipeline_integration.py and minimal explicit-legacy config updates in existing initializer/finalizer tests. Read actual accepted M2 module APIs/report and exact model output contracts before writing fake provider responses. Top-level APIs unchanged; authoritative statement refs are being tightened by generator owner.

Target interface:
`discover_cards(index,cfg,*,run_id,use_llm=True,kinds=('concept','case'),providers=None,skill='kb-finalize')` returns planned page specs + explicit per-kind stage outcomes/issues. Use collect_eligible_sources once, no second scan; call generate_concepts/cases once each with qualified raw snapshots plus metadata.upstream_analysis. Pass injectable provider via existing generate_* seam. No source-floor for these types. Zero, disabled, error and partial must stay distinct.

Plan page adapter must retain item and stored card_state; map configured concepts_dir/cases_dir; safe readable filename; skill/operation=create/rel_path/content/content_sha256/sources/origin/review_required/confidence, and retrieval_source_hashes pinning BOTH used original bytes and their upstream source-card snapshots. Existing plan_objects is the only object-id/revision authority. No direct writer. Only existing known paths may be linked; no sibling-candidate wikilinks. Related candidates from bounded existing Retriever results (actual paths); don't send entire index/whole-vault text to a model. Oversize input is explicit blocked/deferred, never silently truncate. This checkpoint need not implement a new queue scheduler.

Initialization: keep source/seed pending batch generation; downstream discovery reads ONLY previously persisted eligible sources (not newly proposed source pages). A first init produces source/seed candidates; after saved-plan review/apply, a subsequent init discovers concept/case. Always disclose stage outcomes even when no eligible sources. Keep existing explicitly configured legacy candidate_promotion behavior available under explicit legacy mode; no generic old aggregation presented as new typed output.

Finalizer: default typed pipeline delegates to same discover_cards; explicit legacy mode retains existing old finalizer behavior for compatibility tests. Add use_llm/no-llm seam and CLI --no-llm equivalent; no-model path cannot claim generation. CLI line budget: move the existing executor_notes adapter to core/executor_adapters.py if needed rather than expanding CLI beyond 1700.

Case skill: implement thin executor calling shared discovery for cases only with persisted-source eligibility. Register in real CLI routing/MVP dispatch; pass index/retriever context. Ensure task/plan --llm for newly typed source/atomic-seed/case does NOT ALSO call the generic runtime after the specialized producer: current make_plan executes mvp_executor_plan then unconditionally run_skill_runtime(use_llm). This wastes calls and can add contradictory diagnostics. One authority/call path per typed skill; preserve explicit legacy and non-typed skill runtime behavior. Mock/no-llm must remain honest and must never trigger a live provider. Do not retrofit legacy cards.

A2 integration tests, offline provider boundary only (actual generators/renderers, not ready-page mocks):
1 actual init -> persisted plan -> review -> apply source/seed; then actual init/finalize -> concept/case saved plan -> review -> apply; reload both compiled claims against originals and pin upstream hashes;
2 single-source concept/case allowed, explicit zero/disabled/error stages truthful;
3 changed original or changed upstream source-note snapshot blocked before downstream apply;
4 reject one candidate while accepting another: no dangling sibling links;
5 actual case skill uses same generator; typed plan --llm provider-call count proves no extra generic runtime request;
6 Chinese content intact and originals byte-identical.

Identity/update/cache/per-input apply lifecycle and topics are next B/C checkpoint. Do not silently skip existing target and count a new success: until B implements confirmed identity reuse, surface collision explicitly. Tests should use new isolated targets; report limitation honestly. Existing tests asserting old heuristics may opt into explicit legacy config, but keep safety assertions and new default tests.

Run focused integration + affected initializer/finalizer/config/runtime checks once final changes complete; no entire suite while other modules change. Evidence M2-integration/checkpoint-A2.md + report JSON, exact commands and public artifact paths. STOP after handoff for root review.
