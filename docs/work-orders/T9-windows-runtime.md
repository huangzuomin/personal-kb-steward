# T9 — Windows write boundaries and per-apply probes

Owner: Claude CLI runtime coding agent; Astra reviews and accepts. Baseline 4d95bc8, feat-demo-baseline. You share the checkout with M0 agent. Do not revert others or edit their owned files. Implement this bounded task, not the whole project.

## Boundaries

Read AGENTS.md here. Stay inside this checkout. No parent/private vaults, no .env/config.json/credentials/global settings, no network or model APIs. Public code and synthetic temporary vaults only. Original/legacy cards are out of scope. Keep normal CLI permissions; no bypass, no setting changes, no install, no commits/push, no subagents. Run pytest offline using provided Python and existing PYTEST_DEBUG_TEMPROOT; do not clean temp directories. Never run actual app --apply against a live configuration. File operations stay in test-owned resolved paths.

## Exclusive allowed files

- core/output_paths.py, core/safety.py; new core/apply_preflight.py if helpful.
- scripts/personal_kb_steward.py ONLY preflight_apply_pages and necessary imports/thin adapter, preserve <=1700 line limit. The M0 agent does not own this script; future integration worker will take it after you finish.
- tests/test_preflight_probe_policy.py (new), tests/test_windows_write_boundaries.py (new); minimally adjust existing Windows tests only with documented rationale, never weaken guard expectations.
- docs/iteration-evidence/T9/*, docs/windows-write-boundaries.md (new).
- Do NOT edit core/config.py, public config example, contracts/schemas, card generators, ledger or work orders. If extra scope is necessary report it.

## Starting evidence

Run relevant original tests before modifications: tests/test_platform_paths.py, tests/test_producer_recovery.py native junction case, tests/test_seed_quality_outputs.py::test_configured_auxiliary_directory_symlink_is_rejected_before_apply. This last test was historically failing on native Windows; capture actual baseline and diagnose. Missing privilege skip is unverified, not pass.

## Target behavior

1. Validate native Windows symlink/junction aliases to raw/protected directories, outside-vault targets and not-yet-existing target files. No target, auxiliary output, state or processed mutation on rejected preflight. Retain resolved containment and protected-path semantics; do not replace everything by is_symlink alone. Only alter guards in response to demonstrated gaps/false negatives; preserve valid native paths/case behavior.
2. Current preflight in scripts/personal_kb_steward.py probes each page with create+delete. Within one apply, probe each actual parent directory once, refresh on every new apply. No global cache, no historical exists=>writable shortcut. Standard default: unique owned probe, write, cleanup once per directory. Do not bypass deletion guards. If cleanup denied, return accurate preflight/recovery diagnostics, not false success. Avoid adding speculative host modes unless necessary and explain.
3. Existing-file updates still check their write conditions; parent-only create checks must not silently approve read-only targets. Partial apply/recovery logic and run scoping preserved. Report exception cause and counts where relevant through existing mechanisms, without logging sensitive content.
4. CLI thin adapter delegates added logic to core as needed. No generic refactor or full permission framework.

## Acceptance and report

- At least 100 new pages in one parent => one probe within an apply; two parents => two; second apply probes again; simulated permission change caught; occupied/update targets tested.
- Real native junction tests including raw and outside-vault alias. If symlink creation unavailable, explicitly distinguish junction evidence and symlink unverified. Use temporary synthetic vaults under this task's temp root.
- Run targeted new tests plus relevant test_apply_plan.py/test_run_recovery.py/test_platform_paths.py/test_producer_recovery.py and historical failing seed path test. Do not run entire suite or model-calling tests.
- Preserve command output, exit codes and baseline-vs-after evidence in docs/iteration-evidence/T9. Report changed files and any shared-script adapter modifications for later integrator.
- report.md and report.json: status, changed_files, tests, native_platform_evidence, skips, pending, permission_denials. done is handoff to Astra, not acceptance.
