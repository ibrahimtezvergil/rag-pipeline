import pytest

from app.services import health as health_service


@pytest.mark.asyncio
async def test_health_endpoint_reports_all_services_up(client, app):
    async def healthy_checkers():
        return {
            "postgres": {"status": "up"},
            "redis": {"status": "up"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "up", "model": "gemini-embedding-2"},
        }

    app.state.health_checkers = healthy_checkers

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "services": {
            "postgres": {"status": "up"},
            "redis": {"status": "up"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "up", "model": "gemini-embedding-2"},
        },
    }


@pytest.mark.asyncio
async def test_health_endpoint_reports_degraded_when_service_fails(client, app):
    async def degraded_checkers():
        return {
            "postgres": {"status": "up"},
            "redis": {"status": "down", "detail": "connection refused"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "up", "model": "gemini-embedding-2"},
        }

    app.state.health_checkers = degraded_checkers

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "services": {
            "postgres": {"status": "up"},
            "redis": {"status": "down", "detail": "connection refused"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "up", "model": "gemini-embedding-2"},
        },
    }


@pytest.mark.asyncio
async def test_health_endpoint_reports_embedder_down_when_api_key_missing(client, app):
    async def embedder_down_checkers():
        return {
            "postgres": {"status": "up"},
            "redis": {"status": "up"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "down", "detail": "Missing Gemini API key"},
        }

    app.state.health_checkers = embedder_down_checkers

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "services": {
            "postgres": {"status": "up"},
            "redis": {"status": "up"},
            "qdrant": {"status": "up"},
            "embedder": {"status": "down", "detail": "Missing Gemini API key"},
        },
    }


@pytest.mark.asyncio
async def test_collect_health_status_includes_embedder(monkeypatch):
    async def service_up():
        return {"status": "up"}

    async def embedder_up():
        return {"status": "up", "model": "gemini-embedding-2"}

    monkeypatch.setattr(health_service, "check_postgres", service_up)
    monkeypatch.setattr(health_service, "check_redis", service_up)
    monkeypatch.setattr(health_service, "check_qdrant", service_up)
    monkeypatch.setattr(health_service, "check_embedder", embedder_up)

    result = await health_service.collect_health_status()

    assert result == {
        "postgres": {"status": "up"},
        "redis": {"status": "up"},
        "qdrant": {"status": "up"},
        "embedder": {"status": "up", "model": "gemini-embedding-2"},
    }
