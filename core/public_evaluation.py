"""Bounded public Claude provider adapter (T10 checkpoint A, TEST-ONLY).

This module is the provider-adapter layer for the public baseline evaluation
harness. It is deliberately narrow:

- The provider seam is compatible with the real generator callables: a
  bound round accepts ``(cfg, system_prompt, payload)`` (generators that
  pass the production cfg) and ``(system_prompt, payload)``. The cfg
  argument is accepted for call-shape compatibility but its VALUES ARE
  IGNORED — the adapter always uses its frozen construction-time
  :class:`AdapterConfig`; a generator cfg never overrides model, bounds,
  timeout or liveness. Rounds are selected explicitly via
  :meth:`PublicClaudeAdapter.bind_for_round`; there is no implicit
  round 0.
- The adapter returns the EXACT ``result`` string from the installed
  Claude CLI ``-p --output-format json`` envelope. The result must be an
  actual JSON string; ``null``/objects/arrays are rejected (raw evidence
  preserved). JSON interpretation is owned by generators, never repaired
  here. ``is_error`` responses, nonzero exit codes, missing ``result``
  fields and timeouts are explicit errors. No invisible retry, no
  fallback provider.
- Live invocation must be EXPLICITLY enabled as a real JSON boolean;
  offline tests patch :func:`subprocess.run` and assert no real
  CLI/network use. Every subprocess attempt — including failures and
  timeouts — consumes budget, checked and refused BEFORE the attempt.
  Bounds: <=30 calls total, <=10 per round (callers may only lower them).
- Unattended invocation uses print mode: the argv starts with the native
  executable (npm-shim-confirmed path) followed by ``-p``. Content never
  crosses a shell: the JSON user payload goes via stdin and the exact
  generator system prompt via ``--system-prompt``.
- The model process runs in a freshly created empty temp directory outside
  the checkout / private vault ancestry, so repository prompts, AGENTS.md
  and CLAUDE.md files cannot be auto-loaded. ``--restricted`` plus
  ``--tools ""``, ``--strict-mcp-config`` and ``--disable-slash-commands``
  give no-project/no-user-settings execution without ``--bare``'s OAuth
  breakage. No session persistence, no resume, no credential access or
  auth change by this harness.
- Model input is the EXACT payload dict/list/str built by the accepted
  generators. :class:`PublicContextBundle` registers payloads with public
  source provenance (allowlisted synthetic fixture hashes and registered
  public intermediates) and serializes with key-order canonicalization
  only — deep JSON equality with the generator argument is preserved and
  no wrapper or extra fields are added.

TRUST BOUNDARY (stated honestly): hash/provenance registration is
*accounting*, not proof that arbitrary free strings are public. The run
harness is trusted to construct payloads from allowlisted fixtures and
registered public intermediates; the bundle verifies registered documents
byte-for-byte and blocks manifest annotation keys/values anywhere in the
payload, but it cannot cryptographically prove the provenance of a free
string inside a generator payload. The root operator enables live mode
only after the coding session has exited.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "claude-opus-5[1m]"
DEFAULT_EFFORT = "medium"
DEFAULT_MAX_TOTAL_CALLS = 30
DEFAULT_MAX_ROUND_CALLS = 10
ABSOLUTE_MAX_TOTAL_CALLS = 30
ABSOLUTE_MAX_ROUND_CALLS = 10
DEFAULT_TIMEOUT_SECONDS = 600

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "card-baseline"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# Keys of manifest fixture entries that are evaluation annotations. They are
# for Astra's independent review only and must never reach a model payload,
# at ANY nesting depth of a registered payload.
_ANNOTATION_KEYS = (
    "expected_units",
    "expected_speaker_markers",
    "prohibited_overclaims",
)


class PublicEvaluationError(RuntimeError):
    """Explicit adapter/registration failure. Never silently repaired."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Immutable allowlisted fixture snapshots
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureSnapshot:
    """One manifest-listed synthetic fixture, pinned to exact bytes."""

    id: str
    path: Path
    material_kind: str
    sha256: str
    text: str


def load_fixture_manifest(manifest_path: Path | None = None) -> dict[str, FixtureSnapshot]:
    """Load ONLY the card-baseline manifest and pin its synthetic fixtures.

    Every entry must be marked ``synthetic: true``; the referenced file must
    exist under the fixture directory, must not escape it, and is hashed at
    load time. Annotation keys are stripped so they can never become model
    content. A manifest outside the canonical directory, a non-synthetic
    entry, a path escape or a missing file is rejected.
    """
    path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    resolved = path.resolve()
    base = FIXTURE_DIR.resolve()
    if resolved != MANIFEST_PATH.resolve() and base not in resolved.parents:
        raise PublicEvaluationError(
            f"fixture manifest must live under {base.as_posix()}: {resolved.as_posix()}"
        )
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublicEvaluationError(f"cannot read fixture manifest: {exc}") from exc

    snapshots: dict[str, FixtureSnapshot] = {}
    for entry in data.get("fixtures", []):
        if not entry.get("synthetic"):
            raise PublicEvaluationError(
                f"fixture {entry.get('id')!r} is not marked synthetic; refusing"
            )
        rel = str(entry.get("path", ""))
        # Manifest paths are repo-root relative ("tests/fixtures/card-baseline/x.md").
        repo_root = Path(__file__).resolve().parents[1]
        candidates = [(resolved.parent / rel).resolve(), (repo_root / rel).resolve()]
        valid = [c for c in candidates if base == c or base in c.parents]
        if not valid:
            raise PublicEvaluationError(f"fixture path escapes allowlist dir: {rel}")
        existing = [c for c in valid if c.is_file()]
        if not existing:
            raise PublicEvaluationError(f"fixture file missing: {rel}")
        candidate = existing[0]
        raw = candidate.read_bytes()
        snap = FixtureSnapshot(
            id=str(entry["id"]),
            path=candidate,
            material_kind=str(entry.get("material_kind", "")),
            sha256=sha256_bytes(raw),
            text=raw.decode("utf-8"),
        )
        snapshots[snap.id] = snap
    if not snapshots:
        raise PublicEvaluationError("fixture manifest lists no synthetic fixtures")
    return snapshots


def fixture_annotation(snapshot_id: str, manifest_path: Path | None = None) -> dict[str, Any]:
    """Reviewer-only annotations for a fixture (expected answers / rubric).

    These are for Astra's independent content review; the bundle refuses to
    let them into any registered payload, at any nesting depth.
    """
    path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data.get("fixtures", []):
        if entry.get("id") == snapshot_id:
            return {k: entry[k] for k in _ANNOTATION_KEYS if k in entry}
    raise PublicEvaluationError(f"unknown fixture id: {snapshot_id!r}")


# ---------------------------------------------------------------------------
# Provenance accounting + exact-payload registration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredDocument:
    """A document provenance-accounted for payload construction.

    ``provenance`` is ``fixture`` for an exact manifest snapshot or
    ``public_generated`` for a registered intermediate whose bytes hash to
    the supplied ``sha256``. This is accounting for the run harness (which
    is trusted to build payloads from these documents); it is NOT proof
    that a free string is public.
    """

    name: str
    kind: str
    provenance: str  # "fixture" | "public_generated"
    sha256: str
    text: str


@dataclass(frozen=True)
class PublicPayload:
    """The EXACT generator payload plus its provenance accounting.

    ``data`` is the generator's own dict/list/str argument, unmodified.
    ``to_json`` canonicalizes key order only; deep JSON equality with the
    generator argument is preserved and no wrapper or extra fields are
    added.
    """

    data: Any
    provenance: dict[str, str]  # document name -> sha256 accounting

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, sort_keys=True)


def _check_no_annotations(value: Any, banned_keys: tuple[str, ...],
                         where: str = "payload") -> None:
    """Refuse manifest annotation KEYS at ANY nesting depth.

    Only key names are checked, not values: legitimate fixture-derived
    content legitimately overlaps annotation strings (e.g. the seed
    payload's speaker is a manifest expected_speaker_marker), but a
    generator payload never carries an annotation KEY.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key in banned_keys:
                raise PublicEvaluationError(
                    f"manifest annotation key {key!r} found in {where}; "
                    "annotations never become model content"
                )
            _check_no_annotations(item, banned_keys, where)
    elif isinstance(value, list):
        for item in value:
            _check_no_annotations(item, banned_keys, where)


class PublicContextBundle:
    """Run-created bundle: provenance accounting + exact payload registration.

    Two distinct responsibilities:

    - ``register_fixture`` / ``register_generated`` pin the PUBLIC source
      documents (exact manifest snapshots, or intermediates whose bytes
      hash to the supplied sha256) that the run harness used to build
      payloads. Their hashes feed the evidence records.
    - ``register_payload`` registers the EXACT generator payload argument
      (dict/list/str — a source chunk dict, a seed units list, a
      concept/case/topic documents payload) together with the names of the
      registered documents it was built from. Serialization preserves deep
      JSON equality; no wrapper is added. Annotation keys are refused at
      any nesting depth (values are not checked: legitimate fixture-derived
      content overlaps annotation strings, e.g. seed payload speakers).

    The bundle cannot prove a free string is public — that is the trusted
    caller boundary, documented in the module docstring.
    """

    def __init__(self, manifest_path: Path | None = None) -> None:
        self._fixtures = load_fixture_manifest(manifest_path)
        self._documents: dict[str, RegisteredDocument] = {}
        self._banned_keys = _ANNOTATION_KEYS

    # -- source documents (accounting) ------------------------------------

    def register_fixture(self, name: str, fixture_id: str) -> RegisteredDocument:
        snap = self._fixtures.get(fixture_id)
        if snap is None:
            raise PublicEvaluationError(f"fixture id not in manifest: {fixture_id!r}")
        doc = RegisteredDocument(
            name=name, kind=snap.material_kind, provenance="fixture",
            sha256=snap.sha256, text=snap.text,
        )
        self._documents[name] = doc
        return doc

    def register_generated(
        self, name: str, kind: str, text: str, expected_sha256: str
    ) -> RegisteredDocument:
        """Register a PUBLIC-generated intermediate with its exact hash."""
        actual = sha256_text(text)
        if actual != expected_sha256:
            raise PublicEvaluationError(
                f"generated document {name!r} hash mismatch: "
                f"expected {expected_sha256}, got {actual}"
            )
        doc = RegisteredDocument(
            name=name, kind=kind, provenance="public_generated",
            sha256=actual, text=text,
        )
        self._documents[name] = doc
        return doc

    def source_hashes(self) -> dict[str, str]:
        return {name: doc.sha256 for name, doc in self._documents.items()}

    # -- exact generator payloads ------------------------------------------

    def register_payload(
        self, payload: Any, built_from: list[str]
    ) -> PublicPayload:
        """Register the EXACT generator payload for adapter submission.

        ``payload`` must be the generator's own argument (dict, list or
        plain string), unmodified — no wrapper is added and no document
        fields are injected. ``built_from`` names the registered source
        documents this payload was constructed from (provenance
        accounting recorded in evidence).
        """
        if not isinstance(payload, (dict, list, str)):
            raise PublicEvaluationError(
                "payload must be the exact generator argument (dict, list or str)"
            )
        for name in built_from:
            if name not in self._documents:
                raise PublicEvaluationError(
                    f"provenance document {name!r} was not registered in this bundle"
                )
        _check_no_annotations(payload, self._banned_keys)
        return PublicPayload(
            data=payload,
            provenance={name: self._documents[name].sha256 for name in built_from},
        )


# ---------------------------------------------------------------------------
# Adapter configuration
# ---------------------------------------------------------------------------


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise PublicEvaluationError(
            f"{name} must be an explicit JSON boolean (got {type(value).__name__})"
        )
    return value


def _strict_positive_int(value: Any, name: str) -> int:
    # bool is an int subclass; exclude it explicitly.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PublicEvaluationError(f"{name} must be a positive integer")
    return value


def _strict_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicEvaluationError(f"{name} must be a non-empty string")
    return value


@dataclass
class AdapterConfig:
    """Frozen adapter settings. Live mode is opt-in by the root operator."""

    live_enabled: bool = False
    executable: list[str] = field(default_factory=list)  # argv prefix, e.g. [claude.exe]
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    max_total_calls: int = DEFAULT_MAX_TOTAL_CALLS
    max_round_calls: int = DEFAULT_MAX_ROUND_CALLS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.max_total_calls > ABSOLUTE_MAX_TOTAL_CALLS:
            raise PublicEvaluationError(
                f"max_total_calls {self.max_total_calls} exceeds hard bound "
                f"{ABSOLUTE_MAX_TOTAL_CALLS}"
            )
        if self.max_round_calls > ABSOLUTE_MAX_ROUND_CALLS:
            raise PublicEvaluationError(
                f"max_round_calls {self.max_round_calls} exceeds hard bound "
                f"{ABSOLUTE_MAX_ROUND_CALLS}"
            )
        if self.max_total_calls < 1 or self.max_round_calls < 1:
            raise PublicEvaluationError("call bounds must be >= 1")
        if self.timeout_seconds < 1:
            raise PublicEvaluationError("timeout_seconds must be >= 1")

    @classmethod
    def from_cfg(cls, cfg: dict[str, Any]) -> "AdapterConfig":
        live = cfg.get("public_evaluation")
        if not isinstance(live, dict):
            raise PublicEvaluationError("cfg['public_evaluation'] must be a mapping")
        executable = live.get("executable")
        if executable is not None:
            if not isinstance(executable, list) or not executable:
                raise PublicEvaluationError(
                    "public_evaluation.executable must be a non-empty argv list "
                    "(never a shell string)"
                )
            for arg in executable:
                if not isinstance(arg, str) or not arg or arg.strip() != arg:
                    raise PublicEvaluationError(
                        "executable argv entries must be plain path tokens"
                    )
        # Strict typing: a string "false"/"30" never enables or widens anything.
        return cls(
            live_enabled=_strict_bool(live.get("enabled", False), "public_evaluation.enabled"),
            executable=[str(a) for a in executable] if executable else [],
            model=_strict_str(live.get("model", DEFAULT_MODEL), "public_evaluation.model"),
            effort=_strict_str(live.get("effort", DEFAULT_EFFORT), "public_evaluation.effort"),
            max_total_calls=_strict_positive_int(
                live.get("max_total_calls", DEFAULT_MAX_TOTAL_CALLS),
                "public_evaluation.max_total_calls"),
            max_round_calls=_strict_positive_int(
                live.get("max_round_calls", DEFAULT_MAX_ROUND_CALLS),
                "public_evaluation.max_round_calls"),
            timeout_seconds=_strict_positive_int(
                live.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
                "public_evaluation.timeout_seconds"),
        )


def default_executable() -> list[str]:
    """Native CLI path confirmed via the npm shim (no shell resolution)."""
    return [
        r"C:/Users/zooma/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    ]


# ---------------------------------------------------------------------------
# Run recorder (evidence)
# ---------------------------------------------------------------------------


class RunRecorder:
    """Appends per-attempt JSON evidence under a versioned run directory.

    Output is bounded to the requested artifact root; an existing run or
    attempt file is never overwritten.
    """

    def __init__(self, artifact_root: Path, run_id: str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.run_id = run_id
        self.run_dir = self.artifact_root / run_id
        if self.run_dir.exists():
            raise PublicEvaluationError(
                f"refusing to overwrite existing run directory: {self.run_dir}"
            )
        (self.run_dir / "attempts").mkdir(parents=True)
        self.evidence_path = self.run_dir / "evidence.jsonl"

    def _check_path(self, path: Path) -> None:
        resolved = path.resolve()
        if self.artifact_root != resolved and self.artifact_root not in resolved.parents:
            raise PublicEvaluationError(
                f"output path escapes artifact root: {resolved.as_posix()}"
            )

    def _write(self, rel: str, data: str, mode: str = "w", encoding: str = "utf-8") -> Path:
        path = self.run_dir / rel
        self._check_path(path)
        if mode == "w" and path.exists():
            raise PublicEvaluationError(
                f"refusing to overwrite existing attempt file: {path.name}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode, encoding=encoding, newline="") as fh:
            fh.write(data)
            if mode == "a":
                fh.write("\n")
        return path

    def save_attempt_inputs(
        self, attempt_dir: str, system_prompt: str, payload: PublicPayload
    ) -> None:
        self._write(f"{attempt_dir}/system_prompt.txt", system_prompt)
        self._write(f"{attempt_dir}/user_payload.json", payload.to_json() + "\n")

    def save_raw_outputs(self, attempt_dir: str, stdout: str, stderr: str) -> None:
        self._write(f"{attempt_dir}/stdout.raw.txt", stdout)
        self._write(f"{attempt_dir}/stderr.raw.txt", stderr)

    def append_evidence(self, record: dict[str, Any]) -> None:
        self._write(
            "evidence.jsonl",
            json.dumps(record, ensure_ascii=False, sort_keys=True),
            mode="a",
        )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PublicClaudeAdapter:
    """Budgeted, evidence-recording provider adapter for generator callables.

    Callable seam: use :meth:`bind_for_round` to obtain a callable that
    accepts both generator shapes — ``(cfg, system_prompt, payload)`` and
    ``(system_prompt, payload)``. The production cfg passed by generators
    is IGNORED: the adapter always uses its frozen :class:`AdapterConfig`.
    Every subprocess attempt — including failures and timeouts — consumes
    budget, refused BEFORE the attempt. No retry, no fallback.
    """

    def __init__(
        self,
        cfg: dict[str, Any] | AdapterConfig,
        recorder: RunRecorder,
        executable: list[str] | None = None,
        run_subprocess: Any = None,
    ) -> None:
        self.config = cfg if isinstance(cfg, AdapterConfig) else AdapterConfig.from_cfg(cfg)
        self.recorder = recorder
        self.executable = (
            list(executable) if executable is not None
            else (self.config.executable or default_executable())
        )
        self._run = run_subprocess if run_subprocess is not None else subprocess.run
        self.total_attempts = 0
        self.round_attempts: dict[int, int] = {}

    # -- budget -----------------------------------------------------------

    def _consume_budget(self, round_index: int) -> None:
        """Refuse BEFORE the attempt if it would exceed either bound."""
        if self.total_attempts + 1 > self.config.max_total_calls:
            raise PublicEvaluationError(
                f"global call budget exhausted: {self.total_attempts}/"
                f"{self.config.max_total_calls}; attempt refused before launch"
            )
        used_round = self.round_attempts.get(round_index, 0)
        if used_round + 1 > self.config.max_round_calls:
            raise PublicEvaluationError(
                f"round {round_index} budget exhausted: {used_round}/"
                f"{self.config.max_round_calls}; attempt refused before launch"
            )
        self.total_attempts += 1
        self.round_attempts[round_index] = used_round + 1

    # -- argv -------------------------------------------------------------

    def build_argv(self, system_prompt: str) -> list[str]:
        """Unattended print-mode argv; content never crosses a shell."""
        argv = list(self.executable)
        argv += [
            "-p",  # print mode: unattended, never interactive
            "--restricted",  # no code-running tools/WebFetch, no user/project settings
            "--tools", "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--output-format", "json",
            "--model", self.config.model,
            "--effort", self.config.effort,
            "--system-prompt", system_prompt,
        ]
        return argv

    # -- invocation -------------------------------------------------------

    def call(
        self,
        cfg: Any,
        system_prompt: str,
        payload: PublicPayload,
        round_index: int,
    ) -> str:
        """Run one model attempt and return the EXACT CLI result string.

        ``cfg`` may be the production generator config dict; its values are
        IGNORED (the adapter is bound to its construction-time frozen
        :class:`AdapterConfig`). ``payload`` must be a run-registered
        :class:`PublicPayload`. ``round_index`` is REQUIRED — rounds are
        never implicit.
        """
        if not isinstance(payload, PublicPayload):
            raise PublicEvaluationError(
                "payload must be a run-registered PublicPayload from a "
                "PublicContextBundle; arbitrary content is refused"
            )
        if not self.config.live_enabled:
            raise PublicEvaluationError(
                "live mode is not enabled; the root operator enables it "
                "explicitly after the coding session"
            )
        if not system_prompt:
            raise PublicEvaluationError("system_prompt must be non-empty")

        index = self.total_attempts + 1
        attempt_dir = f"attempts/round{round_index:02d}/attempt{index:03d}"
        self.recorder.save_attempt_inputs(attempt_dir, system_prompt, payload)

        self._consume_budget(round_index)  # refuses BEFORE launching if over budget

        argv = self.build_argv(system_prompt)
        started = time.monotonic()
        failure: str | None = None
        result_text: str | None = None
        usage: dict[str, Any] | None = None
        returncode: int | None = None
        timed_out = False
        stdout = ""
        stderr = ""

        # Fresh empty temp dir OUTSIDE the checkout/vault ancestry so no
        # repository CLAUDE.md/AGENTS.md/prompt files can be auto-loaded.
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="public-eval-cwd-") as tmp:
            cwd = Path(tmp).resolve()
            if cwd == repo_root or repo_root in cwd.parents or cwd in repo_root.parents:
                raise PublicEvaluationError("model cwd must be outside checkout ancestry")
            stdin_bytes = payload.to_json().encode("utf-8")
            try:
                completed = self._run(
                    argv,
                    input=stdin_bytes,
                    capture_output=True,
                    shell=False,           # content never crosses a shell
                    timeout=self.config.timeout_seconds,
                    cwd=str(cwd),
                )
                returncode = completed.returncode
                stdout = completed.stdout.decode("utf-8", errors="replace")
                stderr = completed.stderr.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                failure = f"timeout after {self.config.timeout_seconds}s"
                stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
                stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            except OSError as exc:
                failure = f"OSError: {safe_os_error(exc)}"

        duration = round(time.monotonic() - started, 3)
        if failure is None:
            envelope: dict[str, Any] | None = None
            try:
                envelope = json.loads(stdout)
            except ValueError:
                failure = "stdout is not a JSON envelope"
            if failure is None:
                if not isinstance(envelope, dict):
                    failure = "CLI envelope is not a JSON object"
                elif envelope.get("is_error"):
                    failure = "CLI reported is_error"
                elif "result" not in envelope:
                    failure = "CLI envelope has no result field"
                elif not isinstance(envelope["result"], str):
                    # null/object/array results are rejected, not coerced;
                    # raw stdout stays preserved in the attempt directory.
                    failure = (
                        f"CLI result is not a string "
                        f"(got {type(envelope['result']).__name__})"
                    )
                else:
                    result_text = envelope["result"]
                    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else None
            if failure is None and returncode != 0:
                failure = f"nonzero exit code {returncode}"
                result_text = None

        self.recorder.save_raw_outputs(attempt_dir, stdout, stderr)
        record = {
            "run": self.recorder.run_id,
            "round": round_index,
            "index": index,
            "model": self.config.model,
            "effort": self.config.effort,
            "system_prompt_sha256": sha256_text(system_prompt),
            "user_payload_sha256": sha256_text(payload.to_json()),
            "source_hashes": payload.provenance,
            "duration_seconds": duration,
            "usage": usage,
            "return_code": returncode,
            "timeout": timed_out,
            "result_sha256": sha256_text(result_text) if result_text is not None else None,
            "result_text": result_text,
            "failure": failure,
            "argv_logged": [
                a if a != system_prompt else "<system-prompt-logged-separately>"
                for a in argv
            ],
            "cwd_policy": "fresh empty temp dir outside checkout/vault ancestry",
        }
        self.recorder.append_evidence(record)
        if failure is not None:
            raise PublicEvaluationError(
                f"attempt {index} round {round_index} failed: {failure}"
            )
        assert result_text is not None
        return result_text

    # -- generic provider seam ---------------------------------------------

    def bind_for_round(self, round_index: int) -> "BoundRound":
        """Bind an explicit round; the returned callable fits generator seams.

        Supports both accepted generator shapes::

            provider(cfg, system_prompt, payload)   # production generators
            provider(system_prompt, payload)        # two-arg generators

        The cfg argument is accepted but its values are ignored — model,
        bounds, timeout and liveness always come from the frozen
        AdapterConfig.
        """
        return BoundRound(self, round_index)


class BoundRound:
    """One explicit round of an adapter, callable in both generator shapes."""

    def __init__(self, adapter: PublicClaudeAdapter, round_index: int) -> None:
        self._adapter = adapter
        self.round_index = round_index

    def __call__(self, *args: Any) -> str:
        if len(args) == 3:
            cfg, system_prompt, payload = args
        elif len(args) == 2:
            cfg, (system_prompt, payload) = None, args
        else:
            raise PublicEvaluationError(
                "bound provider accepts (cfg, system_prompt, payload) or "
                "(system_prompt, payload)"
            )
        return self._adapter.call(cfg, system_prompt, payload, round_index=self.round_index)


def safe_os_error(exc: OSError) -> str:
    """Log OS failures without leaking path/env detail beyond the message."""
    return f"{type(exc).__name__}: {exc.strerror or ''}".strip()
