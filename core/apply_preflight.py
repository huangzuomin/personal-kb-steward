"""Per-apply write preflight probes.

Each apply probes every actual parent directory at most once, with a probe file
created exclusively (O_CREAT|O_EXCL): a collision with a pre-existing or
planted file is a hard failure — this attempt never truncates, modifies, or
deletes a file it does not own. The prober is created fresh inside a single
preflight pass, so there is no global or cross-apply cache and no historical
exists=>writable shortcut: a new apply always re-probes. A failed or denied
cleanup is reported together with the original failure, never as success.
Existing update targets get a non-creating writability check (open 'r+b', no
bytes written) so a parent-only create probe cannot silently approve a
read-only target; a target that has disappeared fails instead of being
recreated.
"""
from __future__ import annotations

import os
from pathlib import Path

from .layout import INPUT_DIRS, INTERNAL_DIRS


def _protected_roots(cfg: dict) -> frozenset[str]:
    configured = {str(p).strip().strip("/\\").casefold()
                  for p in cfg.get("safety", {}).get("protected_dirs", []) if str(p).strip()}
    return frozenset(configured | {d.casefold() for d in INPUT_DIRS | INTERNAL_DIRS})


def assert_resolved_target_allowed(cfg: dict, root: Path, target: Path) -> None:
    """Reject targets whose RESOLVED location lands in raw/protected data.

    The plan text may name a clean path while an ancestor junction aliases
    protected data (or uppercase-native variants). This complements resolved
    containment (still enforced by the caller) and the identity-layer symlink
    rejection; it is not an is_symlink-only rule and preserves valid native
    case behaviour.
    """
    try:
        rel = target.relative_to(root)
    except ValueError:
        raise SystemExit(f"拒绝越界写入：{target}") from None
    first = rel.parts[0].casefold() if rel.parts else ""
    if first and first in _protected_roots(cfg):
        raise SystemExit(f"拒绝写入受保护目录（解析后实际路径）：{target}")


def _write_probe(probe: Path) -> None:
    """Exclusively create and fill the probe file; never touch an existing one.

    A failure after the exclusive create leaves an owned file; it is cleaned up
    here, with any cleanup failure chained onto the original write failure.
    """
    try:
        fd = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PermissionError(
            f"写入探针名称已被占用，可能存在伪造或残留文件，拒绝本次 apply：{probe}"
        ) from exc
    except OSError as exc:
        raise PermissionError(f"目标目录不可写：{probe.parent}") from exc
    try:
        try:
            os.write(fd, b"ok")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
    except OSError as write_error:
        try:
            _delete_probe(probe)
        except OSError as cleanup_error:
            raise PermissionError(
                f"写入探针 {probe.name} 写入失败且无法清理（{cleanup_error}），目录状态不确定，拒绝本次 apply：{probe.parent}"
            ) from write_error
        raise PermissionError(
            f"目标目录不可写（探针已清理，未改动任何既有文件）：{probe.parent}"
        ) from write_error


def _delete_probe(probe: Path) -> None:
    probe.unlink()


class ParentWriteProber:
    def __init__(self, attempt_id: str) -> None:
        self._attempt_id = attempt_id
        self._probed: dict[str, str] = {}

    def probe_parent(self, parent: Path) -> None:
        key = str(parent)
        if key in self._probed:
            return
        probe = parent / f".write-check-{self._attempt_id}-{len(self._probed)}.tmp"
        try:
            _write_probe(probe)
        except PermissionError:
            raise
        except OSError as exc:
            raise PermissionError(f"目标目录不可写：{parent}") from exc
        try:
            _delete_probe(probe)
        except OSError as cleanup_error:
            raise PermissionError(
                f"写入探针 {probe.name} 无法删除，目录状态不确定，拒绝本次 apply：{parent}"
            ) from cleanup_error
        self._probed[key] = probe.name

    def check_existing_target(self, target: Path) -> None:
        # r+b never creates and never writes; it only proves the required
        # existing update target is still present and writable.
        try:
            with target.open("r+b"):
                pass
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"更新目标在预检时消失，拒绝写入：{target}") from exc
        except OSError as exc:
            raise PermissionError(f"目标文件已存在且不可写入（可能为只读）：{target}") from exc
