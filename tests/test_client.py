from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from src.youtube.client import YouTubeRequestError, execute_with_retry


def _http_error(status: int, reason: str) -> HttpError:
    content = ('{"error":{"errors":[{"reason":"%s"}]}}' % reason).encode()
    return HttpError(SimpleNamespace(status=status, reason=reason), content)


def test_retries_transient_error_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _http_error(503, "backendError")
        return {"items": []}

    assert execute_with_retry(operation, sleep=sleeps.append) == {"items": []}
    assert attempts == 3
    assert sleeps == [1.0, 2.0]


def test_does_not_retry_permanent_error() -> None:
    attempts = 0

    def operation() -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        raise _http_error(403, "quotaExceeded")

    with pytest.raises(YouTubeRequestError, match="quotaExceeded"):
        execute_with_retry(operation, sleep=lambda _: None)
    assert attempts == 1

