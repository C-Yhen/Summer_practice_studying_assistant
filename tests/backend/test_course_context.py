from datetime import date, timedelta

from fastapi.testclient import TestClient


def _course(
    client: TestClient, headers: dict[str, str], name: str, code: str
) -> dict:
    response = client.post(
        "/api/v1/courses",
        headers=headers,
        json={
            "name": name,
            "code": code,
            "description": f"{name} description",
            "target_score": 80,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


def _second_user(client: TestClient) -> dict[str, str]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "course-context-second@example.com",
            "password": "course-context-password",
            "display_name": "Course Context Second",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "course-context-second@example.com",
            "password": "course-context-password",
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _generate_plan(
    client: TestClient, headers: dict[str, str], course_id: int
) -> dict:
    start = date.today()
    response = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=headers,
        json={
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=2)).isoformat(),
            "daily_availability": {"default_minutes": 60},
            "session_minutes": 30,
            "goal": "Course context verification",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_course_detail_update_archive_and_permissions(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course = _course(client, auth_headers, "Context A", "CTX-A")
    course_id = course["id"]
    second_headers = _second_user(client)

    own = client.get(f"/api/v1/courses/{course_id}", headers=auth_headers)
    assert own.status_code == 200
    assert own.json()["data"]["name"] == "Context A"
    assert client.get("/api/v1/courses/999999", headers=auth_headers).status_code == 404
    assert client.get(f"/api/v1/courses/{course_id}", headers=second_headers).status_code == 404

    updated = client.patch(
        f"/api/v1/courses/{course_id}",
        headers=auth_headers,
        json={
            "name": "Context A Updated",
            "code": "CTX-A2",
            "description": "Persisted description",
            "exam_date": "2026-09-01",
            "target_score": 93,
            "color": "#123456",
        },
    )
    assert updated.status_code == 200
    persisted = client.get(f"/api/v1/courses/{course_id}", headers=auth_headers)
    assert persisted.json()["data"] == updated.json()["data"]
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        headers=auth_headers,
        json={"name": "   "},
    ).status_code == 422

    assert client.patch(
        f"/api/v1/courses/{course_id}",
        headers=second_headers,
        json={"name": "Not allowed"},
    ).status_code == 404
    assert client.delete(
        f"/api/v1/courses/{course_id}", headers=second_headers
    ).status_code == 404

    archived = client.delete(f"/api/v1/courses/{course_id}", headers=auth_headers)
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"
    assert client.get(f"/api/v1/courses/{course_id}", headers=auth_headers).status_code == 404
    listed_ids = {
        item["id"]
        for item in client.get("/api/v1/courses", headers=auth_headers).json()["data"]["items"]
    }
    assert course_id not in listed_ids


def test_course_document_scope_and_real_reparse(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Documents A", "DOC-A")
    course_b = _course(client, auth_headers, "Documents B", "DOC-B")
    uploaded_a = client.post(
        f"/api/v1/courses/{course_a['id']}/documents",
        headers=auth_headers,
        files={"file": ("a.txt", b"Course A document content.", "text/plain")},
    )
    uploaded_b = client.post(
        f"/api/v1/courses/{course_b['id']}/documents",
        headers=auth_headers,
        files={"file": ("b.txt", b"Course B document content.", "text/plain")},
    )
    assert uploaded_a.status_code == uploaded_b.status_code == 201
    document_a = uploaded_a.json()["data"]["document"]
    document_b = uploaded_b.json()["data"]["document"]

    listed_a = client.get(
        f"/api/v1/courses/{course_a['id']}/documents", headers=auth_headers
    ).json()["data"]["items"]
    assert [item["id"] for item in listed_a] == [document_a["id"]]
    assert document_b["id"] not in {item["id"] for item in listed_a}

    reparsed = client.post(
        f"/api/v1/documents/{document_a['id']}/reparse", headers=auth_headers
    )
    assert reparsed.status_code == 200
    assert reparsed.json()["data"]["document_id"] == document_a["id"]
    assert reparsed.json()["data"]["version"] == 2
    assert reparsed.json()["data"]["async_task_id"]
    assert client.delete(
        f"/api/v1/courses/{course_a['id']}", headers=auth_headers
    ).status_code == 200
    assert client.get(
        f"/api/v1/documents/{document_a['id']}", headers=auth_headers
    ).status_code == 404


def test_mastery_and_learning_records_are_real_and_course_scoped(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Learning A", "LRN-A")
    course_b = _course(client, auth_headers, "Learning B", "LRN-B")
    generated_a = _generate_plan(client, auth_headers, course_a["id"])
    _generate_plan(client, auth_headers, course_b["id"])

    initial_mastery = client.get(
        f"/api/v1/courses/{course_a['id']}/knowledge-mastery",
        headers=auth_headers,
    )
    assert initial_mastery.status_code == 200
    assert initial_mastery.json()["data"]["items"]
    assert all(
        item["has_record"] is False
        and item["score"] is None
        and item["confidence"] is None
        and item["attempts"] == 0
        for item in initial_mastery.json()["data"]["items"]
    )

    confirmed = client.post(
        f"/api/v1/study-plans/{generated_a['plan_id']}/versions/1/confirm",
        headers=auth_headers,
        json={
            "expected_base_version": generated_a["expected_base_version"],
            "confirmation_token": generated_a["confirmation_token"],
        },
    )
    assert confirmed.status_code == 200
    task = generated_a["candidate_version"]["tasks"][0]
    completed = client.post(
        f"/api/v1/study-tasks/{task['id']}/complete",
        headers=auth_headers,
        json={"actual_minutes": 31},
    )
    assert completed.status_code == 200

    mastery_a = client.get(
        f"/api/v1/courses/{course_a['id']}/knowledge-mastery",
        headers=auth_headers,
    ).json()["data"]["items"]
    completed_mastery = next(
        item for item in mastery_a if item["knowledge_point_id"] == task["knowledge_point_id"]
    )
    assert completed_mastery["has_record"] is True
    assert completed_mastery["score"] == completed.json()["data"]["mastery_score"]
    assert completed_mastery["attempts"] == 1

    mastery_b = client.get(
        f"/api/v1/courses/{course_b['id']}/knowledge-mastery",
        headers=auth_headers,
    ).json()["data"]["items"]
    assert all(item["has_record"] is False for item in mastery_b)

    records_a = client.get(
        f"/api/v1/courses/{course_a['id']}/learning-records",
        headers=auth_headers,
    ).json()["data"]
    assert records_a["total"] == 1
    assert records_a["items"][0]["task_id"] == task["id"]
    assert records_a["items"][0]["task_title"] == task["title"]
    assert records_a["items"][0]["knowledge_point"]
    assert records_a["summary"]["minutes"] == 31

    records_b = client.get(
        f"/api/v1/courses/{course_b['id']}/learning-records",
        headers=auth_headers,
    ).json()["data"]
    assert records_b == {"items": [], "total": 0, "summary": {"minutes": 0}}
