"""M0 shared card contracts: JSON Schema is the single type truth.

Canonical schemas live in core/schemas/ and are loaded locally only; unknown
$ref targets raise instead of being fetched. Requires jsonschema>=4.18
(Draft202012Validator + referencing); there is deliberately no legacy
RefResolver fallback because it cannot reliably block remote retrieval.

Validation is fail-closed: any reported issue means the card must not become a
page or advance processed state. Existing/legacy pages are never rewritten by
this module. Source hashes refer to ORIGINAL BYTES of source files; producers
without a full-source snapshot hash record coverage/source_hashes as unknown
instead of inventing one from cleaned text (core.claims.digest hashes text and
is NOT a raw source hash).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

CARD_SCHEMA_VERSION = "m0-1"
GENERATOR_VERSION = "pks-m0"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"

# Per-skill envelope mapping: which canonical card type each skill produces.
# Skills not listed here are unaffected by card validation.
SKILL_CARD_TYPES: dict[str, str] = {
    "mindseed-grow": "seed-card",
    "topic-research-compile": "source-note",
    "case-story-bank-builder": "case-story",
}

# Producer normalization: legacy status/stage values map to the canonical
# minimal state model. Anything unmapped passes through and fails schema
# validation; the runtime never "accepts every stage".
LEGACY_STATUS_STAGE: dict[str, dict[str, dict[str, str]]] = {
    "seed-card": {
        "status": {"growing": "seed", "seed": "seed", "manual_review": "manual_review"},
        "stage": {"seed": "candidate", "candidate": "candidate", "needs_context": "needs_context"},
    },
    "source-note": {
        "status": {"growing": "growing", "compiled": "growing", "manual_review": "manual_review"},
        "stage": {"compiled": "compiling", "compiling": "compiling", "needs_context": "needs_context"},
    },
}


class CardContractError(RuntimeError):
    """A local schema/reference/envelope problem; never resolved remotely."""


def _read_json(path: Path) -> dict[str, Any]:
    # utf-8-sig tolerates an original BOM; CRLF is normalized on read.
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    return json.loads(text)


def _retrieve(uri: str) -> Resource:
    raise CardContractError(f"未登记的本地 schema 引用，拒绝解析或远程获取：{uri}")


class _LocalStore:
    """Strict local store: only preloaded canonical schemas resolve."""

    def __init__(self) -> None:
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(self, schema: dict[str, Any]) -> str:
        schema_id = str(schema.get("$id") or "")
        if not schema_id:
            raise CardContractError("注册 schema 缺少 $id")
        Draft202012Validator.check_schema(schema)
        self._schemas[schema_id] = schema
        return schema_id

    def get(self, schema_id: str) -> dict[str, Any] | None:
        return self._schemas.get(schema_id)


_STORE = _LocalStore()
for _name in ("seed-card.schema.json", "source-note.schema.json"):
    _STORE.register(_read_json(SCHEMA_DIR / _name))


def register_card_schema(schema: dict[str, Any]) -> str:
    """Register a future canonical schema (concept/case/topic) without new loader code."""
    return _STORE.register(schema)


def _build_registry() -> Registry:
    # Each registered ID maps to ITS OWN schema; a $ref must never resolve back
    # to whatever schema is currently being validated.
    registry = Registry(retrieve=_retrieve)
    for schema_id, schema in _STORE._schemas.items():
        registry = registry.with_resource(
            schema_id, Resource.from_contents(schema, default_specification=DRAFT202012))
    return registry


def _validator_for(schema: dict[str, Any], schema_id: str | None = None) -> Draft202012Validator:
    registry = _build_registry()
    if schema_id and schema_id not in _STORE._schemas:
        registry = registry.with_resource(
            schema_id, Resource.from_contents(schema, default_specification=DRAFT202012))
    return Draft202012Validator(schema, registry=registry)


def _schema_for_card_type(card_type: str) -> dict[str, Any] | None:
    return _STORE.get(card_type + ".schema.json")


def _format_errors(validator: Draft202012Validator, item: Any, prefix: str = "") -> list[str]:
    issues: list[str] = []
    try:
        errors = list(validator.iter_errors(item))
    except CardContractError:
        raise
    except Exception as exc:  # unresolvable local refs surface in wrapped forms
        nodes = [exc, exc.__cause__, exc.__context__]
        if any(isinstance(node, Unresolvable) for node in nodes if node is not None):
            raise CardContractError(f"本地 schema 引用无法解析，拒绝放行：{exc}") from exc
        raise
    for error in sorted(errors, key=lambda e: list(e.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        issues.append(f"{prefix}{path}: {error.message}")
    return issues


def validate_card_item(item: Any, card_type: str | None = None) -> list[str]:
    """Validate one structured card item against its canonical schema.

    Returns a list of issues; empty means valid. Unknown declared types fail
    closed (they must not silently bypass the contract).
    """
    if not isinstance(item, dict):
        return ["卡片条目必须是对象"]
    declared = card_type or item.get("type")
    if not isinstance(declared, str) or not declared:
        return ["type: 卡片条目缺少合法 type 字段"]
    schema = _schema_for_card_type(declared)
    if schema is None:
        return [f"type: 未注册的卡片类型，拒绝放行：{declared}"]
    return _format_errors(_validator_for(schema), item)


# ---------------------------------------------------------------------------
# Per-skill envelope schemas (skills/<skill>/schema.json) referencing the
# canonical schemas by their $id. Loaded lazily and registered locally.
# ---------------------------------------------------------------------------
_ENVELOPES: dict[str, Draft202012Validator] = {}


def _envelope_validator(skill_name: str) -> Draft202012Validator:
    if skill_name in _ENVELOPES:
        return _ENVELOPES[skill_name]
    path = SKILLS_ROOT / skill_name / "schema.json"
    if not path.exists():
        raise CardContractError(f"已登记的卡片 skill 缺少 envelope schema：{path}")
    envelope = _read_json(path)
    envelope_id = f"{skill_name}-envelope.schema.json"
    envelope.setdefault("$id", envelope_id)
    _STORE.register(envelope)
    validator = _validator_for(envelope, schema_id=envelope_id)
    _ENVELOPES[skill_name] = validator
    return validator


def validate_skill_payload(skill_name: str, data: Any) -> list[str]:
    """Validate a skill's typed payload envelope: {"items": [...]}.

    Only skills registered in SKILL_CARD_TYPES are card-producing; anything
    else returns no issues so unrelated skills remain unaffected. Pages and
    created executor envelopes are NOT validated here. A registered skill
    whose envelope schema is missing raises instead of being waved through.
    """
    if skill_name not in SKILL_CARD_TYPES:
        return []
    validator = _envelope_validator(skill_name)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [f"{skill_name}: payload 必须包含 items 数组"]
    return _format_errors(validator, data)


# ---------------------------------------------------------------------------
# Producer helpers: program-owned metadata injection and legacy normalization.
# ---------------------------------------------------------------------------
def prepare_card_item(
    item: dict[str, Any],
    card_type: str,
    analysis_mode: str,
    *,
    trusted_source_hashes: dict[str, str] | None = None,
    trusted_coverage: str | None = None,
) -> dict[str, Any]:
    """Return a copy with program-owned contract metadata and canonical states.

    schema_version/generator_version/analysis_mode are always set by the
    program, never trusted from the model. Provenance is trusted only when a
    producer explicitly passes it via the keyword parameters; model-supplied
    source_hashes/coverage on the item are ALWAYS discarded (a generic runtime
    passes raw model items, so an invented hash or coverage='full' must not
    survive). Without trusted values they are recorded as {} / "unknown".
    Never hash cleaned text and call it original bytes.
    """
    prepared = dict(item)
    mapping = LEGACY_STATUS_STAGE.get(card_type, {})
    prepared["status"] = mapping.get("status", {}).get(prepared.get("status"), prepared.get("status"))
    prepared["stage"] = mapping.get("stage", {}).get(prepared.get("stage"), prepared.get("stage"))
    prepared["schema_version"] = CARD_SCHEMA_VERSION
    prepared["generator_version"] = GENERATOR_VERSION
    prepared["analysis_mode"] = analysis_mode
    prepared["source_hashes"] = dict(trusted_source_hashes) if trusted_source_hashes else {}
    prepared["coverage"] = trusted_coverage if trusted_coverage in ("full", "partial") else "unknown"
    return prepared
