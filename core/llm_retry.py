"""Pure, bounded retry policy helpers for the provider transport seam."""
from __future__ import annotations

import errno
import http.client
import math
import urllib.error
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


DEFAULT_MAX_ATTEMPTS = 3
MAX_MAX_ATTEMPTS = 10
DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
MAX_RETRY_BACKOFF_SECONDS = 60.0
DEFAULT_RETRY_BUDGET_SECONDS = 300.0
MAX_RETRY_BUDGET_SECONDS = 3600.0

TRANSIENT_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_TRANSIENT_ERRNOS = frozenset({
    errno.ECONNABORTED,
    errno.ECONNRESET,
    errno.ECONNREFUSED,
    errno.EPIPE,
    errno.ETIMEDOUT,
})
_TRANSIENT_NETWORK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
)


@dataclass(frozen=True)
class RetryPolicy:
    """Validated provider retry settings.

    ``retry_budget_seconds`` is a wall-clock budget used to cap the timeout
    passed to a later socket call and the sleep before a retry. ``urlopen``
    itself remains a socket-level timeout; callers must not treat this as a
    hard wall-clock cancellation mechanism.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS
    retry_budget_seconds: float = DEFAULT_RETRY_BUDGET_SECONDS

    def delay_seconds(self) -> float:
        return self.retry_backoff_seconds


def _bounded_finite_number(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def retry_policy(llm_cfg: Mapping[str, Any] | None) -> RetryPolicy:
    """Return validated retry settings without loading environment or config files."""
    if not isinstance(llm_cfg, Mapping):
        raise ValueError("llm must be an object")
    values = llm_cfg
    attempts = values.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ValueError("max_attempts must be an integer")
    if attempts < 1 or attempts > MAX_MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be between 1 and {MAX_MAX_ATTEMPTS}")
    backoff = _bounded_finite_number(
        values.get("retry_backoff_seconds", DEFAULT_RETRY_BACKOFF_SECONDS),
        "retry_backoff_seconds", minimum=0.0, maximum=MAX_RETRY_BACKOFF_SECONDS,
    )
    budget = _bounded_finite_number(
        values.get("retry_budget_seconds", DEFAULT_RETRY_BUDGET_SECONDS),
        "retry_budget_seconds", minimum=0.001, maximum=MAX_RETRY_BUDGET_SECONDS,
    )
    return RetryPolicy(
        max_attempts=attempts,
        retry_backoff_seconds=backoff,
        retry_budget_seconds=budget,
    )


def _is_transient_network_error(error: BaseException) -> bool:
    if isinstance(error, _TRANSIENT_NETWORK_EXCEPTIONS):
        return True
    if isinstance(error, OSError) and getattr(error, "errno", None) in _TRANSIENT_ERRNOS:
        return True
    return False


def is_transient_error(error: BaseException) -> bool:
    """Return true only for explicitly retryable provider failures."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code in TRANSIENT_HTTP_STATUS
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        return isinstance(reason, BaseException) and _is_transient_network_error(reason)
    return _is_transient_network_error(error)
