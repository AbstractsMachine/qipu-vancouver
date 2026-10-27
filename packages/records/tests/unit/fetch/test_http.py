from __future__ import annotations

import io
import urllib.error
import urllib.request
from email.message import Message

import pytest

from qipu_records.fetch import http


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _failing_once(monkeypatch: pytest.MonkeyPatch, error: Exception) -> list[str]:
    calls: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        calls.append(request.full_url)
        if len(calls) == 1:
            raise error
        return _Response(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return calls


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.org/x", code, "x", Message(), None)


@pytest.mark.parametrize("code", [500, 502, 503, 504, 408, 429])
def test_a_transient_status_is_retried(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    calls = _failing_once(monkeypatch, _http_error(code))
    sleeps: list[float] = []
    assert http.get("https://example.org/x", user_agent="t", timeout=1, sleep=sleeps.append) == b"ok"
    assert len(calls) == 2
    assert sleeps == [http.BACKOFF_SECONDS]


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410])
def test_a_client_error_is_raised_at_once(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    calls = _failing_once(monkeypatch, _http_error(code))
    with pytest.raises(urllib.error.HTTPError) as raised:
        http.get("https://example.org/x", user_agent="t", timeout=1, sleep=lambda s: None)
    assert raised.value.code == code
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error", [urllib.error.URLError("reset"), TimeoutError("read timed out"), ConnectionResetError("reset")]
)
def test_a_dropped_connection_is_retried(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    calls = _failing_once(monkeypatch, error)
    assert http.get("https://example.org/x", user_agent="t", timeout=1, sleep=lambda s: None) == b"ok"
    assert len(calls) == 2


def test_the_last_error_is_raised_when_the_retries_run_out() -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def attempt() -> bytes:
        attempts.append(1)
        raise _http_error(503)

    with pytest.raises(urllib.error.HTTPError):
        http.with_retries(attempt, retries=3, backoff=1.0, sleep=sleeps.append)
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]


def test_headers_are_sent_with_the_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        seen.append(request)
        return _Response(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    http.get("https://example.org/x", user_agent="qipu-test", timeout=1, headers={"Cookie": "a=b"})
    assert seen[0].get_header("User-agent") == "qipu-test"
    assert seen[0].get_header("Cookie") == "a=b"
