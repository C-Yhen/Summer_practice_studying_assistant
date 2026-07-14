from __future__ import annotations

import json
import os
from typing import Any


def set_task_progress(task_id: str, payload: dict[str, Any], ttl_seconds: int = 86400) -> None:
    """Best-effort Redis progress. PostgreSQL remains the source of truth."""
    try:
        import redis

        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        client.setex(f"job:{task_id}", ttl_seconds, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        return
