# Claim + Evidence v1

Reconcile now produces explicit assertions with exact evidence fragments. It does
not prove that a quote logically supports a claim. Review both the source context
and the model's proposed `supports`/`contradicts` relation before applying.

## Usage

Use the existing topic command and review flow:

```bash
python scripts/reconcile.py "新闻智能体" --source raw/新增资料.md
python scripts/claims.py wiki/topics/topic-新闻智能体.md
```

`claims.py` also accepts an existing `kb:<UUID>` object ID. It emits JSON and is
strictly read-only: no provider call, revision change or index write. Evidence
status is `matched`, `source_changed`, `unavailable` or `mismatch`. `matched`
means the stored fragment and source version match, **not that a fact is true**.
A changed source is not silently relocated or used to refresh the old evidence.

## Stored data

The owning page's `reconcile_state` is version 2 and contains `claims`. Records
remain in Markdown (inline JSON frontmatter), with no sidecar or database:

- Claim: `claim_id`, `statement`, `kind` (`fact`/`inference`), `confidence`, `evidence`.
- Evidence: `source`, original-byte `source_sha256`, exact `quote`, `quote_sha256`,
  `start`, `end`, `start_line`, `end_line`, `relation` (`supports`/`contradicts`).

IDs are generated from exact statement wording and kind, not supplied by the
model. The identity key is `(owning object_id, claim_id)`: adding supporting
sources preserves a claim ID; rewording or changing kind yields a new one. This
is not semantic entity resolution. The page's existing revision tracks updates.
Run manifests carry the written `claim_ids`; the saved plan and page hash identify
the full records, including evidence versions. Failed retries retain those facts.

The model supplies a verbatim quote and, only if needed, `start_line` to disambiguate
a repeated occurrence. The program calculates offsets and hashes. Offsets are
zero-based Unicode character positions, end-exclusive, after removing an initial
UTF-8 BOM and normalizing CRLF/CR to LF. Line numbers are one-based in that same
full document, **including frontmatter**. Punctuation, case and spaces are not
fuzzily matched. Repeated quotes without an unambiguous location are rejected.

The managed synthesis is rendered from these records, not from a separate
free-form summary. Statement, location and quoted text are visible together;
quoted markup is escaped. Save and apply verify the record, source version,
fragment location and rendered section agree. All writes still require the
existing review gate. Missing evidence, fabricated quotes or reported counter-
evidence yield a non-writing conflict; validated opposing fragments stay in the
conflict plan for inspection. They are not silently resolved by the engine.

## Compatibility and scope

Existing pages and stored version-1 plans remain readable; no bulk migration runs.
An explicit reconcile of a v1 page may propose the evidence upgrade even with
unchanged sources. Subsequent v2 runs with unchanged sources/managed section are
no-ops. Other producers and hand-written page content are not converted to claims.

`fact` is an assertion type, not an approval status. `confidence` is model-assessed,
not a calibrated probability. Exact fragment checks do not detect every semantic
contradiction or establish source independence. Tests stub model responses; actual
provider extraction quality is still unmeasured. Existing provider disclosure and
update-rollback restrictions remain unchanged. This slice adds no graph, database,
automatic stale propagation, batch migration or cross-file transaction system.
