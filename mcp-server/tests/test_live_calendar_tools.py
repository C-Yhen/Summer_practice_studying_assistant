from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from smart_learning_mcp import server


@pytest.mark.skipif(
    os.getenv("ROUND13_LIVE_MCP") != "1",
    reason="requires the opt-in Round 13 live backend environment",
)
def test_live_calendar_tool_two_phase_contract_and_audit_redaction():
    base_url = os.environ["BACKEND_BASE_URL"].rstrip("/")
    unique = uuid.uuid4().hex
    credentials = {
        "email": f"round13-mcp-{unique}@example.com",
        "password": "round13-live-mcp-password",
        "display_name": "Round 13 MCP",
    }
    with httpx.Client(base_url=base_url, timeout=20) as api:
        assert api.post("/auth/register", json=credentials).status_code == 201
        login = api.post(
            "/auth/login",
            json={"email": credentials["email"], "password": credentials["password"]},
        ).json()["data"]
        user_id = login["user"]["id"]
        access_token = login["access_token"]

        available = asyncio.run(
            server.get_available_time(
                user_id=user_id,
                start_at="2026-07-20T00:00:00Z",
                end_at="2026-07-21T00:00:00Z",
                minimum_minutes=45,
                access_token=access_token,
            )
        )
        assert available["ok"] is True

        event = {
            "title": "Live MCP calendar",
            "start_at": "2026-07-20T12:00:00Z",
            "end_at": "2026-07-20T13:00:00Z",
        }
        preview = asyncio.run(
            server.create_calendar_event(
                user_id=user_id,
                event=event,
                idempotency_key=f"live-{unique}",
                access_token=access_token,
            )
        )
        assert preview["status"] == "confirmation_required"
        created = asyncio.run(
            server.create_calendar_event(
                user_id=user_id,
                event=event,
                confirmation_token=preview["confirmation_token"],
                idempotency_key=f"live-{unique}",
                access_token=access_token,
            )
        )
        assert created["ok"] is True
        event_id = created["data"]["data"]["event_id"]

        changes = {
            "title": "Live MCP updated",
            "start_at": "2026-07-20T13:00:00Z",
            "end_at": "2026-07-20T14:00:00Z",
        }
        update_preview = asyncio.run(
            server.update_calendar_event(
                user_id=user_id,
                event_id=event_id,
                changes=changes,
                access_token=access_token,
            )
        )
        updated = asyncio.run(
            server.update_calendar_event(
                user_id=user_id,
                event_id=event_id,
                changes=changes,
                confirmation_token=update_preview["confirmation_token"],
                access_token=access_token,
            )
        )
        assert updated["ok"] is True

        delete_preview = asyncio.run(
            server.delete_calendar_event(
                user_id=user_id,
                event_id=event_id,
                access_token=access_token,
            )
        )
        deleted = asyncio.run(
            server.delete_calendar_event(
                user_id=user_id,
                event_id=event_id,
                confirmation_token=delete_preview["confirmation_token"],
                access_token=access_token,
            )
        )
        assert deleted["ok"] is True

        headers = {"Authorization": f"Bearer {access_token}"}
        audit = api.get(
            "/mcp/tool-calls?calendar_only=true&limit=20",
            headers=headers,
        ).json()["data"]
        assert audit["total"] >= 7
        assert {
            "get_available_time",
            "create_calendar_event",
            "update_calendar_event",
            "delete_calendar_event",
        }.issubset({item["tool_name"] for item in audit["items"]})
