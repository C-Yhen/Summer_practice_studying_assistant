"""HTTP adapter used by MCP tools to call controlled backend APIs."""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

import httpx


class BackendError(RuntimeError):
    pass


SENSITIVE_KEYS = {
    "confirmation_token",
    "access_token",
    "authorization",
    "jwt",
    "refresh_token",
    "api_key",
}


def sanitize_audit_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_audit_value(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [sanitize_audit_value(item) for item in value]
    return value


def sanitize_error(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(
        r"(?i)(authorization|confirmation_token|access_token|refresh_token|api_key|jwt)\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        r"\1=[REDACTED]",
        value,
    )


class BackendClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
        self.service_token = os.getenv("MCP_SERVICE_TOKEN", "")

    async def request(
        self,
        method: str,
        path: str,
        *,
        user_id: int,
        access_token: str = "",
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        confirmation_token: str | None = None,
    ) -> Any:
        headers = {
            "X-MCP-User-ID": str(user_id),
            "X-Request-ID": str(uuid.uuid4()),
        }
        token = access_token or self.service_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if confirmation_token:
            headers["X-Confirmation-Token"] = confirmation_token

        timeout = httpx.Timeout(20.0, connect=5.0)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            try:
                response = await client.request(method, path, json=json, params=params, headers=headers)
            except httpx.HTTPError as exc:
                raise BackendError(f"后端服务暂时不可用: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise BackendError(f"后端返回 {response.status_code}: {detail}")
        if response.status_code == 204:
            return {"ok": True}
        return response.json()

    async def audit(
        self,
        *,
        user_id: int,
        access_token: str = "",
        agent_run_id: str,
        tool_name: str,
        input_data: dict[str, Any],
        output_data: Any,
        status: str,
        error: str | None,
        started_at: float,
    ) -> None:
        safe_input = sanitize_audit_value(input_data)
        safe_output = sanitize_audit_value(output_data)
        payload = {
            "user_id": user_id,
            "agent_run_id": agent_run_id,
            "tool_name": tool_name,
            "input_data": safe_input,
            "output_data": safe_output,
            "status": status,
            "error_message": sanitize_error(error),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }
        try:
            await self.request(
                "POST",
                "/mcp/tool-calls",
                user_id=user_id,
                access_token=access_token,
                json=payload,
            )
        except BackendError:
            # Tool execution result must not be hidden merely because audit delivery failed.
            # The backend endpoint is the durable audit sink in production.
            return

