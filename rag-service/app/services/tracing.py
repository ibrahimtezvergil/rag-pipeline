from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from app.config import get_settings


def _load_langfuse_class():
    try:
        from langfuse import Langfuse  # type: ignore

        return Langfuse
    except Exception:
        try:
            from langfuse.otel import Langfuse  # type: ignore

            return Langfuse
        except Exception:
            return None


@lru_cache
def _get_langfuse_client():
    settings = get_settings()
    if not settings.langfuse_public_key.strip() or not settings.langfuse_secret_key.strip():
        return None

    langfuse_class = _load_langfuse_class()
    if langfuse_class is None:
        return None

    try:
        return langfuse_class(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        return None


def is_tracing_enabled() -> bool:
    return _get_langfuse_client() is not None


def observe(*, name: str, as_type: str = "span") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    client = _get_langfuse_client()
    if client is None:
        return _noop_observe()

    try:
        return client.observe(
            name=name,
            as_type=as_type,
            capture_input=False,
            capture_output=False,
        )
    except Exception:
        return _noop_observe()


def update_current_observation(
    *,
    input: Any = None,
    output: Any = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = _get_langfuse_client()
    if client is None:
        return

    try:
        client.update_current_observation(
            input=input,
            output=output,
            metadata=metadata,
        )
    except Exception:
        return


def flush_traces() -> None:
    client = _get_langfuse_client()
    if client is None:
        return

    try:
        client.flush()
    except Exception:
        return


def _noop_observe() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return decorator
