"""Read-side generation receipts and the existing plan save boundary.

This module deliberately does not write plans, queues, receipts, or run
records.  Producers create a receipt draft immediately before they are called;
``finalize_generation_receipts`` binds that draft to the already-bound plan
pages at the normal plan save seam.  The selector only reads saved plans,
review queue records, run manifests, and the current index.
"""
from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .config import (
    kb_root,
    plan_dir,
    read_json,
    review_queue_path,
    runs_dir,
    sha256_file,
    sha256_text,
    seed_generation_mode,
)
from .knowledge_objects import identity_from_metadata
from .vault import Note, VaultIndex
from .content_identity import stored_version_covers as _stored_version_covers


RECEIPT_SCHEMA_VERSION = 1
SOURCE_SKILL = "topic-research-compile"
SOURCE_STAGE = "source_compile"
SEED_SKILL = "mindseed-grow"
SEED_STAGE = "seed_cluster"
DERIVED_STAGE_KINDS = {
    "concept_generation": "concept",
    "case_generation": "case",
    "topic_generation": "topic",
}
DERIVED_HISTORY_SKILLS = frozenset({"kb-initialize", "kb-finalize"})


def _history_skill(skill: Any, stage: str | None = None) -> str:
    """Return the stable producer identity used by derived receipts.

    Initializer and finalizer are separate entry points, but they call the
    same typed concept/case/topic producers.  Their plan/action skill labels
    remain distinct for audit and target binding; only the receipt closure and
    lookup comparison use this shared history identity.
    """
    value = str(skill or "")
    if stage in DERIVED_STAGE_KINDS and value in DERIVED_HISTORY_SKILLS:
        return "typed-derived"
    return value


def _same_history_skill(expected: Any, saved: Any, stage: str) -> bool:
    return _history_skill(expected, stage) == _history_skill(saved, stage)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256_text(_canonical(value))


def _rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path(__file__).resolve().parents[1]).as_posix()
    except ValueError:
        return path.name


def _file_digest(path: Path) -> str:
    try:
        return sha256_file(path)
    except (OSError, ValueError):
        return "missing"


def _prompt_digest(path: Path, name: str) -> str:
    """Hash the actual prompt literal, with a full-file fallback.

    Parsing the source keeps this independent of importing the skill executor,
    whose renderer imports are intentionally runtime-bound.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            targets = getattr(node, "targets", [])
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return sha256_text(value)
    except (OSError, SyntaxError, ValueError):
        pass
    return _file_digest(path)


def source_generator_contract() -> dict[str, Any]:
    """Return hashes for the source producer's real local implementation.

    The explicit inventory includes the executor, renderer, schema, source
    analysis, and template bytes.  Hashing the inventory itself gives a stable
    generator version while the prompt and schema fields remain inspectable.
    """
    root = Path(__file__).resolve().parents[1]
    executor = root / "skills" / "topic-research-compile" / "executor.py"
    renderer = root / "skills" / "topic-research-compile" / "renderer.py"
    schema = root / "skills" / "topic-research-compile" / "schema.json"
    analysis = root / "core" / "source_analysis.py"
    template = root / "core" / "templates" / "source_note.j2"
    base_frontmatter = root / "core" / "templates" / "base_frontmatter.j2"
    # These files sit on the actual source-card contract/acceptance path.  A
    # prompt or executor constant alone is not enough to invalidate a receipt
    # when validation, claims, or the accepted typed updater changes.
    contract = root / "core" / "card_contracts.py"
    claims = root / "core" / "claims.py"
    typed_updates = root / "core" / "typed_card_updates.py"
    adapters = root / "core" / "executor_adapters.py"
    identity_binding = root / "core" / "plan_objects.py"
    integrity = root / "core" / "text_integrity.py"
    source_schema = root / "core" / "schemas" / "source-note.schema.json"
    llm = root / "core" / "llm.py"
    jinja = root / "core" / "jinja_renderer.py"
    inventory = {
        _rel_path(path): _file_digest(path)
        for path in (executor, renderer, schema, analysis, template,
                     base_frontmatter, contract,
                     claims, typed_updates, adapters, identity_binding,
                     integrity, source_schema, llm, jinja)
    }
    return {
        "generator_version": _digest(inventory),
        "prompt_sha256": _prompt_digest(executor, "CHUNK_SYSTEM_PROMPT"),
        "schema_sha256": inventory[_rel_path(schema)],
        "implementation_files": inventory,
    }


def seed_generator_contract() -> dict[str, Any]:
    """Return hashes for the seed producer and atomic updater contract.

    This inventory is intentionally separate from the source producer: seed
    reuse must notice changes to atomic extraction, seed rendering, and the
    single seed updater without inheriting source-only dependencies.
    """
    root = Path(__file__).resolve().parents[1]
    executor = root / "skills" / "mindseed-grow" / "executor.py"
    renderer = root / "skills" / "mindseed-grow" / "renderer.py"
    schema = root / "skills" / "mindseed-grow" / "schema.json"
    atomic = root / "core" / "atomic_seed.py"
    speaker_parser = root / "core" / "source_analysis.py"
    updater = root / "core" / "seed_updates.py"
    clustering = root / "core" / "clustering.py"
    quality = root / "core" / "seed_quality.py"
    contracts = root / "core" / "card_contracts.py"
    relations = root / "core" / "card_relations.py"
    claims = root / "core" / "claims.py"
    integrity = root / "core" / "text_integrity.py"
    identity_binding = root / "core" / "plan_objects.py"
    llm = root / "core" / "llm.py"
    jinja = root / "core" / "jinja_renderer.py"
    inventory = {
        _rel_path(path): _file_digest(path)
        for path in (executor, renderer, schema, atomic, speaker_parser, updater, clustering,
                     quality, contracts, relations, claims, integrity,
                     identity_binding, llm, jinja)
    }
    return {
        "generator_version": _digest(inventory),
        "prompt_sha256": _prompt_digest(atomic, "ATOMIC_SYSTEM_PROMPT"),
        "schema_sha256": inventory[_rel_path(schema)],
        "implementation_files": inventory,
    }


def derived_generator_contract(kind: str) -> dict[str, Any]:
    """Hash the actual typed derived producer and its acceptance contract."""
    if kind not in {"concept", "case", "topic"}:
        raise ValueError(f"unsupported derived generator kind: {kind}")
    root = Path(__file__).resolve().parents[1]
    schema_name = {"concept": "concept-page", "case": "case-story", "topic": "topic-page"}[kind]
    files = [
        root / "core" / f"{kind}_generation.py",
        root / "core" / "schemas" / f"{schema_name}.schema.json",
        root / "core" / "templates" / {
            "concept": "concept_page.j2", "case": "case_story.j2", "topic": "topic_page.j2"
        }[kind],
        root / "core" / "templates" / "base_frontmatter.j2",
        root / "core" / "evidence_cards.py",
        root / "core" / "card_contracts.py",
        root / "core" / "claims.py",
        root / "core" / "text_integrity.py",
        root / "core" / "plan_objects.py",
        root / "core" / "typed_card_updates.py",
        root / "core" / "card_pipeline.py",
        root / "core" / "retrieval.py",
        root / "core" / "llm.py",
        root / "core" / "jinja_renderer.py",
    ]
    inventory = {_rel_path(path): _file_digest(path) for path in files}
    executor = root / "core" / f"{kind}_generation.py"
    return {
        "kind": kind,
        "generator_version": _digest(inventory),
        "prompt_sha256": _prompt_digest(executor, "_SYSTEM_PROMPT"),
        "schema_sha256": inventory[_rel_path(files[1])],
        "implementation_files": inventory,
    }


def _nonsecret_config(cfg: dict[str, Any], skill: str, stage: str | None = None) -> dict[str, Any]:
    """Select semantic, nonsecret configuration inputs for a receipt.

    Paths, environment names, credentials, run metadata, and safety locations
    are intentionally excluded.  Output directory and analysis settings are
    semantic inputs because changing either changes the generated proposal.
    """
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    scan = cfg.get("scan") if isinstance(cfg.get("scan"), dict) else {}
    source = cfg.get("source_analysis") if isinstance(cfg.get("source_analysis"), dict) else {}
    write = cfg.get("write") if isinstance(cfg.get("write"), dict) else {}
    history_skill = _history_skill(skill, stage)
    result: dict[str, Any] = {
        "skill": history_skill,
        "analysis_mode": "llm" if cfg.get("_receipt_use_llm", True) else "heuristic",
        "source_analysis": {
            str(key): value for key, value in source.items()
            if str(key) not in {"api_key", "token", "secret", "password"}
        },
        "scan": {
            str(key): scan.get(key) for key in ("max_files_per_run", "max_chars_per_file")
            if key in scan
        },
        "llm": {
            str(key): llm.get(key) for key in ("provider", "model", "temperature", "max_tokens")
            if key in llm
        },
        "write": {"sources_dir": write.get("sources_dir")} if "sources_dir" in write else {},
    }
    # ``core.llm.call_chat_completion`` resolves these values by precedence
    # from the process environment before the configured values.  Record only
    # the effective non-secret provider identity: the model name is useful for
    # invalidation, while the endpoint is kept as a digest so a credential
    # bearing URL can never be copied into a receipt.  API keys and their
    # values are deliberately absent.
    effective_model = (os.environ.get("OPENAI_MODEL")
                       or os.environ.get("LLM_MODEL")
                       or llm.get("model"))
    effective_endpoint = (os.environ.get("OPENAI_BASE_URL")
                          or llm.get("base_url")
                          or "https://api.openai.com/v1")
    result["effective_llm"] = {
        "model": str(effective_model or ""),
        "endpoint_sha256": sha256_text(str(effective_endpoint)),
    }
    # Derived producers read their card-pipeline and typed-generator budgets
    # directly.  Keep those semantic knobs in the closure so changing a
    # question, source cap, sufficiency limit, or generator budget cannot reuse
    # an old derived result forever.  Filter secret-looking keys recursively;
    # paths and run metadata are not part of this contract.
    if history_skill == "typed-derived":
        secret_names = {"api_key", "token", "secret", "password", "credential"}

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): clean(item) for key, item in value.items()
                        if str(key).casefold() not in secret_names}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        for section_name in ("card_pipeline", "concept_generation",
                             "case_generation", "topic_generation"):
            section = cfg.get(section_name)
            if isinstance(section, dict):
                result[section_name] = clean(section)
    if history_skill == SEED_SKILL:
        seed = cfg.get("seed_generation") if isinstance(cfg.get("seed_generation"), dict) else {}
        clustering = cfg.get("clustering") if isinstance(cfg.get("clustering"), dict) else {}
        result["seed_generation"] = {
            str(key): value for key, value in seed.items()
            if str(key) not in {"api_key", "token", "secret", "password"}
        }
        result["clustering"] = {
            str(key): value for key, value in clustering.items()
            if str(key) not in {"api_key", "token", "secret", "password"}
        }
    return result


def _note_snapshot(note: Note | dict[str, Any]) -> dict[str, str]:
    if isinstance(note, Note):
        return {"rel": note.rel, "sha256": note.sha256}
    rel = str(note.get("rel") or "")
    sha = note.get("source_sha256") or note.get("sha256") or ""
    return {"rel": rel, "sha256": str(sha)}


def _sorted_snapshots(items: Iterable[Note | dict[str, Any]]) -> list[dict[str, str]]:
    values = [_note_snapshot(item) for item in items]
    return sorted(values, key=lambda item: (item["rel"], item["sha256"]))


def make_generation_receipt_draft(
    index: VaultIndex | None,
    cfg: dict[str, Any],
    *,
    skill: str,
    stage: str,
    notes: list[Note | dict[str, Any]],
    use_llm: bool,
    upstream_cards: list[dict[str, Any]] | None = None,
    retrieval_context: list[dict[str, Any]] | None = None,
    semantic: dict[str, Any] | None = None,
    generator_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the pre-provider-call portion of a generation receipt."""
    del index  # kept in the seam so typed stages can add indexed context later
    cfg_for_receipt = dict(cfg)
    cfg_for_receipt["_receipt_use_llm"] = bool(use_llm)
    if semantic is None and skill == SEED_SKILL:
        semantic = {
            "kind": "seed", "skill": skill,
            "mode": seed_generation_mode(cfg_for_receipt),
            "question": None,
            "analysis_mode": "llm" if use_llm else "heuristic",
        }
    history_skill = _history_skill(skill, stage)
    closure_semantic = copy.deepcopy(semantic) if isinstance(semantic, dict) else {
        "kind": "source",
        "skill": skill,
        "question": None,
        "analysis_mode": "llm" if use_llm else "heuristic",
    }
    if stage in DERIVED_STAGE_KINDS:
        closure_semantic["skill"] = history_skill
    closure = {
        "originals": _sorted_snapshots(notes),
        "upstream_cards": sorted(
            [dict(item) for item in (upstream_cards or []) if isinstance(item, dict)],
            key=lambda item: (str(item.get("rel") or ""), str(item.get("sha256") or "")),
        ),
        "retrieval_context": sorted(
            [dict(item) for item in (retrieval_context or []) if isinstance(item, dict)],
            key=lambda item: (str(item.get("rel") or ""), str(item.get("sha256") or ""),
                              str(item.get("object_id") or "")),
        ),
        "semantic": closure_semantic,
        "nonsecret_config": _nonsecret_config(cfg_for_receipt, skill, stage),
        "generator_contract": generator_contract or (
            source_generator_contract() if skill == SOURCE_SKILL else seed_generator_contract()
        ),
    }
    fingerprint = _digest({"skill": history_skill, "stage": stage, "input_closure": closure})
    return {
        "receipt_id": sha256_text(f"{skill}\0{stage}\0{fingerprint}"),
        "skill": skill,
        "stage": stage,
        "generation_state": "pending",
        "fingerprint_sha256": fingerprint,
        "input_closure": closure,
    }


def _normalise_outcomes(result: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for raw in result.get("input_outcomes", []) if isinstance(result, dict) else []:
        if not isinstance(raw, dict):
            continue
        item = copy.deepcopy(raw)
        item["rel"] = str(item.get("rel") or "")
        item["source_sha256"] = str(item.get("source_sha256") or "")
        item["outcome"] = str(item.get("outcome") or "error")
        item["complete"] = item.get("complete") is True
        required = item.get("required_targets")
        if not isinstance(required, list):
            required = item.get("targets") if isinstance(item.get("targets"), list) else []
        item["required_targets"] = list(dict.fromkeys(str(target) for target in required if target))
        item["reason"] = str(item.get("reason") or "")
        outcomes.append(item)
    return sorted(outcomes, key=lambda item: (item["rel"], item["source_sha256"]))


def _generation_state(outcomes: list[dict[str, Any]], result: dict[str, Any]) -> str:
    if not outcomes:
        return "error" if result.get("issues") else "zero"
    states = {str(item.get("outcome") or "error") for item in outcomes}
    if states == {"zero"} and all(item.get("complete") is True for item in outcomes):
        return "zero"
    if states & {"error"}:
        return "error"
    if states & {"blocked"}:
        return "blocked"
    if states & {"partial"} or any(item.get("complete") is not True for item in outcomes):
        return "partial"
    return "ok"


def complete_generation_receipt_draft(draft: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Add producer outcomes after the call, keeping the pre-call fingerprint."""
    completed = copy.deepcopy(draft)
    outcomes = _normalise_outcomes(result)
    completed["generation_state"] = _generation_state(outcomes, result)
    completed["input_outcomes"] = outcomes
    return completed


def _target_catalog(plan: dict[str, Any], draft: dict[str, Any],
                    index: VaultIndex | None = None) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    source_rels = {str(item.get("rel") or "") for item in draft.get("input_outcomes", [])}
    catalog: dict[str, dict[str, Any]] = {}
    binding_issues: list[dict[str, str]] = []
    for page in plan.get("planned_pages", []) if isinstance(plan.get("planned_pages"), list) else []:
        if not isinstance(page, dict) or str(page.get("skill") or "") != str(draft.get("skill") or ""):
            continue
        sources = {str(value) for value in (page.get("sources") or []) if value}
        if source_rels and not sources.intersection(source_rels):
            derived_kind = DERIVED_STAGE_KINDS.get(str(draft.get("stage") or ""))
            item = page.get("item") if isinstance(page.get("item"), dict) else {}
            expected_type = {
                "concept": "concept-page", "case": "case-story",
                "topic": "topic-page",
            }.get(derived_kind)
            if not expected_type or item.get("type") != expected_type:
                continue
        target = str(page.get("canonical_path") or page.get("rel_path") or page.get("target") or "")
        if not target:
            continue
        if target in catalog:
            raise ValueError(f"duplicate generation receipt target: {target}")
        content = page.get("content")
        content_hash = str(page.get("content_sha256") or (sha256_text(content) if isinstance(content, str) else ""))
        catalog[target] = {
            "operation": str(page.get("operation") or "create"),
            "content_sha256": content_hash,
            "object_id": page.get("object_id"),
            "revision": page.get("revision"),
            "canonical_path": target,
        }
    # A typed updater noop is a real, verified disposition rather than a
    # generated page.  Its target snapshot is captured by the updater before
    # this save boundary.  Compare that snapshot with the save-time index;
    # never rebind a noop receipt to bytes that appeared after the decision.
    for item in draft.get("input_outcomes", []):
        if not isinstance(item, dict):
            continue
        noop_targets = item.get("updater_noop_targets")
        if not isinstance(noop_targets, list):
            noop_targets = (item.get("required_targets") or item.get("targets") or []) \
                if item.get("updater_disposition") == "noop" else []
        snapshots = item.get("updater_target_snapshots")
        if not isinstance(snapshots, dict):
            snapshots = {}
        rel = str(item.get("rel") or "")
        for raw_target in noop_targets:
            target = str(raw_target or "")
            if not target:
                continue
            snapshot = snapshots.get(target)
            if not isinstance(snapshot, dict):
                binding_issues.append({"rel": rel, "target": target,
                                       "reason": "NOOP updater target snapshot missing"})
                continue
            if index is None:
                binding_issues.append({"rel": rel, "target": target,
                                       "reason": "NOOP save binding has no current index"})
                continue
            note = index.by_rel.get(target)
            if note is None:
                binding_issues.append({"rel": rel, "target": target,
                                       "reason": "NOOP target disappeared before save"})
                continue
            try:
                identity = identity_from_metadata(note.metadata)
            except (TypeError, ValueError):
                identity = None
            expected_identity = (snapshot.get("object_id"), snapshot.get("revision"))
            if (identity is None or type(identity[1]) is not int
                    or identity != expected_identity
                    or str(snapshot.get("content_sha256") or "") != str(note.sha256)
                    or str(snapshot.get("canonical_path") or target) != target):
                binding_issues.append({"rel": rel, "target": target,
                                       "reason": "NOOP target changed between updater decision and save"})
                continue
            if target in catalog:
                continue
            catalog[target] = {
                "operation": "noop",
                "content_sha256": str(snapshot.get("content_sha256") or ""),
                "object_id": snapshot.get("object_id"),
                "revision": snapshot.get("revision"),
                "canonical_path": target,
                "verification": "updater_snapshot",
            }
    return dict(sorted(catalog.items())), binding_issues


def _binding_digest(catalog: dict[str, dict[str, Any]]) -> str:
    rows = [
        {"target": target, **{key: entry.get(key) for key in
                               ("operation", "content_sha256", "object_id", "revision", "canonical_path")}}
        for target, entry in sorted(catalog.items())
    ]
    return _digest(rows)


def finalize_generation_receipts(plan: dict[str, Any], *, index: VaultIndex | None = None) -> None:
    """Bind pre-call drafts to bound pages before the single plan write."""
    drafts = plan.pop("_generation_receipt_drafts", [])
    if not isinstance(drafts, list) or not drafts:
        return
    stages: list[dict[str, Any]] = []
    for raw in drafts:
        if not isinstance(raw, dict):
            continue
        stage = copy.deepcopy(raw)
        catalog, binding_issues = _target_catalog(plan, stage, index=index)
        stage["target_catalog"] = catalog
        stage["binding_sha256"] = _binding_digest(catalog)
        if binding_issues:
            stage["receipt_binding_issues"] = binding_issues
            stage["generation_state"] = "blocked"
            for item in stage.get("input_outcomes", []):
                if not isinstance(item, dict):
                    continue
                matches = [issue for issue in binding_issues
                           if issue.get("rel") == str(item.get("rel") or "")]
                if not matches:
                    continue
                item["receipt_binding_disposition"] = "blocked"
                item["receipt_binding_reasons"] = [str(issue.get("reason") or "")
                                                    for issue in matches]
                item["complete"] = False
                item["outcome"] = "blocked"
                item["reason"] = ((str(item.get("reason") or "") + "；")
                                   + "；".join(item["receipt_binding_reasons"])).strip("；")
        # A successful input must name every target it claims.  Incomplete,
        # blocked, and explicit-zero outcomes stay visible and retryable rather
        # than being promoted by the presence of a page count.
        available = set(catalog)
        for item in stage.get("input_outcomes", []):
            required = set(item.get("required_targets") or [])
            if item.get("complete") is True and item.get("outcome") == "ok" and not required.issubset(available):
                item["complete"] = False
                item["outcome"] = "error"
                item["reason"] = (str(item.get("reason") or "") + "；receipt target catalog incomplete").strip("；")
                stage["generation_state"] = "error"
        stages.append(stage)
    stages.sort(key=lambda item: (str(item.get("skill") or ""), str(item.get("stage") or ""),
                                  str(item.get("fingerprint_sha256") or "")))
    plan["generation_receipts"] = {"schema_version": RECEIPT_SCHEMA_VERSION, "stages": stages}


def _stage_name(stage_key: str | tuple[str, str]) -> str:
    if isinstance(stage_key, tuple):
        return str(stage_key[1])
    aliases = {SOURCE_SKILL: SOURCE_STAGE, SOURCE_STAGE: SOURCE_STAGE,
               SEED_SKILL: SEED_STAGE, SEED_STAGE: SEED_STAGE, "seed": SEED_STAGE}
    return aliases.get(str(stage_key), str(stage_key))


def _skill_for_stage(stage_key: str | tuple[str, str]) -> str | None:
    if isinstance(stage_key, tuple):
        return str(stage_key[0])
    if str(stage_key) == SOURCE_STAGE:
        return SOURCE_SKILL
    if str(stage_key) == SEED_STAGE:
        return SEED_SKILL
    return None


def _receipt_stages(plan: dict[str, Any]) -> list[dict[str, Any]]:
    root = plan.get("generation_receipts")
    if (not isinstance(root, dict)
            or type(root.get("schema_version")) is not int
            or root.get("schema_version") != RECEIPT_SCHEMA_VERSION):
        return []
    stages = root.get("stages")
    return [item for item in stages if isinstance(item, dict)] if isinstance(stages, list) else []


def _receipt_shape_error(receipt: dict[str, Any]) -> str | None:
    """Return a retryable reason for malformed stored receipt data."""
    if not isinstance(receipt.get("receipt_id"), str) or not receipt.get("receipt_id"):
        return "receipt_id missing"
    if not isinstance(receipt.get("fingerprint_sha256"), str) or not receipt.get("fingerprint_sha256"):
        return "fingerprint missing"
    closure = receipt.get("input_closure")
    if not isinstance(closure, dict) or not isinstance(closure.get("originals"), list):
        return "input_closure.originals is malformed"
    outcomes = receipt.get("input_outcomes")
    if not isinstance(outcomes, list):
        return "input_outcomes is malformed"
    catalog = receipt.get("target_catalog")
    if not isinstance(catalog, dict):
        return "target_catalog is malformed"
    for target, entry in catalog.items():
        if not isinstance(target, str) or not isinstance(entry, dict):
            return "target_catalog entry is malformed"
        if type(entry.get("revision")) is not int:
            return f"invalid receipt revision: {target}"
    binding = receipt.get("binding_sha256")
    if not isinstance(binding, str) or binding != _binding_digest(catalog):
        return "binding_sha256 does not match target_catalog"
    return None


def _contract_snapshot(cfg: dict[str, Any], stage: str, source_rel: str,
                      source_sha256: str, use_llm: bool,
                      skill: str | None = None) -> dict[str, Any] | None:
    if stage not in {SOURCE_STAGE, SEED_STAGE, *DERIVED_STAGE_KINDS}:
        return None
    # Reuse the same canonical builder as the producer.  Only the contract
    # portions are compared here; the saved receipt may represent a larger
    # batch, whose complete original closure is handled by the producer call.
    skill = skill or (SOURCE_SKILL if stage == SOURCE_STAGE else SEED_SKILL)
    derived_kind = DERIVED_STAGE_KINDS.get(stage)
    semantic = None if skill == SOURCE_SKILL else {
        "kind": "seed", "skill": skill,
        "mode": seed_generation_mode(cfg),
        "question": None,
        "analysis_mode": "llm" if use_llm else "heuristic",
    }
    if derived_kind:
        semantic = {"kind": "derived", "derived_kind": derived_kind,
                    "skill": skill, "question": None,
                    "analysis_mode": "llm" if use_llm else "heuristic"}
    draft = make_generation_receipt_draft(
        None, cfg, skill=skill, stage=stage,
        notes=[{"rel": source_rel, "source_sha256": source_sha256}],
        use_llm=use_llm, semantic=semantic,
        generator_contract=derived_generator_contract(derived_kind) if derived_kind else None)
    closure = draft.get("input_closure")
    return closure if isinstance(closure, dict) else None


def _derived_closure_base(closure: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(closure.get(key)) for key in (
        "originals", "upstream_cards", "semantic", "nonsecret_config", "generator_contract"
    )}


def _derived_closure_compatible(saved: dict[str, Any], current: dict[str, Any]) -> bool:
    """Return whether a saved cohort closure is compatible with the current one.

    Semantic, config, and generator contract must match exactly.  Originals and
    upstream cards may only GROW: the saved canonical-JSON row sets must be
    exact subsets of the current rows.  This lets a cumulative input wave
    (A/B -> A/B/C) recognize its previous own discovery cohort while any
    changed or genuinely external context stays incompatible.
    """
    for key in ("semantic", "nonsecret_config", "generator_contract"):
        if saved.get(key) != current.get(key):
            return False
    for key in ("originals", "upstream_cards"):
        saved_value = saved.get(key)
        current_value = current.get(key)
        if (not isinstance(saved_value, list)
                or any(not isinstance(item, dict) for item in saved_value)
                or not isinstance(current_value, list)
                or any(not isinstance(item, dict) for item in current_value)):
            return False
        saved_rows = {_canonical(item) for item in saved_value}
        current_rows = {_canonical(item) for item in current_value}
        if not saved_rows.issubset(current_rows):
            return False
    return True


def _explicit_zero_anchor_receipt(receipt: dict[str, Any]) -> bool:
    """Return whether a receipt is a valid explicit zero-output discovery.

    Such a receipt produced no target of its own, but its closure still
    identifies the same saved discovery attempt, so it may anchor that plan's
    cohort.  It never counts as a written output: peer collection still
    requires exact verified current evidence for every sibling target.
    """
    if receipt.get("generation_state") != "zero":
        return False
    if _receipt_shape_error(receipt) is not None:
        return False
    catalog = receipt.get("target_catalog")
    if catalog != {}:
        return False
    outcomes = receipt.get("input_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        return False
    for item in outcomes:
        if not isinstance(item, dict):
            return False
        if item.get("complete") is not True or item.get("outcome") != "zero":
            return False
        if item.get("required_targets", []) != [] or item.get("targets", []) != []:
            return False
    return True


def derived_cohort_paths(cfg: dict[str, Any], *, skill: str, stage: str,
                         input_closure: dict[str, Any], index: VaultIndex) -> set[str]:
    """Return verified peer outputs from the same saved discovery plan.

    A current-kind receipt is the anchor: its pre-context closure identifies the
    exact discovery attempt.  Once that anchor is verified applied (or verified
    all-NOOP), the other derived receipts in that same saved plan are the only
    peer cohort considered.  This keeps topic's bounded source set/question
    differences from splitting a concept/case/topic cohort while avoiding
    accidental unions across historical plans.

    GP001: when the newest candidate attempt is INCOMPLETE — its plan carries no
    verified peer-stage outputs at all (a batch-scoped intake whose
    concept/case stages were scope-narrowed before any receipt exists) — its
    empty peer set is a bookkeeping artifact, not evidence that no siblings
    exist.  Resolution then walks back to the most recent candidate plan that
    DID verify peer outputs; a genuine explicit-zero attempt keeps the empty
    cohort.  Peer membership therefore follows the current verified sibling
    outputs, not which plan happens to hold the receipts.
    """
    paths: set[str] = set()
    if stage not in DERIVED_STAGE_KINDS:
        return paths
    directory = plan_dir(cfg)
    if not directory.exists():
        return paths
    from .layout import knowledge_dirs
    dirs = knowledge_dirs(cfg)

    def verified_outputs(plan_path: Path, receipt: dict[str, Any]) -> bool:
        catalog = receipt.get("target_catalog")
        if not isinstance(catalog, dict) or not catalog:
            return False
        evidence = _receipt_output_evidence(cfg, plan_path, receipt)
        if evidence.get("conflicts"):
            return False
        facts = {
            **(evidence.get("verified") or {}),
            **(evidence.get("observed_failed") or {}),
        }
        # A no-write all-NOOP receipt has its own updater snapshots.  A create
        # or update catalog without linked apply/observed evidence is only a
        # proposal and must not remove a candidate from related retrieval.
        return all(target in facts for target in catalog)

    expected = _derived_closure_base(input_closure)
    candidates: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        plan = _read_plan(path)
        if plan is None:
            continue
        receipts = _receipt_stages(plan)
        anchor = None
        for receipt in receipts:
            if (not _same_history_skill(skill, receipt.get("skill"), stage)
                    or receipt.get("stage") != stage):
                continue
            closure = receipt.get("input_closure")
            if (not isinstance(closure, dict)
                    or not _derived_closure_compatible(
                        _derived_closure_base(closure), expected)):
                continue
            if closure.get("generator_contract") != derived_generator_contract(
                    DERIVED_STAGE_KINDS[stage]):
                continue
            if (receipt.get("generation_state") == "ok"
                    and verified_outputs(path, receipt)) or (
                    isinstance(closure, dict)
                    and _explicit_zero_anchor_receipt(receipt)):
                anchor = receipt
                break
        if anchor is None:
            continue
        candidates.append({"plan_path": path, "plan": plan,
                           "receipts": receipts, "anchor": anchor})

    # A retry can leave several verified plans with the same pre-context
    # closure.  Resolve that history to one candidate plan before collecting
    # peers.  Unioning every matching plan would let an unrelated older
    # retrieval cohort disappear from the current Retriever scope.
    if not candidates:
        return paths
    def verified_anchor_peers(candidate: dict[str, Any]) -> set[str]:
        """Keep only current, verified outputs from each derived peer stage
        in that candidate's saved plan (anchor identity is the plan itself)."""
        collected: set[str] = set()
        path = candidate["plan_path"]
        for receipt in candidate["receipts"]:
            peer_stage = str(receipt.get("stage") or "")
            peer_kind = DERIVED_STAGE_KINDS.get(peer_stage)
            if (not _same_history_skill(skill, receipt.get("skill"), peer_stage)
                    or peer_kind is None) \
                    or receipt.get("generation_state") != "ok":
                continue
            closure = receipt.get("input_closure")
            if (not isinstance(closure, dict)
                    or closure.get("generator_contract") != derived_generator_contract(peer_kind)
                    or not verified_outputs(path, receipt)):
                continue
            catalog = receipt.get("target_catalog")
            for target, saved in (catalog or {}).items():
                if not isinstance(target, str) or not isinstance(saved, dict):
                    continue
                expected_dir = dirs.get(f"{peer_kind}s_dir")
                if not expected_dir or not target.startswith(expected_dir + "/"):
                    continue
                note = index.by_rel.get(target)
                if note is None or note.sha256 != saved.get("content_sha256"):
                    continue
                if type(saved.get("revision")) is not int:
                    continue
                try:
                    identity = identity_from_metadata(note.metadata)
                except (TypeError, ValueError):
                    continue
                if identity == (saved.get("object_id"), saved.get("revision")):
                    collected.add(target)
        return collected

    # GP001: walk the candidates from newest to oldest.  The newest attempt is
    # authoritative whenever it verified peer outputs; an INCOMPLETE newest
    # attempt (no verified peer outputs at all — see the docstring) falls back
    # to the most recent candidate that did, so the cohort tracks current
    # verified siblings instead of receipt bookkeeping distribution.
    for candidate in sorted(candidates, key=_plan_recency_key, reverse=True):
        peer_paths = verified_anchor_peers(candidate)
        if peer_paths:
            return peer_paths
    return paths


def _contract_mismatch(receipt: dict[str, Any], expected: dict[str, Any] | None) -> str | None:
    if expected is None:
        return None
    actual = receipt.get("input_closure")
    if not isinstance(actual, dict):
        return "receipt input closure is malformed"
    for key in ("semantic", "nonsecret_config", "generator_contract"):
        if actual.get(key) != expected.get(key):
            return f"receipt {key} differs from current producer/config contract"
    return None


def _read_plan(path: Path) -> dict[str, Any] | None:
    try:
        data = read_json(path, None)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _plan_matches(path: Path, plan: dict[str, Any], *, stage: str,
                  fingerprint: str | None, source_rel: str | None,
                  source_sha256: str | None,
                  source_bytes: bytes | None = None) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    skill = _skill_for_stage(stage)
    for receipt in _receipt_stages(plan):
        if receipt.get("stage") != stage:
            continue
        if skill and not _same_history_skill(skill, receipt.get("skill"), stage):
            continue
        if fingerprint and receipt.get("fingerprint_sha256") != fingerprint:
            continue
        if source_rel is not None:
            closure = receipt.get("input_closure")
            if not isinstance(closure, dict):
                continue
            originals = closure.get("originals", [])
            if not isinstance(originals, list):
                continue
            if not any(item.get("rel") == source_rel and
                       (source_sha256 is None or item.get("sha256") == source_sha256 or
                        _stored_version_covers(
                            item.get("sha256"), item.get("content_identity_sha256"),
                            source_bytes))
                       for item in originals if isinstance(item, dict)):
                continue
            if source_sha256 is not None:
                outcomes = receipt.get("input_outcomes", [])
                if not any(item.get("rel") == source_rel and (
                        item.get("source_sha256") == source_sha256 or
                        _stored_version_covers(
                            item.get("source_sha256"), item.get("content_identity_sha256"),
                            source_bytes))
                        for item in outcomes if isinstance(item, dict)):
                    continue
        matches.append({"plan_path": path, "plan": plan, "receipt": receipt})
    return matches


def _plan_action_has_input(plan: dict[str, Any], stage: str,
                           source_rel: str, source_sha256: str | None,
                           source_bytes: bytes | None = None) -> bool:
    """Locate a source version even when its stored receipt envelope is corrupt."""
    actions = plan.get("actions")
    if not isinstance(actions, list):
        return False
    for action in actions:
        if not isinstance(action, dict) or action.get("stage") != stage:
            continue
        for item in action.get("input_outcomes", []) if isinstance(action.get("input_outcomes"), list) else []:
            if (isinstance(item, dict) and item.get("rel") == source_rel
                    and (item.get("source_sha256") == source_sha256 or
                         _stored_version_covers(item.get("source_sha256"),
                                                item.get("content_identity_sha256"),
                                                source_bytes))):
                return True
    return False


def _queue_status(cfg: dict[str, Any], run_id: str | None) -> str | None:
    if not run_id:
        return None
    try:
        lines = review_queue_path(cfg).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    statuses = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("run_id") == run_id:
            statuses.append(str(item.get("status") or "pending"))
    if "rejected" in statuses:
        return "rejected"
    if "pending" in statuses or "approved" in statuses:
        return "pending"
    return None


def _plan_target_catalog(plan: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Build the complete bound page catalog required by output evidence."""
    pages = plan.get("planned_pages")
    if not isinstance(pages, list):
        return None
    catalog: dict[str, dict[str, Any]] = {}
    for page in pages:
        if not isinstance(page, dict):
            return None
        target = str(page.get("canonical_path") or page.get("rel_path")
                     or page.get("target") or "")
        if not target or target in catalog:
            return None
        content_hash = page.get("content_sha256")
        object_id = page.get("object_id")
        revision = page.get("revision")
        if (not isinstance(content_hash, str) or not content_hash
                or not isinstance(object_id, str) or not object_id
                or type(revision) is not int):
            return None
        catalog[target] = {
            "canonical_path": target,
            "content_sha256": content_hash,
            "object_id": object_id,
            "revision": revision,
            "operation": str(page.get("operation") or "create"),
        }
    return catalog


def _receipt_output_evidence(
    cfg: dict[str, Any], plan_path: Path, receipt: dict[str, Any],
) -> dict[str, Any]:
    """Collect exact output facts across all linked parent/subset manifests.

    ``verified_plan_outputs`` requires the complete saved parent catalog.  The
    receipt catalog is then used only as the per-stage/per-input projection.
    Failed attempts remain in ``observed_failed``; callers may use their exact
    current-byte evidence to avoid replay, but they are never relabeled as an
    applied manifest.
    """
    empty = {"verified": {}, "observed_failed": {}, "conflicts": [],
             "manifest_paths": []}
    catalog = receipt.get("target_catalog")
    if not isinstance(catalog, dict):
        empty["conflicts"].append({"kind": "receipt_target_catalog_invalid"})
        return empty
    write_targets = {
        target: entry for target, entry in catalog.items()
        if isinstance(entry, dict) and entry.get("operation") in {"create", "update"}
    }
    noop_targets = {
        target: entry for target, entry in catalog.items()
        if isinstance(entry, dict) and entry.get("operation") == "noop"
    }
    if write_targets:
        plan = _read_plan(plan_path)
        full_catalog = _plan_target_catalog(plan) if plan is not None else None
        if not full_catalog:
            empty["conflicts"].append({
                "kind": "parent_target_catalog_invalid",
                "detail": "saved parent plan has no complete bound page catalog",
            })
            return empty
        try:
            from .plan_output_evidence import verified_plan_outputs
            from .vault import build_index
            evidence = verified_plan_outputs(
                build_index(cfg), cfg, plan_path, _file_digest(plan_path), full_catalog,
            )
        except Exception as exc:
            empty["conflicts"].append({
                "kind": "output_evidence_unavailable", "detail": str(exc),
            })
            return empty
        empty["conflicts"].extend(evidence.get("conflicts") or [])
        empty["manifest_paths"].extend(evidence.get("manifest_paths") or [])
        for key in ("verified", "observed_failed"):
            facts = evidence.get(key) if isinstance(evidence.get(key), dict) else {}
            empty[key].update({target: fact for target, fact in facts.items()
                               if target in write_targets})
        if empty["conflicts"]:
            # A forged or conflicting sibling manifest invalidates the whole
            # parent evidence set.  Keep no partial authority in the result.
            empty["verified"] = {}
            empty["observed_failed"] = {}
            return empty
    if noop_targets:
        try:
            from .knowledge_objects import identity_from_metadata
            from .vault import build_index
            index = build_index(cfg)
            for target, expected in noop_targets.items():
                note = index.by_rel.get(str(target))
                identity = identity_from_metadata(note.metadata) if note is not None else None
                if (note is None or note.sha256 != expected.get("content_sha256")
                        or identity != (expected.get("object_id"), expected.get("revision"))):
                    empty["conflicts"].append({
                        "kind": "verified_noop_target_changed", "target": target,
                    })
                    continue
                empty["verified"][target] = {
                    "canonical_path": target,
                    "content_sha256": expected.get("content_sha256"),
                    "object_id": expected.get("object_id"),
                    "revision": expected.get("revision"),
                    "verification": "updater_snapshot",
                }
        except Exception as exc:
            empty["conflicts"].append({
                "kind": "verified_noop_unavailable", "detail": str(exc),
            })
    return empty


def _review_state_for_targets(
    cfg: dict[str, Any], plan: dict[str, Any], required_targets: list[str],
) -> dict[str, Any]:
    """Read exact page and non-page review state for one input's targets."""
    try:
        from .review_queue import is_page_review_item
        from .review_runs import load_checked_queue
        items = load_checked_queue(review_queue_path(cfg))
    except Exception as exc:
        return {"error": f"review queue is malformed or unreadable: {exc}"}
    run_id = str(plan.get("run_id") or "")
    related = [item for item in items if isinstance(item, dict)
               and item.get("run_id") == run_id]
    page_contract = plan.get("review_contract") == "page-scoped-v1"
    required = set(str(target) for target in required_targets if target)
    rows_by_target: dict[str, list[dict[str, Any]]] = {target: [] for target in required}
    non_page_blockers: list[dict[str, Any]] = []
    for item in related:
        if is_page_review_item(item):
            target = item.get("target")
            if target in rows_by_target:
                rows_by_target[target].append(item)
            continue
        if item.get("status", "pending") not in {"approved", "applied"}:
            non_page_blockers.append(item)
    conflicts: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    catalog = None
    # Compare queue authority to the saved plan page tuple where available.
    pages = {str(page.get("rel_path") or page.get("target") or ""): page
             for page in plan.get("planned_pages", [])
             if isinstance(page, dict)}
    if not page_contract:
        # A legacy full-apply plan has no per-page review rows; its run-level
        # gate is the related non-page rows above (mirroring
        # review_runs.review_blockers).  Page states are deliberately left
        # empty: page authority must never be fabricated, and exact
        # run-manifest output evidence decides unchanged vs pending.
        return {
            "states": {},
            "non_page_blockers": non_page_blockers,
            "conflicts": conflicts,
            "related": related,
            "page_contract": page_contract,
        }
    for target, rows in rows_by_target.items():
        if len(rows) != 1:
            states[target] = "pending" if not rows else "conflict"
            if len(rows) != 1 and page_contract:
                conflicts.append({"kind": "page_review_authority_missing_or_duplicate",
                                  "target": target})
            continue
        row = rows[0]
        page = pages.get(target)
        if page is not None:
            for key in ("content_sha256", "object_id", "revision"):
                # JSON booleans compare equal to integers in Python; review
                # authority fields are typed identity, so equality alone is
                # insufficient for a fail-closed comparison.
                if (type(row.get(key)) is not type(page.get(key))
                        or row.get(key) != page.get(key)):
                    conflicts.append({"kind": "page_review_authority_mismatch",
                                      "target": target, "field": key})
        status = row.get("status", "pending")
        states[target] = status if status in {"pending", "approved", "rejected", "applied"} else "conflict"
    rejection_types: dict[str, str] = {}
    for target, rows in rows_by_target.items():
        if rows and rows[0].get("status") == "rejected":
            # GP002: 缺字段的历史拒绝按 other 兼容（never parse free-text reason）。
            rejection_types[target] = str(rows[0].get("rejection_type") or "other")
    return {
        "states": states,
        "rejection_types": rejection_types,
        "non_page_blockers": non_page_blockers,
        "conflicts": conflicts,
        "related": related,
        "page_contract": page_contract,
    }


def _manifest_for_plan(cfg: dict[str, Any], path: Path, plan_hash: str) -> dict[str, Any] | None:
    if not runs_dir(cfg).exists():
        return None
    expected = str(path.resolve())
    found: list[dict[str, Any]] = []
    for candidate in sorted(runs_dir(cfg).glob("*.json")):
        try:
            data = read_json(candidate, None)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("status") != "applied":
            continue
        recorded = str(data.get("plan_path") or "")
        try:
            recorded = str(Path(recorded).resolve())
        except (OSError, ValueError):
            pass
        if recorded != expected or data.get("plan_sha256") != plan_hash:
            continue
        found.append(data)
    return found[-1] if found else None


def _targets_intact(cfg: dict[str, Any], receipt: dict[str, Any], manifest: dict[str, Any],
                    required_targets: list[str] | None = None) -> tuple[bool, str]:
    if manifest.get("reconcile", {}).get("ok") is not True:
        return False, "run manifest reconcile is not ok"
    root = kb_root(cfg)
    try:
        from .vault import build_index
        index = build_index(cfg)
    except Exception as exc:
        return False, f"cannot rebuild current index: {exc}"
    observed = {
        str(item.get("rel_path")): item for item in manifest.get("created", [])
        if isinstance(item, dict) and item.get("rel_path")
    }
    catalog = receipt.get("target_catalog") or {}
    if not isinstance(catalog, dict):
        return False, "receipt target catalog is malformed"
    if required_targets is not None:
        required = [str(target) for target in required_targets if target]
        if not required:
            return False, "input has no required target mapping"
        missing = [target for target in required if target not in catalog]
        if missing:
            return False, f"receipt target catalog missing input targets: {missing}"
        catalog = {target: catalog[target] for target in required}
    for rel, expected in catalog.items():
        if type(expected.get("revision")) is not int:
            return False, f"invalid receipt revision: {rel}"
        note = index.by_rel.get(str(rel))
        if expected.get("operation") == "noop":
            if (note is None or note.sha256 != expected.get("content_sha256")
                    or identity_from_metadata(note.metadata) !=
                    (expected.get("object_id"), expected.get("revision"))):
                return False, f"verified noop target changed: {rel}"
            continue
        item = observed.get(str(rel))
        if not item or item.get("content_verified") is not True:
            return False, f"missing verified applied target: {rel}"
        if item.get("expected_sha256") != expected.get("content_sha256") or item.get("sha256") != expected.get("content_sha256"):
            return False, f"applied target hash mismatch: {rel}"
        if note is None or note.sha256 != expected.get("content_sha256"):
            return False, f"current target changed: {rel}"
        identity = identity_from_metadata(note.metadata)
        if (expected.get("object_id"), expected.get("revision")) != identity:
            return False, f"current target identity changed: {rel}"
        if not (root / str(rel)).is_file():
            return False, f"target is not a file: {rel}"
    return True, "verified applied targets"


def _decision_for_match(cfg: dict[str, Any], match: dict[str, Any], *,
                        source_rel: str | None = None,
                        expected_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    path = match["plan_path"]
    plan = match["plan"]
    receipt = match["receipt"]
    base = {
        "receipt_ref": receipt.get("receipt_id"),
        "plan_ref": str(path),
        "run_id": plan.get("run_id"),
        "input_outcomes": copy.deepcopy(receipt.get("input_outcomes") or []),
        "generation_state": receipt.get("generation_state"),
        "target_catalog": copy.deepcopy(receipt.get("target_catalog") or {}),
        "fingerprint_sha256": receipt.get("fingerprint_sha256"),
    }
    shape_error = _receipt_shape_error(receipt)
    if shape_error:
        return {**base, "decision": "retryable", "reason": shape_error}
    source_outcome = None
    if source_rel is not None:
        candidates = [item for item in receipt.get("input_outcomes", [])
                      if isinstance(item, dict) and item.get("rel") == source_rel]
        if len(candidates) != 1:
            return {**base, "decision": "retryable",
                    "reason": "saved receipt has no unique per-input outcome"}
        source_outcome = candidates[0]
    input_state = str(source_outcome.get("outcome")) if source_outcome else str(receipt.get("generation_state"))
    input_complete = (source_outcome.get("complete") is True if source_outcome
                      else receipt.get("generation_state") in {"ok", "zero"})
    required_targets = None
    if source_outcome is not None:
        required_targets = source_outcome.get("required_targets")
        if not isinstance(required_targets, list):
            required_targets = source_outcome.get("targets") if isinstance(source_outcome.get("targets"), list) else []
    else:
        # A derived receipt represents one bounded discovery call.  Its
        # stage-level target catalog is the only safe required-target mapping;
        # selecting one arbitrary manifest would silently complete a partial
        # subset.
        catalog = receipt.get("target_catalog")
        required_targets = list(catalog) if isinstance(catalog, dict) else []
    required_targets = list(dict.fromkeys(
        str(target) for target in (required_targets or []) if target
    ))
    base["required_targets"] = list(required_targets)
    # A failed sibling must not turn a successful sibling into retryable, and a
    # pending review on that sibling must not suppress this input's visible
    # retryable state.  Per-input disposition precedes queue/status handling.
    if input_state in {"error", "blocked", "partial"} or not input_complete:
        return {**base, "decision": "retryable", "reason": "this input outcome is incomplete or failed"}
    # Review is scoped to this input's page targets.  Unrelated page siblings
    # and non-page rows already resolved as approved/applied must not suppress
    # a complete input, while genuine non-page blockers remain effective.
    review = _review_state_for_targets(cfg, plan, required_targets)
    if review.get("error"):
        return {**base, "decision": "retryable", "reason": review["error"]}
    if review.get("conflicts"):
        return {**base, "decision": "retryable",
                "reason": "review authority conflicts with the saved plan",
                "review_state": review}
    # GP002: duplicate rejection persists across producer contracts — 重新生成
    # 恰恰是用户拒绝过的重复提案。quality/policy/other 维持 contract-scoped。
    rejection_types = review.get("rejection_types") or {}
    if any(rejection_types.get(target) == "duplicate" for target in required_targets):
        return {**base, "decision": "review_rejected",
                "reason": "duplicate rejection persists across producer contracts",
                "review_state": review}
    contract_error = _contract_mismatch(receipt, expected_contract)
    if contract_error:
        return {**base, "decision": "retryable", "reason": contract_error}
    non_page = review.get("non_page_blockers") or []
    if any(item.get("status") == "rejected" for item in non_page if isinstance(item, dict)):
        return {**base, "decision": "review_rejected",
                "reason": "an effective non-page review item was rejected",
                "review_state": review}
    if non_page:
        return {**base, "decision": "pending_review",
                "reason": "an effective non-page review item is still pending",
                "review_state": review}
    states = review.get("states") or {}
    required_page = [
        target for target in required_targets
        if review.get("page_contract")
        and (isinstance(receipt.get("target_catalog"), dict)
             and isinstance(receipt["target_catalog"].get(target), dict)
             and receipt["target_catalog"][target].get("operation") in {"create", "update"})
    ]
    required_states = [states.get(target, "pending") for target in required_page]
    if "rejected" in required_states:
        return {**base, "decision": "review_rejected",
                "reason": "a required page review item was rejected",
                "review_state": review}
    if any(state in {"pending", "approved", "conflict"} for state in required_states):
        return {**base, "decision": "pending_review",
                "reason": "a required page review item is not applied",
                "review_state": review}
    if input_state == "zero":
        return {**base, "decision": "zero_output",
                "reason": "explicit fully-read zero output", "review_state": review}
    if input_state != "ok":
        return {**base, "decision": "retryable", "reason": "saved receipt is incomplete or failed"}
    if (source_outcome is not None
            and source_outcome.get("updater_disposition") == "evaluated"
            and not required_targets):
        return {**base, "decision": "unchanged_inputs",
                "reason": "completed evaluation produced no cited target",
                "review_state": review}

    evidence = _receipt_output_evidence(cfg, path, receipt)
    base["output_evidence"] = copy.deepcopy(evidence)
    if evidence.get("conflicts"):
        return {**base, "decision": "retryable",
                "reason": "saved output evidence is malformed or conflicting"}
    facts = {
        **(evidence.get("verified") or {}),
        **(evidence.get("observed_failed") or {}),
    }
    missing = [target for target in required_targets if target not in facts]
    if missing:
        # An approved page with no exact manifest evidence is still waiting for
        # its safe apply boundary.  An applied page without evidence indicates
        # stale, deleted, or forged authority and must be retried/blocked.
        if any(states.get(target) == "applied" for target in missing):
            return {**base, "decision": "retryable",
                    "reason": f"required output evidence is missing: {missing}",
                    "review_state": review}
        return {**base, "decision": "pending_review",
                "reason": f"required output has not been verified: {missing}",
                "review_state": review}
    return {**base, "decision": "unchanged_inputs",
            "reason": "all required outputs have exact applied, observed, or NOOP evidence",
            "review_state": review}


def _plan_recency_key(match: dict[str, Any]) -> tuple[str, int, str]:
    """Order saved attempts by recorded time, then filesystem time/run ID.

    The filename is deliberately not part of the resolution policy.  A plan
    with a later recorded run is the authoritative history when a source
    version was retried and both plans remain on disk.
    """
    path = match.get("plan_path")
    plan = match.get("plan") if isinstance(match.get("plan"), dict) else {}
    try:
        mtime = int(path.stat().st_mtime_ns) if isinstance(path, Path) else 0
    except OSError:
        mtime = 0
    return (str(plan.get("created_at") or ""), mtime, str(plan.get("run_id") or ""))


def _valid_source_input(match: dict[str, Any], source_rel: str) -> bool:
    receipt = match.get("receipt") if isinstance(match.get("receipt"), dict) else {}
    for item in receipt.get("input_outcomes", []) if isinstance(receipt.get("input_outcomes"), list) else []:
        if (isinstance(item, dict) and item.get("rel") == source_rel
                and item.get("complete") is True
                and item.get("outcome") in {"ok", "zero"}):
            return True
    return False


def lookup_generation_receipt(
    cfg: dict[str, Any],
    stage_key: str | tuple[str, str],
    fingerprint: str | None = None,
    *,
    source_rel: str | None = None,
    source_sha256: str | None = None,
    source_bytes: bytes | None = None,
    use_llm: bool = True,
) -> dict[str, Any] | None:
    """Read an exact fingerprint or per-input saved receipt.

    ``source_rel``/``source_sha256`` are used by the intake selector before a
    new batch fingerprint exists.  ``source_bytes`` enables GP002 content
    identity matching (CRLF/LF/BOM representation drift is the SAME content).
    No write or queue backfill occurs here.
    """
    stage = _stage_name(stage_key)
    matches: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    directory = plan_dir(cfg)
    if not directory.exists():
        return None
    for path in sorted(directory.glob("*.json")):
        plan = _read_plan(path)
        if plan is None:
            continue
        matches.extend(_plan_matches(path, plan, stage=stage, fingerprint=fingerprint,
                                     source_rel=source_rel, source_sha256=source_sha256,
                                     source_bytes=source_bytes))
        if (source_rel is not None and isinstance(plan.get("generation_receipts"), dict)
                and (type(plan["generation_receipts"].get("schema_version")) is not int
                     or plan["generation_receipts"].get("schema_version") != RECEIPT_SCHEMA_VERSION)
                and _plan_action_has_input(plan, stage, source_rel, source_sha256,
                                           source_bytes=source_bytes)):
            malformed.append({"plan_ref": str(path), "run_id": plan.get("run_id")})
    if not matches:
        if malformed:
            return {"decision": "retryable", "reason": "saved generation receipt schema is corrupt",
                    "matches": malformed}
        return None
    expected_contract = (
        _contract_snapshot(cfg, stage, source_rel, source_sha256 or "", use_llm,
                           skill=_skill_for_stage(stage))
        if source_rel is not None else None
    )
    if expected_contract is not None:
        current_matches = [
            match for match in matches
            if _contract_mismatch(match["receipt"], expected_contract) is None
        ]
        if current_matches:
            matches = current_matches
    matches = sorted(matches, key=_plan_recency_key, reverse=True)
    decisions = [
        (match, _decision_for_match(cfg, match, source_rel=source_rel,
                                    expected_contract=expected_contract))
        for match in matches
    ]
    if source_rel is not None:
        # A failed/blocked retry remains audit history but cannot hide an older
        # verified success after the target is restored.  Prefer the newest
        # complete per-input ok/zero decision; within that class, pending or
        # rejected review remains authoritative over an older applied result.
        valid = [(match, decision) for match, decision in decisions
                 if _valid_source_input(match, source_rel)
                 and decision.get("decision") != "retryable"]
        if valid:
            return valid[0][1]
    # No complete reusable result exists; the newest failed/incomplete attempt
    # is the visible retryable decision.  Historical plans remain untouched.
    return decisions[0][1]


def _candidate_notes(index: VaultIndex, skill: str) -> list[Note]:
    if skill == SOURCE_SKILL:
        prefixes = ("raw/",)
    elif skill == "mindseed-grow":
        prefixes = ("quicknote/", "inbox/")
    else:
        prefixes = ("raw/", "quicknote/", "inbox/")
    return sorted([note for note in index.notes if note.rel.startswith(prefixes)], key=lambda note: note.rel)


def select_generation_inputs(index: VaultIndex, cfg: dict[str, Any], skill: str,
                             include_all: bool = False, *, use_llm: bool = True) -> dict[str, Any]:
    """Classify every current indexed input by exact saved receipt state.

    ``include_all`` is retained as a stable seam; both modes still inspect all
    current versions so an unchanged sibling cannot hide a pending or failed
    input.  Pending/rejected inputs never occupy the generated batch.
    """
    del include_all
    result: dict[str, list[Any]] = {
        "generate": [], "pending": [], "rejected": [], "unchanged": [], "retryable": []
    }
    stage = _stage_name(skill)
    for note in _candidate_notes(index, skill):
        # GP002: 读取当前字节，供 content identity 匹配（CRLF/LF/BOM 表示漂移
        # 属同一内容，不再重复知识生产）。byte sha 语义不变。
        try:
            source_bytes = note.path.read_bytes()
        except OSError:
            source_bytes = None
        decision = lookup_generation_receipt(
            cfg, stage, source_rel=note.rel, source_sha256=note.sha256,
            source_bytes=source_bytes, use_llm=use_llm)
        if decision is None:
            result["generate"].append(note)
            continue
        record = {"note": note, **decision}
        category = {
            "pending_review": "pending",
            "review_rejected": "rejected",
            "unchanged_inputs": "unchanged",
            "zero_output": "unchanged",
            "retryable": "retryable",
        }.get(str(decision.get("decision")), "retryable")
        result[category].append(record)
    return result


def selection_stage_summary(selection: dict[str, Any], *, use_llm: bool,
                            skill: str = SOURCE_SKILL) -> dict[str, Any]:
    """Build a truthful no-call stage envelope for cached producer inputs."""
    label = "seed" if skill == SEED_SKILL else "source"
    records = [item for key in ("pending", "rejected", "unchanged", "retryable")
               for item in selection.get(key, []) if isinstance(item, dict)]
    decisions = {str(item.get("decision")) for item in records}
    if "pending_review" in decisions:
        outcome, reason = "pending_review", f"已有 {label} 计划待人工审核；未重新调用 provider。"
    elif "review_rejected" in decisions:
        outcome, reason = "review_rejected", f"已有 {label} 计划被拒绝；未自动重新提交。"
    elif "retryable" in decisions:
        outcome, reason = "retryable", f"已有 {label} 证据不可验证；本批保留为可重试。"
    elif any(item.get("decision") == "zero_output" for item in records):
        outcome, reason = "zero_output", f"已有显式完整读取零产出；未重新调用 {label} provider。"
    elif records:
        outcome, reason = "unchanged_inputs", f"已有 {label} 输出已应用且当前目标完整；未重新调用 provider。"
    else:
        outcome, reason = "no_inputs", f"当前没有 {label} 输入。"
    input_outcomes = []
    refs = []
    plan_refs = []
    for item in records:
        refs.append(item.get("receipt_ref"))
        if item.get("plan_ref"):
            plan_refs.append(item.get("plan_ref"))
        input_outcomes.extend(copy.deepcopy(item.get("input_outcomes") or []))
    # Keep the long-standing no-input stage wording for an applied source that
    # has already left intake.  The exact B2 decision remains explicit in
    # ``receipt_decision`` so callers can distinguish cached success from an
    # actually empty vault; pending/rejected/zero retain their precise stage
    # outcomes. Seed uses the same explicit decision envelope.
    stage_outcome = "no_inputs" if outcome == "unchanged_inputs" else outcome
    return {
        "outcome": stage_outcome,
        "receipt_decision": outcome,
        "reason": reason,
        "reason_detail": reason,
        "provider_calls": 0,
        "inputs": [item.get("note").rel for item in records if isinstance(item.get("note"), Note)],
        "planned_inputs": len(records),
        "planned_pages": 0,
        "processed": 0,
        "input_outcomes": input_outcomes,
        "receipt_refs": [ref for ref in refs if ref],
        "receipt_plan_refs": [ref for ref in plan_refs if ref],
        "receipt_decisions": {item.get("note").rel: item.get("decision")
                              for item in records if isinstance(item.get("note"), Note)},
        "execution_mode": "llm" if use_llm else "heuristic",
    }


def receipt_ids(plan: dict[str, Any]) -> list[str]:
    return [str(item.get("receipt_id")) for item in _receipt_stages(plan) if item.get("receipt_id")]
