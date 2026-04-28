# Review Report

Baseline branch: `review/baseline`

Scope: architecture and safety review for the knowledge-base management agent. This report does not include business-code changes.

## P0

### 1. Raw long-form ingestion chain is broken

**Issue**

`topic-research-compile` returns a `created` list whose page objects use `target`, `content`, and `manual_review`. The main runtime applies executor output through `apply_executor_pages()`, which only reads `result["pages"]` and expects each page to contain `rel_dir_key`, `filename`, `content`, and `sources`.

**Impact**

Raw research reports can be classified as `research_report` but fail to become source notes or topic stubs. Manual-review items for these generated pages are also not queued, and processed-index inputs are not reliably recorded. The ingestion -> source note -> topic stub path is therefore not dependable for real knowledge-base work.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `skills/topic-research-compile/executor.py`
- `skills/topic-research-compile/renderer.py`

**Suggested Fix**

Define one executor output contract and make all skills return it:

- `pages[].rel_dir_key`
- `pages[].filename`
- `pages[].content`
- `pages[].sources`
- `pages[].item`
- optional `pages[].manual_review`

Then update `topic-research-compile` to return `pages` rather than `created`, or add a strict adapter that validates and converts legacy skill output before apply.

**Acceptance Criteria**

- A raw markdown report classified as `research_report` produces at least one `wiki/sources/` source note and one `wiki/topics/` topic stub in dry-run plan.
- Applying the plan writes those pages to the expected directories.
- Generated pages include concrete `sources` pointing to the original raw file.
- Any generated page marked for manual review creates a queue item.
- A regression test fails if a skill returns page objects without the required fields.

## P1

### 2. `apply-plan` bypasses manual-review requirements

**Issue**

Plans include `review_required` and `confidence`, but `command_apply_plan()` only validates path safety, target existence, and content hash. It does not block low-confidence or review-required pages.

**Impact**

Content explicitly marked as uncertain can be written into the knowledge base without user approval. This violates the project safety model and can pollute the knowledge base with unverified conclusions.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `core/review_queue.py`

**Suggested Fix**

Make manual review a hard gate in `apply-plan`:

- Reject pages with `review_required: true` by default.
- Reject pages with `confidence: low` unless an approved review item is attached.
- Bind approval to `run_id`, page path, and content hash.
- Show a clear CLI message explaining which review item must be approved.

**Acceptance Criteria**

- A plan containing a `review_required: true` page is rejected by `apply-plan`.
- The same plan applies only after the related review item is approved.
- Changing the page content after approval invalidates the approval.
- Tests cover approved, unapproved, and tampered-plan cases.

### 3. Manual-review pages are marked as processed

**Issue**

`update_processed_index()` marks all operation inputs as processed whenever they appear in `op.inputs`, regardless of whether generated outputs are `manual_review`, low confidence, rejected, or failed.

**Impact**

Sources that only produced unapproved review pages can be skipped in future runs. This creates data-loss-by-omission: the source remains in the vault but no longer flows through the ingestion or organization pipeline.

**Affected Files**

- `core/state.py`
- `scripts/personal_kb_steward.py`

**Suggested Fix**

Extend processed-index state beyond a boolean processed marker. Suggested statuses:

- `planned`
- `pending_review`
- `applied`
- `rejected`
- `failed`
- `superseded`

Only `applied` outputs should make a source count as processed for a skill.

**Acceptance Criteria**

- A source that generates only manual-review pages remains eligible for processing until approval and successful apply.
- Approved and applied pages mark their sources as `applied`.
- Rejected pages mark their source as `rejected` or leave it eligible according to an explicit policy.
- Processed-index records include output paths, output hashes, review status, and skill name.

### 4. Root `index.md` is overwritten without confirmation

**Issue**

`update_index()` writes directly to the knowledge-base root `index.md` on each apply. It also creates directory README files automatically.

**Impact**

If the user maintains their own Obsidian or markdown homepage, a run can overwrite it. This is a direct knowledge-base data safety risk.

**Affected Files**

- `core/index_builder.py`
- `scripts/personal_kb_steward.py`

**Suggested Fix**

Move generated indexes into a system-controlled path such as `wiki/_system/index.md` or `outputs/kb-index.md`. If root `index.md` must be managed, require:

- opt-in config
- existing-file hash check
- backup before write
- rollback support

**Acceptance Criteria**

- Running `apply-plan` does not overwrite an existing user-authored root `index.md` by default.
- Generated index content appears in a system-owned path.
- If opt-in root index writing is enabled, the old file is backed up and included in rollback metadata.
- Tests cover pre-existing `index.md` preservation.

### 5. Templates generate invalid or inconsistent frontmatter

**Issue**

`source_note.j2` and `topic_stub.j2` include `base_frontmatter.j2` and then write a second YAML frontmatter block. The second block also omits fields required by `AGENTS.md`, such as `updated`, `related`, and `review_required`.

**Impact**

Generated markdown can contain ambiguous metadata. Indexing, health checks, source validation, and status transitions may read the wrong metadata or fail to detect missing fields.

**Affected Files**

- `core/templates/base_frontmatter.j2`
- `core/templates/source_note.j2`
- `core/templates/topic_stub.j2`
- `core/jinja_renderer.py`

**Suggested Fix**

Use a single frontmatter generator for all templates. Templates should receive normalized metadata and render exactly one YAML block.

**Acceptance Criteria**

- Rendered source notes and topic stubs contain exactly one frontmatter block.
- Rendered pages include all required fields from `config.knowledge_model.required_frontmatter`.
- Healthcheck reports no missing metadata for newly generated pages.
- Template rendering tests parse frontmatter and validate required fields.

### 6. Rollback is not complete

**Issue**

Rollback deletes files listed in the run manifest, but it does not restore changes to `log.md`, `index.md`, processed index, state files, review queue, or directory README files.

**Impact**

A failed or bad apply can leave the project in an inconsistent state even after rollback. The content files may be removed, while runtime state still says they were processed or applied.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `core/state.py`
- `core/log_manager.py`
- `core/index_builder.py`
- `core/review_queue.py`

**Suggested Fix**

Make apply transactional enough for recovery:

- Record every file written by apply.
- Store pre-write hashes and, where practical, pre-write content snapshots.
- Include state, log, processed-index, review queue, and generated index writes in the manifest.
- Roll back state files as well as content pages.

**Acceptance Criteria**

- After applying and rolling back a plan, the knowledge-base tree and runtime state match the pre-apply snapshot.
- Rollback skips files whose hash changed after apply and reports them clearly.
- Tests cover rollback of generated pages, state file, processed index, and log file.

## P2

### 7. Workflow declarations do not match execution

**Issue**

`workflows.json` declares multi-step pipelines such as `topic-insight-miner + knowledge-gap-finder` and `writing-evidence-harvester + knowledge-gap-finder + writing-material-pack`. The runtime often executes only the primary skill.

**Impact**

User-facing entries promise a closed workflow, but actual execution can stop after one partial artifact. This makes "discover topics" and "prepare writing" incomplete for real tasks.

**Affected Files**

- `workflows.json`
- `router.json`
- `scripts/personal_kb_steward.py`

**Suggested Fix**

Make `workflows.json` the execution source of truth. Dry-run plans should list every pipeline step, expected inputs, expected outputs, and blocking conditions. Apply should execute each step or explicitly mark it skipped with a reason.

**Acceptance Criteria**

- `prepare_writing` produces or plans evidence, gap, and material outputs.
- `discover_topics` produces or plans both topic and gap outputs.
- CLI output shows declared and executed pipeline steps.
- Tests fail if a workflow declares multiple steps but the plan executes only one without a skip reason.

### 8. Duplicate detection has no dedupe workflow

**Issue**

Healthcheck detects duplicate titles, but there is no workflow for dedupe planning, merge decisions, archive candidates, or user approval.

**Impact**

The agent can identify duplicate-like structures but cannot complete the knowledge-base management task of resolving them safely.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `workflows.json`
- `core/review_queue.py`

**Suggested Fix**

Add a dedupe planning workflow that only proposes actions:

- canonical page candidate
- duplicate candidates
- evidence for similarity
- suggested merge or archive action
- risk level
- required review approval

Do not automatically delete, move, or merge content in the first implementation.

**Acceptance Criteria**

- Duplicate titles produce dedupe-plan items.
- Dedupe-plan items include sources and rationale.
- No file is deleted, moved, or rewritten without explicit approval.
- Approved dedupe actions are tracked in run manifest and can be rolled back.

### 9. Archive lifecycle is not implemented

**Issue**

The status model includes `archived`, and config has `archive` as an excluded directory, but there is no clear archive workflow or safe state transition.

**Impact**

Stale, orphaned, or superseded notes can accumulate. The system reports clutter but cannot safely reduce it.

**Affected Files**

- `config.json`
- `workflows.json`
- `scripts/personal_kb_steward.py`
- `AGENTS.md`

**Suggested Fix**

Introduce an archive-plan workflow that marks candidates first. It should avoid moving files in the initial iteration unless rollback and approval are fully implemented.

**Acceptance Criteria**

- Healthcheck can produce archive candidates with reason codes.
- Archive candidates require approval before any state or path change.
- Archived status changes preserve original source paths and backlinks.
- No protected directory content is moved or rewritten.

### 10. Documentation and configuration paths are inconsistent

**Issue**

The current repo path is `workspace-personal-stewad`, `README.md` uses `workspace-personal-steward`, `AGENTS.md` references `workspace-agent-f731ab99`, and config resolves the knowledge base through `${AGENT_HOME}\\..\\workspace\\wiki`.

**Impact**

Users can configure or run the agent against the wrong workspace or knowledge base. This is especially risky when multiple agents or vaults exist.

**Affected Files**

- `README.md`
- `AGENTS.md`
- `config.json`
- `config.example.json`
- `core/config.py`

**Suggested Fix**

Normalize path terminology:

- `agent_home`
- `kb_root`
- `state_home`

Use those names consistently in docs and config. Avoid hidden parent-directory assumptions in examples.

**Acceptance Criteria**

- README, AGENTS, config, and config example reference the same workspace model.
- `validate_config.py` reports the resolved agent home, state home, and knowledge-base root.
- A test config can point to a temporary knowledge base without relying on `..\\workspace\\wiki`.

### 11. Error handling is string-based and hard to act on

**Issue**

Most failures are stored as free-form strings in `issues`. There is no stable error code, retryability marker, source component, or recommended action.

**Impact**

CLI output, reports, review queue, and tests cannot reliably distinguish provider errors, validation errors, source-quality problems, and permission risks.

**Affected Files**

- `scripts/personal_kb_steward.py`
- `core/validator.py`
- `core/review_queue.py`
- `skills/*/executor.py`

**Suggested Fix**

Define a structured issue object:

- `code`
- `severity`
- `component`
- `message`
- `source`
- `retryable`
- `recommended_action`

Use this structure in executors, healthcheck, reports, and review queue.

**Acceptance Criteria**

- New executor issues are emitted as structured objects.
- CLI and reports render structured issues into readable text.
- Tests can assert issue codes instead of matching free-form strings.
- Existing string issues are either migrated or normalized at runtime.

### 12. Tests cannot run from declared dependencies

**Issue**

The repository contains tests, but the current `requirements.txt` only declares `jinja2>=3.0.0`. Running `python -m pytest -q` fails when pytest is not already installed.

**Impact**

The review baseline cannot be verified consistently on a fresh machine. Safety regressions can go unnoticed.

**Affected Files**

- `requirements.txt`
- `tests/*`
- project packaging configuration, if added later

**Suggested Fix**

Add a development dependency path such as `requirements-dev.txt` or `pyproject.toml` with pytest. Keep runtime dependencies separate from test dependencies.

**Acceptance Criteria**

- A documented install command installs test dependencies.
- `python -m pytest -q` runs on a fresh environment.
- Tests include acceptance coverage for ingestion, duplicate detection, apply-plan safety, empty directories, and rollback.
