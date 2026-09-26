# M2 final card readability (presentation only)

Root independently verified the canonical statement fixes: 142 passed, both root probes now exclude invented display text. Core engineering accepted pending this small presentation handoff; no further contract/semantic changes in this task.

Own concept/case templates and their view-context formatting only, relevant narrow render assertions and refreshed M2 mock samples/report. Do not alter core.claims, canonical candidates/schemas, identity, inputs, or other agents' files. Same public-only/no-live-call constraints.

Actual card bodies currently expose long `claim:<64 hex>` identifiers and headings like `可复用机制（权威文字 = 所引判断原文）`. Those are implementation details, and a compiled model judgment is not literally original source wording. Keep machine IDs fully in card_state, but use human-readable ordinal references in visible body (e.g. `证据 1、证据 3`, mapped from the existing claims render order). Existing evidence section already carries source paths and exact original quote lines; preserve it. Replace engineering headings with plain 概念定义 / 来源中的边界 / 可复用机制 / 适用条件. Keep interpretation, source assertion and unverified-data labels explicit.

No redesign or new evidence renderer. A small context mapping claim_id -> ordinal and template formatting is enough. Avoid confusing generic disclaimer '也不代表特定人物的自报' when provenance actually is a self-report: state that evidence level follows the source map and remains unverified, without overriding the actual provenance.

Add one or two actual-render checks that the parsed Markdown BODY has no opaque claim identifiers/engineering headings, while frontmatter card_state IDs and reload validation remain intact. Re-run own concept/case tests only; regenerate existing samples and report exact results, no broad suite. Stop after handoff.
