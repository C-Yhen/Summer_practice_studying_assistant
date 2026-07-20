from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import os
from threading import Barrier
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import func, select

from backend.app.database import Database
from backend.app.models import (
    CalendarEvent,
    Course,
    MCPToolCall,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
    User,
)


def _user_id(client: TestClient, email: str = "learner@example.com") -> int:
    with client.app.state.database.session_factory() as db:
        return db.scalar(select(User.id).where(User.email == email))


def _course(client: TestClient, headers: dict, name: str = "Calendar course") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _other_user(client: TestClient) -> dict:
    payload = {
        "email": "calendar-other@example.com",
        "password": "calendar-other-password",
        "display_name": "Calendar Other",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _active_tasks(
    client: TestClient,
    user_id: int,
    course_id: int,
    tasks: list[dict],
) -> list[int]:
    with client.app.state.database.session_factory() as db:
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            goal="calendar",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 26),
            active_version=1,
            status="active",
        )
        db.add(plan)
        db.flush()
        version = StudyPlanVersion(plan_id=plan.id, version=1, status="active")
        db.add(version)
        db.flush()
        records = [
            StudyTask(
                plan_version_id=version.id,
                user_id=user_id,
                course_id=course_id,
                scheduled_date=item.get("scheduled_date", date(2026, 7, 20)),
                title=item["title"],
                task_type=item.get("task_type", "review"),
                estimated_minutes=item.get("estimated_minutes", 30),
                priority=item.get("priority", 0.5),
                status=item.get("status", "todo"),
            )
            for item in tasks
        ]
        db.add_all(records)
        db.commit()
        return [item.id for item in records]


def _direct_event(
    client: TestClient,
    user_id: int,
    title: str,
    start_at: datetime,
    end_at: datetime,
    *,
    task_id: int | None = None,
    key: str | None = None,
) -> int:
    with client.app.state.database.session_factory() as db:
        event = CalendarEvent(
            user_id=user_id,
            study_task_id=task_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            provider="local",
            sync_status="local",
            idempotency_key=key,
        )
        db.add(event)
        db.commit()
        return event.id


def test_calendar_event_range_pagination_timezone_and_user_isolation(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    _direct_event(
        client,
        user_id,
        "Monday at twenty",
        datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        datetime(2026, 7, 20, 13, tzinfo=timezone.utc),
    )
    _direct_event(
        client,
        user_id,
        "Boundary excluded",
        datetime(2026, 7, 27, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 27, 1, tzinfo=timezone.utc),
    )
    other_headers = _other_user(client)
    _direct_event(
        client,
        _user_id(client, "calendar-other@example.com"),
        "Other user",
        datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        datetime(2026, 7, 20, 13, tzinfo=timezone.utc),
    )
    response = client.get(
        "/api/v1/calendar/events?start_date=2026-07-20&end_date=2026-07-26&limit=1&offset=0",
        headers=auth_headers,
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert data["timezone"] == "Asia/Shanghai"
    assert data["total"] == 1
    assert [item["title"] for item in data["items"]] == ["Monday at twenty"]
    assert client.get(
        "/api/v1/calendar/events?start_date=2026-07-20&end_date=2026-07-26",
        headers=other_headers,
    ).json()["data"]["total"] == 1
    assert client.get(
        "/api/v1/calendar/events?start_at=2026-07-20T00:00:00Z&end_date=2026-07-26",
        headers=auth_headers,
    ).status_code == 422


def test_local_date_range_uses_dst_timezone_and_matches_utc_range(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        user.timezone = "America/New_York"
        db.commit()
    included = _direct_event(
        client,
        user_id,
        "DST Sunday",
        datetime(2026, 3, 8, 5, 30, tzinfo=timezone.utc),
        datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )
    _direct_event(
        client,
        user_id,
        "Next local day",
        datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 9, 5, 0, tzinfo=timezone.utc),
    )

    local = client.get(
        "/api/v1/calendar/events?start_date=2026-03-08&end_date=2026-03-08",
        headers=auth_headers,
    ).json()["data"]
    utc = client.get(
        "/api/v1/calendar/events"
        "?start_at=2026-03-08T05:00:00Z&end_at=2026-03-09T04:00:00Z",
        headers=auth_headers,
    ).json()["data"]

    assert local["timezone"] == "America/New_York"
    assert [item["id"] for item in local["items"]] == [included]
    assert local["items"] == utc["items"]


def test_calendar_availability_merges_overlap_and_allows_adjacent(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    _direct_event(client, user_id, "A", datetime(2026, 7, 20, 9, tzinfo=timezone.utc), datetime(2026, 7, 20, 10, tzinfo=timezone.utc))
    _direct_event(client, user_id, "B", datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc), datetime(2026, 7, 20, 11, tzinfo=timezone.utc))
    data = client.get(
        "/api/v1/calendar/availability?start_at=2026-07-20T08:00:00Z&end_at=2026-07-20T12:00:00Z&minimum_minutes=60",
        headers=auth_headers,
    ).json()["data"]
    assert data["slots"] == [
        {"start_at": "2026-07-20T08:00:00+00:00", "end_at": "2026-07-20T09:00:00+00:00", "source": "local-calendar"},
        {"start_at": "2026-07-20T11:00:00+00:00", "end_at": "2026-07-20T12:00:00+00:00", "source": "local-calendar"},
    ]


def test_plan_preview_timezone_confirm_and_repeat_are_idempotent(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers)
    task_ids = _active_tasks(client, user_id, course_id, [
        {"title": "High", "priority": 0.9},
        {"title": "Low", "priority": 0.1},
    ])
    request = {
        "start_date": "2026-07-20",
        "end_date": "2026-07-26",
        "course_id": course_id,
        "daily_start_time": "20:00",
        "gap_minutes": 10,
    }
    preview_response = client.post("/api/v1/calendar/plan-sync/preview", headers=auth_headers, json=request)
    preview = preview_response.json()["data"]
    assert preview_response.status_code == 200
    assert [item["task_id"] for item in preview["items"]] == task_ids
    assert preview["items"][0]["start_at"] == "2026-07-20T12:00:00+00:00"
    before = _event_count(client)
    first = client.post(
        "/api/v1/calendar/plan-sync/confirm",
        headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]},
        json={"preview": preview},
    )
    second = client.post(
        "/api/v1/calendar/plan-sync/confirm",
        headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]},
        json={"preview": preview},
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["created_count"] == 2
    assert second.json()["data"]["created_count"] == 0
    assert second.json()["data"]["replayed_count"] == 2
    assert second.json()["data"]["idempotent_replay"] is True
    assert _event_count(client) == before + 2


def test_plan_preview_rejects_nonexistent_dst_local_time(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "DST boundary")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        user.timezone = "America/New_York"
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            goal="DST boundary",
            start_date=date(2026, 3, 8),
            end_date=date(2026, 3, 8),
            active_version=1,
            status="active",
        )
        db.add(plan)
        db.flush()
        version = StudyPlanVersion(plan_id=plan.id, version=1, status="active")
        db.add(version)
        db.flush()
        db.add(StudyTask(
            plan_version_id=version.id,
            user_id=user_id,
            course_id=course_id,
            scheduled_date=date(2026, 3, 8),
            title="Nonexistent local time",
            task_type="review",
            estimated_minutes=30,
            priority=1,
            status="todo",
        ))
        db.commit()

    response = client.post(
        "/api/v1/calendar/plan-sync/preview",
        headers=auth_headers,
        json={
            "start_date": "2026-03-08",
            "end_date": "2026-03-08",
            "course_id": course_id,
            "daily_start_time": "02:30",
            "gap_minutes": 10,
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_LOCAL_TIME"


def test_plan_preview_keeps_regular_shanghai_local_time(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "Shanghai boundary")
    _active_tasks(client, user_id, course_id, [{"title": "Regular local time"}])
    response = client.post(
        "/api/v1/calendar/plan-sync/preview",
        headers=auth_headers,
        json={
            "start_date": "2026-07-20",
            "end_date": "2026-07-26",
            "course_id": course_id,
            "daily_start_time": "02:30",
            "gap_minutes": 10,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["start_at"] == "2026-07-19T18:30:00+00:00"


def test_plan_preview_uses_first_occurrence_for_ambiguous_fall_time(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "DST fall boundary")
    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        user.timezone = "America/New_York"
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            goal="DST fall boundary",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 1),
            active_version=1,
            status="active",
        )
        db.add(plan)
        db.flush()
        version = StudyPlanVersion(plan_id=plan.id, version=1, status="active")
        db.add(version)
        db.flush()
        db.add(StudyTask(
            plan_version_id=version.id,
            user_id=user_id,
            course_id=course_id,
            scheduled_date=date(2026, 11, 1),
            title="First repeated local time",
            task_type="review",
            estimated_minutes=20,
            priority=1,
            status="todo",
        ))
        db.commit()

    payload = {
        "start_date": "2026-11-01",
        "end_date": "2026-11-01",
        "course_id": course_id,
        "daily_start_time": "01:30",
        "gap_minutes": 10,
    }
    first = client.post(
        "/api/v1/calendar/plan-sync/preview",
        headers=auth_headers,
        json=payload,
    )
    second = client.post(
        "/api/v1/calendar/plan-sync/preview",
        headers=auth_headers,
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_item = first.json()["data"]["items"][0]
    second_item = second.json()["data"]["items"][0]
    assert first_item["scheduled_date"] == "2026-11-01"
    assert first_item["start_at"] == "2026-11-01T05:30:00+00:00"
    assert first_item["end_at"] == "2026-11-01T05:50:00+00:00"
    assert second_item["start_at"] == first_item["start_at"]
    assert second_item["end_at"] == first_item["end_at"]


def test_plan_preview_only_uses_active_version_todo_tasks(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "Version isolation")
    with client.app.state.database.session_factory() as db:
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            goal="versions",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 26),
            active_version=2,
            status="active",
        )
        db.add(plan)
        db.flush()
        superseded = StudyPlanVersion(plan_id=plan.id, version=1, status="superseded")
        active = StudyPlanVersion(plan_id=plan.id, version=2, status="active")
        candidate = StudyPlanVersion(plan_id=plan.id, version=3, status="candidate")
        db.add_all([superseded, active, candidate])
        db.flush()
        tasks = [
            StudyTask(
                plan_version_id=version.id,
                user_id=user_id,
                course_id=course_id,
                scheduled_date=date(2026, 7, 20),
                title=title,
                task_type="review",
                estimated_minutes=30,
                priority=priority,
                status=status,
            )
            for version, title, priority, status in (
                (superseded, "Superseded", 1.0, "todo"),
                (candidate, "Candidate", 1.0, "todo"),
                (active, "Completed", 1.0, "completed"),
                (active, "Active todo", 0.5, "todo"),
            )
        ]
        db.add_all(tasks)
        db.commit()
        active_id = tasks[-1].id

    before = _event_count(client)
    response = client.post(
        "/api/v1/calendar/plan-sync/preview",
        headers=auth_headers,
        json={
            "start_date": "2026-07-20",
            "end_date": "2026-07-26",
            "course_id": course_id,
            "daily_start_time": "20:00",
            "gap_minutes": 10,
        },
    )
    data = response.json()["data"]
    assert response.status_code == 200
    assert [item["task_id"] for item in data["items"]] == [active_id]
    assert data["ready_count"] == 1
    assert _event_count(client) == before


def _event_count(client: TestClient) -> int:
    with client.app.state.database.session_factory() as db:
        return db.scalar(select(func.count()).select_from(CalendarEvent))


def test_plan_confirm_rejects_stale_task_and_new_conflict(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "Stale course")
    task_id = _active_tasks(client, user_id, course_id, [{"title": "Stale"}])[0]
    request = {"start_date": "2026-07-20", "end_date": "2026-07-26", "course_id": course_id, "daily_start_time": "20:00", "gap_minutes": 10}
    preview = client.post("/api/v1/calendar/plan-sync/preview", headers=auth_headers, json=request).json()["data"]
    with client.app.state.database.session_factory() as db:
        db.get(StudyTask, task_id).status = "completed"
        db.commit()
    response = client.post(
        "/api/v1/calendar/plan-sync/confirm",
        headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]},
        json={"preview": preview},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "CALENDAR_PREVIEW_STALE"
    assert _event_count(client) == 0


def test_manual_event_namespace_replay_and_payload_binding(
    client: TestClient, auth_headers: dict
):
    payload = {
        "title": "Manual",
        "start_at": "2026-07-21T12:00:00Z",
        "end_at": "2026-07-21T13:00:00Z",
        "idempotency_key": "plan-task:123",
    }
    preview = client.post("/api/v1/calendar/events/preview", headers=auth_headers, json=payload).json()["data"]
    created = client.post("/api/v1/calendar/events", headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]}, json=payload)
    replay = client.post("/api/v1/calendar/events", headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]}, json=payload)
    assert created.status_code == replay.status_code == 200
    assert replay.json()["data"]["idempotent_replay"] is True
    with client.app.state.database.session_factory() as db:
        event = db.get(CalendarEvent, created.json()["data"]["event_id"])
        assert event.idempotency_key == f"calendar:{_user_id(client)}:manual:plan-task:123"


def test_calendar_update_delete_preserve_study_task(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    course_id = _course(client, auth_headers, "Mutation course")
    task_id = _active_tasks(client, user_id, course_id, [{"title": "Mutable"}])[0]
    event_id = _direct_event(
        client, user_id, "Mutable",
        datetime(2026, 7, 22, 12, tzinfo=timezone.utc),
        datetime(2026, 7, 22, 13, tzinfo=timezone.utc),
        task_id=task_id,
    )
    changes = {"title": "Changed", "start_at": "2026-07-22T13:00:00Z", "end_at": "2026-07-22T14:00:00Z"}
    preview = client.post(f"/api/v1/calendar/events/{event_id}/preview-update", headers=auth_headers, json=changes).json()["data"]
    updated = client.patch(f"/api/v1/calendar/events/{event_id}", headers={**auth_headers, "X-Confirmation-Token": preview["confirmation_token"]}, json=changes)
    assert updated.status_code == 200
    assert updated.json()["data"]["event"]["course_id"] == course_id
    deletion = client.post(f"/api/v1/calendar/events/{event_id}/preview-delete", headers=auth_headers).json()["data"]
    assert client.delete(f"/api/v1/calendar/events/{event_id}", headers={**auth_headers, "X-Confirmation-Token": deletion["confirmation_token"]}).status_code == 200
    with client.app.state.database.session_factory() as db:
        assert db.get(CalendarEvent, event_id) is None
        assert db.get(StudyTask, task_id) is not None


def test_calendar_ics_is_safe_read_only_and_escaped(
    client: TestClient, auth_headers: dict
):
    user_id = _user_id(client)
    _direct_event(
        client, user_id, "中文,标题;换行\n测试",
        datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        datetime(2026, 7, 23, 13, tzinfo=timezone.utc),
    )
    before = _event_count(client)
    response = client.get("/api/v1/calendar/export.ics?start_date=2026-07-20&end_date=2026-07-26", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "\r\n" in response.text
    assert "BEGIN:VCALENDAR" in response.text and "END:VCALENDAR" in response.text
    assert "DTSTART:20260723T120000Z" in response.text
    assert "SUMMARY:中文\\,标题\\;换行\\n测试" in response.text
    assert "learner@example.com" not in response.text
    assert _event_count(client) == before


def test_mcp_audit_recursively_redacts_and_paginates(
    client: TestClient, auth_headers: dict
):
    payload = {
        "agent_run_id": "calendar-audit-1",
        "tool_name": "create_calendar_event",
        "input_data": {"nested": [{"confirmation_token": "secret"}, {"value": 1}], "Authorization": "Bearer secret"},
        "output_data": {"result": {"access_token": "secret", "ok": True}},
        "status": "waiting_for_user",
        "duration_ms": 2,
        "error_message": "Authorization: Bearer secret",
    }
    response = client.post("/api/v1/mcp/tool-calls", headers=auth_headers, json=payload)
    assert response.status_code == 200
    with client.app.state.database.session_factory() as db:
        call = db.scalar(select(MCPToolCall))
        rendered = str(call.input_data) + str(call.output_data) + str(call.error_message)
        assert "secret" not in rendered
        assert call.input_data == {"nested": [{}, {"value": 1}]}
    listing = client.get("/api/v1/mcp/tool-calls?calendar_only=true&limit=1&offset=0", headers=auth_headers).json()["data"]
    assert listing["total"] == 1 and len(listing["items"]) == 1
    assert client.post("/api/v1/mcp/tool-calls", headers=auth_headers, json={**payload, "tool_name": "not_allowed"}).status_code == 422


@pytest.mark.skipif(
    not os.getenv("ROUND13_API_BASE_URL")
    or not (
        os.getenv("ROUND13_POSTGRES_URL")
        or os.getenv("DATABASE_URL", "")
    ).startswith("postgresql"),
    reason="requires the opt-in Round 13 PostgreSQL API environment",
)
def test_postgres_plan_confirmation_concurrency_and_api_contract():
    base_url = os.environ["ROUND13_API_BASE_URL"].rstrip("/")
    database = Database(
        os.getenv("ROUND13_POSTGRES_URL") or os.environ["DATABASE_URL"]
    )
    unique = uuid.uuid4().hex
    credentials = {
        "email": f"round13-{unique}@example.com",
        "password": "round13-postgres-password",
        "display_name": "Round 13 PostgreSQL",
    }
    with httpx.Client(timeout=20) as api:
        assert api.post(f"{base_url}/auth/register", json=credentials).status_code == 201
        login = api.post(
            f"{base_url}/auth/login",
            json={"email": credentials["email"], "password": credentials["password"]},
        )
        assert login.status_code == 200
        user_id = login.json()["data"]["user"]["id"]
        headers = {
            "Authorization": f"Bearer {login.json()['data']['access_token']}"
        }
        course_id = api.post(
            f"{base_url}/courses",
            headers=headers,
            json={"name": "Round 13 concurrent calendar"},
        ).json()["data"]["id"]
        with database.session_factory() as db:
            plan = StudyPlan(
                user_id=user_id,
                course_id=course_id,
                goal="concurrent calendar",
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 26),
                active_version=1,
                status="active",
            )
            db.add(plan)
            db.flush()
            version = StudyPlanVersion(plan_id=plan.id, version=1, status="active")
            db.add(version)
            db.flush()
            db.add_all(
                [
                    StudyTask(
                        plan_version_id=version.id,
                        user_id=user_id,
                        course_id=course_id,
                        scheduled_date=date(2026, 7, 20),
                        title=f"Concurrent {index}",
                        task_type="review",
                        estimated_minutes=30,
                        priority=1 - index / 10,
                        status="todo",
                    )
                    for index in range(2)
                ]
            )
            db.commit()
        request = {
            "start_date": "2026-07-20",
            "end_date": "2026-07-26",
            "course_id": course_id,
            "daily_start_time": "20:00",
            "gap_minutes": 10,
        }
        preview = api.post(
            f"{base_url}/calendar/plan-sync/preview",
            headers=headers,
            json=request,
        ).json()["data"]
        confirm_headers = {
            **headers,
            "X-Confirmation-Token": preview["confirmation_token"],
        }
        barrier = Barrier(2)

        def confirm():
            barrier.wait()
            with httpx.Client(timeout=20) as concurrent_api:
                return concurrent_api.post(
                    f"{base_url}/calendar/plan-sync/confirm",
                    headers=confirm_headers,
                    json={"preview": preview},
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: confirm(), range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        results = [response.json()["data"] for response in responses]
        assert sorted(item["created_count"] for item in results) == [0, 2]
        assert sorted(item["replayed_count"] for item in results) == [0, 2]
        assert sorted(item["idempotent_replay"] for item in results) == [False, True]

        replay = api.post(
            f"{base_url}/calendar/plan-sync/confirm",
            headers=confirm_headers,
            json={"preview": preview},
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["created_count"] == 0
        assert replay.json()["data"]["replayed_count"] == 2

        manual_payload = {
            "title": "Concurrent manual event",
            "start_at": "2026-07-21T12:00:00Z",
            "end_at": "2026-07-21T13:00:00Z",
            "idempotency_key": f"concurrent-manual-{unique}",
        }
        manual_preview = api.post(
            f"{base_url}/calendar/events/preview",
            headers=headers,
            json=manual_payload,
        ).json()["data"]
        manual_headers = {
            **headers,
            "X-Confirmation-Token": manual_preview["confirmation_token"],
        }
        manual_barrier = Barrier(2)

        def create_manual():
            manual_barrier.wait()
            with httpx.Client(timeout=20) as concurrent_api:
                return concurrent_api.post(
                    f"{base_url}/calendar/events",
                    headers=manual_headers,
                    json=manual_payload,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            manual_responses = list(
                executor.map(lambda _: create_manual(), range(2))
            )
        assert [response.status_code for response in manual_responses] == [200, 200]
        manual_results = [response.json()["data"] for response in manual_responses]
        assert len({item["event_id"] for item in manual_results}) == 1
        assert sorted(item["idempotent_replay"] for item in manual_results) == [
            False,
            True,
        ]

        listing = api.get(
            f"{base_url}/calendar/events"
            "?start_date=2026-07-20&end_date=2026-07-26",
            headers=headers,
        ).json()["data"]
        assert listing["total"] == 3
        assert listing["timezone"] == "Asia/Shanghai"
        event_id = listing["items"][0]["id"]
        exported = api.get(
            f"{base_url}/calendar/export.ics"
            "?start_date=2026-07-20&end_date=2026-07-26",
            headers=headers,
        )
        assert exported.status_code == 200
        assert exported.text.startswith("BEGIN:VCALENDAR\r\n")

        other_credentials = {
            "email": f"round13-other-{unique}@example.com",
            "password": "round13-other-password",
            "display_name": "Round 13 Other",
        }
        assert (
            api.post(f"{base_url}/auth/register", json=other_credentials).status_code
            == 201
        )
        other_login = api.post(
            f"{base_url}/auth/login",
            json={
                "email": other_credentials["email"],
                "password": other_credentials["password"],
            },
        ).json()["data"]
        other_headers = {
            "Authorization": f"Bearer {other_login['access_token']}"
        }
        other_listing = api.get(
            f"{base_url}/calendar/events"
            "?start_date=2026-07-20&end_date=2026-07-26",
            headers=other_headers,
        ).json()["data"]
        assert other_listing["total"] == 0
        assert (
            api.post(
                f"{base_url}/calendar/events/{event_id}/preview-update",
                headers=other_headers,
                json={"title": "Cross-user mutation"},
            ).status_code
            == 404
        )

        with database.session_factory() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(CalendarEvent)
                    .where(CalendarEvent.user_id == user_id)
                )
                == 3
            )
