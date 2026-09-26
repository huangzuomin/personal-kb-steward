# Seed final provenance checkpoint (small correction)

Same seed ownership/restrictions; no shared integration edits. Current third-run duplicate probe now passes (create/update/noop), thank you. One independently reproduced provenance failure remains.

Run/read `.execution/astra-seed-same-path-version-probe.py` and `docs/iteration-evidence/astra-seed-same-path-version-probe.json`. A confirmed thought has evidence from A+B. A's text changes, current proposal uses new A+B, overlap on B permits update. `_verified_hashes` selects generation_hashes[A] over recorded_hashes[A]; merged card_state retains old A evidence. Result is update with NO issues but persisted_stale_evidence=[quicknote/a.md]. This is a real workflow probe with matching real input bytes, not just a helper assertion.

Required fix: for atomic updates retaining old evidence, reject when an existing recorded source hash differs from the new generation hash for the SAME path, even if the generation hash matches current index. Do not mix old and new versions under a single path/hash or relabel old evidence. This iteration may fail closed and request a reviewed re-extraction; no complex automatic migration needed. Synchronize all retained outer/state/analysis hashes only from verified consistent evidence.

Also run provenance verification BEFORE early identity/evidence-containment NOOP returns: a stale proposal must report source mismatch, not silently count as harmless successful repeat. Add regression for source changes after generation but before prepare_seed_updates.

Keep explicit legacy topic mode semantics unchanged. Run focused atomic_seed/seed_growth_links/seed_quality_outputs and relevant contracts; add meaningful exact regression(s), update M1 report and preserved before/after evidence. Do not rerun full suite during others' edits. Stop after handoff.
