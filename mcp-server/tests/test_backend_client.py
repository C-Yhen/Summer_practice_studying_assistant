import asyncio

import httpx

from smart_learning_mcp.client import (
    BackendClient,
    sanitize_audit_value,
    sanitize_error,
)


def test_recursive_audit_sanitizer_removes_nested_secrets():
    value = {
        "confirmation_token": "secret",
        "nested": [{"ACCESS_TOKEN": "secret"}, {"ok": True}],
        "authorization": "secret",
    }
    assert sanitize_audit_value(value) == {"nested": [{}, {"ok": True}]}
    assert "secret" not in sanitize_error("Authorization: Bearer secret")


def test_backend_client_only_sends_confirmation_header_when_explicit(monkeypatch):
    captured = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, path, **kwargs):
            captured.append(kwargs["headers"])
            return httpx.Response(
                200,
                json={"code": 0, "data": {}},
                request=httpx.Request(method, f"http://test{path}"),
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    client = BackendClient()
    asyncio.run(client.request("GET", "/calendar/events", user_id=1))
    asyncio.run(
        client.request(
            "POST",
            "/calendar/events",
            user_id=1,
            confirmation_token="backend-token",
        )
    )
    assert "X-Confirmation-Token" not in captured[0]
    assert captured[1]["X-Confirmation-Token"] == "backend-token"
