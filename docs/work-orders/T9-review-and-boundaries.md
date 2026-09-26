# Astra review — T9 probe ownership and remaining native boundaries

Resume T9 session after its checkpoint report completes. Preserve M0 files. Same data/permission boundary as original work order; no original vaults, credentials, installs, commits, API calls or permission bypass.

## Required correctness fixes

1. `_write_probe` currently uses write_text, so a pre-existing file (or planted reparse target) with the computed probe name is truncated and later deleted. A unique-looking name does not establish ownership. Create exclusively, fail safely on collision, never modify/delete an unowned probe. Correctly handle a partial write failure of a probe this attempt did create; preserve original failure plus any cleanup failure. Add collision/sentinel-byte preservation and real successful create-cleanup tests. Current counter tests mock away actual probe creation, so they do not prove ownership.
2. `check_existing_target` uses open('ab'), which can create a missing update target if it disappears between exists() and open(). Use a non-creating writability check for required existing update targets (e.g. r+b without writes), and fail if gone. Add missing/race simulation demonstrating no new file and no byte change. Preserve Windows read-only rejection.

## Complete bounded remaining T9 evidence

Add tests/test_windows_write_boundaries.py for actual native junction aliases into raw/protected paths and outside the test vault, including not-yet-existing targets. Inspect command_apply_plan real path behavior; if a real guard gap is exposed, make the smallest guard fix under owned core/output_paths.py/core/safety.py and CLI preflight adapter (or a small helper). Do not remove resolved containment. Record symlink privilege absence as unverified, no skipped-as-pass claims.

No full refactor. Keep script <=1700 lines, preserve existing review/hash/manifest handling. Tests use only temporary synthetic paths; no cross-shell recursive deletion. Save logs as actual files (Write tool can persist captured output if shell redirect is denied), exact commands and exit codes. Baseline logs named in reports must exist; mark unavailable old raw logs honestly rather than claim they are saved.

Run new ownership/probe and native tests plus affected existing apply/run/platform/producer/object tests. Process UTF8 env inherited. Deliver report.md/report.json with changed files, actual commands/results, native passed vs skipped, and any remaining requirements. Do not claim original private demo/system acceptance. Stop for Astra review.
