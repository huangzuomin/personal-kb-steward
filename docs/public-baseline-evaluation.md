# Public baseline evaluation — adapter and runner (T10 C3)

Status: **adapter and offline runner checkpoint complete, revised after root
review.** The runner executes the accepted production plan/save/review/apply
path in an isolated synthetic vault. The coding session uses smoke mode only;
the root operator owns any later live run after the production freeze and
Claude quota are available.

## Runner invocation

Use a fresh output directory for every run. Smoke mode lazily loads the
test-only offline provider and never starts a native model process:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
& 'C:\Users\zooma\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe' `
  scripts/evaluate_public_baseline.py --smoke --rounds 1 `
  --output-dir .execution/<fresh-run>
```

The full round expects source ×4, seed ×1, concept ×1, case ×1, and topic
×1, and records the observed split in `metrics.json`. `--intake-only` is an
explicit five-call checkpoint (source ×4 and seed ×1); it does not claim a
full baseline. The runner enforces the adapter hard bounds of 10 calls per
round and 30 calls total, including failed or timed-out attempts.

The artifact root must not already exist and contains a marked synthetic
vault. Output counts come only from normal applied run manifests whose
reconcile result, content hash, typed frontmatter, object identity, revision,
and current bytes agree. README files, backups, missing proof, replacement
characters, failed applies, and writes without an apply manifest do not count.
Raw prompt, payload, response, and error records remain under the artifact
root for each observed attempt.

## Actual invocation contract

Unattended print-mode invocation against the native CLI
(npm-shim-confirmed path
`C:/Users/zooma/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe`,
CLI 2.1.278, help verified by Astra):

```
claude.exe -p --restricted --tools "" --strict-mcp-config \
    --disable-slash-commands --no-session-persistence \
    --output-format json --model <model> --effort <effort> \
    --system-prompt <exact generator system prompt>   # payload via stdin
```

- `-p`/`--print` is REQUIRED: provider calls are unattended and must never
  launch interactive mode.
- `--restricted` removes code-running tools and WebFetch and ignores
  user/project/local settings (managed settings and `--settings` still
  apply), composed with `--tools ""` and `--strict-mcp-config`. This gives
  the intended no-project/no-user-settings execution without `--bare`'s
  documented OAuth breakage. No `--settings` or `--add-dir` is used.
  `--setting-sources` is listed in installed help but redundant under
  restricted mode, so it is not sent.
- argv list with `shell=False`; content never crosses a shell — the JSON
  user payload goes via stdin, the exact generator system prompt via
  `--system-prompt`.
- The model process runs in a freshly created empty temp directory outside
  the checkout/private-vault ancestry, so repository `CLAUDE.md`/
  `AGENTS.md`/prompt files cannot auto-load. No resume, no session
  inheritance, no credential access or auth change by the harness.

## Provider seam

`adapter.bind_for_round(n)` returns a callable compatible with BOTH
generator shapes:

- `(cfg, system_prompt, payload)` — production generators passing the
  production cfg dict
- `(system_prompt, payload)` — two-arg generators

The cfg argument is accepted for call-shape compatibility but its values
are IGNORED: the adapter always uses its frozen construction-time
`AdapterConfig`; a generator cfg never overrides model, bounds, timeout or
liveness. Round selection is EXPLICIT via `bind_for_round` (also visible
as `round` in every evidence record) — there is no implicit round 0.

## Exact payload preservation

`PublicContextBundle.register_payload(payload, built_from=[...])`
registers the generator's OWN payload argument — dict, list or plain
string. Real shapes supported and tested:

- source stage: chunk dict `{"text": header + chunk_text}`
  (topic-research-compile chunk calls)
- seed stage: `{"task": "atomic_seed", "coverage_note": ..., "units":
  [...]}` (core.atomic_seed)
- concept/case stage: `{"task": ..., "documents": [...], "known_paths":
  [...], "upstream_source_analysis": [...], "output_contract": {...}}`
- topic stage: `{"task": "question_led_topic_synthesis", "question": ...,
  "documents": [...], ...}`

Serialization canonicalizes key order only (`sort_keys=True`); deep JSON
equality with the generator argument is preserved and NO wrapper or extra
document fields are added — tests assert stdin bytes deserialize
deep-equal to the generator argument for all five shapes. Prompt-equivalence
evaluation therefore sees exactly what the generator would send.

Provenance: `register_fixture` / `register_generated` pin the PUBLIC
source documents (exact manifest snapshots; intermediates whose bytes hash
to a supplied sha256) that the run harness built payloads from; their
hashes travel in evidence as accounting.

**Trusted-caller boundary (stated honestly):** hash/provenance
registration is accounting, not proof that a free string inside a payload
is public. The run harness is trusted to construct payloads from
allowlisted fixtures and registered public intermediates; the bundle
verifies registered documents byte-for-byte and blocks manifest annotation
keys anywhere in the payload, but cannot cryptographically prove the
provenance of a free string. (Annotation VALUES are deliberately not
string-blocked: legitimate fixture-derived content overlaps annotation
strings — e.g. the seed payload's speaker is a manifest
`expected_speaker_marker`.)

## Trust boundary and annotations

The adapter and runner provide execution, schema, provenance, and byte-level
evidence only; they perform no semantic quality judgment. Passing these checks
does not imply a semantic pass, and three valid public rounds cannot prove
private-demo equality. `semantic_pass` remains `null` until Astra's content
review.

`tests/fixtures/card-baseline/manifest.json` is the only fixture source:
entries must be `synthetic: true`, paths must stay under the fixture dir,
bytes are sha256-pinned at load. `expected_units`,
`expected_speaker_markers`, `prohibited_overclaims` and `topic_groups` are
reviewer-only: annotation KEYS are refused at ANY nesting depth of a
registered payload (`_check_no_annotations`); reviewer code reads them via
`fixture_annotation(id)`. The adapter accepts only run-registered
`PublicPayload` objects — no arbitrary `--input`, no path-based input.

## Budget

Every subprocess attempt — including failures and timeouts (and
`is_error`/nonzero exits) — consumes budget, checked and refused BEFORE
the attempt. Hard bounds: ≤30 calls total, ≤10 per round; configuration
above the bounds is rejected. Config typing is strict: `enabled` must be
an explicit JSON boolean (the string `"true"`/`"false"` is an error, never
truthy coercion); call counts and timeout must be positive integers
(`"30"`, `0`, `true` all rejected); `executable` must be a non-empty argv
list, never a shell string.

## Result handling

The adapter returns the EXACT `result` string from the envelope. The
result must be an actual JSON string — `null`, objects, arrays and numbers
are rejected as explicit errors with raw stdout preserved in the attempt
directory; no `str()` coercion, no repair. `is_error`, nonzero exit,
missing `result` and non-JSON stdout likewise become explicit
`PublicEvaluationError`s. No invisible retry or fallback.

## Evidence

Each run writes under `<artifact-root>/<run-id>/` (existing run
directories refused; attempt files are never overwritten; all writes
path-checked under the artifact root):

- `evidence.jsonl` — per attempt: run, round, index, model, effort,
  system/user payload sha256, source provenance hashes, duration, usage,
  return code, timeout, result text + sha256, failure, logged argv
  (system prompt elided), cwd policy.
- `attempts/roundNN/attemptNNN/system_prompt.txt`, `user_payload.json`
  (exact generator JSON, canonicalized), `stdout.raw.txt`,
  `stderr.raw.txt`.

## Testing

`tests/test_public_evaluation_harness.py` — 46 offline tests; `subprocess`
is patched everywhere (no real CLI/network). Coverage: print flag +
`--restricted` + tools-disabled + strict-MCP + no-resume + native
shell=False + isolated cwd; both generator call shapes; ignored cfg
values; budget at/beyond boundaries with failure/timeout/is_error
accounting and refusal-before-launch; strict config typing; explicit-bool
live flag; non-string result rejection with preserved raw evidence;
deep-JSON-equality for all five real payload shapes; annotation keys
blocked at any depth; fixture corruption/escape/nonsynthetic rejection;
run/attempt overwrite refusal; no private-path opens.

Runner-specific focused checks live in
`tests/test_public_baseline_runner_c2.py` and
`tests/test_public_baseline_runner_c3.py`; they cover the actual smoke
plan/save/review/apply path, live fake subprocess accounting, manifest-backed
outputs, failure history, stage splits, bounds, and artifact confinement.

## Current checkpoint evidence

The C3 runner report is
`docs/iteration-evidence/T10/runner-C3.md` with machine-readable details in
`runner-C3.json`. It records the focused runner tests, a fresh one-round smoke
artifact, the complete version freeze, manifest-backed card counts, source
byte hashes, and artifact confinement. Root retains responsibility for the
final three-round live evaluation and semantic review.
