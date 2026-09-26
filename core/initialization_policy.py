"""Fixed, validated policy for the ``init_kb`` pipeline.

The initialization workflow is intentionally a small ordered pipeline.  This
module validates the declaration read through the existing router seam; it is
not a general DAG or an arbitrary executor registry.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .router import workflow_for_entry


INITIALIZATION_PIPELINE_ORDER = (
    "intake",
    "source_compile",
    "seed_cluster",
    "promote_candidates",
    "quality_gate",
)
REQUIRED_INITIALIZATION_STAGES = frozenset({
    "intake",
    "source_compile",
    "quality_gate",
})
OPTIONAL_INITIALIZATION_STAGES = frozenset({
    "seed_cluster",
    "promote_candidates",
})


class InitializationPipelineError(ValueError):
    """The configured initialization pipeline is not a supported sequence."""


def validate_initialization_pipeline(pipeline: Any) -> tuple[str, ...]:
    """Validate and return the supported fixed initialization stage order.

    The only legal variation is omission of one or both optional stages.  A
    malformed declaration fails before the initializer inspects inputs or
    reaches an executor/provider.
    """
    if not isinstance(pipeline, (list, tuple)):
        raise InitializationPipelineError(
            "pipeline 必须是阶段名称列表；缺少 required intake/source_compile/quality_gate"
        )

    stages = tuple(pipeline)
    unknown = [stage for stage in stages if stage not in INITIALIZATION_PIPELINE_ORDER]
    if unknown:
        raise InitializationPipelineError(f"unknown initialization pipeline stage: {unknown!r}")

    duplicates = sorted({stage for stage in stages if stages.count(stage) > 1})
    if duplicates:
        raise InitializationPipelineError(
            f"duplicate initialization pipeline stage: {duplicates!r}"
        )

    missing = sorted(REQUIRED_INITIALIZATION_STAGES.difference(stages))
    if missing:
        raise InitializationPipelineError(
            f"required initialization pipeline stage missing: {missing!r}"
        )

    order = {stage: index for index, stage in enumerate(INITIALIZATION_PIPELINE_ORDER)}
    positions = [order[stage] for stage in stages]
    if positions != sorted(positions):
        raise InitializationPipelineError(
            "initialization pipeline stage order is invalid; expected fixed order "
            f"{list(INITIALIZATION_PIPELINE_ORDER)!r}"
        )
    return stages


def load_initialization_pipeline(
    workflow_loader: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Read and validate ``init_kb.pipeline`` through the existing router path.

    ``workflow_loader`` is an explicit test seam.  Production callers leave it
    unset, so the configured ``workflows.json`` remains the single declaration
    source without changing global runtime configuration in tests.
    """
    loader = workflow_loader or workflow_for_entry
    workflow = loader("init_kb")
    if not isinstance(workflow, dict):
        raise InitializationPipelineError("init_kb workflow declaration must be an object")
    return validate_initialization_pipeline(workflow.get("pipeline"))


def validate_initialization_config(cfg: Any) -> bool:
    """Validate the optional initializer override and return its enabled value.

    The field is deliberately strict: an absent field preserves the historical
    default, while a present section/value of the wrong shape is a config
    error rather than a silently truthy/falsey coercion.
    """
    if not isinstance(cfg, dict):
        raise InitializationPipelineError("initialize 配置必须是对象")
    if "initialize" not in cfg:
        return True
    section = cfg.get("initialize")
    if not isinstance(section, dict):
        raise InitializationPipelineError("initialize 配置必须是对象")
    if "seed_stage" not in section:
        return True
    value = section["seed_stage"]
    if type(value) is not bool:
        raise InitializationPipelineError(
            f"initialize.seed_stage 必须是布尔值，当前为：{value!r}"
        )
    return value


def stage_declared(pipeline: Sequence[str], stage: str) -> bool:
    """Return whether a validated optional stage is present."""
    return stage in pipeline
