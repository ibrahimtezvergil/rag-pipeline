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
            "X-Project-ID": "project-123",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_valid_headers(client, valid_headers):
    response = await client.get("/protected", headers=valid_headers)

    assert response.status_code == 200
    assert response.json() == {
        "project_id": valid_headers["X-Project-ID"],
        "status": "authorized",
    }
