# M1-seed — Atomic ideas with specific growth and honest relations

Owner: Claude seed coding agent; Astra dispatches and accepts. Start only when dispatched after M0. Read docs/card-contracts.md first. Other workers share this checkout; preserve their changes.

## Boundaries and owned files

Stay within checkout. No parent/private vaults, .env/config.json/global credentials, network/model API calls, subagents, commit/push or installs. Normal permissions apply. Public/synthetic fixtures only. No legacy-card migration or private original writes.

Own core/{seed_quality.py,seed_updates.py,atomic_seed.py,card_relations.py}, skills/mindseed-grow/{executor.py,renderer.py,schema.json,SKILL.md}, core/schemas/seed-card.schema.json, docs/seed-quality.md, tests/test_atomic_seed.py, tests/test_seed_growth_links.py, tests/fixtures/atomic-seed/*, docs/iteration-evidence/M1-seed/*. core/clustering.py only if strictly necessary for explicit legacy topic mode compatibility. Do not modify shared contracts/config/base_frontmatter, source files, CLI, initializer/finalizer, safety/path modules. Report exact shared-interface gaps instead of changing others' code.

Shared input seam fixed by Astra: source worker will wire executor_notes with source_text (full original text with BOM/CRLF) and source_sha256 (verified original-byte hash), retaining rel/title/body/summary/metadata. mvp context also carries vault_index and retriever; consume these for known candidate retrieval, do not rescan whole vault or invent a parallel index. No dependency on unfinished source_analysis functions: operate on the dictionary fields. Unit fixtures may directly supply known full text plus its computed raw-byte SHA256. Missing original snapshot fields => explicit unknown provenance/limited or blocked result, not a hash of body claimed as original. Use prepare_card_item's trusted provenance keyword parameters documented by M0, never raw model metadata.

## Target behavior

1. seed_generation.mode defaults atomic (M0 defines config); explicit topic keeps prior grouping pathway. Atomic builds independent thought candidates from attributable information units; cluster reasoning must not become the thought's content. One source can yield multiple ideas; several sources can support one. Empty or no-substance input yields zero with a clear reason.
2. Model output must contain thought statement, evidence/source attribution, specific growth actions and negative scope. Preserve question/uncertainty, don't turn intuition into proven fact. Reuse core.claims for supported assertion/inference evidence; non-assertion questions retain traceable origins without pretending to be facts.
3. Growth directions answer what is uncertain, what evidence/action would help, and which boundary/counterexample/cost matters. No canned pair, no synonyms to fill quota. No invented first-person user preferences; title/sections may say “卡片边界” absent explicit personal statement.
4. Candidate relations use core.retrieval.Retriever within configured known documents/index; distinguish related knowledge from suspected duplicates. Explain relation, verify full vault-relative target; unknown => pending. not_attempted/no_match/candidates_found truthfully set. No-match legal, no fixed required link count, no first-N fallback unrelated pages.
5. Same-title distinct ideas must not auto-merge. For repeated generation use confirmed object identity plus exact source-information evidence identity; preserve existing object_id/revision and handwritten content through current update plan semantics. Ambiguous semantic matches => review, not auto-collapse.
6. No-model atomic execution must explicitly be a limited preview or blocked; cannot silently emit topic card and say atomic success. Keep legacy topic tests by explicit mode; update tests only where default meaning legitimately changes. Don't turn off new atomic default to satisfy old tests.
7. Provide reusable generator entry accepting note dictionaries and/or already extracted information units for later source→seed integration. Do not force long raw to bypass scope restrictions. Keep secret screening and renderer dependency preflight before model payload, preserve source snapshots.

## Tests and artifacts

Test one-source two-ideas; two-source one-idea; unrelated multi-source no forced merge; zero-content zero-output; quote fidelity and speaker attribution; growth varies by thought/unknown; no relationship candidate vs not attempted; valid candidate resolution and pending unknowns; same-title different thoughts; unchanged repeat no duplicate; explicit topic mode and no-model atomic truthful status.

Run targeted new tests, existing test_seed_quality_outputs.py, relevant test_workflows.py/test_pr15_contracts.py and PR29 tests; providers mocked/offline. PYTHONUTF8=1/PYTHONIOENCODING=utf-8 and existing temproot supplied. Record original failures vs regressions. You may minimally adapt mode-specific old fixtures in those tests; never weaken safety/content assertions.

Ownership extension for explicit legacy mode fixtures only: tests/test_apply_plan.py, tests/test_mvp_skill_executors.py, tests/test_llm_runtime.py if they relied on the old implicit topic default. Set topic/use_llm=False explicitly for old behavior and keep dedicated new tests proving atomic is the real default. Do not broaden unrelated test edits. T9 runtime tests remain unchanged.

Write report.md/report.json and exact logs under docs/iteration-evidence/M1-seed. Include 2–3 rendered synthetic sample cards and structured evidence payload; label fixture/mock origin. Document source-information-unit interface and new update identity behavior for integration. done is a handoff, not Astra acceptance or real-model demo certification.
