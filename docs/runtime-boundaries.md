# Runtime Boundaries

Phase 14 starts splitting `scripts/personal_kb_steward.py` by stable boundaries, not by arbitrary line count.

## Extracted Core Modules

```text
core/config.py
```

Owns portable path expansion, JSON IO, hash helpers, and configured locations such as `plans_dir`, `runs_dir`, `processed_index`, and `manual_review_queue`.

```text
core/vault.py
```

Owns Markdown note reading, YAML frontmatter parsing, and vault indexing.

```text
core/state.py
```

Owns `state_file`, changed-file detection, and `processed-index` updates.

```text
core/router.py
```

Owns product entry routing and workflow lookup from `router.json` / `workflows.json`.

```text
core/markdown.py
```

Owns common Markdown rendering helpers: frontmatter, slug, bullet lists, and note summaries.

## Still In Runner

`scripts/personal_kb_steward.py` still owns:

- CLI commands;
- legacy Skill functions not yet migrated;
- plan/apply-plan/rollback orchestration;
- safety checks that need full runtime context;
- report/log writing.

## Why Not Split Everything Yet

The goal is to reduce coupling while preserving behavior. The remaining legacy Skill functions should move only when each Skill gets its own `schema.json`, `renderer.py`, and `executor.py`, as already done for the three MVP Skills.
