# Skill: kb-initialize

`kb-initialize` is the controlled full-initialization pipeline for a personal
knowledge base. It should be used when the user wants to organize an existing
raw/quicknote/inbox corpus from scratch.

## Pipeline

1. `intake`
   - Build an inventory of raw Markdown, quicknote/inbox notes, and unsupported
     files such as PDFs.
   - Split inputs into small batches. Raw long-form material defaults to 6 files
     per batch.

2. `source_compile`
   - Convert each raw Markdown file into a source note.
   - Prefer LLM analysis. If the provider is unavailable, fall back to heuristic
     extraction and mark the result in the generated page.
   - Source notes must include a cleaned summary, key facts, candidate topics,
     and quality flags.

3. `seed_cluster`
   - Convert quicknote/inbox fragments into seed cards.

4. `promote_candidates`
   - Generate candidate topic, concept, case, and material-pack pages when the
     current batch has enough source material.
   - Candidate pages require manual review before apply.

5. `quality_gate`
   - Report duplicate targets, placeholder content, raw coverage, and PDF
     extraction backlog before any writes.

## Safety

- Never write raw/quicknote/inbox.
- Never treat a batch as full initialization completion while later batches
  remain.
- Do not silently ignore PDFs; put them into `needs_extraction`.
- Keep plan output self-auditing: current batch, remaining inputs, planned pages,
  review requirements, and quality gate results must be visible.
