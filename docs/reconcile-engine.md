# Reconcile Engine

Reconcile adds a source-grounded synthesis to one topic, rather than making a new
numbered page for every run. The engine returns `create`, `update`, `conflict` or
`noop` and reuses the existing stable-object plan, review, apply and audit paths.
It is an internal command under knowledge organization, not a sixth public entry.

## Use

Configure the existing LLM provider and vault as usual. This command sends the
selected sources **and the existing target page / its previous sources** to that
provider, but never writes a knowledge page directly:

```bash
python scripts/reconcile.py "新闻智能体" --source raw/新增资料.md
python scripts/reconcile.py "新闻智能体" --target wiki/topics/新闻智能体.md --source raw/新增资料.md
```

`--source` can be repeated. `--target` accepts either a concrete existing path or
an existing `kb:<UUID>` object ID. Paths are vault-relative Markdown files within
the configured scan scope. Raw material is read only. A missing explicit target
is a conflict, not permission to create a different page.

Without `--target`, normalized exact title matching chooses an existing knowledge
page. Multiple matches require an explicit target. No semantic/fuzzy merging is
performed. New files use a deterministic path in `write.topics_dir`; an occupied
path is a conflict, never a reason to add `-2` or a timestamp.

The command prints the decision, saved plan, and unified diff (including the
bound object ID/revision). Both create and update always enter the existing review
queue. Read the **full proposed diff**, then use:

```bash
python scripts/personal_kb_steward.py review list
python scripts/personal_kb_steward.py review show <ID>
python scripts/personal_kb_steward.py review approve <ID> --reason "已核对来源与修改"
python scripts/personal_kb_steward.py review apply-approved
```

`apply-approved` is the existing queue-wide operation: it applies all eligible
approved runs, not just the most recent reconcile. Review the pending queue first.
Conflicts have no executable pages; approving a conflict ticket cannot turn it into
an update. Resolve the reason, reject the obsolete ticket, and generate a new plan.
Exit codes: 0 proposal/noop, 2 conflict report, 1 provider/IO/validation error.

## What changes

A bounded section is appended on first adoption and replaced on later updates:

```markdown
<!-- kb-steward:reconcile:start -->
## 资料综合

综合内容及 [[raw/新增资料.md]] 来源标注。
<!-- kb-steward:reconcile:end -->
```

Existing handwriting and custom YAML are not rendered again. Only `sources`,
`updated`, and `reconcile_state` are owned by reconcile; the existing plan boundary
owns `object_id` and `revision`. It preserves the file's BOM and line endings.
Existing manual text is not automatically made consistent with the generated
section. A conflict requiring edits to that text must be handled by a human.

`reconcile_state` records the input source hashes and exact managed-section hash
in Markdown, so no second index is needed. Unchanged sources plus an unchanged
section produce noop before calling the model: no new file, plan, queue entry,
revision or processed marker. Manually changed managed sections produce conflict,
not overwrite. To relinquish an edited section to a new synthesis, preserve its
content as handwritten text and remove **both boundary comments and the entire
reconcile_state field**, then regenerate and review the new section.

The model reads all earlier sources plus the supplied sources. Sources cannot be
silently dropped. Complete input is bounded by `reconcile.max_context_chars`
(default 60000, optional config key); exceeding it yields a conflict asking for
source notes or a smaller topic, rather than silently truncating evidence.

## Safety and limits

- Source hashes are verified when saving **and** applying. A changed/deleted
  source requires a new proposal, even when the target itself is unchanged.
- Target baseline comes from the exact snapshot sent to the model. The existing
  ID/revision/hash guard rejects later edits, including the first-save window.
- Successful/partial run manifests and backups retain the existing replay guard.
  Pure create rollback works as before; update or mixed rollback stays refused.
- The model can report conflicts or noop. Invalid decisions, missing citations and
  invalid source references yield non-writing conflict reports. Path/citation checks are
  not proof of factual accuracy; the human must verify what each source supports.
- No graph database, fuzzy entity resolution, background scheduling, cross-file
  transactions or new UI are introduced.
- Tests stub external model responses, not the plan/review/apply machinery. They
  establish engineering behavior, not synthesis quality on real personal data.

## Claim + Evidence extension

New proposals use reconcile version 2 and require structured claims with exact
source quotes, rather than free-form summaries with page-level links. The managed
section displays each assertion and its evidence; machine records live in
`reconcile_state.claims`. Existing version-1 pages/plans remain compatible. See
[Claim + Evidence v1](claim-evidence.md) for matching rules and read-only inspection.
