# M2 generators — Concepts and cases from evidence-qualified sources

Owner: Claude generator coding agent. Astra handles design/acceptance; you implement/test. Preserve others' edits in shared checkout. Astra may dispatch this independent module against the fixed full-snapshot/claims interface while M1 final corrections run; actual pipeline integration still waits for M1 acceptance. Do not change or depend on transient source/seed implementation details.

Read AGENTS.md, docs/card-contracts.md and this workorder's fixed interface section; read M1 reports only if already available. Do not read private/parent vaults, live config/.env/global credentials or use network/model APIs. Public/synthetic data only; offline patched providers. No legacy repair, subagents, install, commit/push, settings or permission bypass. Python UTF-8 and temproot supplied.

Own new core/concept_generation.py, core/case_generation.py, core/templates/concept_page.j2, core/templates/case_story.j2, core/schemas/concept-page.schema.json, core/schemas/case-story.schema.json, tests/test_concept_generation.py, tests/test_case_generation.py, public fixtures in tests/fixtures/concept-case, docs/iteration-evidence/M2-generators/*. Update skills/case-story-bank-builder/SKILL.md content only. No shared loader/config/CLI/initializer/finalizer/source/seed changes; integration agent owns them. Report required registration/adapter changes with exact signatures.

## Contracts

Reuse current canonical card contracts, source information/evidence format and existing claims compilation/validation. Inputs must carry actual source text snapshots/hashes, not trust extracted paraphrases as raw evidence. Expose small documented generator/render functions the integrator can call for both init/finalize and case skill, bounded model call/retry budgets, injectable/patchable existing call_chat_completion. Return typed structured candidates plus reviewable pages/issues and explicit zero/error reasons aligned with M1; no alternate file writer/identity authority.

## Concept content

- Independently useful concept with one-sentence definition, explanation, near-concept boundary, aliases where known and provenance. Single source can qualify. If no concept in material, output zero rather than fabricate.
- Separate source-defined boundaries from suggested interpretation; interpretation labeled inference with supporting context, never invented ontology/causality.
- Related targets only from provided actual known paths; pending otherwise. Duplication by exact identity/confirmed equivalent, ambiguous synonyms review only.

## Case content

- Context/action/result/reusable mechanism/applicability/evidence sections, distinguish project-level and mechanism-level cards. Shared source doesn't require shared object; don't rewrite same story twice under titles.
- Every material number and claimed outcome attributed. Source assertion != independent verification. Separate observation from mechanism inference; no unsupported causal success claim.
- Applicability is concrete conditions and uncertainties supported by the case context. Zero output or manual_review if evidence insufficient; no universal multi-source threshold.
- Defend against quote mismatch, malicious/unknown paths and secrets pre/post payload; reused existing validators shouldn't be bypassed by new types.

## Tests and evidence

Offline real generator→schema→renderer tests for single-source concept/case; no-substance input; boundary with exact source support vs marked inference; repeated quotes; case outcome figures labeled unverified; distinct mechanism vs project and repeated candidate dedupe; missing/invented evidence rejected; known/pending links; states/versions/hashes preserved. Test schema local registration compatibility without editing other owners' loader.

Produce public sample cards with mock/fixture provenance explicitly labeled. Run relevant new tests plus existing claim_evidence/source_traceability/contract suites. Write report.md/report.json, commands/results/logs, signatures and integration registration requirements. Do not claim pipeline/end-to-end acceptance before integrator hooks the modules up or real-model semantic acceptance before actual evaluation.

## Interface details fixed by Astra after first generator review

- Source cards persist `card_state: {version: 1, type: "source-note", info_units: [...], analysis: {...}}` in frontmatter. Integration supplies actual original snapshots along with validated source units; do not trust arbitrary unit payloads without rechecking raw SHA256 and quotes. Public notes seam: rel/title/body/metadata/source_text/source_sha256. Use original normalized text for model context/claim coordinates; reject budget excess or mark explicit partial, never silently slice body and report full.
- Prefer `generate_concepts(notes, cfg, *, known_paths=None, call_provider=None)` and analogous `generate_cases`, returning state/reason/items/pages/issues plus compiled claims. Document final signatures. One bounded provider call per type is enough for the public fixture; model can return zero or multiple useful distinct candidates.
- You may own NEW core/evidence_cards.py as a small shared concept/case helper if it avoids duplicated snapshot/path/budget/claims validation. Do not import a second canonical schema definition in Python: load owned JSON schema files and register them. Do not use this as permission for a broad framework rewrite.
- Persist typed `card_state: {version: 1, type: ..., claims: [...], analysis: {...}}` in actual Markdown via existing `_patch_header` if needed. Test disk reload/validate_claims, not merely returned dictionaries. Keep base_frontmatter frozen.
- Exact model prompt output contract must include every core.claims-required field, including evidence.relation. Reject malformed model responses distinctly from explicit valid zero-output. A card with no usable compiled evidence cannot satisfy full content quality. Don't silently substitute a generic summary for rejected claims.
- All freeform text can contain model-invented wikilinks, not just the related array. Validate/sanitize the entire rendered card against known real source/object paths; pending text remains literal even if malicious nested bracket syntax. Canonical paths reject traversal, absolute paths, backslash and control syntax.
- Source hashes, positions and `fact` kind only establish traceability, never independent truth. Case results retain original self-report/uncited limitations and mechanism inference; do not create a second card just to meet a count.
