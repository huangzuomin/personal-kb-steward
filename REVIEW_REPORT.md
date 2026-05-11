# Review Report

Baseline commit: `0b44074`

Comparison command:

```powershell
git diff 0b44074..HEAD
```

Scope: this baseline includes code changes for write safety, dry-run preservation, backup, operation logging, and failure recovery. It also records the remaining architecture risks found during review.

## Implemented Data Safety Fixes

### Write-before-backup and operation logging

**Problem**

Write, delete, and rollback paths needed concrete protection rather than documentation-only review notes.

**Impact**

Without executable safety logic, generated pages, logs, indexes, state files, and rollback deletes could change the knowledge base without a recovery trail.

**Affected Files**

- `core/safety.py`
- `scripts/personal_kb_steward.py`
- `core/index_builder.py`
- `core/log_manager.py`
- `core/state.py`
- `config.example.json`
- `tests/test_apply_plan.py`

**Fix**

Added a shared safety layer for:

- configurable backup directory through `config.example.json`
- operation log JSONL
- backup before overwriting existing files
- backup before rollback deletes generated files
- failed apply manifest with recovery hint

`apply-plan` still rejects writes into protected source directories: `raw/`, `quicknote/`, and `inbox/`.

**Acceptance Criteria**

- Applying a valid plan creates an operation log.
- Applying a valid plan creates a run-specific backup directory.
- Rollback deletes generated files only after backing them up.
- Applying an invalid plan writes a failed run manifest and prints a recovery path.
- Dry-run commands do not write to the knowledge base.

**Executed Tests**

```powershell
python -m unittest tests.test_apply_plan tests.test_dry_run -v
python -m compileall core scripts tests
python scripts\validate_config.py
```

## P0

### 1. Raw long-form ingestion chain is not fully closed

**Problem**

`topic-research-compile` and the main runtime still need a single enforced executor output contract for raw long-form ingestion.

**Impact**

Raw reports can be classified but may not reliably become source notes and topic stubs in every execution path.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `skills/topic-research-compile/executor.py`
- `skills/topic-research-compile/renderer.py`

**Suggested Fix**

Unify all skill executor output around a single `pages[]` contract:

- `rel_dir_key`
- `filename`
- `content`
- `sources`
- `item`
- optional `manual_review`

Reject executor output that does not match the contract.

**Acceptance Criteria**

- A raw markdown report classified as `research_report` produces one `wiki/sources/` source note and one `wiki/topics/` topic stub in dry-run plan.
- Applying the plan writes both pages.
- Generated pages include concrete `sources` pointing to the raw file.
- Manual-review pages create review queue entries.
- A malformed executor result fails with a clear contract error.

## P1

### 2. Manual-review gate is not yet a hard apply gate

**Problem**

Plans can contain `review_required` and `confidence`, but apply safety currently focuses on path protection, backup, logging, and recovery. It does not yet require an approved review item before applying low-confidence pages.

**Impact**

Uncertain generated content can still be written if it is present in a plan and passes path/hash checks.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `core/review_queue.py`

**Suggested Fix**

Reject `review_required: true` and `confidence: low` pages unless they reference an approved review item tied to the same run id, path, and content hash.

**Acceptance Criteria**

- `apply-plan` rejects review-required pages without approval.
- Approval is invalidated if page content changes.
- Tests cover approved, unapproved, and tampered review-required pages.

### 3. Processed index can still mark unresolved review content as processed

**Problem**

Processed state is still too coarse for review lifecycle semantics.

**Impact**

Sources that only produced unapproved review pages can be skipped in later runs.

**Affected Files**

- `core/state.py`
- `scripts/personal_kb_steward.py`

**Suggested Fix**

Track processed status as lifecycle states such as `planned`, `pending_review`, `applied`, `rejected`, and `failed`.

**Acceptance Criteria**

- Only successfully applied outputs mark a source as processed.
- Pending review outputs keep the source eligible for later processing.
- Processed-index records include output path, hash, review status, and skill.

## P2

### 4. Workflow declarations do not fully match execution

**Problem**

`workflows.json` declares multi-step pipelines, but execution can still stop at the primary skill.

**Impact**

User-facing tasks such as writing preparation and topic discovery may produce partial artifacts.

**Affected Files**

- `workflows.json`
- `router.json`
- `scripts/personal_kb_steward.py`

**Suggested Fix**

Make `workflows.json` the execution source of truth. Plans should list every declared pipeline step and mark skipped steps with explicit reasons.

**Acceptance Criteria**

- `prepare_writing` plans evidence, gap, and material outputs.
- `discover_topics` plans topic and gap outputs.
- Tests fail if a declared step is silently skipped.

### 5. Duplicate detection has no dedupe workflow

**Problem**

Healthcheck can detect duplicate titles, but there is no safe dedupe plan, merge decision, archive candidate, or approval flow.

**Impact**

The agent can report duplicates but cannot safely resolve them.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `workflows.json`
- `core/review_queue.py`

**Suggested Fix**

Add a read-only dedupe planning workflow that proposes canonical pages and duplicate candidates without deleting, moving, or merging by default.

**Acceptance Criteria**

- Duplicate titles produce dedupe-plan items.
- Each item includes sources and rationale.
- No file is deleted, moved, or rewritten without explicit approval.

### 6. Documentation and configuration references must use repository files

**Problem**

Reports and docs should not cite local-only ignored config as the authoritative repository config.

**Impact**

Future reviewers should be able to reproduce configuration from the tracked template without relying on ignored local files.

**Affected Files**

- `REVIEW_REPORT.md`
- `README.md`
- `AGENTS.md`
- `config.example.json`

**Suggested Fix**

Use repository-stable names and examples:

- repository: `personal-kb-steward`
- tracked config template: `config.example.json`
- local runtime configuration should be described only as an untracked copy derived from `config.example.json`

**Acceptance Criteria**

- Review report references `config.example.json` for tracked configuration.
- Review report does not use the misspelled workspace path.
- Baseline is identified by commit SHA, not only by branch name.

### 7. Tests must run from declared development dependencies

**Problem**

The project has tests, but a fresh environment may not have `pytest`. The current executable safety checks use `unittest`, which does run without additional test dependencies.

**Impact**

Some test commands may fail on a fresh machine if they assume undeclared dependencies.

**Affected Files**

- `requirements.txt`
- `tests/*`

**Suggested Fix**

Either document `unittest` as the supported baseline test command or add development dependency metadata for `pytest`.

**Acceptance Criteria**

- A documented test command runs on a fresh Python environment.
- Safety tests cover apply, rollback, failure recovery, operation log, and dry-run behavior.
