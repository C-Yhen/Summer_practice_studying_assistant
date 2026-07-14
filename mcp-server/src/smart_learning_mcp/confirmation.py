"""Stateless, short-lived confirmation tokens for sensitive MCP writes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class ConfirmationError(ValueError):
    """Raised when a confirmation token is missing, expired, or modified."""


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class ConfirmationManager:
    secret: str
    ttl_seconds: int = 300

    def issue(self, *, user_id: int, tool_name: str, payload: dict[str, Any]) -> str:
        body = {
            "user_id": user_id,
            "tool_name": tool_name,
            "payload_sha256": hashlib.sha256(_canonical_payload(payload).encode()).hexdigest(),
            "expires_at": int(time.time()) + self.ttl_seconds,
        }
        encoded = _b64encode(_canonical_payload(body).encode())
        signature = _b64encode(hmac.new(self.secret.encode(), encoded.encode(), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        user_id: int,
        tool_name: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            encoded, supplied_signature = token.split(".", maxsplit=1)
            expected_signature = _b64encode(
                hmac.new(self.secret.encode(), encoded.encode(), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise ConfirmationError("确认令牌签名无效")
            body = json.loads(_b64decode(encoded))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            if isinstance(exc, ConfirmationError):
                raise
            raise ConfirmationError("确认令牌格式无效") from exc

        expected_hash = hashlib.sha256(_canonical_payload(payload).encode()).hexdigest()
        if body.get("user_id") != user_id or body.get("tool_name") != tool_name:
            raise ConfirmationError("确认令牌与用户或操作不匹配")
        if body.get("payload_sha256") != expected_hash:
            raise ConfirmationError("操作参数已变化，请重新确认")
        if int(body.get("expires_at", 0)) < int(time.time()):
            raise ConfirmationError("确认令牌已过期，请重新确认")

