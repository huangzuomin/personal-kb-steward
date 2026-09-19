# Small Obsidian workspace pilot

One Home note, one Base with three views, and a dependency-review snapshot.
No runtime change, automatic installation, Node dependency, REST adapter or plugin.

## Open the pilot

Copy the complete `vault/Steward` directory into a disposable Obsidian vault whose
root contains `wiki/` and `raw/`. Open `Steward/首页.md`, with the built-in Bases
plugin enabled. Do not open the Steward CODE checkout as though it were the vault.
Do not overwrite an existing Steward directory. Real vault installation is not
part of this pilot. Existing notes are not migrated or given new IDs.

The Base is JSON-formatted YAML, so its structure is testable with the standard
library. It uses Obsidian's file.inFolder, file.asLink, comparison, if and date
arithmetic. The table displays formulas rather than editable identity properties.
This reduces accidental edits but is NOT a permission boundary.

Three views: all wiki topic-page notes (including legacy); files modified within
7 days; persistent page review flags. `stage` and `status` are kept separate.
File mtime is local and may change on extraction/sync. The review flag view is NOT
the current review queue: approved/applied pages may retain review_required=true.
It is also NOT the dependency-stale worklist.

## Dependency report

Run in the existing, configured code checkout:

```bash
python scripts/kb_index.py rebuild
python scripts/workspace_report.py
```

The second command calls the existing stale() implementation and prints Markdown.
It never saves, rebuilds, invokes a model, changes note metadata, or queues work.
An absent/broken cache is an error, not a zero-result success. The template report
is deliberately marked not generated. A generated report has index/check times,
coverage warnings, reasons, live-resolvable links, affected claims and upstream
blocking. It is a snapshot, not a live subscription. Do not use a shell redirect
over an existing report: the shell can truncate it before the command succeeds.

For an export, capture successful UTF-8 stdout first and save it as a NEW report
only when explicitly requested. Keep workspace presentation files outside scan
include_dirs (the default wiki/raw/inbox/quicknote do not include Steward).
Do not feed an exported report back into knowledge synthesis as new evidence.

## Outer Agent skill

`skills/steward-workspace/SKILL.md` is a host-neutral optional instruction pack.
Install by the outer Agent's supported skill mechanism, not in the project's
internal `skills/` executor directory. No host-specific install has been tested.
Use the current checkout commands; never let a formatting skill bypass plan/review.

## Validation scope

Automated tests cover links and the limited Base configuration contract, read-only
report projection, upstream blocking, changed/deleted sources, and the real
synthesis → review → apply → rebuild → report chain. Only the external model
response is replaced in the integration test. Tests do not implement another
Bases expression engine or claim to validate Obsidian's UI parser.

Native Obsidian rendering, sorting, clicking, and actual host-Agent skill selection
are not covered by pytest. Confirm them on a disposable vault before calling the
pilot a desktop integration. No real personal vault is touched by these tests.

## References

Syntax and embedding references checked on 2026-09-19:
- https://help.obsidian.md/bases/syntax
- https://help.obsidian.md/bases/functions
- https://help.obsidian.md/bases/create-base
- https://github.com/kepano/obsidian-skills/tree/3ccff5338ea700537839b21900aa5358a0402c98

The templates and bridge here are project-specific original content; the upstream
Skill is not vendored. Optional copying of upstream content must retain its MIT
notice. This pilot does not require installing the full upstream suite.
