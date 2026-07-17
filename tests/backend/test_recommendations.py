from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import Course, RecommendationRecord


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_recommendations_are_read_only_and_feedback_history_is_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Recommendation course")
    with client.app.state.database.session_factory() as db:
        before = db.scalar(select(func.count()).select_from(RecommendationRecord))
    first = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers)
    second = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]
    items = first.json()["data"]["items"]
    assert any(item["item_type"] == "create_plan" for item in items)
    assert any(item["item_type"] == "upload_document" for item in items)
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(RecommendationRecord)) == before
    key = items[0]["recommendation_key"]
    for _ in range(2):
        assert client.post(f"/api/v1/courses/{course_id}/recommendations/feedback", headers=auth_headers, json={"recommendation_key": key, "action": "saved"}).status_code == 200
    history = client.get(f"/api/v1/courses/{course_id}/recommendations/history", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()["data"]["total"] == 1
    assert history.json()["data"]["metrics"]["saved"] == 1
    assert client.get(f"/api/v1/courses/{course_id}/recommendations/exercises", headers=auth_headers).status_code == 501


def test_recommendation_course_ownership_and_archive_are_hidden(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Archived recommendation course")
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_id)
        assert course is not None
        course.archived = True
        db.commit()
    assert client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/courses/999999/recommendations", headers=auth_headers).status_code == 404
    assert client.get(f"/api/v1/courses/{course_id}/recommendations").status_code == 401
