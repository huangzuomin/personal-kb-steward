# MVP Skill Executors

Phase 12 moves the first three product-critical Skills from script-embedded string builders into their own Skill directories.

## Scope

Only these Skills were rewritten:

- `skills/mindseed-grow/`
- `skills/topic-insight-miner/`
- `skills/writing-material-pack/`

The other eight Skills remain on the legacy runtime until later phases.

## File Contract

Each MVP Skill now owns:

```text
SKILL.md
schema.json
renderer.py
executor.py
```

The executor returns page specs instead of writing files directly:

```json
{
  "skill": "mindseed-grow",
  "pages": [
    {
      "rel_dir_key": "seed_dir",
      "filename": "seed-example.md",
      "content": "...",
      "sources": ["quicknote/example.md"]
    }
  ],
  "inputs": ["quicknote/example.md"],
  "issues": []
}
```

The main runtime still owns:

- path resolution;
- protected directory policy;
- `dry-run` / `--apply`;
- unique file names;
- Markdown validation;
- logs, reports, state, processed index.

This keeps Skill logic modular without letting Skills bypass the safety model.

## Current Behavior

- `mindseed-grow`: uses dynamic clustering and creates only seed-card outputs.
- `topic-insight-miner`: creates only topic-card outputs, never formal topic pages.
- `writing-material-pack`: creates material-pack outputs and does not write formal articles.

## Next Step

Phase 13 can make these executor outputs flow through plan preview / apply-plan / rollback, instead of direct `--apply` execution.
