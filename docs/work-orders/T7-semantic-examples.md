# T7 semantic sample correction and prompt precision

Resume same T7 owner. Engineering acceptance is recorded in docs/iteration-evidence/astra-topic-acceptance.md; read its semantic finding. Own only core/topic_generation.py prompt/output-contract explanatory text (no algorithm rewrite), tests/test_topic_generation.py fixtures/tests, and docs/iteration-evidence/M3-topic samples/report. Preserve other modules; no parent/private vault/network/live model/subagents/commits. No whole-suite run.

The current full MOCK sample still has two semantic errors, so it cannot be an exemplar of the accepted demo floor:
1. Successful original versus failure under different applicability conditions is labeled real_conflict, while its own note admits conditions differ. Classify as context_difference. Different numbers/time windows/denominators or different case conditions are not factual contradictions.
2. Owner/adviser interpretation tension is linked to numerical outcome judgments instead of their actual competing interpretation statements. Add exact speaker-quote-backed claims from the supplied public followup source; use those two claims as the sides of the disagreement, with source attribution and no adjudication. Same-source reported debate is allowed. The tool should not invent a contradicts evidence relation against an unrelated claim.

Refine the generic model prompt accordingly (no hardcoded fixture names/answers). For factual conflict require claims about the same referent/context/measurement scope; absent that, use context_difference or clearly unverified interpretation tension. Tension labels are model proposals pending human semantic review, unchanged engineering semantics.

Create a clean full synthetic mock payload/card with the above, real gaps (no control, untested scenarios where supported) and ordered actions. Keep the genuine two-source stub consistent with its own input scope. Preserve old failed full sample/payload under a clearly named historical-failed-example subdir (do not silently erase it). Samples remain labeled mock/synthetic, NEVER real model semantic acceptance.

Run topic+claims focused tests and make sure actual Markdown claims/tension references reload and match original hashes. Update report exact counts and why sample semantics changed. No live calls, no production classifier designed around fixtures.
