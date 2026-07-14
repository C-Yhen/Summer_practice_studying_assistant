from __future__ import annotations

from typing import Any

import jwt


def issue_confirmation(
    secret: str,
    *,
    user_id: int,
    action: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
    expires_seconds: int = 300,
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "action": action,
            "resource_id": resource_id,
            "payload": payload or {},
            "exp": __import__("time").time() + expires_seconds,
        },
        secret,
        algorithm="HS256",
    )


def verify_confirmation(
    token: str,
    secret: str,
    *,
    user_id: int,
    action: str,
    resource_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("confirmation token is invalid or expired") from exc
    if (
        claims.get("sub") != str(user_id)
        or claims.get("action") != action
        or claims.get("resource_id") != resource_id
        or claims.get("payload", {}) != (payload or {})
    ):
        raise ValueError("confirmation token does not match this operation")
