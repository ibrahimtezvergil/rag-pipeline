from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Callable

from app.config import get_settings


class CircuitOpenError(RuntimeError):
    def __init__(self, service_name: str) -> None:
        super().__init__(f"Circuit is open for service: {service_name}")
        self.service_name = service_name


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    service_name: str
    failure_threshold: int
    recovery_timeout_seconds: int
    now_fn: Callable[[], float] = monotonic
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    opened_at: float | None = field(default=None, init=False)

    def before_call(self) -> None:
        if self.state is CircuitState.OPEN:
            if self.opened_at is None:
                self.opened_at = self.now_fn()
            if (self.now_fn() - self.opened_at) < self.recovery_timeout_seconds:
                raise CircuitOpenError(self.service_name)
            self.state = CircuitState.HALF_OPEN

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self._open()
            return
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = CircuitState.OPEN
        self.failure_count = self.failure_threshold
        self.opened_at = self.now_fn()


_BREAKERS: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(service_name: str) -> CircuitBreaker:
    settings = get_settings()
    breaker = _BREAKERS.get(service_name)
    if breaker is None:
        breaker = CircuitBreaker(
            service_name,
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=settings.circuit_breaker_recovery_timeout_seconds,
        )
        _BREAKERS[service_name] = breaker
    return breaker


def reset_circuit_breakers() -> None:
    _BREAKERS.clear()
