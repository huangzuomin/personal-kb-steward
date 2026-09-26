# M0 — Public baseline and shared card contracts

Owner: Claude CLI coding agent. Astra owns design, integration decisions and final acceptance. Worktree baseline: 4d95bc8, branch feat-demo-baseline. You are not alone in this checkout; preserve other changes and respect file ownership. User authorized implementation, not just a proposal. Complete this bounded work order, test it, and write evidence. Do not execute other milestones.

## Data and execution boundaries

- Read AGENTS.md here. Work ONLY inside this checkout. Do not read parent directories, original/private vaults, other worktrees, .env, config.json, credentials, user configuration, browser sessions, or outside-workspace memory. The checkout deliberately has no live config.json.
- Use repository public source and examples plus synthetic fixtures only. Do not retrieve private demo material named in the overarching plan. This work order supplies its content requirements.
- Normal Claude permissions apply. Never use bypass/skip permissions or change permission settings. Do not install dependencies, invoke network/model APIs, spawn agents, git commit/push, or delete original files. If a command is denied, report it and continue independent work.
- Tests run offline with use_llm=False or patched providers; no actual app commands against a configured vault. Python 3.13, pytest, jinja2, jsonschema are already installed; PATH includes the right Python. PYTEST_DEBUG_TEMPROOT is provided and exists. Do not clean temporary directories.
- Keep CLI <=1700 lines; put implementation in core. UTF-8 throughout.

## Product baseline (already accepted)

Source: complete original-source/summary/key-statements/topic-hints/quality sections; distinguish speakers, AI-generated reports without citations, orally reported numbers, source limitations. Seed: one independently expressible thought, single source legal, specific growth directions incl. applicable counterexample/boundary, real related links or honest no-match. Concepts: definition plus boundaries/aliases. Cases: context/actions/outcomes/mechanism/applicability/evidence; unverified numbers explicitly unverified. Topics: source map, evidence-supported disagreement vs context differences, gaps, next actions. No forced cardinalities or fabricated content. Original and existing cards remain untouched; no migration tooling.

## Ownership

You may modify core/json_contract.py, core/validator.py, core/skill_executor.py, core/skill_runtime.py, core/renderer.py, core/templates/base_frontmatter.j2, core/config.py, config.example.json, scripts/validate_config.py, docs/status-stage-model.md, requirements.txt.
New files: core/card_contracts.py, core/schemas/seed-card.schema.json, core/schemas/source-note.schema.json, docs/card-contracts.md, docs/demo-baseline-rubric.md, tests/test_card_contracts.py, tests/fixtures/card-baseline/*, docs/iteration-evidence/M0/*.
You may minimally adapt skills/mindseed-grow/schema.json and skills/topic-research-compile/schema.json (new), existing executors/renderers for these two skills ONLY for contract wiring and consistent metadata/stage. Full atomic extraction and source analysis are separate later tasks. If additional ownership is truly needed, explain in report; do not silently redesign.
Do not edit work orders, the iteration plan, Astra ledger, core/output_paths.py or core/safety.py (a separate worker may own them).

## Deliverables

1. Public synthetic fixture set + manifest + rubric for 5 card types and negative cases (dialogue user/AI speakers, uncited AI report, oral case, single idea, irrelevant/empty content, damaged text, repeated quote). Preserve damaged existing fixture; do not guess its original content. The rubric is a quality contract, not canned exact model output.
2. Draft 2020-12 schemas as single type truth in core/schemas. Per-skill envelope schemas reference local canonical schemas. Local registry/loader only; no remote ref fetching. Add jsonschema runtime requirement. Avoid a bespoke partial schema checker.
3. Validate typed structured items before rendering in both executor and generic skill runtime entry paths for supported seed/source cards; preserve unrelated skills. Do not validate pages/created executor envelopes as card items. Explicit type adapters where source renderer data differs. Invalid type/stage/source/boolean fails closed and cannot become a page or advance processed state. Required renderer dependencies checked before model call. Do not make renderer fields optional merely to pass tests.
4. Minimal states: new seed status seed|manual_review, stage candidate|needs_context; new source status growing|manual_review, stage compiling|needs_context. Old pages read-only compatibility; no historical rewrite. Explicit legacy topic mode can keep required semantics via producer normalization rather than accepting every stage.
5. New metadata contract schema_version/generator_version/analysis_mode/source hashes/coverage, preserve through rendering, without falsely inventing full coverage or verified evidence. Unknown/unavailable are explicit. Future concept/case/topic schemas must register cleanly without reimplementing loader. Existing claims.py owns IDs/hashes/spans; no second identity authority.
6. Configuration seed_generation.mode atomic|topic, default atomic, validation before model calls; update public example and tests. Do NOT implement atomic generation in M0. Explicitly report that until M1 the new mode is a contract seam and full generator behavior is pending.
7. Concrete handoff documentation for M1: callable signatures, data dictionaries, source adapter fields, required/default metadata and local ref resolution. Keep reasonable minimal interfaces; do not build unused framework abstractions.

## Required verification

- Run tests/test_card_contracts.py with valid/invalid cards, envelope adapters, local refs, non-boolean flags, incompatible states, original BOM/CRLF handling and preserved metadata. Include real call-path tests, not only calling validator directly.
- Run existing tests/test_render_fail_closed.py tests/test_signal_safety.py tests/test_review_run_scope.py tests/test_priority_fixes_integration.py; add source/seed tests relevant to changes (test_seed_quality_outputs.py, test_source_traceability.py, relevant workflow cases). Provider network forbidden. Do not blindly run all tests.
- Save logs, exact commands and actual exit codes under docs/iteration-evidence/M0. Report pre-existing failures separately with evidence; never weaken assertions to hide regressions.
- Finish report.md with changed files, interfaces, check results, deviations/pending M1 features. Also machine-readable report.json with status, changed_files, tests, pending, permission_denials. "done" means ready for Astra review, not acceptance.

Start by proving real execution: inspect one allowed source file, create the fixture/rubric skeleton and run a small no-network test. Then implement the entire M0 work order.
