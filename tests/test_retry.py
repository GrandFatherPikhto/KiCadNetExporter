"""Тесты retry_on_transient_read — защита от гонки «файл ещё не дописан»."""
from __future__ import annotations

import pytest

from netexp.infra._retry import retry_on_transient_read


def test_success_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry_on_transient_read(fn, (ValueError,), what="t") == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("empty yet")
        return "ok"

    result = retry_on_transient_read(fn, (ValueError,), what="t", retries=5, delay_sec=0)
    assert result == "ok"
    assert len(calls) == 3


def test_exhausted_raises_last_error(monkeypatch):
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("always broken")

    # замена сна — не ждём в тесте реальные 0.2с
    monkeypatch.setattr("netexp.infra._retry.time.sleep", lambda s: None)
    with pytest.raises(ValueError, match="always broken"):
        retry_on_transient_read(fn, (ValueError,), what="t", retries=3, delay_sec=0.2)
    assert len(calls) == 3


def test_unrelated_exception_not_retried(monkeypatch):
    calls = []

    def fn():
        calls.append(1)
        raise KeyError("boom")

    monkeypatch.setattr("netexp.infra._retry.time.sleep", lambda s: None)
    with pytest.raises(KeyError):
        retry_on_transient_read(fn, (ValueError,), what="t", retries=3, delay_sec=0.1)
    # не наше исключение -> не повторяем
    assert len(calls) == 1


def test_single_retry_raises_immediately():
    def fn():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError, match="x"):
        retry_on_transient_read(fn, (RuntimeError,), what="t", retries=1, delay_sec=0)


def test_defaults_exist():
    from netexp.infra import _retry

    assert _retry.DEFAULT_RETRIES == 5
    assert _retry.DEFAULT_DELAY_SEC == 0.2
