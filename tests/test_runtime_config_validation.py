"""Configuration checks must use the same policies as actual runtime."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import validate_config
from tests.test_initialization_policy import _cfg, _plan


def validate_with(cfg, workflows):
    root = Path(validate_config.__file__).resolve().parents[1]
    router = json.loads((root / "router.json").read_text(encoding="utf-8"))
    with patch.object(validate_config, "read_json", side_effect=[cfg, router, workflows]):
        return validate_config.main()


@pytest.fixture
def sample():
    root = Path(validate_config.__file__).resolve().parents[1]
    return [json.loads((root / name).read_text(encoding="utf-8"))
            for name in ("config.example.json", "workflows.json")]


@pytest.mark.parametrize("settings", [
    {"max_attempts": 0}, {"max_attempts": True},
    {"retry_budget_seconds": float("nan")}, {"retry_backoff_seconds": -1},
])
def test_validation_rejects_runtime_retry_misconfiguration(sample, settings, capsys):
    cfg, workflows = copy.deepcopy(sample)
    cfg.setdefault("llm", {}).update(settings)
    assert validate_with(cfg, workflows) == 1
    assert "llm 重试配置无效" in capsys.readouterr().out


def test_validation_checks_the_actual_loaded_workflow(sample, capsys):
    cfg, workflows = copy.deepcopy(sample)
    workflows["entries"]["init_kb"]["pipeline"] = ["intake", "quality_gate"]
    assert validate_with(cfg, workflows) == 1
    assert "required initialization pipeline stage missing" in capsys.readouterr().out


@pytest.mark.parametrize("value", [None, [], "invalid"])
def test_malformed_llm_section_is_rejected_in_validator_and_runtime(sample, value, capsys):
    from core.llm import LLMError, call_chat_completion
    cfg, workflows = copy.deepcopy(sample)
    cfg["llm"] = value
    assert validate_with(cfg, workflows) == 1
    assert "llm 重试配置无效" in capsys.readouterr().out
    with patch("urllib.request.urlopen") as request:
        with pytest.raises(LLMError, match="configuration"):
            call_chat_completion(cfg, "普通分析请求", {})
        request.assert_not_called()


def test_disabled_seed_does_not_even_read_seed_history(tmp_path):
    for name in ("quicknote", "inbox", "raw", "wiki"):
        (tmp_path / name).mkdir()
    cfg = _cfg(tmp_path)
    cfg["initialize"] = {"seed_stage": False}
    skills = []
    def select(index, cfg, skill, **kwargs):
        skills.append(skill)
        assert skill != "mindseed-grow", "disabled history must not be consulted"
        return {"generate": [], "pending": [], "rejected": [], "retryable": []}
    with patch("core.initializer.select_generation_inputs", side_effect=select):
        plan = _plan(cfg)
    assert skills == ["topic-research-compile"]
    stage = next(a for a in plan["actions"] if a["stage"] == "seed_cluster")
    assert stage["outcome"] == "no_inputs"  # B11 wire compatibility
    assert stage["reason"] == "seed_stage_disabled"
