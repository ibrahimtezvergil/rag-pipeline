import pytest


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth_headers(client):
    response = await client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authentication headers"


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_invalid_api_key(client):
    response = await client.get(
        "/protected",
        headers={
            "X-API-Key": "invalid-key",
            "X-Application-ID": "application-123",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_application_header(client, valid_headers):
    response = await client.get("/protected", headers=valid_headers)

    assert response.status_code == 200
    assert response.json() == {
        "application_id": valid_headers["X-Application-ID"],
        "status": "authorized",
    }


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_project_header_as_deprecated_fallback(client, valid_headers):
    legacy_headers = {
        "X-API-Key": valid_headers["X-API-Key"],
        "X-Application-ID": valid_headers["X-Application-ID"],
    }

    response = await client.get("/protected", headers=legacy_headers)

    assert response.status_code == 200
    assert response.json() == {
        "application_id": valid_headers["X-Application-ID"],
        "status": "authorized",
    }
