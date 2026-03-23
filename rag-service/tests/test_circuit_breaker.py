import pytest

from app.services.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


def test_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker(
        "gemini_llm",
        failure_threshold=2,
        recovery_timeout_seconds=30,
    )

    breaker.record_failure()
    breaker.before_call()
    breaker.record_failure()

    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_breaker_recovers_after_timeout():
    now = {"value": 100.0}
    breaker = CircuitBreaker(
        "qdrant",
        failure_threshold=1,
        recovery_timeout_seconds=10,
        now_fn=lambda: now["value"],
    )

    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        breaker.before_call()

    now["value"] = 111.0
    breaker.before_call()
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


def test_breaker_reopens_when_half_open_attempt_fails():
    now = {"value": 50.0}
    breaker = CircuitBreaker(
        "cohere_rerank",
        failure_threshold=1,
        recovery_timeout_seconds=5,
        now_fn=lambda: now["value"],
    )

    breaker.record_failure()
    now["value"] = 56.0
    breaker.before_call()
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
