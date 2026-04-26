# Dynamic Topic Clustering

Phase 11 removes the fixed `THEME_RULES` path from `mindseed-grow`.

## What Changed

Before this phase, seed creation depended on hard-coded topic buckets such as media, AI workflow, or knowledge management. That made the agent brittle outside the author’s own vault.

Now `mindseed-grow` clusters the current eligible inputs dynamically:

```text
changed quicknote/inbox/allowed raw
-> extract local terms from title and body
-> choose 3-5 cluster anchors from this run
-> generate seed-card candidates
-> low-confidence clusters go to manual_review
```

## Product Boundary

Dynamic clustering still follows the existing safety model:

- `raw/` long files are not pulled into `mindseed-grow` by default.
- Low-confidence single-source clusters become `status: manual_review`.
- The output is still only `seed-card`; it does not create formal topic pages.
- Sources must remain concrete file paths.

## Config

```json
{
  "clustering": {
    "mode": "dynamic",
    "max_clusters": 5,
    "min_sources_for_confident_cluster": 2,
    "allow_fixed_theme_rules": false
  }
}
```

## Next Step

The deterministic local clusterer is intentionally lightweight. In the next MVP Skill rewrite, `mindseed-grow` can use the LLM Skill Runtime to produce richer cluster labels while keeping the same JSON validation and safety checks.
