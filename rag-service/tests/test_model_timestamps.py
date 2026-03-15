from datetime import UTC

import pytest

from app.models.db import RagTenant


@pytest.mark.asyncio
async def test_model_timestamps_are_timezone_aware_utc(integration_session):
    tenant = RagTenant(name="Tenant", api_key_hash="hash")
    integration_session.add(tenant)
    await integration_session.flush()

    assert tenant.created_at.tzinfo is UTC
