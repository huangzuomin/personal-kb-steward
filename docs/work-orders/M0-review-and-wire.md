# Astra review — M0 checkpoint correction and producer wiring

Resume same Claude M0 coding session. Normal permissions/data boundaries/ownership from M0 remain. This is a bounded implementation task, no more broad discovery. Runtime/preflight script belongs to T9; do not edit it.

## Mandatory reviewer correction before wiring

1. core/card_contracts.py::_validator_for currently maps EVERY registered schema ID to Resource.from_contents(the schema being validated). A seed $ref inside an envelope therefore resolves back to the envelope, not the canonical seed schema. Astra reproduced an invalid seed `{type:'source-note'}` being accepted through `{'type':'object','properties':{'seed':{'$ref':'seed-card.schema.json'}}}`. Evidence: docs/iteration-evidence/astra-schema-ref-repro.log. Build each registry resource from its corresponding registered schema. Add positive and negative cross-schema/local-envelope reference tests, not merely scalar validation.
2. Remove speculative old-jsonschema RefResolver fallback, whose handler for empty scheme does not reliably block HTTP/HTTPS/file fetch. Require jsonschema>=4.18 (Draft202012Validator + referencing). Unknown refs fail without network; patch network retrieval in test to assert no call. Validate registered schemas themselves. Do not silently accept missing schema for an enrolled skill.
3. Original source hashes are hashes of ORIGINAL BYTES; core.claims.digest hashes text/quotes and is NOT a substitute for raw source snapshot hash. Correct checkpoint.md wording. If a producer lacks a full-source hash, record unknown instead of inventing one from cleaned body. Future M1 source extraction will provide exact snapshots.

## Then implement next M0 bounded wiring slice

- Per-skill envelope JSON schemas reference canonical type schemas locally (mindseed-grow existing, topic-research-compile new).
- Hook typed validation before rendering into existing source/seed executor+renderer paths AND generic skill runtime for managed types. Do not validate pages/created envelopes as card items. Preserve unrelated skills. Invalid model item must produce no rendered page or processed advancement; add integration tests demonstrating the call order.
- Inject program-owned schema_version/generator_version/analysis_mode/source_hashes/coverage (unknown if unavailable) before validation; preserve them and quality_flags into generated frontmatter/page metadata. In base_frontmatter use conditional fields so unrelated old templates continue to work.
- Source adapter documented in checkpoint: summary/key_statements/topic_hints derived from existing source_summary/key_facts/topics. Use new growing/compiling or manual_review/needs_context states; old stored pages remain unchanged.
- Add seed_generation.mode default atomic and enum validation in core/config.py, config.example.json, scripts/validate_config.py with no live config access. This is the seam only; M1 will implement atomic execution. Explicitly note that M0 is not yet full new-generator functionality.
- Add requirements.txt dependency. Produce docs/card-contracts.md with concrete interfaces for source and seed workers.
- Extend tests/test_card_contracts.py for real executor/runtime paths and invalid stage/boolean/hash provenance/metadata persistence; reuse mock/offline fixtures. Rerun relevant existing tests and original PR29 regression subset under inherited UTF8. Existing source notes lacking metadata must remain read-only compatible, not rewritten.

No public semantic fixture expansion in this slice; Astra will dispatch a separate short fixture task. Stop after correction+wiring+report for acceptance. report.md/report.json must accurately state remaining M0 fixture/rubric work and M1 atomic semantics pending. Report any test failures without weakening assertions. No network/model APIs, no CLI/live-vault apply, no migrations. Keep code compact and tests focused.
