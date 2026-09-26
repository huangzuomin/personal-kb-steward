# M2 final review — one authoritative statement per cited field

Same ownership/restrictions. No pipeline edits. Your broad suites pass; Astra independently got 102 passed for concept/case/claims/source traceability. However two direct counterexamples still survive. Do not claim the original probe fixed by changing its input or omitting the new reference field.

Evidence:
- `.execution/astra-M2-initial-probe.py` / `astra-M2-probe-after.json`: existing valid definition_claim left intact, free definition replaced with '销量必定增长十倍' => invented definition still rendered (stub only because another boundary is invalid).
- `.execution/astra-M2-bound-text-probe.py` / `astra-M2-bound-text-probe.json`: valid outcome claim left intact, description replaced with '活动已经证实带来999倍净利润。' => state=full, invented outcome rendered, issues=[].

Design decision: remove the TWO independent authoritative texts for the same cited field. Definition, source-defined boundary and outcome description must render the referenced COMPILED CLAIM'S statement as their authoritative text. The model's duplicate definition/text/description may be omitted from the input contract or ignored with a diagnostic when it differs; never retain a contradictory duplicate as supported content. This is mechanical consistency, not an NLP truth classifier; semantic validity of the compiled statement against its quote is still human/Astra review. Keep useful paraphrase explanation separate and labeled as model organization.

Case reusable mechanism and applicability also currently have no binding to compiled claims despite the previous brief. Add a small explicit reference seam (e.g. reusable_mechanism_claim, mechanism_inference_claim, applicability.conditions entries with claim), derive those authoritative statements from compiled claims, and require inference claims to have kind=inference. Source-asserted mechanism can be fact-kind with clear attribution. If references absent/invalid, drop unsupported mechanisms/conditions, give diagnostic and mark case limited where required. Do not invent a mechanism merely to fill sections. Context/action can remain clearly attributed model summaries, not machine-verified facts. Questions/uncertainties may be proposed research questions and must be labeled as such, not source facts.

Update exact output_contract/system prompt, owned canonical schema/render/tests/samples accordingly. Top-level generate_* signatures/result envelopes stay fixed for integrator. Existing helper core.claims remains unchanged.

Regression must leave a VALID reference in place while corrupting only the separate display text and assert false invented content absent; add valid single-source qualitative full case and bound mechanism conditions. Run own concept/case tests plus claims/source traceability (not full suite), update report exact counts and preserve before/after probes. Hand off when done.
