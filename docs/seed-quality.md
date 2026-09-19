# Seed quality, cross-batch reuse and auxiliary output paths (#16)

`mindseed-grow` still uses the existing clustering and plan/review/apply runtime.
It does not alter raw/quicknote/inbox or bulk-clean previously generated cards.

## Useful signals, not a summary of a template

Seed signals now extract complete source sentences after ignoring headings,
checkbox routines, separators, bare URLs and fenced code. Substantive ordinary
bullets are allowed. Each excerpt links to its source. This is a deterministic
excerpt filter, not an LLM quality verdict; long unpunctuated paragraphs may
produce no excerpt and need review. Other uses of `note_summary` are unchanged.
The clustering input also uses those excerpts, rather than a diary's boilerplate.
`--no-llm` does not accidentally call a model for seed clustering.

Clustering confidence is stored separately as `cluster_confidence`. It cannot
make an empty seed high-confidence knowledge. Empty/no-substance clusters,
low-confidence grouping, real unresolved links and fewer than
`quality_gate.min_sources_for_seed` (default 2) trigger explicit review reasons.
A single useful thought is allowed as a reviewed seed; the setting is not a ban.
All new seed candidates require review. Ordinary cluster terms are displayed as
keywords, not falsely advertised as pending links.

## Reuse before creating duplicates

Before persisting a seed proposal, search existing seed-card titles in the
configured seed directory. A unique normalized exact title produces an update
proposal retaining the object's ID and increasing revision at the plan boundary.
It appends this round's source-backed candidate material, preserving original
body and custom YAML. Same incorporated source versions result in no new page.
Source/target snapshots remain pinned through save and apply. Initialization no
longer mistakes an existing update target for a create that should be skipped.

Similar titles are review suggestions, NOT permission to merge. Ambiguous exact
titles or occupied targets do not select a winner. Merely sharing a source does
not imply two thoughts are identical. Existing duplicate cards are left alone;
this does not claim to solve general semantic deduplication or rewrite history.

## Keep navigation and logs where the user configured them

Merge the following keys into the existing config; do not replace a private config:

```json
{
  "write": {
    "index_file": "_kb-steward/index.md",
    "index_title": "个人知识工作台",
    "logs_dir": "_kb-steward/logs",
    "log_file": "_kb-steward/log.md",
    "reports_dir": "_kb-steward/reports"
  },
  "quality_gate": {"min_sources_for_seed": 2}
}
```

Without these overrides, `index.md`, `logs/` and `log.md` retain their legacy
locations. Navigation/log files are excluded from both live material selection
and the derived SQLite index. Changing these paths requires `kb_index.py rebuild`.
Invalid or symlink output paths fail before knowledge-page writes. Existing
handwritten indexes/logs are preserved; generated fallback files use `.openclaw`.
Run-log filenames include the execution ID, avoiding same-minute collisions.

## Review is already reachable; a failed batch is not discarded

`init-kb --apply` pauses when a batch requires review, keeping its saved plan
and queue. Inspect with `review show <id>`, approve the appropriate queue items
using `review approve <id>`, then run `review apply-approved`. All items for the
run must be approved. Continue initialization after that batch has succeeded.
There is no new bypass flag and no silent partial approval.

Dry-run writes proposals and audit/queue data but not knowledge pages. Do not
blindly replay a partially failed apply: run records reject such retries and
retain actual writes/backups. Update-containing rollback is still conservatively
refused, not a full restoration system. Inspect the manifest before recovering.
A successful creation-only rollback remains supported by the existing runtime.

The reported real-vault counts and model quality conclusions are observations
from the reporter, not revalidated by synthetic regression tests. These changes
are tested on isolated fixtures; no real model account or private vault is used.
