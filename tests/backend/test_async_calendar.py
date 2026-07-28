from fastapi.testclient import TestClient


def test_async_task_and_calendar_confirmation_are_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    task = client.post(
        "/api/v1/async-tasks",
        headers=auth_headers,
        json={"task_type": "weekly_report", "input_data": {"start_date": "2026-07-10", "end_date": "2026-07-16"}},
    )
    assert task.status_code == 201
    task_data = task.json()["data"]
    assert task_data["status"] == "success"
    progress = client.get(
        f"/api/v1/async-tasks/{task_data['task_id']}/progress", headers=auth_headers
    )
    assert progress.json()["data"]["progress"] == 100

    event = {
        "title": "Database review",
        "start_at": "2026-07-15T09:00:00+08:00",
        "end_at": "2026-07-15T10:00:00+08:00",
        "idempotency_key": "calendar-db-review-1",
    }
    preview = client.post(
        "/api/v1/calendar/events/preview", headers=auth_headers, json=event
    )
    assert preview.status_code == 200
    token = preview.json()["data"]["confirmation_token"]
    created = client.post(
        "/api/v1/calendar/events",
        headers={**auth_headers, "X-Confirmation-Token": token},
        json=event,
    )
    assert created.status_code == 200
    assert created.json()["data"]["provider"] == "local"
    replay = client.post(
        "/api/v1/calendar/events",
        headers={**auth_headers, "X-Confirmation-Token": token},
        json=event,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["idempotent_replay"] is True

