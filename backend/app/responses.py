from __future__ import annotations

import uuid
from typing import Any


def ok(data: Any, message: str = "ok") -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": f"req_{uuid.uuid4().hex[:16]}",
    }
