from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import KnowledgeMastery, KnowledgePoint, StudyPlanVersion, User


def _course(client: TestClient, headers: dict[str, str], name: str = "Personalized course") -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _second_user(client: TestClient) -> dict[str, str]:
    assert client.post("/api/v1/auth/register", json={"email": "preferences-b@example.com", "password": "preferences-password", "display_name": "Preference B"}).status_code == 201
    response = client.post("/api/v1/auth/login", json={"email": "preferences-b@example.com", "password": "preferences-password"})
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _generate(client: TestClient, headers: dict[str, str], course_id: int, **payload: object) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/study-plans/generate",
        headers=headers,
        json={"start_date": "2026-11-02", "end_date": "2026-11-08", "goal": "Personalize review", **payload},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_profile_and_preferences_are_partial_validated_and_user_scoped(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/v1/users/me/profile").status_code == 401
    initial = client.get("/api/v1/users/me/profile", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.json()["data"]["preferences"]["session_minutes"] == 45

    changed = client.patch("/api/v1/users/me", headers=auth_headers, json={"display_name": "  New Learner  ", "timezone": "Asia/Tokyo"})
    assert changed.status_code == 200
    assert changed.json()["data"]["display_name"] == "New Learner"
    assert changed.json()["data"]["timezone"] == "Asia/Tokyo"
    assert client.patch("/api/v1/users/me", headers=auth_headers, json={"email": "not-allowed@example.com"}).status_code == 422
    assert client.patch("/api/v1/users/me", headers=auth_headers, json={"timezone": "Mars/Olympus"}).json()["detail"] == "INVALID_TIMEZONE"

    updated = client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"daily_minutes": 90, "preferred_resource_types": ["pdf", "pdf", "markdown"]})
    assert updated.status_code == 200
    assert updated.json()["data"]["preferred_resource_types"] == ["pdf", "markdown"]
    partial = client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"session_minutes": 30})
    assert partial.status_code == 200
    assert partial.json()["data"]["daily_minutes"] == 90
    assert partial.json()["data"]["session_minutes"] == 30
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"daily_minutes": 20}).status_code == 422
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"foundation_level": "expert"}).status_code == 422
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"preferred_resource_types": ["video"]}).status_code == 422

    other = _second_user(client)
    other_profile = client.get("/api/v1/users/me/profile", headers=other).json()["data"]
    assert other_profile["user"]["display_name"] == "Preference B"
    assert other_profile["preferences"]["daily_minutes"] == 120


@pytest.mark.parametrize(
    "field",
    [
        "foundation_level", "learning_order", "preferred_difficulty",
        "preferred_resource_types", "session_minutes", "daily_minutes",
        "needs_exam_focus", "needs_error_points", "needs_derivation",
    ],
)
def test_patch_rejects_explicit_null_without_changing_saved_values(
    client: TestClient, auth_headers: dict[str, str], field: str
) -> None:
    baseline_profile = client.get("/api/v1/users/me/profile", headers=auth_headers).json()["data"]
    assert client.patch("/api/v1/users/me", headers=auth_headers, json={"display_name": None}).status_code == 422
    assert client.patch("/api/v1/users/me", headers=auth_headers, json={"timezone": None}).status_code == 422
    response = client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={field: None})
    assert response.status_code == 422
    after_null = client.get("/api/v1/users/me/profile", headers=auth_headers).json()["data"]
    assert after_null["user"] == baseline_profile["user"]
    assert after_null["preferences"] == baseline_profile["preferences"]
    assert client.patch("/api/v1/users/me", headers=auth_headers, json={}).status_code == 200
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={}).status_code == 200
    assert client.get("/api/v1/users/me/profile", headers=auth_headers).json()["data"] == baseline_profile


def test_plan_uses_preferences_overrides_and_preserves_generation_snapshot(client: TestClient, auth_headers: dict[str, str]) -> None:
    course_id = _course(client, auth_headers)
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={
        "daily_minutes": 60, "session_minutes": 30, "foundation_level": "advanced",
        "learning_order": "weakness_first", "preferred_difficulty": "advanced",
        "needs_exam_focus": False, "needs_error_points": True, "needs_derivation": True,
        "preferred_resource_types": ["pdf"],
    }).status_code == 200
    first = _generate(client, auth_headers, course_id)
    context = first["candidate_version"]["diff"]["generation_context"]
    assert context["daily_minutes"] == 60 and context["session_minutes"] == 30
    assert context["foundation_level"] == "advanced" and context["needs_derivation"] is True
    assert context["overrides"] == {"daily_minutes": False, "session_minutes": False}
    tasks = first["candidate_version"]["tasks"]
    assert all(task["estimated_minutes"] <= 30 for task in tasks if task["task_type"] != "exam_review")
    assert all(task["task_type"] != "exam_review" for task in tasks)
    assert any(task["title"].startswith("概念推导：") for task in tasks)
    assert all(task["difficulty"] in {"intermediate", "advanced", "mixed"} for task in tasks)
    by_day: dict[str, int] = {}
    for task in tasks: by_day[task["scheduled_date"]] = by_day.get(task["scheduled_date"], 0) + task["estimated_minutes"]
    assert all(minutes <= 60 for minutes in by_day.values())

    daily_only = _generate(client, auth_headers, course_id, daily_availability={"default_minutes": 90})
    assert daily_only["candidate_version"]["diff"]["generation_context"]["overrides"] == {"daily_minutes": True, "session_minutes": False}
    restored_defaults = _generate(client, auth_headers, course_id)
    assert restored_defaults["candidate_version"]["diff"]["generation_context"]["overrides"] == {"daily_minutes": False, "session_minutes": False}
    session_only = _generate(client, auth_headers, course_id, session_minutes=20)
    assert session_only["candidate_version"]["diff"]["generation_context"]["overrides"] == {"daily_minutes": False, "session_minutes": True}

    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"daily_minutes": 120, "session_minutes": 45, "needs_derivation": False, "needs_exam_focus": True}).status_code == 200
    with client.app.state.database.session_factory() as db:
        original_version = db.scalar(select(StudyPlanVersion).where(StudyPlanVersion.plan_id == first["plan_id"]))
        assert original_version is not None
        assert original_version.diff["generation_context"] == context
    overridden = _generate(client, auth_headers, course_id, daily_availability={"default_minutes": 90}, session_minutes=20)
    override_context = overridden["candidate_version"]["diff"]["generation_context"]
    assert override_context["daily_minutes"] == 90 and override_context["session_minutes"] == 20
    assert override_context["overrides"] == {"daily_minutes": True, "session_minutes": True}
    assert client.post(f"/api/v1/courses/{course_id}/study-plans/generate", headers=auth_headers, json={"start_date": "2026-11-02", "end_date": "2026-11-03", "daily_availability": {"default_minutes": 20}, "session_minutes": 30, "goal": "bad"}).status_code == 422


def test_weakness_order_uses_only_real_attempts_and_keeps_prerequisites(client: TestClient, auth_headers: dict[str, str]) -> None:
    course_id = _course(client, auth_headers, "Ordering course")
    profile = client.get("/api/v1/users/me/profile", headers=auth_headers).json()["data"]
    user_id = profile["user"]["id"]
    with client.app.state.database.session_factory() as db:
        prerequisite = KnowledgePoint(course_id=course_id, name="Prerequisite", importance=0.2, estimated_minutes=30)
        weak = KnowledgePoint(course_id=course_id, name="Real weak", importance=0.3, estimated_minutes=30, prerequisite_ids=[])
        unknown = KnowledgePoint(course_id=course_id, name="Unknown", importance=0.95, estimated_minutes=30, prerequisite_ids=[prerequisite.id] if prerequisite.id else [])
        db.add_all([prerequisite, weak])
        db.flush()
        unknown.prerequisite_ids = [prerequisite.id]
        db.add(unknown)
        db.flush()
        db.add(KnowledgeMastery(user_id=user_id, course_id=course_id, knowledge_point_id=weak.id, score=0.1, confidence=0.5, attempts=2, correct_attempts=0))
        db.add(KnowledgeMastery(user_id=user_id, course_id=course_id, knowledge_point_id=unknown.id, score=0.0, confidence=0.0, attempts=0, correct_attempts=0))
        db.commit()

    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"daily_minutes": 30, "session_minutes": 30, "learning_order": "weakness_first", "needs_error_points": True, "needs_exam_focus": False}).status_code == 200
    planned = _generate(client, auth_headers, course_id)
    names = [task["title"] for task in planned["candidate_version"]["tasks"] if task["task_type"] != "spaced_review"]
    assert "Real weak" in names[0]
    assert next(index for index, name in enumerate(names) if "Prerequisite" in name) < next(index for index, name in enumerate(names) if "Unknown" in name)
    assert client.patch("/api/v1/users/me/preferences", headers=auth_headers, json={"needs_error_points": False, "learning_order": "explain_first"}).status_code == 200
    explain = _generate(client, auth_headers, course_id)
    explain_names = [task["title"] for task in explain["candidate_version"]["tasks"] if task["task_type"] != "spaced_review"]
    assert "Prerequisite" in explain_names[0] or "Unknown" not in explain_names[0]
