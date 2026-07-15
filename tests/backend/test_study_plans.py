from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import KnowledgeMastery, LearningRecord, StudyPlanVersion


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _generate(
    client: TestClient,
    headers: dict[str, str],
    course_id: int,
    start: date,
    end: date | None = None,
    **overrides,
) -> dict:
    payload = {
        "start_date": start.isoformat(),
        "end_date": (end or start + timedelta(days=6)).isoformat(),
        "daily_availability": {"default_minutes": 120},
        "session_minutes": 45,
        "goal": "Finish the real course review",
        **overrides,
    }
    response = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200
    return response.json()["data"]


def _confirm(client: TestClient, headers: dict[str, str], generated: dict):
    return client.post(
        f"/api/v1/study-plans/{generated['plan_id']}/versions/{generated['candidate_version']['version']}/confirm",
        headers=headers,
        json={
            "expected_base_version": generated["expected_base_version"],
            "confirmation_token": generated["confirmation_token"],
        },
    )


def _second_user(client: TestClient) -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": "plan-second@example.com", "password": "plan-second-password", "display_name": "Plan Second"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "plan-second@example.com", "password": "plan-second-password"},
    )
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def test_candidate_current_recovery_and_active_task_gate(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Candidate plan")
    assert client.get(
        f"/api/v1/courses/{course_id}/study-plans/current", headers=auth_headers
    ).status_code == 404

    start = date(2026, 8, 3)
    generated = _generate(client, auth_headers, course_id, start)
    candidate = generated["candidate_version"]
    assert candidate["status"] == "candidate"
    assert candidate["tasks"]
    assert isinstance(candidate["risks"], list)
    assert generated["expected_base_version"] == 0

    current = client.get(
        f"/api/v1/courses/{course_id}/study-plans/current", headers=auth_headers
    )
    assert current.status_code == 200
    current_data = current.json()["data"]
    assert current_data["plan_id"] == generated["plan_id"]
    assert current_data["plan_status"] == "draft"
    assert current_data["version"] == 1
    assert current_data["status"] != "active"
    assert current_data["confirmation_token"]
    assert current_data["expected_base_version"] == 0

    hidden = client.get(
        "/api/v1/study-tasks/today",
        headers=auth_headers,
        params={"target_date": candidate["tasks"][0]["scheduled_date"]},
    )
    assert hidden.status_code == 200
    assert hidden.json()["data"] == {"items": [], "total": 0}
    blocked = client.post(
        f"/api/v1/study-tasks/{candidate['tasks'][0]['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 30},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "TASK_NOT_ACTIVE"

    recovered_confirm = client.post(
        f"/api/v1/study-plans/{generated['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={"expected_base_version": 0, "confirmation_token": current_data["confirmation_token"]},
    )
    assert recovered_confirm.status_code == 200
    refreshed = client.get(
        f"/api/v1/courses/{course_id}/study-plans/current", headers=auth_headers
    ).json()["data"]
    assert refreshed["plan_status"] == "active"
    assert refreshed["status"] == "active"
    assert refreshed["version"] == refreshed["active_version"] == 1
    assert refreshed["confirmation_token"] is None


def test_active_today_completion_records_mastery_and_idempotency(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Active plan")
    start = date(2026, 8, 10)
    generated = _generate(client, auth_headers, course_id, start)
    assert _confirm(client, auth_headers, generated).status_code == 200
    first = generated["candidate_version"]["tasks"][0]
    task_day = first["scheduled_date"]

    listed = client.get(
        "/api/v1/study-tasks/today",
        headers=auth_headers,
        params={"target_date": task_day, "course_id": course_id},
    )
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert first["id"] in {item["id"] for item in items}
    assert all(item["course_id"] == course_id for item in items)
    assert all(item["scheduled_date"] == task_day for item in items)
    assert all("actual_minutes" in item and "knowledge_point_id" in item for item in items)
    assert client.get(
        "/api/v1/study-tasks/today",
        headers=auth_headers,
        params={"target_date": "2027-01-01", "course_id": course_id},
    ).json()["data"]["total"] == 0

    completed = client.post(
        f"/api/v1/study-tasks/{first['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 37},
    )
    assert completed.status_code == 200
    completed_data = completed.json()["data"]
    assert completed_data["status"] == "completed"
    assert completed_data["actual_minutes"] == 37
    assert completed_data["mastery_score"] > 0.3
    assert completed_data["idempotent_replay"] is False

    replay = client.post(
        f"/api/v1/study-tasks/{first['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 99},
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["idempotent_replay"] is True
    assert replay.json()["data"]["actual_minutes"] == 37

    persisted = client.get(
        "/api/v1/study-tasks/today",
        headers=auth_headers,
        params={"target_date": task_day, "course_id": course_id},
    ).json()["data"]["items"]
    persisted_task = next(item for item in persisted if item["id"] == first["id"])
    assert persisted_task["status"] == "completed"
    assert persisted_task["actual_minutes"] == 37

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count(LearningRecord.id)).where(LearningRecord.task_id == first["id"])) == 1
        mastery = db.scalar(
            select(KnowledgeMastery).where(
                KnowledgeMastery.knowledge_point_id == first["knowledge_point_id"]
            )
        )
        assert mastery is not None
        assert mastery.attempts == 1
        assert mastery.score == completed_data["mastery_score"]


def test_new_plan_supersedes_old_tasks_and_enforces_user_isolation(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Replacement plan")
    start = date(2026, 8, 17)
    first_plan = _generate(client, auth_headers, course_id, start)
    assert _confirm(client, auth_headers, first_plan).status_code == 200
    old_task = first_plan["candidate_version"]["tasks"][0]

    second_plan = _generate(client, auth_headers, course_id, start)
    wrong_base = client.post(
        f"/api/v1/study-plans/{second_plan['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={"expected_base_version": 1, "confirmation_token": second_plan["confirmation_token"]},
    )
    assert wrong_base.status_code == 409
    tampered = client.post(
        f"/api/v1/study-plans/{second_plan['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={"expected_base_version": 0, "confirmation_token": second_plan["confirmation_token"] + "x"},
    )
    assert tampered.status_code == 409

    other_headers = _second_user(client)
    assert client.post(
        f"/api/v1/study-plans/{second_plan['plan_id']}/versions/1/confirm",
        headers=other_headers,
        json={"expected_base_version": 0, "confirmation_token": second_plan["confirmation_token"]},
    ).status_code == 404
    assert _confirm(client, auth_headers, second_plan).status_code == 200

    day = old_task["scheduled_date"]
    active_items = client.get(
        "/api/v1/study-tasks/today",
        headers=auth_headers,
        params={"target_date": day, "course_id": course_id},
    ).json()["data"]["items"]
    assert active_items
    assert old_task["id"] not in {item["id"] for item in active_items}
    assert client.post(
        f"/api/v1/study-tasks/{old_task['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 30},
    ).json()["detail"] == "TASK_NOT_ACTIVE"
    assert client.get(
        "/api/v1/study-tasks/today", headers=other_headers, params={"target_date": day}
    ).json()["data"]["total"] == 0
    assert client.post(
        f"/api/v1/study-tasks/{active_items[0]['id']}/complete",
        headers=other_headers,
        json={"actual_minutes": 30},
    ).status_code == 404

    with client.app.state.database.session_factory() as db:
        old_version = db.scalar(
            select(StudyPlanVersion).where(StudyPlanVersion.plan_id == first_plan["plan_id"])
        )
        assert old_version.status == "superseded"


def test_plan_input_validation_and_no_available_dates(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Plan validation")
    endpoint = f"/api/v1/courses/{course_id}/study-plans/generate"
    base = {
        "start_date": "2026-09-01",
        "end_date": "2026-09-07",
        "daily_availability": {"default_minutes": 120},
        "session_minutes": 45,
        "goal": "Review",
    }
    invalid_payloads = [
        {**base, "start_date": "2026-09-08"},
        {**base, "end_date": "2027-04-01"},
        {**base, "daily_availability": {"default_minutes": 0}},
        {**base, "daily_availability": {"default_minutes": 30}, "session_minutes": 45},
        {**base, "daily_availability": {"default_minutes": 120, "bad-date": 30}},
        {**base, "unavailable_dates": ["2026-10-01"]},
        {**base, "goal": "   "},
    ]
    for payload in invalid_payloads:
        assert client.post(endpoint, headers=auth_headers, json=payload).status_code == 422

    unavailable = _generate(
        client,
        auth_headers,
        course_id,
        date(2026, 9, 10),
        date(2026, 9, 10),
        unavailable_dates=["2026-09-10"],
    )
    assert unavailable["candidate_version"]["tasks"] == []
    assert unavailable["candidate_version"]["risks"]
