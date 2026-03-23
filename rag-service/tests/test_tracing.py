import pytest

from app.services import tracing as tracing_module


@pytest.mark.asyncio
async def test_observe_returns_noop_wrapper_when_tracing_disabled(monkeypatch):
    monkeypatch.setattr(tracing_module, "_get_langfuse_client", lambda: None, raising=False)

    @tracing_module.observe(name="test-op")
    async def sample(value: str) -> str:
        return value.upper()

    assert await sample("ok") == "OK"


@pytest.mark.asyncio
async def test_observe_uses_langfuse_client_when_enabled(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def observe(self, *, name=None, as_type=None, capture_input=None, capture_output=None):
            captured["name"] = name
            captured["as_type"] = as_type
            captured["capture_input"] = capture_input
            captured["capture_output"] = capture_output

            def decorator(func):
                async def wrapped(*args, **kwargs):
                    return await func(*args, **kwargs)

                return wrapped

            return decorator

    monkeypatch.setattr(tracing_module, "_get_langfuse_client", lambda: FakeClient(), raising=False)

    @tracing_module.observe(name="query-service", as_type="chain")
    async def sample(value: str) -> str:
        return value.upper()

    assert await sample("ok") == "OK"
    assert captured == {
        "name": "query-service",
        "as_type": "chain",
        "capture_input": False,
        "capture_output": False,
    }


def test_update_current_observation_swallows_client_errors(monkeypatch):
    class FakeClient:
        def update_current_observation(self, **kwargs):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(tracing_module, "_get_langfuse_client", lambda: FakeClient(), raising=False)

    tracing_module.update_current_observation(metadata={"project_id": "project-1"})
