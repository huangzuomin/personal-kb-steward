"""Bounded provider retry contract tests (offline, synthetic responses only)."""
from __future__ import annotations

import io
import json
import socket
import traceback
import urllib.error
from unittest.mock import Mock, patch

import pytest

from core.content_safety import SensitiveContentError
from core.llm import LLMError, call_chat_completion
from core.llm_retry import retry_policy


SUCCESS = {"choices": [{"message": {"content": '{"ok": true}'}}]}


class FakeResponse:
    def __init__(self, payload: object):
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds: float):
        self.sleeps.append(seconds)
        self.now += seconds


def http_error(status: int, body: bytes = b"temporary provider failure") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://provider.invalid/v1/chat/completions",
        status,
        "provider failure",
        {},
        io.BytesIO(body),
    )


def cfg(**llm_overrides):
    llm = {
        "model": "test-model",
        "timeout_seconds": 10,
        "max_attempts": 3,
        "retry_backoff_seconds": 1.0,
        "retry_budget_seconds": 30.0,
    }
    llm.update(llm_overrides)
    return {"llm": llm}


def invoke(configuration):
    return call_chat_completion(configuration, "Summarize this note.", {"text": "A clean note."})


def test_transient_http_error_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    clock = FakeClock()
    first_failure = http_error(503)
    network = Mock(side_effect=[first_failure, FakeResponse(SUCCESS)])

    with patch("time.monotonic", side_effect=clock.monotonic), \
            patch("time.sleep", side_effect=clock.sleep), \
            patch("core.llm.urllib.request.urlopen", network):
        assert invoke(cfg()) == '{"ok": true}'

    assert network.call_count == 2
    assert clock.sleeps == [1.0]
    assert [call.kwargs["timeout"] for call in network.call_args_list] == [10, 10]
    assert first_failure.fp.closed


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_each_declared_transient_status_can_retry(monkeypatch, status):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(side_effect=[http_error(status), FakeResponse(SUCCESS)])

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep"), \
            patch("core.llm.urllib.request.urlopen", network):
        assert invoke(cfg(retry_backoff_seconds=0)) == '{"ok": true}'

    assert network.call_count == 2


@pytest.mark.parametrize("failure", [
    urllib.error.URLError(socket.timeout("timed out")),
    urllib.error.URLError(ConnectionResetError("connection reset")),
    ConnectionResetError("connection reset"),
])
def test_connection_interruption_or_timeout_retries(monkeypatch, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(side_effect=[failure, FakeResponse(SUCCESS)])

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep"), \
            patch("core.llm.urllib.request.urlopen", network):
        assert invoke(cfg(retry_backoff_seconds=0)) == '{"ok": true}'

    assert network.call_count == 2


def test_retry_attempts_are_bounded_and_terminal_error_has_attempt_count(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(side_effect=[http_error(503), http_error(503), http_error(503)])

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep"), \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match=r"3 attempts") as error:
            invoke(cfg(retry_backoff_seconds=0))

    assert network.call_count == 3
    assert "transport-only-test-key" not in str(error.value)


def test_budget_caps_attempt_timeout_and_wait(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    clock = FakeClock()

    def network_side_effect(*_args, **_kwargs):
        if clock.now == 100.0:
            clock.now += 1.0
            raise http_error(503)
        clock.now += 3.0
        raise http_error(503)

    network = Mock(side_effect=network_side_effect)
    with patch("time.monotonic", side_effect=clock.monotonic), \
            patch("time.sleep", side_effect=clock.sleep), \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match="retry budget"):
            invoke(cfg(timeout_seconds=10, retry_budget_seconds=5, retry_backoff_seconds=1))

    assert network.call_count == 2
    assert [call.kwargs["timeout"] for call in network.call_args_list] == [5.0, 3.0]
    assert clock.sleeps == [1.0]


def test_permanent_http_error_is_single_attempt(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(side_effect=http_error(401, b"unauthorized"))

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep") as sleeper, \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match=r"LLM HTTP error 401.*attempt 1"):
            invoke(cfg())

    assert network.call_count == 1
    sleeper.assert_not_called()


def test_malformed_response_is_not_retried(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(return_value=FakeResponse(b"not-json"))

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep") as sleeper, \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match="Invalid LLM response JSON"):
            invoke(cfg())

    assert network.call_count == 1
    sleeper.assert_not_called()


@pytest.mark.parametrize("payload", [
    {},
    {"choices": []},
    {"choices": [{}]},
    {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": 123}}]},
])
def test_invalid_response_shape_is_not_retried(monkeypatch, payload):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock(return_value=FakeResponse(payload))

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep") as sleeper, \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match="Invalid LLM response shape"):
            invoke(cfg())

    assert network.call_count == 1
    sleeper.assert_not_called()


def test_non_mapping_llm_config_is_rejected_by_pure_policy():
    with pytest.raises(ValueError, match="llm must be an object"):
        retry_policy(None)


def test_unsafe_response_is_not_retried(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    unsafe = {"choices": [{"message": {"content": "password=UnsafeSecret9!Example"}}]}
    network = Mock(return_value=FakeResponse(unsafe))

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep") as sleeper, \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(SensitiveContentError) as error:
            invoke(cfg())

    assert network.call_count == 1
    sleeper.assert_not_called()
    assert "UnsafeSecret9!Example" not in str(error.value)


def test_provider_error_body_redacts_api_key(monkeypatch):
    api_key = "transport-only-test-key"
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    network = Mock(side_effect=http_error(503, f"provider echoed {api_key}".encode()))

    with patch("time.monotonic", return_value=100.0), \
            patch("time.sleep"), \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError) as error:
            invoke(cfg(max_attempts=1))

    assert network.call_count == 1
    assert api_key not in str(error.value)
    assert api_key not in "".join(traceback.format_exception(error.value))


def test_missing_key_fails_before_any_attempt(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    network = Mock()

    with patch("time.monotonic") as monotonic, \
            patch("time.sleep") as sleeper, \
            patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match="Missing API key"):
            invoke(cfg())

    network.assert_not_called()
    monotonic.assert_not_called()
    sleeper.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("max_attempts", 0),
    ("max_attempts", -1),
    ("max_attempts", 11),
    ("max_attempts", 1.5),
    ("max_attempts", True),
    ("retry_backoff_seconds", -1),
    ("retry_backoff_seconds", float("nan")),
    ("retry_backoff_seconds", float("inf")),
    ("retry_budget_seconds", 0),
    ("retry_budget_seconds", -1),
    ("retry_budget_seconds", float("nan")),
])
def test_retry_config_is_finite_and_bounded(monkeypatch, field, value):
    monkeypatch.setenv("OPENAI_API_KEY", "transport-only-test-key")
    network = Mock()

    with patch("core.llm.urllib.request.urlopen", network):
        with pytest.raises(LLMError, match="Invalid LLM retry"):
            invoke(cfg(**{field: value}))

    network.assert_not_called()
