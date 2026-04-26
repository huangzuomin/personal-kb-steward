"""Debug LLM input selection."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import config
from core.vault import build_index
from scripts.personal_kb_steward import (
    load_state, load_processed_index, raw_seed_allowed, unprocessed_notes
)

cfg = config()
index = build_index(cfg)
state = load_state(cfg)
changed = state.get("changed", [])
print(f"Changed in state: {len(changed)}")

processed = load_processed_index(cfg)
processed_entries = list(processed.get("processed", {}).keys())
print(f"Processed index entries: {len(processed_entries)}")

# Check quicknote
qn_changed = [n for n in changed if n.rel.startswith("quicknote/")]
print(f"Quicknote changed: {len(qn_changed)}")
for n in qn_changed:
    print(f"  {n.rel}: {n.title}")

# Check candidates
candidates = [
    n for n in changed
    if n.rel.startswith(("quicknote/", "inbox/")) or (n.rel.startswith("raw/") and raw_seed_allowed(n, cfg))
]
print(f"\nCandidates (mindseed-grow eligible): {len(candidates)}")
for n in candidates:
    print(f"  {n.rel}")

# Check unprocessed
unproc = unprocessed_notes(processed, candidates, "mindseed-grow")
print(f"\nUnprocessed for mindseed-grow: {len(unproc)}")
for n in unproc:
    print(f"  {n.rel}")
