from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime


logger = logging.getLogger("app.observability")


def emit_event(event: str, payload: dict[str, object]) -> None:
    message = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }
    try:
        logger.info(json.dumps(message, sort_keys=True, default=str))
    except Exception:
        logger.info(
            json.dumps(
                {
                    "event": event,
                    "timestamp": message["timestamp"],
                    "serialization_error": True,
                },
                sort_keys=True,
            )
        )


def hash_query(*, question: str, tenant_id: str, project_id: str) -> str:
    raw = f"{question}\n{tenant_id}\n{project_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
