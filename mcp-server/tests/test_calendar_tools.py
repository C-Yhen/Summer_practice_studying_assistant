import asyncio

from smart_learning_mcp.client import BackendError
from smart_learning_mcp import server


class FakeBackend:
    def __init__(self):
        self.requests = []
        self.audits = []

    async def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if path.endswith("preview") or "preview-" in path:
            return {
                "data": {
                    "preview": kwargs.get("json") or {"event_id": 1},
                    "confirmation_token": "backend-token",
                    "expires_in_seconds": 300,
                }
            }
        return {"data": {"ok": True}}

    async def audit(self, **kwargs):
        self.audits.append(kwargs)


def _call(value):
    return asyncio.run(value)


def test_get_available_time_uses_backend_parameter_contract(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(server, "client", fake)
    result = _call(
        server.get_available_time(
            user_id=1,
            start_at="2026-07-20T00:00:00Z",
            end_at="2026-07-21T00:00:00Z",
            minimum_minutes=45,
        )
    )
    assert result["ok"] is True
    assert fake.requests[0][2]["params"] == {
        "start_at": "2026-07-20T00:00:00Z",
        "end_at": "2026-07-21T00:00:00Z",
        "minimum_minutes": 45,
    }


def test_create_calendar_event_uses_backend_preview_then_confirmation(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(server, "client", fake)
    event = {
        "title": "Study",
        "start_at": "2026-07-20T12:00:00Z",
        "end_at": "2026-07-20T13:00:00Z",
    }
    preview = _call(server.create_calendar_event(user_id=1, event=event, idempotency_key="one"))
    assert preview["status"] == "confirmation_required"
    assert preview["confirmation_token"] == "backend-token"
    assert fake.requests[0][1] == "/calendar/events/preview"
    assert fake.audits[0]["status"] == "waiting_for_user"
    assert "confirmation_token" not in fake.audits[0]["output_data"]
    result = _call(
        server.create_calendar_event(
            user_id=1,
            event=event,
            confirmation_token="backend-token",
            idempotency_key="one",
        )
    )
    assert result["ok"] is True
    method, path, kwargs = fake.requests[-1]
    assert (method, path) == ("POST", "/calendar/events")
    assert kwargs["confirmation_token"] == "backend-token"
    assert kwargs["idempotency_key"] == "one"
    assert fake.audits[-1]["status"] == "success"


def test_update_and_delete_use_backend_preview_and_write_paths(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(server, "client", fake)
    _call(server.update_calendar_event(user_id=1, event_id=7, changes={"title": "New"}))
    _call(server.update_calendar_event(user_id=1, event_id=7, changes={"title": "New"}, confirmation_token="token"))
    _call(server.delete_calendar_event(user_id=1, event_id=7))
    _call(server.delete_calendar_event(user_id=1, event_id=7, confirmation_token="token"))
    paths = [(method, path) for method, path, _ in fake.requests]
    assert ("POST", "/calendar/events/7/preview-update") in paths
    assert ("PATCH", "/calendar/events/7") in paths
    assert ("POST", "/calendar/events/7/preview-delete") in paths
    assert ("DELETE", "/calendar/events/7") in paths


def test_backend_failure_is_returned_and_audited(monkeypatch):
    class FailingBackend(FakeBackend):
        async def request(self, method, path, **kwargs):
            if path == "/calendar/events/preview":
                raise BackendError("backend returned 409: CALENDAR_CONFLICT")
            return await super().request(method, path, **kwargs)

    fake = FailingBackend()
    monkeypatch.setattr(server, "client", fake)
    result = _call(
        server.create_calendar_event(
            user_id=1,
            event={
                "title": "Conflict",
                "start_at": "2026-07-20T12:00:00Z",
                "end_at": "2026-07-20T13:00:00Z",
            },
        )
    )
    assert result["ok"] is False
    assert "409" in result["error"]
    assert fake.audits[-1]["status"] == "failed"


def test_audit_failure_does_not_hide_successful_tool_result(monkeypatch):
    class AuditFailingBackend(FakeBackend):
        async def audit(self, **kwargs):
            raise BackendError("audit unavailable")

    fake = AuditFailingBackend()
    monkeypatch.setattr(server, "client", fake)
    result = _call(
        server.get_available_time(
            user_id=1,
            start_at="2026-07-20T00:00:00Z",
            end_at="2026-07-21T00:00:00Z",
        )
    )
    assert result["ok"] is True


def test_existing_non_calendar_confirmation_flow_still_verifies(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(server, "client", fake)
    preview = _call(
        server.create_study_task(
            user_id=1,
            plan_id=9,
            task={"title": "Review"},
            access_token="user-token",
        )
    )
    assert preview["status"] == "confirmation_required"
    result = _call(
        server.create_study_task(
            user_id=1,
            plan_id=9,
            task={"title": "Review"},
            confirmation_token=preview["confirmation_token"],
            access_token="user-token",
        )
    )
    assert result["ok"] is True
