# Apply Plan and Rollback

Phase 13 upgrades safe landing for the three MVP Skills.

## Flow

```text
scan -> route -> Skill executor -> planned_pages -> apply-plan -> run manifest -> rollback
```

## Commands

```powershell
python scripts\personal_kb_steward.py plan "整理知识库"
python scripts\personal_kb_steward.py apply-plan <plan-path-or-run-id>
python scripts\personal_kb_steward.py rollback <run-id>
```

## MVP Scope

For these Skills, `task --apply` no longer writes directly. It generates a plan and asks the user to run `apply-plan` after review:

- `mindseed-grow`
- `topic-insight-miner`
- `writing-material-pack`

The remaining legacy Skills still use the older direct `--apply` path until they are migrated.

## Safety Rules

`apply-plan` writes only the `planned_pages` already stored in the plan. It refuses to:

- overwrite existing files;
- write outside the knowledge base root;
- write into protected directories such as `raw/`, `quicknote/`, and `inbox/`;
- write content whose hash no longer matches the plan.

Each successful apply writes:

```text
.openclaw/runs/<run_id>.json
```

`rollback` deletes only files listed in that manifest and only when the current file hash still matches the applied hash.
