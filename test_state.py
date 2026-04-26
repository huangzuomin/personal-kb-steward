"""Full diagnostic of LLM input selection."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.config import config
from core.vault import build_index, Note
from core.state import changed_notes, load_processed_index, load_state, unprocessed_notes

cfg = config()
index = build_index(cfg)
state = load_state(cfg)

# Show all tracked files
files = state.get("files", {})
print(f"Files tracked in state: {len(files)}")
quicknote_files = [k for k in files if k.startswith("quicknote/")]
print(f"Quicknote files in state: {len(quicknote_files)}")
for k in quicknote_files:
    print(f"  {k}")

# Show all notes in index
all_qn = [n for n in index.notes if n.rel.startswith("quicknote/")]
print(f"\nQuicknote notes in index: {len(all_qn)}")
for n in all_qn:
    print(f"  {n.rel}: sha={n.sha256[:8]}")

# Show changed
changed = changed_notes(index, state)
print(f"\nChanged notes: {len(changed)}")
for n in changed:
    print(f"  {n.rel}")

# Show processed index
processed = load_processed_index(cfg)
proc_entries = processed.get("processed", {})
print(f"\nProcessed index entries: {len(proc_entries)}")
qn_proc = [k for k in proc_entries if k.startswith("quicknote/")]
print(f"Quicknote in processed index: {len(qn_proc)}")
for k in qn_proc:
    rec = proc_entries[k]
    skills = list(rec.get("skills", {}).keys())
    print(f"  {k}: skills={skills}")
