"""Temporary transport helper; never included in the feature branch tree."""
import hashlib
import lzma
import os
from pathlib import Path
import subprocess

BASE = 'f829f283f74742e7c6a4b27f88176a7d79b2fd63'
TREE = '73479db4210af0937c3c0193ed6b0e6b535ce3bd'
PATCH = '9ae6e2785aa14b375501b03528909dc2d5781f0cf6966d0d6fb1584c8b212b06'
FILES = [
    '.github/workflows/ci.yml', 'HANDOVER.md', 'README.md', 'config.example.json',
    'core/derived_index.py', 'core/finalizer.py', 'core/index_builder.py',
    'core/initializer.py', 'core/json_contract.py', 'core/knowledge_objects.py',
    'core/layout.py', 'core/plan_objects.py', 'core/reconcile.py', 'core/retrieval.py',
    'core/skill_loader.py', 'core/skill_runtime.py', 'core/validator.py', 'core/vault.py',
    'scripts/fix_broken_links.py', 'scripts/fix_broken_links_v2.py',
    'scripts/personal_kb_steward.py', 'scripts/validate_config.py',
    'skills/topic-research-compile/executor.py', 'skills/topic-research-compile/renderer.py',
    'tests/test_pr15_contracts.py',
]
def out(*args):
    return subprocess.check_output(['git', *args])
if out('rev-parse', 'HEAD').decode().strip() != BASE:
    raise SystemExit('PR head moved; refusing to apply an outdated patch')
ref = os.environ['GITHUB_SHA']
raw = b''.join(out('show', f'{ref}:.github/pr15-review.part{i}') for i in range(2))
patch = lzma.decompress(raw)
if hashlib.sha256(patch).hexdigest() != PATCH:
    raise SystemExit('Patch checksum mismatch')
path = Path(os.environ['RUNNER_TEMP']) / 'pr15-reviewed.patch'
path.write_bytes(patch)
subprocess.run(['git', 'apply', '--unidiff-zero', '--check', str(path)], check=True)
subprocess.run(['git', 'apply', '--unidiff-zero', str(path)], check=True)
followup = Path(os.environ['RUNNER_TEMP']) / 'pr15-platform.patch'
followup.write_bytes(out('show', f'{ref}:.github/pr15-platform-followup.patch'))
subprocess.run(['git', 'apply', '--check', str(followup)], check=True)
subprocess.run(['git', 'apply', str(followup)], check=True)
subprocess.run(['git', 'add', '--', *FILES], check=True)
subprocess.run(['git', 'diff', '--cached', '--check'], check=True)
actual = out('write-tree').decode().strip()
print('VERIFIED_SOURCE_TREE=' + actual, flush=True)
if actual != TREE:
    raise SystemExit('Result differs from the locally tested source tree')
