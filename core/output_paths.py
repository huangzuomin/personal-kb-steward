"""Configured navigation/log paths. Validate before the apply write phase."""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from .config import kb_root, state_path
from .layout import INPUT_DIRS, INTERNAL_DIRS, relative_dir, knowledge_dirs

DEFAULTS = {'index_file': 'index.md', 'logs_dir': 'logs', 'log_file': 'log.md', 'reports_dir': 'outputs'}


def auxiliary_layout(cfg: dict) -> dict[str, str]:
    paths = {key: relative_dir(cfg.get('write', {}).get(key, default)) for key, default in DEFAULTS.items()}
    protected = INPUT_DIRS | INTERNAL_DIRS | set(cfg.get('safety', {}).get('protected_dirs', []))
    for key, rel in paths.items():
        p = PurePosixPath(rel)
        if set(p.parts) & protected:
            raise ValueError(f'write.{key} overlaps protected data: {rel}')
        if key.endswith('_file') and p.suffix.lower() != '.md':
            raise ValueError(f'write.{key} must name a Markdown file')
    if any(rel == paths['logs_dir'] or rel.startswith(paths['logs_dir'] + '/')
           for rel in knowledge_dirs(cfg).values()):
        raise ValueError('write.logs_dir must not contain a knowledge directory')
    if paths['index_file'] == paths['log_file']:
        raise ValueError('write.index_file and write.log_file must differ')
    return paths


def safe_output_path(cfg: dict, rel: str) -> Path:
    root = kb_root(cfg)
    path = root / relative_dir(rel)
    if path.resolve() != path or not path.resolve().is_relative_to(root):
        raise ValueError(f'Generated output must not use a symlink or escape the vault: {rel}')
    return path


def auxiliary_paths(cfg: dict) -> dict[str, Path]:
    return {key: safe_output_path(cfg, rel) for key, rel in auxiliary_layout(cfg).items()}


def ensure_output_dirs(cfg: dict) -> None:
    # All paths must be checked before ANY mkdir or knowledge-page mutation.
    auxiliary_paths(cfg)
    dirs = [safe_output_path(cfg, value) for key, value in cfg['write'].items() if key.endswith('_dir')]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
    state_path(cfg).parent.mkdir(parents=True, exist_ok=True)


def is_auxiliary_note(cfg: dict, rel: str) -> bool:
    layout = auxiliary_layout(cfg)
    return rel in (layout['index_file'], layout['log_file']) or rel.startswith(layout['logs_dir'] + '/')
