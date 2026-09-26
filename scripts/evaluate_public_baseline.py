#!/usr/bin/env python3
"""Public baseline evaluation runner (T10 C1).

Runs the ACTUAL production pipeline (initialization plan -> save -> review ->
apply, then finalize plan -> save -> review -> apply) over a fresh isolated
SYNTHETIC vault built ONLY from the canonical public fixtures
(tests/fixtures/card-baseline/manifest.json), for a fixed number of rounds
(default 3). All model calls go through the accepted adapter seam
(core.public_evaluation.PublicClaudeAdapter, bound per round) in live mode,
or through the test-only offline mock in explicit --smoke mode.

Hard rules enforced here:
- ZERO live/native-Claude calls from the coding session: live mode requires
  the explicit --live flag and is executed by the root operator only.
- The LIVE path never imports tests/public_round_support (the mock corpus).
  Only the --smoke branch lazily imports that test-only module.
- Fixed budget: 8 target calls per round (4 source + 1 atomic seed +
  concept + case + topic), hard bounds <=10 per round / <=30 total
  INCLUDING failures, enforced by the adapter before any attempt.
- Version freeze: hashes of pipeline code/schemas/prompts are snapshotted at
  start and re-verified before every round; any change blocks the run rather
  than mixing versions.
- All output stays under the explicit artifact root (--output-dir); an
  existing root is never reused. No writes outside it except the adapter's
  empty temp cwd.
- Auto-approval is an ENGINEERING FIXTURE approval inside the marked
  synthetic vault created under the artifact root (normal review commands,
  run-scoped). It is NOT human semantic acceptance and a user vault is never
  touched. The runner cannot declare semantic pass: metrics separate
  execution/schema/provenance checks from the pending Astra content review.

The topic stage receives the fixed configured question through the production
pipeline. This runner never substitutes a second topic writer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.public_evaluation import (  # noqa: E402
    AdapterConfig,
    PublicClaudeAdapter,
    PublicContextBundle,
    PublicEvaluationError,
    RunRecorder,
    load_fixture_manifest,
)
from core.vault import parse_frontmatter  # noqa: E402

# Fixed explicit research question for the finalize topic stage. Written for
# this public baseline; never copied from manifest annotations (expected_* /
# topic_groups stay review-only).
TOPIC_QUESTION = "合成案例中，青梧书店的分段转化做法在哪些条件下有效，哪些条件下会失效？"

ROUND_SOURCES = {
    "research_summary_uncited_01": "raw/research_summary_uncited_01.md",
    "project_case_01": "raw/project_case_01.md",
    "project_case_01_followup": "raw/project_case_01_followup.md",
    "project_case_01_counterexample": "raw/project_case_01_counterexample.md",
}
ROUND_DIALOGUE = ("dialogue_user_ai_01", "quicknote/dialogue_user_ai_01.md")

TARGET_CALLS_PER_ROUND = 8
HARD_MAX_ROUNDS = 3
HARD_MAX_CALLS_PER_ROUND = 10
HARD_MAX_TOTAL_CALLS = 30
EXPECTED_STAGE_SPLIT = {
    "source": 4,
    "seed": 1,
    "concept": 1,
    "case": 1,
    "topic": 1,
}

# Public pipeline inputs frozen for the whole run (verify before each round
# and at the end; any change blocks rather than mixing versions).  The
# enumerator deliberately includes untracked files in these production input
# trees, while excluding caches and artifact roots.
FREEZE_FILE_EXTENSIONS = {".py", ".json", ".md", ".j2", ".yaml", ".yml", ".toml"}
FREEZE_PRODUCTION_DIRS = ("core", "skills")
FREEZE_EXPLICIT_FILES = (
    "config.example.json",
    "router.json",
    "workflows.json",
    "scripts/personal_kb_steward.py",
    "scripts/evaluate_public_baseline.py",
    "tests/public_round_support.py",
    "tests/fixtures/card-baseline/manifest.json",
)
FREEZE_SKIP_PARTS = {"__pycache__", ".execution", ".git"}

CARD_TYPES_REQUIRED = ("source-note", "seed-card", "concept-page",
                       "case-story", "topic-page")

class RunnerError(RuntimeError):
    """Explicit runner failure; never silently repaired."""


def _error_record(exc: BaseException) -> dict[str, Any]:
    """Keep a bounded, JSON-safe record of a failed production step."""
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "raw_response": getattr(exc, "raw_response", None),
    }


# ---------------------------------------------------------------------------
# Version freeze
# ---------------------------------------------------------------------------


def _is_reparse_point(path: Path) -> bool:
    """Return whether *path* is a symlink/junction/reparse point."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.stat(), "st_file_attributes", 0)
        return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except OSError:
        return False


def _reparse_components(path: Path) -> list[str]:
    """List existing symlink/junction components without resolving them."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    found: list[str] = []
    for part in absolute.parts[1:]:
        current /= part
        # lexists also sees a broken link, which must not be followed by a
        # later mkdir/write operation.
        if os.path.lexists(os.fspath(current)) and _is_reparse_point(current):
            found.append(str(current))
    return found


def _assert_no_reparse_components(path: Path, label: str) -> None:
    found = _reparse_components(path)
    if found:
        raise RunnerError(
            f"{label} contains symlink/junction/reparse component: {found}")


def _assert_fresh_artifact_root(path: Path) -> Path:
    """Validate a new output root before any runner write occurs."""
    candidate = Path(os.path.abspath(os.fspath(path)))
    _assert_no_reparse_components(candidate, "artifact root")
    if os.path.lexists(os.fspath(candidate)):
        raise RunnerError(
            f"refusing to reuse existing artifact root: {candidate}")
    parent = candidate.parent
    _assert_no_reparse_components(parent, "artifact root parent")
    return candidate


def _assert_fresh_vault(vault: Path, artifact_root: Path | None = None) -> None:
    """Reject prepopulated or escaped synthetic vault targets."""
    if artifact_root is not None:
        root = Path(os.path.abspath(os.fspath(artifact_root)))
        target = Path(os.path.abspath(os.fspath(vault)))
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RunnerError(
                f"synthetic vault escapes artifact root: {target}") from exc
    _assert_no_reparse_components(vault, "synthetic vault")
    if os.path.lexists(os.fspath(vault)):
        raise RunnerError(f"refusing to reuse synthetic vault: {vault}")


def _fixture_input_paths() -> list[Path]:
    """Return manifest plus every canonical public fixture by manifest path."""
    manifest = REPO_ROOT / "tests" / "fixtures" / "card-baseline" / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerError(f"fixture manifest unreadable: {exc}") from exc
    entries = data.get("fixtures") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise RunnerError("fixture manifest fixtures is not a list")
    fixture_root = manifest.parent.resolve()
    paths = [manifest]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RunnerError("fixture manifest contains an invalid path entry")
        path = (REPO_ROOT / entry["path"]).absolute()
        try:
            path.resolve().relative_to(fixture_root)
        except ValueError as exc:
            raise RunnerError(
                f"fixture path escapes canonical fixture root: {entry['path']}") from exc
        if not path.is_file():
            raise RunnerError(f"fixture file missing: {entry['path']}")
        paths.append(path)
    return paths


def _freeze_input_paths() -> list[Path]:
    """Enumerate all public code/config/prompt/schema/template inputs."""
    paths: set[Path] = set()
    for rel in FREEZE_EXPLICIT_FILES:
        paths.add(REPO_ROOT / rel)
    for rel_root in FREEZE_PRODUCTION_DIRS:
        root = REPO_ROOT / rel_root
        if not root.is_dir():
            raise RunnerError(f"version-freeze directory missing: {rel_root}")
        for path in root.rglob("*"):
            if (path.is_file() and path.suffix.lower() in FREEZE_FILE_EXTENSIONS
                    and not any(part in FREEZE_SKIP_PARTS for part in path.parts)):
                paths.add(path)
    paths.update(_fixture_input_paths())
    ordered = sorted(paths, key=lambda value: value.relative_to(REPO_ROOT).as_posix())
    for path in ordered:
        if not path.is_file():
            rel = path.relative_to(REPO_ROOT).as_posix()
            raise RunnerError(f"version-freeze file missing: {rel}")
    return ordered


def freeze_versions() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in _freeze_input_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def verify_versions(frozen: dict[str, str]) -> None:
    current = freeze_versions()
    if current != frozen:
        changed = sorted(
            key for key in set(frozen) | set(current)
            if frozen.get(key) != current.get(key))
        raise RunnerError(
            f"pipeline code changed after start; blocking instead of mixing "
            f"versions: {changed}")


# ---------------------------------------------------------------------------
# Isolated synthetic vault + fixed config
# ---------------------------------------------------------------------------


def prepare_vault(vault: Path, artifact_root: Path | None = None) -> None:
    """Create a fresh marked synthetic vault with exact fixture bytes."""
    _assert_fresh_vault(vault, artifact_root)
    vault.parent.mkdir(parents=True, exist_ok=True)
    vault.mkdir(parents=True)
    (vault / "_SYNTHETIC_VAULT.json").write_text(json.dumps({
        "marker": "engineering synthetic fixture vault",
        "statement": "Created by scripts/evaluate_public_baseline.py from the "
                     "canonical public synthetic fixtures only. Auto-approval "
                     "inside this vault is an engineering fixture approval, "
                     "NOT human semantic acceptance. Never approve a user vault.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    fixtures = load_fixture_manifest()
    for fid, rel in {**ROUND_SOURCES, ROUND_DIALOGUE[0]: ROUND_DIALOGUE[1]}.items():
        snap = fixtures.get(fid)
        if snap is None:
            raise RunnerError(f"fixture not in canonical manifest: {fid}")
        target = vault / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(snap.path.read_bytes())  # EXACT raw bytes


def build_cfg(vault: Path) -> dict[str, Any]:
    """Fixed nonsecret synthetic config built in code (repo example template,
    paths redirected into the isolated vault; never the user's config.json)."""
    import json as _json
    example = REPO_ROOT / "config.example.json"
    cfg = _json.loads(example.read_text(encoding="utf-8-sig"))
    cfg["knowledge_base"] = str(vault)
    cfg["state_file"] = str(vault / ".openclaw" / "state.json")
    cfg["scan"]["include_dirs"] = ["raw", "quicknote"]
    cfg["scan"]["max_files_per_run"] = 20
    cfg["seed_generation"] = {"mode": "atomic"}
    cfg["card_pipeline"] = {"mode": "typed", "topic_questions": [TOPIC_QUESTION]}
    safety = cfg.setdefault("safety", {})
    base = vault / ".openclaw"
    safety["plans_dir"] = str(base / "plans")
    safety["runs_dir"] = str(base / "runs")
    safety["processed_index"] = str(base / "processed-index.json")
    safety["manual_review_queue"] = str(base / "manual-review" / "queue.jsonl")
    safety["backup_dir"] = str(base / "backups")
    safety["operation_log"] = str(base / "operation-log.jsonl")
    return cfg


# ---------------------------------------------------------------------------
# Provider seam
# ---------------------------------------------------------------------------


def _fixture_hashes() -> dict[str, str]:
    return {fid: snap.sha256 for fid, snap in load_fixture_manifest().items()}


def _payload_provenance(payload: Any, fixture_hashes: dict[str, str]) -> list[str]:
    """Name the canonical fixtures an ACTUAL generator payload was built from.

    Matched by exact byte hashes / source rels recorded in the payload.  The
    source executor's payload is deliberately only ``{"text": ...}``, so
    its header is removed and the remaining text must equal one complete
    public fixture snapshot.  No fuzzy matching or answer data is added to
    the payload.
    """
    rels = {**ROUND_SOURCES, ROUND_DIALOGUE[0]: ROUND_DIALOGUE[1]}
    round_ids = set(rels)
    fid_by_hash = {h: fid for fid, h in fixture_hashes.items()
                   if fid in round_ids}
    all_fixtures = load_fixture_manifest()
    fixtures = {fid: snap for fid, snap in all_fixtures.items()
                if fid in round_ids}
    names: list[str] = []

    def add(fid: str) -> None:
        if fid not in names:
            names.append(fid)

    def by_hash(value: Any) -> None:
        if isinstance(value, str) and value in fid_by_hash:
            add(fid_by_hash[value])

    def by_rel(value: Any) -> None:
        if not isinstance(value, str):
            return
        value = value.replace("\\", "/").lstrip("./")
        for fid, rel in rels.items():
            canonical = rel.replace("\\", "/")
            # The accepted generators use both vault-relative paths and
            # public fixture paths.  A basename is accepted only for one of
            # the five fixed round fixtures, all of which are unique.
            aliases = {
                canonical,
                f"tests/fixtures/card-baseline/{Path(canonical).name}",
                Path(canonical).name,
                f"raw/{Path(canonical).name}",
                f"quicknote/{Path(canonical).name}",
            }
            if value in aliases:
                add(fid)
                break

    def by_exact_text(value: Any) -> None:
        if not isinstance(value, str) or not value:
            return
        for fid, snap in fixtures.items():
            if value == snap.text:
                add(fid)

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                key_name = str(child_key)
                if key_name in {"sha256", "source_sha256", "content_sha256"}:
                    by_hash(child)
                if key_name in {"source", "source_path", "path", "rel"}:
                    by_rel(child)
                walk(child, key_name)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str):
            by_hash(value)
            by_exact_text(value)

    # Source chunks have a title/offset header followed by the exact raw
    # snapshot.  Requiring equality after the separator prevents an arbitrary
    # user string that merely mentions a fixture from becoming provenance.
    if isinstance(payload, dict) and isinstance(payload.get("text"), str) \
            and not payload.get("task") and not payload.get("documents"):
        source_text = payload["text"]
        body = source_text.split("\n\n", 1)[-1]
        source_matches = [fid for fid, snap in fixtures.items()
                          if body == snap.text]
        # A real source executor may split a long public note.  In that case
        # accept only the exact offset range declared by its own header; a
        # short arbitrary substring without a trusted range is rejected.
        if not source_matches:
            offset_match = re.search(
                r"字符偏移\s+(\d+)-(\d+)，全文\s+(\d+)", source_text)
            if offset_match:
                start, end, total = (int(v) for v in offset_match.groups())
                source_matches = [
                    fid for fid, snap in fixtures.items()
                    if len(snap.text) == total and 0 <= start <= end <= total
                    and snap.text[start:end] == body
                ]
        if len(source_matches) > 1:
            raise PublicEvaluationError(
                "source payload matches multiple public fixture snapshots")
        for fid in source_matches:
            add(fid)

    walk(payload)
    return names


def _register_generated_payload_documents(
    payload: Any, bundle: PublicContextBundle, fixture_hashes: dict[str, str]
) -> list[str]:
    """Register generated source-card snapshots carried by a payload.

    The production typed generators use ``content`` + ``sha256`` for an
    upstream source-card snapshot.  These fields are inspected for accounting
    only; the original payload object is passed to ``register_payload``
    unchanged.  Fixture hashes stay fixture provenance, while any other
    exact hash is registered as a public generated intermediate.
    """
    generated: list[str] = []
    used_names: set[str] = set()
    fixture_digests = set(fixture_hashes.values())

    def walk(value: Any, index: list[int]) -> None:
        if isinstance(value, dict):
            text = value.get("content")
            digest = value.get("sha256") or value.get("content_sha256")
            if isinstance(text, str) and isinstance(digest, str) \
                    and digest not in fixture_digests and len(digest) == 64:
                label = (value.get("path") or value.get("rel")
                         or value.get("name") or f"snapshot-{index[0]}")
                index[0] += 1
                safe_label = str(label).replace("\\", "/")
                name = f"generated:{safe_label}"
                if name in used_names:
                    name = f"{name}:{digest[:12]}"
                bundle.register_generated(name, "source-card", text, digest)
                generated.append(name)
                used_names.add(name)
            for child in value.values():
                walk(child, index)
        elif isinstance(value, list):
            for child in value:
                walk(child, index)

    walk(payload, [0])
    return generated


def _normal_rel(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\\", "/").lstrip("./")


def _payload_source_card_provenance(
    payload: Any, source_card_by_source: dict[str, str]
) -> list[str]:
    """Return only applied source-card snapshots used by this payload.

    The accepted concept/case/topic payloads carry the original source
    documents and an ``upstream_source_analysis`` list.  Their source-card
    snapshots are already applied to the isolated vault, so the runner maps
    those exact raw source paths to the registered generated card snapshots
    without adding fields to the model payload.
    """
    names: list[str] = []

    def add_for(value: Any) -> None:
        rel = _normal_rel(value)
        name = source_card_by_source.get(rel)
        if name and name not in names:
            names.append(name)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key) in {"path", "rel", "source", "source_path"}:
                    add_for(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return names


def _register_applied_source_cards(
    vault: Path, plan: dict[str, Any], bundle: PublicContextBundle
) -> tuple[dict[str, str], dict[str, Any]]:
    """Register exact source-card bytes produced by an applied intake plan."""
    source_card_by_source: dict[str, str] = {}
    registered: list[dict[str, Any]] = []
    errors: list[str] = []
    pages = plan.get("planned_pages") if isinstance(plan, dict) else None
    source_pages = [page for page in (pages or [])
                    if isinstance(page, dict)
                    and str(page.get("rel_path") or page.get("target") or "")
                    .replace("\\", "/").startswith("wiki/sources/")]
    if not source_pages:
        errors.append("applied intake plan has no wiki/sources source-card targets")
    root = vault.resolve()
    for page in source_pages:
        rel = _normal_rel(page.get("rel_path") or page.get("target"))
        target = (vault / Path(rel)).resolve()
        if target != root and root not in target.parents:
            errors.append(f"source-card target escapes synthetic vault: {rel}")
            continue
        try:
            raw = target.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"source-card target unreadable {rel}: {_error_record(exc)['message']}")
            continue
        actual_sha = hashlib.sha256(raw).hexdigest()
        expected_sha = page.get("content_sha256")
        if isinstance(expected_sha, str) and expected_sha and actual_sha != expected_sha:
            errors.append(
                f"source-card hash mismatch {rel}: expected {expected_sha}, got {actual_sha}")
            continue
        name = f"generated:{rel}"
        try:
            bundle.register_generated(name, "source-card", text, actual_sha)
        except (Exception, SystemExit) as exc:
            errors.append(f"source-card registration failed {rel}: {type(exc).__name__}: {exc}")
            continue
        sources = [
            _normal_rel(value) for value in (page.get("sources") or [])
            if _normal_rel(value)
        ]
        for source_rel in sources:
            source_card_by_source[source_rel] = name
        registered.append({"name": name, "target": rel,
                           "sources": sources, "sha256": actual_sha})
    return source_card_by_source, {
        "ok": not errors,
        "registered": registered,
        "errors": errors,
    }


def make_live_provider(adapter: PublicClaudeAdapter, round_index: int,
                       bundle: PublicContextBundle, call_log: list | None = None,
                       stage_context: dict[str, Any] | None = None,
                       source_card_by_source: dict[str, str] | None = None
                       ) -> Callable[..., str]:
    """Live provider: registers the EXACT actual payload, then the adapter."""
    bound = adapter.bind_for_round(round_index)
    fixture_hashes = _fixture_hashes()

    def provider(cfg_, system_prompt, payload):
        entry: dict[str, Any] = {
            "round": round_index,
            "stage": (stage_context or {}).get("stage"),
            "system_prompt": system_prompt,
            "payload": payload,
            "response": None,
            "error": None,
            # A provider invocation is logged before provenance and adapter
            # budget checks.  Keep refused-before-launch requests in raw
            # evidence, but distinguish them from attempts that consumed the
            # adapter budget for stage/call accounting.
            "adapter_attempted": False,
        }
        if call_log is not None:
            call_log.append(entry)
        attempts_before = adapter.total_attempts
        try:
            built_from = _payload_provenance(payload, fixture_hashes)
            built_from.extend(_payload_source_card_provenance(
                payload, source_card_by_source or {}))
            built_from.extend(_register_generated_payload_documents(
                payload, bundle, fixture_hashes))
            if not built_from:
                raise PublicEvaluationError(
                    "live payload has no exact public fixture or generated provenance")
            registered = bundle.register_payload(payload, built_from=built_from)
            entry["provenance"] = dict(registered.provenance)
            result = bound(cfg_, system_prompt, registered)
            entry["response"] = result
            return result
        except Exception as exc:
            entry["error"] = {
                "type": type(exc).__name__, "message": str(exc),
                "raw_response": getattr(exc, "raw_response", None),
            }
            raise
        finally:
            entry["adapter_attempted"] = adapter.total_attempts > attempts_before

    return provider


def make_smoke_provider(round_index: int, call_log: list):
    """SMOKE ONLY: lazily import the test-only offline mock provider.

    This is the ONLY place the runner touches the test answer corpus; the
    live path never imports it.
    """
    tests_dir = REPO_ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    import public_round_support  # noqa: PLC0415 - smoke-only, test answers

    log = public_round_support.CallLog()

    active: list[dict[str, Any] | None] = [None]

    class _Log:
        def record(self, stage, system_prompt, payload, response):
            entry = active[0]
            if entry is None:
                entry = {"round": round_index, "stage": stage,
                         "system_prompt": system_prompt, "payload": payload,
                         "response": response, "error": None}
                call_log.append(entry)
            else:
                entry.update({"stage": stage, "response": response})
            log.record(stage, system_prompt, payload, response)

    base = public_round_support.make_offline_provider(_Log())

    def provider(*args: Any) -> str:
        if len(args) == 3:
            _, system_prompt, payload = args
        elif len(args) == 2:
            system_prompt, payload = args
        else:
            raise ValueError("offline provider accepts (cfg, system, payload) or (system, payload)")
        entry = {"round": round_index, "stage": None,
                 "system_prompt": system_prompt, "payload": payload,
                 "response": None, "error": None}
        call_log.append(entry)
        active[0] = entry
        try:
            result = base(*args)
            entry["response"] = result
            return result
        except Exception as exc:
            entry["error"] = {
                "type": type(exc).__name__, "message": str(exc),
                "raw_response": getattr(exc, "raw_response", None),
            }
            raise
        finally:
            active[0] = None

    return provider


# ---------------------------------------------------------------------------
# Steward helpers (normal production review/apply path)
# ---------------------------------------------------------------------------


def _load_steward():
    path = REPO_ROOT / "scripts" / "personal_kb_steward.py"
    spec = importlib.util.spec_from_file_location("pks_steward_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _PatchedLLM:
    """Route the init stage's default provider through `provider` by patching
    core.llm.call_chat_completion (skill executor modules re-import it fresh
    on each execute_skill call). Production code is restored afterwards."""

    def __init__(self, provider: Callable[..., str]) -> None:
        from core import llm as llm_module
        self._llm = llm_module
        self._original = llm_module.call_chat_completion
        self._provider = provider

    def __enter__(self):
        self._llm.call_chat_completion = self._provider
        return self

    def __exit__(self, *exc):
        self._llm.call_chat_completion = self._original
        return False


def _validate_saved_plan(plan_path: str | Path) -> dict[str, Any]:
    """Reject producer partial/error states hidden behind an applied plan."""
    path = Path(plan_path)
    problems: list[str] = []
    if not path.is_file():
        return {"ok": False, "path": str(path),
                "problems": ["saved plan is missing"]}
    try:
        plan = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "path": str(path),
                "problems": [f"saved plan unreadable: {type(exc).__name__}: {exc}"]}
    if not isinstance(plan, dict):
        return {"ok": False, "path": str(path),
                "problems": ["saved plan is not an object"]}

    def normalized_status(value: Any) -> str:
        return (str(value or "").strip().lower()
                .replace("-", "_").replace(" ", "_"))

    producer_failures = {
        "partial", "partial_input", "blocked", "error", "model_error",
        "failed", "failure", "exception", "timeout", "cancelled",
        "incomplete", "zero",
    }
    short_circuit_reasons = {
        "no_eligible_sources", "no_inputs", "no_relevant_sources",
    }
    plan_entry = normalized_status(plan.get("entry"))

    def planned_count(action: dict[str, Any]) -> int:
        counts: list[int] = []
        for key in ("planned_items", "planned_pages", "planned_inputs"):
            value = action.get(key)
            if isinstance(value, list):
                counts.append(len(value))
                continue
            try:
                counts.append(int(value or 0))
            except (TypeError, ValueError):
                continue
        return max(counts, default=0)

    def status_fields(value: dict[str, Any]) -> list[tuple[str, str]]:
        # Both fields are producer output.  Do not let a benign state mask an
        # error outcome (or vice versa).
        result: list[tuple[str, str]] = []
        for key in ("outcome", "state"):
            status = normalized_status(value.get(key))
            if status:
                result.append((key, status))
        return result

    def check_input_outcomes(label: str, outcomes: Any) -> None:
        if outcomes is None:
            return
        if not isinstance(outcomes, list):
            problems.append(f"{label}: input_outcomes is not a list")
            return
        for index, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                problems.append(f"{label}[{index}]: input outcome is not an object")
                continue
            statuses = status_fields(outcome)
            failed = [status for _, status in statuses
                      if status in producer_failures]
            if outcome.get("complete") is False or any(
                    status in {"partial", "partial_input", "error", "model_error",
                               "failed", "failure", "exception", "timeout",
                               "cancelled", "incomplete"}
                    for status in failed):
                state = failed[0] if failed else "unknown"
                problems.append(
                    f"{label}[{index}]: producer outcome={state or 'unknown'} "
                    f"complete={outcome.get('complete')!r}")
            else:
                for _, state in statuses:
                    if state in {"blocked", "zero"} and outcome.get("targets"):
                        problems.append(f"{label}[{index}]: {state} outcome has targets")

    check_input_outcomes("plan", plan.get("input_outcomes"))
    actions = plan.get("actions")
    if not isinstance(actions, list):
        problems.append("saved plan actions is not a list")
        actions = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            problems.append(f"action[{index}] is not an object")
            continue
        stage = normalized_status(action.get("stage") or action.get("executor_stage"))
        label = f"action[{index}]/{action.get('stage') or action.get('executor_stage') or 'unknown'}"
        check_input_outcomes(label, action.get("input_outcomes"))
        planned = planned_count(action)
        required_stage = (
            stage in {"source", "seed", "source_compile", "seed_cluster"}
            or stage.startswith("source_") or stage.startswith("seed_")
        )
        downstream_stage = stage.endswith("_generation") or stage in {
            "promote_candidates", "quality_gate",
        }
        reason_statuses = {
            normalized_status(action.get("reason")),
            normalized_status(action.get("reason_detail")),
        }
        reason_statuses.update(status for _, status in status_fields(action))
        expected_short_circuit = (
            plan_entry == "init_kb" and downstream_stage and not required_stage
            and planned == 0
            and bool(reason_statuses & short_circuit_reasons)
        )
        for field, state in status_fields(action):
            if state not in producer_failures:
                continue
            if state in {"blocked", "zero"}:
                # A downstream init stage may explicitly report that it had
                # no eligible inputs.  Required source/seed stages never get
                # this exemption, and a planned page always makes it a fault.
                if expected_short_circuit:
                    continue
                if state == "zero" and planned == 0 and not required_stage:
                    # Preserve the existing no-work convention for a benign
                    # zero action when no explicit failure was reported.
                    continue
            if field == "state":
                if state in {"blocked", "zero"}:
                    problems.append(
                        f"{label}: producer state={state} with {planned} planned items")
                else:
                    problems.append(f"{label}: producer state={state}")
            else:
                problems.append(f"{label}: producer outcome={state}")

    return {"ok": not problems, "path": str(path),
            "action_count": len(actions), "problems": problems}


def _save_review_apply(steward, cfg: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Save plan -> write review queue -> run-scoped fixture auto-approval ->
    apply-approved (the normal review commands)."""
    plan_path: Path | None = None
    queued: Any = None
    result: dict[str, Any] = {
        "plan_path": None, "queued": None, "applied": False,
        "blocked": None, "apply_code": None,
    }
    try:
        plan_path = steward.write_execution_plan(cfg, plan)
        queued = steward.write_manual_review_queue(cfg, plan)
        result["plan_path"] = str(plan_path)
        result["queued"] = queued
        # Engineering-fixture auto-approval: use the same public, run-scoped
        # review commands as the CLI.  `command_review(apply-approved)` owns
        # page-scoped subset dispatch and its writer callback; the runner must
        # not duplicate that scheduling or bypass the subset contract.
        approval_code = steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="batch-approve",
                run_id=plan["run_id"],
                risk=None,
                type=None,
            ),
        )
        result["approval_code"] = approval_code
        if approval_code != 0:
            result["blocked"] = "review_approval_failed"
            return result
        apply_code = steward.command_review(
            cfg,
            SimpleNamespace(
                review_command="apply-approved",
                run_id=plan["run_id"],
                all=False,
            ),
        )
        result["apply_code"] = apply_code
        # A nonzero code remains a failed stage even when the command wrote
        # some files before returning.  File counts never upgrade this flag.
        if apply_code != 0:
            result["blocked"] = "apply_failed"
            return result
        validation = _validate_saved_plan(plan_path)
        result["plan_validation"] = validation
        if not validation["ok"]:
            result["blocked"] = "producer_output_incomplete"
            return result
        result["applied"] = True
        return result
    except (Exception, SystemExit) as exc:
        result["blocked"] = "stage_exception"
        result["failure"] = _error_record(exc)
        if plan_path is not None:
            result["plan_path"] = str(plan_path)
        result["queued"] = queued
        return result
    finally:
        try:
            result["manifest_paths"] = [
                str(path) for path in _run_manifest_paths(
                    Path(cfg["knowledge_base"]))]
        except (OSError, KeyError, TypeError):
            result["manifest_paths"] = []


# ---------------------------------------------------------------------------
# Round runner
# ---------------------------------------------------------------------------


def _frontmatter_metadata(text: str) -> dict[str, Any]:
    """Parse writer frontmatter with the repository's actual parser.

    The runner must not infer a typed output from a line that merely starts
    with ``type:``.  The writer's parser also preserves identity fields, which
    lets the manifest and the bytes be checked against the same object.
    """
    metadata, _ = parse_frontmatter(text)
    return metadata if isinstance(metadata, dict) else {}


def _frontmatter_card_type(text: str) -> str | None:
    return _frontmatter_metadata(text).get("type")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", value))


def _is_excluded_output(rel: str) -> bool:
    """Return whether a manifest target is auxiliary rather than a card."""
    parts = [part for part in rel.replace("\\", "/").split("/") if part]
    lowered = [part.casefold() for part in parts]
    return (
        any(part in {".openclaw", "backups"} for part in lowered)
        or bool(parts and parts[-1].casefold() == "readme.md")
    )


def _run_manifest_paths(vault: Path) -> list[Path]:
    runs = vault / ".openclaw" / "runs"
    return sorted(runs.glob("*.json")) if runs.is_dir() else []


def _collect_observed_outputs(vault: Path) -> dict[str, Any]:
    """Read actual apply manifests and validate current typed output bytes.

    Manifests are the source of truth for counted outputs.  Failed manifests
    and write-before-failure records are retained in ``observed`` but never
    counted as successful typed pages.
    """
    counts = {t: 0 for t in CARD_TYPES_REQUIRED}
    manifests = _run_manifest_paths(vault)
    # Keep every manifest/item observation.  A later failed write must never
    # erase an earlier failure or make a target look successful merely because
    # the path still exists.  ``verified_by_rel`` is only the final unique
    # count of current, independently verified targets.
    observed: list[dict[str, Any]] = []
    verified_by_rel: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append({"manifest": str(manifest_path),
                             "error": f"manifest unreadable: {exc}"})
            continue
        status = str(manifest.get("status") or "").lower()
        reconcile = manifest.get("reconcile")
        manifest_problems: list[str] = []
        if status != "applied":
            manifest_problems.append(f"manifest status={status or 'missing'}")
        if not isinstance(reconcile, dict):
            manifest_problems.append("manifest reconcile is missing")
        else:
            if reconcile.get("ok") is not True:
                manifest_problems.append("manifest reconcile.ok is not true")
            for key in ("missing", "hash_mismatch"):
                value = reconcile.get(key)
                if value != []:
                    manifest_problems.append(f"manifest reconcile.{key} is non-empty")
            if reconcile.get("duplicate_created") != {}:
                manifest_problems.append("manifest reconcile.duplicate_created is non-empty")
        created = manifest.get("created")
        if not isinstance(created, list):
            failures.append({"manifest": str(manifest_path),
                             "error": "manifest created is not a list"})
            continue
        for item in created:
            if not isinstance(item, dict):
                failure = {"manifest": str(manifest_path),
                           "error": "created output is not an object"}
                failures.append(failure)
                observed.append(dict(failure, counted=False))
                continue
            rel = item.get("rel_path") or item.get("canonical_path")
            rel = rel.replace("\\", "/") if isinstance(rel, str) else ""
            record: dict[str, Any] = {
                "manifest": str(manifest_path), "run_id": manifest.get("run_id"),
                "status": status, "rel_path": rel,
                "canonical_path": item.get("canonical_path"),
                "expected_sha256": item.get("expected_sha256"),
                "manifest_sha256": item.get("sha256"),
                "object_id": item.get("object_id"),
                "revision": item.get("revision"),
                "content_verified": item.get("content_verified"),
                "counted": False,
            }
            observed.append(record)
            if not isinstance(rel, str) or not rel.startswith("wiki/"):
                record["error"] = "output is outside wiki/"
                failures.append({"manifest": str(manifest_path), "rel_path": rel,
                                 "error": record["error"]})
                continue
            if ".." in rel.split("/"):
                record["error"] = "output path contains parent traversal"
                failures.append({"manifest": str(manifest_path), "rel_path": rel,
                                 "error": record["error"]})
                continue
            if _is_excluded_output(rel):
                record["error"] = "README/backups/.openclaw output is excluded"
                failures.append({"manifest": str(manifest_path), "rel_path": rel,
                                 "error": record["error"]})
                continue
            if manifest_problems:
                record["error"] = "; ".join(manifest_problems)
                failures.append({"manifest": str(manifest_path), "rel_path": rel,
                                 "error": record["error"]})
                continue
            candidate = (vault / rel).absolute()
            try:
                resolved = candidate.resolve()
                resolved.relative_to(vault.resolve())
            except (OSError, ValueError) as exc:
                record["error"] = f"output escapes vault: {exc}"
                failures.append({"manifest": str(manifest_path), "rel_path": rel,
                                 "error": record["error"]})
                continue
            record["exists"] = candidate.is_file()
            record["applied"] = status == "applied"
            if candidate.is_file():
                try:
                    raw = candidate.read_bytes()
                    text = raw.decode("utf-8")
                    record["sha256"] = hashlib.sha256(raw).hexdigest()
                    parsed_metadata = _frontmatter_metadata(text)
                    # Keep only the identity proof in round metrics; the raw
                    # card bytes remain available at the current target and
                    # the provider/apply evidence preserves full details.
                    metadata = {
                        "type": parsed_metadata.get("type"),
                        "object_id": parsed_metadata.get("object_id"),
                        "revision": parsed_metadata.get("revision"),
                    }
                    record["metadata"] = metadata
                    record["card_type"] = parsed_metadata.get("type")
                    record["metadata_object_id"] = parsed_metadata.get("object_id")
                    record["metadata_revision"] = parsed_metadata.get("revision")
                    record["replacement_character"] = "\ufffd" in text
                except (OSError, UnicodeDecodeError) as exc:
                    record["error"] = f"output unreadable: {exc}"
            expected = record.get("expected_sha256")
            manifest_sha = record.get("manifest_sha256")
            metadata = record.get("metadata")
            metadata_revision = record.get("metadata_revision")
            revision_matches = (
                isinstance(record.get("revision"), int)
                and not isinstance(record.get("revision"), bool)
                and record.get("revision") > 0
                and isinstance(metadata_revision, (int, str))
                and str(metadata_revision) == str(record.get("revision"))
            )
            valid = (
                not manifest_problems
                and record.get("applied") is True
                and record.get("exists") is True
                and record.get("content_verified") is True
                and _is_sha256(expected)
                and _is_sha256(manifest_sha)
                and expected == manifest_sha
                and record.get("sha256") == expected
                and record.get("card_type") in counts
                and record.get("replacement_character") is False
                and isinstance(metadata, dict)
                and isinstance(record.get("object_id"), str)
                and bool(record.get("object_id"))
                and metadata.get("object_id") == record.get("object_id")
                and revision_matches
                and isinstance(record.get("canonical_path"), str)
                and record.get("canonical_path").replace("\\", "/") == rel
            )
            record["counted"] = bool(valid)
            if valid:
                verified_by_rel.setdefault(rel, record)
            else:
                error = record.get("error") or "output failed manifest/content validation"
                failures.append({
                    "manifest": record.get("manifest"),
                    "rel_path": rel,
                    "error": error,
                    "status": record.get("status"),
                    "card_type": record.get("card_type"),
                    "sha256": record.get("sha256"),
                    "expected_sha256": expected,
                })

    for record in verified_by_rel.values():
        counts[record["card_type"]] += 1
    return {
        "manifest_paths": [str(path) for path in manifests],
        "observed": observed,
        "verified_rel_paths": sorted(verified_by_rel),
        "card_type_counts": counts,
        "failures": failures,
    }


def _source_bytes(vault: Path) -> dict[str, dict[str, Any]]:
    """Capture the exact fixture input bytes used by an intake round."""
    sources = {**ROUND_SOURCES, ROUND_DIALOGUE[0]: ROUND_DIALOGUE[1]}
    result: dict[str, dict[str, Any]] = {}
    for fixture_id, rel in sources.items():
        path = vault / rel
        raw = path.read_bytes() if path.is_file() else b""
        result[fixture_id] = {
            "rel": rel,
            "exists": path.is_file(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest() if path.is_file() else None,
        }
    return result


def _jsonable(value: Any) -> Any:
    """Convert provider evidence to JSON without changing the sent payload."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def _write_provider_evidence(artifact_root: Path, round_index: int,
                             call_log: list[dict[str, Any]]) -> str:
    """Persist raw prompt/payload/response/error records for this round."""
    provider_dir = artifact_root / "rounds" / f"round-{round_index:02d}" / "provider"
    provider_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, call in enumerate(call_log, 1):
        record = _jsonable(call)
        path = provider_dir / f"attempt-{index:03d}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
    calls_path = provider_dir / "calls.jsonl"
    calls_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return str(calls_path)


def _call_stage_kind(call: dict[str, Any]) -> str:
    """Normalize provider evidence to the five generator stages.

    Smoke and live adapters record different stage labels, while production
    payloads carry stable task names.  Use both without changing the payload
    sent to a provider; unknown records remain visible and cannot satisfy an
    expected split.
    """
    stage = str(call.get("stage") or "").strip().lower()
    payload = call.get("payload")
    task = str(payload.get("task") or "").strip().lower() if isinstance(payload, dict) else ""
    if stage.startswith("source:") or stage == "source" or (
            isinstance(payload, dict) and isinstance(payload.get("text"), str)
            and not task):
        return "source"
    if stage.startswith("seed:") or stage == "seed" or task == "atomic_seed":
        return "seed"
    if stage.startswith("concept:") or stage == "concept" or "concept" in task:
        return "concept"
    if stage.startswith("case:") or stage == "case" or "case" in task:
        return "case"
    if stage.startswith("topic:") or stage == "topic" or "topic" in task:
        return "topic"
    return "unknown"


def _stage_split(call_log: list[dict[str, Any]]) -> dict[str, int]:
    split = {**{name: 0 for name in EXPECTED_STAGE_SPLIT}, "unknown": 0}
    for call in call_log:
        if call.get("adapter_attempted") is False:
            continue
        split[_call_stage_kind(call)] += 1
    return split


def run_round(round_index: int, artifact_root: Path, mode: str,
              adapter: PublicClaudeAdapter | None,
              frozen: dict[str, str], *, intake_only: bool = False,
              max_round_calls: int = HARD_MAX_CALLS_PER_ROUND,
              max_total_calls: int = HARD_MAX_TOTAL_CALLS,
              total_attempts_before: int = 0) -> dict[str, Any]:
    if not (1 <= max_round_calls <= HARD_MAX_CALLS_PER_ROUND):
        raise RunnerError(
            f"max_round_calls must be between 1 and {HARD_MAX_CALLS_PER_ROUND}")
    if not (1 <= max_total_calls <= HARD_MAX_TOTAL_CALLS):
        raise RunnerError(
            f"max_total_calls must be between 1 and {HARD_MAX_TOTAL_CALLS}")
    verify_versions(frozen)
    vault = artifact_root / "rounds" / f"round-{round_index:02d}" / "vault"
    prepare_vault(vault, artifact_root)
    cfg = build_cfg(vault)
    fixture_hashes = _fixture_hashes()
    source_before = _source_bytes(vault)

    call_log: list[dict[str, Any]] = []
    stage_context: dict[str, Any] = {"stage": None}
    source_card_by_source: dict[str, str] = {}
    smoke_attempts = [0]
    if mode == "smoke":
        base_provider = make_smoke_provider(round_index, call_log)

        def provider(*args: Any) -> str:
            # The offline provider has no adapter to enforce a budget.  Count
            # before invoking it so failures/timeouts consume an attempt and
            # a refused extra call never reaches the mock or production code.
            if smoke_attempts[0] >= max_round_calls:
                raise RunnerError(
                    f"round {round_index} budget exhausted: "
                    f"{smoke_attempts[0]}/{max_round_calls}; attempt refused before launch"
                )
            if total_attempts_before + smoke_attempts[0] >= max_total_calls:
                raise RunnerError(
                    f"global call budget exhausted: "
                    f"{total_attempts_before + smoke_attempts[0]}/{max_total_calls}; "
                    "attempt refused before launch"
                )
            smoke_attempts[0] += 1
            return base_provider(*args)
    else:
        assert adapter is not None  # live mode always constructs the adapter
        bundle = PublicContextBundle()
        for fid in {**ROUND_SOURCES, ROUND_DIALOGUE[0]: ROUND_DIALOGUE[1]}:
            bundle.register_fixture(fid, fid)
        provider = make_live_provider(adapter, round_index, bundle, call_log,
                                      stage_context, source_card_by_source)

    round_result: dict[str, Any] = {
        "round": round_index, "mode": mode, "vault": str(vault),
        "provider_calls": 0, "provider_calls_logged": 0,
        "stage_split": {**{name: 0 for name in EXPECTED_STAGE_SPLIT}, "unknown": 0},
        "expected_stage_split": {}, "stages": {}, "card_type_counts": {},
        "incomplete_reasons": [], "failures": [],
    }

    def add_reason(reason: str) -> None:
        if reason not in round_result["incomplete_reasons"]:
            round_result["incomplete_reasons"].append(reason)

    def record_failure(phase: str, exc: BaseException) -> None:
        round_result["failures"].append({"phase": phase, **_error_record(exc)})
        add_reason(f"{phase}:exception")

    def record_stage(name: str, result: dict[str, Any], *, allow_skip: bool = False) -> None:
        round_result["stages"][name] = result
        if allow_skip and result.get("skipped"):
            return
        if result.get("applied") is True and result.get("plan_path"):
            validation = result.get("plan_validation")
            if not isinstance(validation, dict):
                validation = _validate_saved_plan(result["plan_path"])
                result["plan_validation"] = validation
            if not validation.get("ok"):
                result["applied"] = False
                result["blocked"] = "producer_output_incomplete"
        if result.get("applied") is not True:
            blocked = result.get("blocked") or "incomplete"
            add_reason(f"{name}:{blocked}")
            if result.get("failure"):
                round_result["failures"].append({
                    "phase": name, **result["failure"]})

    try:
        steward = _load_steward()

        # -- initialization plan (4 source calls + 1 atomic seed call) --
        stage_context["stage"] = "initialization"
        init_result: dict[str, Any]
        plan: dict[str, Any] | None = None
        try:
            with _PatchedLLM(provider):
                plan = steward.build_initialization_plan(
                    cfg, plan_run_id=f"public-baseline-r{round_index:02d}-init",
                    stamp=steward.stamp(), executor_plan_fn=steward.mvp_executor_plan,
                    page_requires_manual_review=steward.page_requires_manual_review,
                    duplicate_page_targets=steward.duplicate_page_targets,
                    page_has_blocked_placeholder=lambda p: steward.page_has_blocked_placeholder(p, cfg),
                    planned_raw_coverage=steward.planned_raw_coverage,
                    batch_size=6, use_llm=True, include_all=True)
            init_result = _save_review_apply(steward, cfg, plan)
            if mode == "live" and init_result.get("applied") is True:
                try:
                    registered_sources, source_card_provenance = (
                        _register_applied_source_cards(vault, plan, bundle))
                    source_card_by_source.update(registered_sources)
                    init_result["source_card_provenance"] = source_card_provenance
                    if not source_card_provenance.get("ok"):
                        init_result["applied"] = False
                        init_result["blocked"] = "source_card_provenance"
                except (Exception, SystemExit) as exc:
                    init_result["source_card_provenance"] = {
                        "ok": False, "registered": [],
                        "errors": [_error_record(exc)["message"]],
                    }
                    init_result["applied"] = False
                    init_result["blocked"] = "source_card_provenance"
        except (Exception, SystemExit) as exc:
            record_failure("initialization", exc)
            init_result = {"applied": False, "blocked": "plan_failed",
                           "failure": _error_record(exc)}
        record_stage("initialization", init_result)

        if intake_only:
            # Narrow checkpoint mode intentionally stops after the accepted
            # intake plan.  It does not call a second writer.
            record_stage("finalize", {
                "applied": False, "skipped": "intake_only_checkpoint",
            }, allow_skip=True)
        elif init_result.get("applied") is not True:
            record_stage("finalize", {
                "applied": False,
                "skipped": "initialization_incomplete",
                "blocked": "upstream_stage_failed",
            }, allow_skip=True)
            add_reason("finalize:upstream_stage_failed")
        else:
            # -- finalize plan (concept + case + topic, one call each) --
            stage_context["stage"] = "finalize"
            finalize_plan: dict[str, Any] | None = None
            try:
                finalize_plan = steward.make_finalize_plan(
                    cfg, plan_run_id=f"public-baseline-r{round_index:02d}-finalize",
                    stamp=steward.stamp(), use_llm=True,
                    providers={"concept": provider, "case": provider, "topic": provider})
            except (Exception, SystemExit) as exc:
                record_failure("finalize", exc)
                record_stage("finalize", {
                    "applied": False, "blocked": "plan_failed",
                    "failure": _error_record(exc),
                })
            else:
                if finalize_plan is None:
                    record_stage("finalize", {
                        "applied": False, "blocked": "plan_empty",
                    })
                else:
                    try:
                        finalize_result = _save_review_apply(steward, cfg, finalize_plan)
                    except (Exception, SystemExit) as exc:
                        record_failure("finalize", exc)
                        finalize_result = {
                            "applied": False, "blocked": "stage_exception",
                            "failure": _error_record(exc),
                        }
                    record_stage("finalize", finalize_result)

        # -- accounting --
        try:
            call_errors = [call for call in call_log if call.get("error")]
            round_result["call_errors"] = call_errors
            if call_errors:
                add_reason(f"provider_call_errors:{len(call_errors)}")
                for call in call_errors:
                    round_result["failures"].append({
                        "phase": "provider_call",
                        "stage": call.get("stage"),
                        **(call.get("error") or {}),
                    })
            observed_outputs = _collect_observed_outputs(vault)
            round_result["manifest_paths"] = observed_outputs["manifest_paths"]
            round_result["observed_outputs"] = observed_outputs["observed"]
            if observed_outputs["manifest_paths"]:
                round_result["card_type_counts"] = observed_outputs["card_type_counts"]
                for failure in observed_outputs["failures"]:
                    round_result["failures"].append({
                        "phase": "typed_output", **failure})
                if observed_outputs["failures"]:
                    add_reason(f"typed_output_failures:{len(observed_outputs['failures'])}")
            else:
                # A file walk is not evidence of a successful writer apply.
                # Without a normal manifest/reconcile record there are zero
                # verified outputs, even if pages happen to be on disk.
                round_result["card_type_counts"] = {
                    card_type: 0 for card_type in CARD_TYPES_REQUIRED}
                add_reason("missing_apply_manifest")
            counts = round_result["card_type_counts"]
            required_types = ("source-note", "seed-card") if intake_only else CARD_TYPES_REQUIRED
            for card_type in required_types:
                if counts.get(card_type, 0) < 1:
                    add_reason(f"missing_card_type:{card_type}")
            split = _stage_split(call_log)
            round_result["stage_split"] = split
            expected_split = {
                name: count for name, count in EXPECTED_STAGE_SPLIT.items()
                if not intake_only or name in {"source", "seed"}
            }
            round_result["expected_stage_split"] = expected_split
            if mode == "smoke":
                attempts = smoke_attempts[0]
            else:
                attempts = adapter.round_attempts.get(round_index, 0) if adapter else 0
            round_result["provider_calls"] = attempts
            round_result["provider_calls_logged"] = len(call_log)
            expected_calls = sum(expected_split.values())
            if attempts != expected_calls:
                add_reason(f"provider_calls:{attempts}!={expected_calls}")
            for stage_name, expected in expected_split.items():
                actual = split.get(stage_name, 0)
                if actual != expected:
                    add_reason(f"stage_split:{stage_name}={actual}!={expected}")
            if split.get("unknown", 0):
                add_reason(f"stage_split:unknown={split['unknown']}")
            if attempts > max_round_calls:
                add_reason(f"round_call_bound:{attempts}>{max_round_calls}")
            total_attempts = (
                adapter.total_attempts if mode == "live" and adapter is not None
                else total_attempts_before + attempts
            )
            round_result["total_provider_calls"] = total_attempts
            if total_attempts > max_total_calls:
                add_reason(f"total_call_bound:{total_attempts}>{max_total_calls}")
        except (Exception, SystemExit) as exc:
            record_failure("accounting", exc)

        source_after = _source_bytes(vault)
        round_result["source_integrity"] = {
            "before": source_before,
            "after": source_after,
            "unchanged": source_before == source_after,
        }
        if source_before != source_after:
            add_reason("source_bytes_changed")

    except (Exception, SystemExit) as exc:
        # Keep a round record even when an unexpected production-stage error
        # escapes the narrower guards above.
        record_failure("round", exc)
    finally:
        round_result["provider_evidence"] = _write_provider_evidence(
            artifact_root, round_index, call_log)

    # Preserve actual call facts even when the separate output accounting
    # block itself failed.  A reporting exception must not turn a real adapter
    # timeout/failure into an apparent zero-call round.
    actual_attempts = (
        smoke_attempts[0] if mode == "smoke"
        else (adapter.round_attempts.get(round_index, 0) if adapter else 0)
    )
    round_result["provider_calls"] = actual_attempts
    round_result["provider_calls_logged"] = len(call_log)
    actual_split = _stage_split(call_log)
    round_result["stage_split"] = actual_split
    expected_split = {
        name: count for name, count in EXPECTED_STAGE_SPLIT.items()
        if not intake_only or name in {"source", "seed"}
    }
    round_result["expected_stage_split"] = expected_split
    expected_calls = sum(expected_split.values())
    if actual_attempts != expected_calls:
        add_reason(f"provider_calls:{actual_attempts}!={expected_calls}")
    for stage_name, expected in expected_split.items():
        actual = actual_split.get(stage_name, 0)
        if actual != expected:
            add_reason(f"stage_split:{stage_name}={actual}!={expected}")
    if actual_split.get("unknown", 0):
        add_reason(f"stage_split:unknown={actual_split['unknown']}")
    if actual_attempts > max_round_calls:
        add_reason(f"round_call_bound:{actual_attempts}>{max_round_calls}")
    total_attempts = (
        adapter.total_attempts if mode == "live" and adapter is not None
        else total_attempts_before + actual_attempts
    )
    round_result["total_provider_calls"] = total_attempts
    if total_attempts > max_total_calls:
        add_reason(f"total_call_bound:{total_attempts}>{max_total_calls}")

    # The intake checkpoint has an explicit scope marker.  Finalize is
    # intentionally pending there; the round outcome only covers its declared
    # intake acceptance criteria.  Stage flags are authoritative even if
    # generated files happen to be present after a failed apply.
    round_result["scope"] = "intake-only" if intake_only else "full"
    if round_result["incomplete_reasons"]:
        round_result["outcome"] = "incomplete"
    else:
        round_result["outcome"] = "complete"
    return round_result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_metrics(artifact_root: Path, payload: dict[str, Any]) -> None:
    (artifact_root / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evaluate_public_baseline.py",
        description="Public baseline evaluation over the actual pipeline "
                    "(canonical synthetic fixtures only).")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--smoke", action="store_true",
                       help="offline smoke: test-only mock provider, no CLI")
    modes.add_argument("--live", action="store_true",
                       help="live: explicit root-run adapter mode (coding "
                            "sessions must never pass this)")
    parser.add_argument("--output-dir", required=True,
                        help="fresh artifact root; existing dirs are refused")
    parser.add_argument("--rounds", type=int, default=3,
                        choices=range(1, HARD_MAX_ROUNDS + 1),
                        help="rounds to run (default 3, hard max 3)")
    parser.add_argument("--intake-only", action="store_true",
                        help="checkpoint mode: stop after intake save/review/apply")
    parser.add_argument("--max-total-calls", type=int, default=30)
    parser.add_argument("--max-round-calls", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)

    if not (1 <= args.max_round_calls <= HARD_MAX_CALLS_PER_ROUND):
        print(
            f"max-round-calls must be between 1 and {HARD_MAX_CALLS_PER_ROUND}",
            file=sys.stderr,
        )
        return 2
    if not (1 <= args.max_total_calls <= HARD_MAX_TOTAL_CALLS):
        print(
            f"max-total-calls must be between 1 and {HARD_MAX_TOTAL_CALLS}",
            file=sys.stderr,
        )
        return 2

    mode = "smoke" if args.smoke else "live"
    try:
        artifact_root = _assert_fresh_artifact_root(Path(args.output_dir))
        frozen = freeze_versions()
    except (OSError, RunnerError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        artifact_root.mkdir(parents=True)
        _assert_no_reparse_components(artifact_root, "artifact root")
        (artifact_root / "version-freeze.json").write_text(
            json.dumps(frozen, indent=1, sort_keys=True), encoding="utf-8")
        (artifact_root / "artifact-root.json").write_text(json.dumps({
            "marker": "public-baseline-artifact-root",
            "synthetic_only": True,
            "fresh": True,
            "root": str(artifact_root),
            "mode": mode,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except (OSError, RunnerError) as exc:
        print(f"artifact root setup failed: {exc}", file=sys.stderr)
        return 2

    adapter = None
    try:
        if mode == "live":
            config = AdapterConfig.from_cfg({"public_evaluation": {
                "enabled": True,
                "max_total_calls": args.max_total_calls,
                "max_round_calls": args.max_round_calls,
                "timeout_seconds": args.timeout_seconds,
            }})
            adapter = PublicClaudeAdapter(
                config, RunRecorder(artifact_root, "adapter-evidence"))
    except PublicEvaluationError as exc:
        print(f"adapter configuration error: {exc}", file=sys.stderr)
        return 2

    report: dict[str, Any] = {
        "mode": mode, "rounds_requested": args.rounds,
        "target_calls_per_round": TARGET_CALLS_PER_ROUND,
        "hard_bounds": {"per_round": args.max_round_calls,
                        "total": args.max_total_calls},
        "semantic_pass": None,
        "limitation": "Execution/schema/provenance metrics only; content "
                      "review is Astra's independent job. Fixture auto-approval "
                      "is an engineering fixture approval inside the marked "
                      "synthetic vault, NOT human semantic acceptance.",
        "version_freeze": {
            "file_count": len(frozen),
            "runner_sha256": frozen.get("scripts/evaluate_public_baseline.py"),
            "smoke_support_sha256": frozen.get("tests/public_round_support.py"),
            "files": frozen,
        },
        "rounds": [],
    }
    exit_code = 0
    total_attempts = 0
    try:
        for round_index in range(args.rounds):
            result = run_round(round_index, artifact_root, mode, adapter, frozen,
                               intake_only=args.intake_only,
                               max_round_calls=args.max_round_calls,
                               max_total_calls=args.max_total_calls,
                               total_attempts_before=total_attempts)
            report["rounds"].append(result)
            total_attempts += result.get("provider_calls", 0)
            if result["outcome"] != "complete":
                exit_code = exit_code or 1
        report["provider_calls_total"] = total_attempts
        if total_attempts > args.max_total_calls:
            report["incomplete"] = "total provider call bound exceeded"
            exit_code = exit_code or 1
        verify_versions(frozen)
    except RunnerError as exc:
        report["blocked"] = str(exc)
        exit_code = 2
    _write_metrics(artifact_root, report)
    print(json.dumps({"exit_code": exit_code,
                      "rounds": [r.get("outcome") for r in report["rounds"]],
                      "metrics": str(artifact_root / "metrics.json")},
                     ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
