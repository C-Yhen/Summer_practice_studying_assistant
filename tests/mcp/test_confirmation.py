from __future__ import annotations

import sys
from pathlib import Path

import pytest

MCP_SRC = Path(__file__).resolve().parents[2] / "mcp-server" / "src"
sys.path.insert(0, str(MCP_SRC))

from smart_learning_mcp.confirmation import ConfirmationError, ConfirmationManager


def test_confirmation_token_accepts_unchanged_payload() -> None:
    manager = ConfirmationManager(secret="test-secret", ttl_seconds=60)
    payload = {"title": "复习第三范式", "minutes": 45}
    token = manager.issue(user_id=7, tool_name="create_study_task", payload=payload)

    manager.verify(
        token,
        user_id=7,
        tool_name="create_study_task",
        payload=payload,
    )


def test_confirmation_token_rejects_changed_payload() -> None:
    manager = ConfirmationManager(secret="test-secret", ttl_seconds=60)
    token = manager.issue(
        user_id=7,
        tool_name="create_calendar_event",
        payload={"title": "学习", "start": "2026-07-15T19:00:00+08:00"},
    )

    with pytest.raises(ConfirmationError, match="参数已变化"):
        manager.verify(
            token,
            user_id=7,
            tool_name="create_calendar_event",
            payload={"title": "学习", "start": "2026-07-15T20:00:00+08:00"},
        )


def test_confirmation_token_is_bound_to_user_and_tool() -> None:
    manager = ConfirmationManager(secret="test-secret", ttl_seconds=60)
    payload = {"event_id": 9}
    token = manager.issue(user_id=7, tool_name="delete_calendar_event", payload=payload)

    with pytest.raises(ConfirmationError, match="不匹配"):
        manager.verify(
            token,
            user_id=8,
            tool_name="delete_calendar_event",
            payload=payload,
        )
