# B05 / B06 minimal user-entry repairs

User authorizes fixing the three reported black-box defects. You own only the two user-entry defects below. Astra retains scope, integration, and independent acceptance; another worker owns speaker attribution.

## Ownership and boundaries

Work in this checkout, preserving every existing dirty/untracked change. You are not alone; do not revert others' edits. Allowed: scripts/personal_kb_steward.py, core/skill_runtime.py, core/renderer.py, core/executor_adapters.py, narrowly necessary new entry writeback helper, skills/work-memory-weave and skills/writing-material-pack, and focused tests. Do not touch core/source_analysis.py, core/clustering.py, core/atomic_seed.py, core/text_integrity.py, core/claims.py (speaker owner). Coordinate in report if other ownership is necessary.

Do not read config.json, .env, actual vaults, private artifacts, or credentials. Do not call providers, install packages, commit, deploy, or spawn agents. Synthetic fixtures only. No architecture expansion, old-card migration, title/relationship redesign, timeout/provider changes, or generic cleanup.

## Observed defects and acceptance

1. Work memory: real CLI `task --llm --all` scans 2 notes, one under `4-项目/...md` and one quicknote, but select_llm_input_notes filters only quicknote/inbox. Model reports project missing despite the project existing. The model returns one valid work-memory item but planned_pages is empty, manual_review empty, apply fails. Fix input selection against actual configured scan locations, retaining processed-input and budget semantics. A supported project-plan fixture must be sent alongside its relevant diary, and valid work-memory items must become valid reviewable pages in configured allowed output directories with source hashes and origin, preserving planned-vs-occurred content. Do not simply select every note in the vault or hardcode one private project path. Account for existing configured directories and established work-memory candidates.

2. Writing material pack: model item correctly distinguishes reports, interview self-report, AI analysis, unverified figures and missing findings. Final planned content instead comes from the old heuristic executor: heading fragments and truncated text in facts, research plans presented as usable cases, '[待人工填写]' tension, and '暂无明显复核项'. Integrate the validated model result into the actual saved page, preserving specific fields/summary/review limitations and traceable sources. Do not merely copy a summary above the old misleading template. No-LLM behavior remains honest; a failed/invalid LLM response must not silently fall back to a page labeled model success. Work-memory and writing entries must use existing review/apply/writer contracts, configured paths, identity and hashes; don't bypass validation to make pages appear.

Known code clue: build_plan integrates generic runtime writeback only for topic-insight-miner. Reuse/extend established patterns without unnecessary abstraction or widening accepted types globally. Inspect schemas/templates and successful writeback examples before implementation.

## Checks / handoff

Use Python `C:/Users/zooma/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe`.
First reproduce with focused synthetic regression(s). Then verify real CLI plan construction, source selection and approved apply using mock response fixtures (label mocked tests honestly). Include invalid/missing sources, empty/invalid/provider failure, and no leakage of old template when model writeback fails; meaningful tests, not implementation mirrors. Run relevant existing tests around product entries, runtime, writeback and review as justified; no whole-suite repetition until Astra integration.

Write `.execution/fix-entries-report.md` with root cause, changed files, focused test evidence, actual behavior, and limitations. Stop after implementation and checks. Astra will privately replay the saved real responses and perform independent live checks.
