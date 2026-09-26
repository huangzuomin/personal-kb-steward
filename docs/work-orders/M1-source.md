# M1-source — Complete, attributable source cards

Owner: Claude source coding agent; Astra dispatches and accepts. Start ONLY after Astra dispatch; M0 interfaces in docs/card-contracts.md and core/card_contracts.py are authoritative. You are not alone; seed and runtime workers may be active. Preserve others' changes.

## Boundary and ownership

Read AGENTS.md and M0 handoff. Stay in this checkout; no parent/private vaults/.env/config.json/global credentials, no API/network/model calls, no subagents/commit/push/dependency installation. Normal permissions retained. Public/synthetic data only; no original/legacy migration.

Own skills/topic-research-compile/{executor.py,renderer.py,schema.json,SKILL.md}, core/source_analysis.py (new), core/templates/source_note.j2, core/schemas/source-note.schema.json, tests/test_source_quality_contract.py, tests/fixtures/source-quality/*, docs/iteration-evidence/M1-source/*.
Do not modify shared contracts/base_frontmatter, seed files, initializer/finalizer, safety/path modules. Exception explicitly assigned by Astra: scripts/personal_kb_steward.py::executor_notes and the shared context handoff immediately before execute_skill in mvp_executor_plan, plus necessary import only. T9 preflight code is frozen; do not touch it. Keep CLI <=1700 lines. Other shared-interface needs must be reported. You may add a pure helper within source_analysis to expose extracted source information units to later integration.

Shared snapshot seam (source worker owns wiring; seed worker consumes): executor_notes must retain existing keys and add source_text (FULL original UTF-8 decoded text, BOM/CRLF preserved) and source_sha256 (original byte hash). Reuse core.reconcile._text(note), which checks bytes against note.sha256 before returning source text; do not rebind a changed source or hash cleaned body. In mvp_executor_plan add context vault_index=index and retriever=retriever before dispatch so atomic seed relation lookup can reuse the already captured index. Do not send the whole context/index to a model. Source and seed consumers read the dictionary fields independently; do not force seed worker to import an unfinished source module. Invalid bytes/snapshot changes must surface explicitly, not yield fabricated complete coverage.

## Target behavior

1. Handle dialogue, AI synthesis, oral/internal case and conventional article. Source type and speaker come from text/metadata, unknown when uncertain; don't attribute AI suggestions to user.
2. Analyze full source via bounded chunks over original normalized text; preserve raw-byte hash, normalized positions and complete/partial/error coverage. Current 6000-character prefix truncation cannot silently claim complete. Configurable budget with sane defaults, explicit unread ranges, fail or partial review if budget insufficient. No unbounded calls or retries. Never destroy original text by cleaning and then use cleaned coordinates as evidence.
3. LLM output includes attributable key statements/information units and source-specific limitations. Program verifies quotes with existing core.claims mechanics where applicable, including repeated occurrence disambiguation. Assertion/question/procedure/reference classification is not factual verification; keep source claims vs inference explicit.
4. A source card contains all five existing main sections, with substantive quality assessment. Numbers in uncited/generated/oral sources are labeled unverified. No generic “no obvious issues” for demonstrably missing citations. Source suggestions stay plain pending text until target cards exist; no invented links.
5. Persist contract metadata through real render/page plan pathway: source hashes, schema/generator versions, analysis mode, coverage, review and quality. Heuristic mode can yield useful explicitly limited review cards; it must not masquerade as semantic/model success. Model/parse/quote errors must remain visible, no silent quality upgrade.
6. Separate a single source's usability from multi-source synthesis threshold; single-source notes are valid. No automatic compiled/linked.
7. Compatibility: existing source executor created/page envelope and write layout stay consumable by CLI; preserve PR29 renderer fail-closed and payload secret checks before calls and after responses. No plaintext secrets in diagnostics.

## Required tests

- Synthetic source with pivotal evidence after char 6000 => full-mode includes it; budget-limited mode records excluded range and cannot be accepted as complete.
- Dialogue role attribution; uncited AI factual claim/number; oral reported outcome; source-specific limitations; unclear type stays unknown.
- Quotes map original BOM/CRLF content; repeated identical quote needs correct occurrence; invalid quote rejected/marked unusable, never “verified”.
- Stub provider captures payloads/chunks; no network. Validate actual execute→render source card, schema, mandatory metadata and all sections. Failure and fallback mode provenance covered.
- Existing source_traceability/render_fail_closed/signal_safety/priority_fixes_integration relevant tests. Use python -m pytest, PYTHONUTF8=1/PYTHONIOENCODING=utf-8 provided. If pre-existing failures occur document before/after; do not weaken safety assertions.

## Handoff

Write docs/iteration-evidence/M1-source/report.md + report.json with changed files, signatures/fields for downstream consumers, precise checks/exit codes, pending limitations. Include rendered public synthetic sample Markdown plus associated structured payload and source hash; label mocked model output as fixture, not real-model quality acceptance. No actual private demo claims. Astra separately reviews real artifacts and later runs bounded real-model public evaluation.
