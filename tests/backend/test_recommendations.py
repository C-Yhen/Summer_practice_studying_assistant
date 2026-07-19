from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import (
    Course,
    Document,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    RecommendationRecord,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
    User,
)
from backend.app.recommendation.engine import select_diverse_recommendations

TARGET = date(2026, 7, 17)


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _user_id(client: TestClient, course_id: int) -> int:
    with client.app.state.database.session_factory() as db:
        return db.scalar(select(Course.owner_id).where(Course.id == course_id))


def _register(client: TestClient, email: str) -> dict[str, str]:
    password = "recommendation-test-password"
    assert client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": email}).status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _items(client: TestClient, headers: dict[str, str], course_id: int, **params):
    response = client.get(
        f"/api/v1/courses/{course_id}/recommendations",
        headers=headers,
        params={"target_date": TARGET.isoformat(), **params},
    )
    assert response.status_code == 200
    return response.json()["data"]["items"]


def _recommendations(client: TestClient, headers: dict[str, str], course_id: int, **params):
    response = client.get(
        f"/api/v1/courses/{course_id}/recommendations",
        headers=headers,
        params={"target_date": TARGET.isoformat(), **params},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _plan_versions(db, user_id: int, course_id: int):
    plan = StudyPlan(
        user_id=user_id, course_id=course_id, goal="recommendation scope",
        start_date=TARGET, end_date=TARGET, active_version=2, status="active",
    )
    db.add(plan)
    db.flush()
    old = StudyPlanVersion(plan_id=plan.id, version=1, status="superseded")
    active = StudyPlanVersion(plan_id=plan.id, version=2, status="active")
    candidate = StudyPlanVersion(plan_id=plan.id, version=3, status="candidate")
    db.add_all([old, active, candidate])
    db.flush()
    return old, active, candidate


def _task(version_id: int, user_id: int, course_id: int, title: str, status: str = "todo", point_id: int | None = None):
    return StudyTask(
        plan_version_id=version_id, user_id=user_id, course_id=course_id,
        knowledge_point_id=point_id, scheduled_date=TARGET, title=title,
        task_type="review", estimated_minutes=30, priority=0.8, status=status,
    )


def _record_count(client: TestClient) -> int:
    with client.app.state.database.session_factory() as db:
        return db.scalar(select(func.count()).select_from(RecommendationRecord)) or 0


def test_recommendations_only_include_incomplete_tasks_from_active_plan_version(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Plan A")
    course_b = _course(client, auth_headers, "Plan B")
    user_id = _user_id(client, course_a)
    with client.app.state.database.session_factory() as db:
        old, active, candidate = _plan_versions(db, user_id, course_a)
        active_task = _task(active.id, user_id, course_a, "same title")
        completed = _task(active.id, user_id, course_a, "completed", "completed")
        old_task = _task(old.id, user_id, course_a, "same title")
        candidate_task = _task(candidate.id, user_id, course_a, "candidate")
        _, other_active, _ = _plan_versions(db, user_id, course_b)
        other_task = _task(other_active.id, user_id, course_b, "course B task")
        db.add_all([active_task, completed, old_task, candidate_task, other_task])
        db.commit()
        ids = {active_task.id, completed.id, old_task.id, candidate_task.id, other_task.id}
        active_id = active_task.id

    task_items = [item for item in _items(client, auth_headers, course_a) if item["item_type"] == "study_task"]
    assert [item["item_id"] for item in task_items] == [active_id]
    assert task_items[0]["recommendation_key"].endswith(f":study_task:{active_id}")
    assert not (ids - {active_id}) & {item["item_id"] for item in task_items}


def test_recommendations_feedback_and_history_are_isolated_between_users(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "User A course")
    user_a = _user_id(client, course_a)
    headers_b = _register(client, "recommendation-b@example.com")
    course_b = _course(client, headers_b, "User B course")
    with client.app.state.database.session_factory() as db:
        _, active, _ = _plan_versions(db, user_a, course_a)
        point = KnowledgePoint(course_id=course_a, name="A secret point")
        db.add(point)
        db.flush()
        task = _task(active.id, user_a, course_a, "A secret task", point_id=point.id)
        db.add_all([
            task,
            KnowledgeMastery(user_id=user_a, course_id=course_a, knowledge_point_id=point.id, score=0.1, attempts=3),
            Document(course_id=course_a, title="A ready", file_type="txt", file_path="a.txt", status="ready"),
            LearningRecord(user_id=user_a, course_id=course_a, duration_seconds=600, completed=True, occurred_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc)),
        ])
        db.commit()
    key_a = _items(client, auth_headers, course_a)[0]["recommendation_key"]
    assert client.post(f"/api/v1/courses/{course_a}/recommendations/feedback", headers=auth_headers, json={"recommendation_key": key_a, "action": "saved"}).status_code == 200

    assert client.get(f"/api/v1/courses/{course_a}/recommendations", headers=headers_b).status_code == 404
    assert client.get(f"/api/v1/courses/{course_a}/recommendations/history", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/courses/{course_a}/recommendations/feedback", headers=headers_b, json={"recommendation_key": key_a, "action": "saved"}).status_code == 404
    assert client.post(f"/api/v1/courses/{course_b}/recommendations/feedback", headers=headers_b, json={"recommendation_key": key_a, "action": "saved"}).status_code == 404
    b_items = _items(client, headers_b, course_b)
    assert "A secret task" not in {item["title"] for item in b_items}
    assert not any(item["item_type"] in {"mastery_review", "course_chat", "weekly_report"} for item in b_items)
    assert client.get(f"/api/v1/courses/{course_b}/recommendations/history", headers=headers_b).json()["data"]["total"] == 0
    assert client.get(f"/api/v1/courses/{course_a}/recommendations").status_code == 401
    assert client.get(f"/api/v1/courses/{course_a}/recommendations/history").status_code == 401
    assert client.post(f"/api/v1/courses/{course_a}/recommendations/feedback", json={"recommendation_key": key_a, "action": "saved"}).status_code == 401


def test_recommendation_feedback_rejects_cross_course_and_forged_keys(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Key A")
    course_b = _course(client, auth_headers, "Key B")
    item_a = _items(client, auth_headers, course_a)[0]
    key = item_a["recommendation_key"]
    before = _record_count(client)
    forged = [
        key.replace("rule-v2", "rule-v1"),
        key.replace(f":{course_a}:", f":{course_b}:"),
        key.replace(":create_plan:", ":study_task:"),
        key.rsplit(":", 1)[0] + ":999999",
        "arbitrary-key",
    ]
    for invalid_key in [key, *forged]:
        response = client.post(
            f"/api/v1/courses/{course_b}/recommendations/feedback",
            headers=auth_headers, json={"recommendation_key": invalid_key, "action": "saved"},
        )
        assert response.status_code == 404
        assert _record_count(client) == before

    endpoint = f"/api/v1/courses/{course_a}/recommendations/feedback"
    for action in ("saved", "saved", "skipped", "clicked"):
        assert client.post(endpoint, headers=auth_headers, json={"recommendation_key": key, "action": action}).status_code == 200
    assert _record_count(client) == before + 3
    history = client.get(f"/api/v1/courses/{course_a}/recommendations/history", headers=auth_headers).json()["data"]
    assert history["metrics"] == {"clicked": 1, "saved": 1, "skipped": 1}
    with client.app.state.database.session_factory() as db:
        candidate = next(item for item in _items(client, auth_headers, course_a) if item["recommendation_key"] == key)
        saved = db.scalar(select(RecommendationRecord).where(RecommendationRecord.feedback_action == "saved"))
        assert saved.score == candidate["score"]
        assert saved.reason == candidate["reason"]
        assert saved.score_breakdown == candidate["score_breakdown"]


def test_mastery_recommendations_require_real_attempts_and_matching_course(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Mastery A")
    course_b = _course(client, auth_headers, "Mastery B")
    user_id = _user_id(client, course_a)
    with client.app.state.database.session_factory() as db:
        low = KnowledgePoint(course_id=course_a, name="Real low")
        unseen = KnowledgePoint(course_id=course_a, name="Unseen default")
        foreign = KnowledgePoint(course_id=course_b, name="Foreign low")
        db.add_all([low, unseen, foreign])
        db.flush()
        other_user = User(email="mastery-other@example.com", display_name="Other", password_hash="unused")
        db.add(other_user)
        db.flush()
        db.add_all([
            KnowledgeMastery(user_id=user_id, course_id=course_a, knowledge_point_id=low.id, score=0.2, attempts=3),
            KnowledgeMastery(user_id=user_id, course_id=course_a, knowledge_point_id=unseen.id, score=0.3, attempts=0),
            KnowledgeMastery(user_id=user_id, course_id=course_a, knowledge_point_id=foreign.id, score=0.05, attempts=5),
            KnowledgeMastery(user_id=other_user.id, course_id=course_a, knowledge_point_id=low.id, score=0.01, attempts=9),
        ])
        db.commit()
        low_id, unseen_id, foreign_id = low.id, unseen.id, foreign.id
    mastery = [item for item in _items(client, auth_headers, course_a, limit=20) if item["item_type"] == "mastery_review"]
    assert [item["item_id"] for item in mastery] == [low_id]
    assert mastery[0]["knowledge_point"]["id"] == low_id
    assert "Real low" in mastery[0]["title"] and "3" in mastery[0]["reason"]
    assert unseen_id not in {item["item_id"] for item in mastery}
    assert foreign_id not in {item["item_id"] for item in mastery}


def test_document_recommendations_only_use_ready_visible_course_documents(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Docs A")
    course_b = _course(client, auth_headers, "Docs B")
    with client.app.state.database.session_factory() as db:
        db.add_all([
            Document(course_id=course_a, title="processing", file_type="txt", file_path="p", status="processing"),
            Document(course_id=course_a, title="failed", file_type="txt", file_path="f", status="failed"),
            Document(course_id=course_a, title="deleted", file_type="txt", file_path="d", status="ready", is_deleted=True),
            Document(course_id=course_b, title="other ready", file_type="txt", file_path="o", status="ready"),
        ])
        db.commit()
    types = {item["item_type"] for item in _items(client, auth_headers, course_a, category="resource")}
    assert "upload_document" in types and "course_chat" not in types
    with client.app.state.database.session_factory() as db:
        db.add(Document(course_id=course_a, title="visible ready", file_type="txt", file_path="r", status="ready"))
        db.commit()
    types = {item["item_type"] for item in _items(client, auth_headers, course_a, category="resource")}
    assert "course_chat" in types and "upload_document" not in types


def test_weekly_report_recommendation_respects_local_date_course_and_user(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Records A")
    course_b = _course(client, auth_headers, "Records B")
    user_id = _user_id(client, course_a)
    with client.app.state.database.session_factory() as db:
        db.add_all([
            LearningRecord(user_id=user_id, course_id=course_a, duration_seconds=60, occurred_at=datetime(2026, 7, 10, 15, 59, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_b, duration_seconds=60, occurred_at=datetime(2026, 7, 11, 12, tzinfo=timezone.utc)),
        ])
        db.commit()
    assert "weekly_report" not in {item["item_type"] for item in _items(client, auth_headers, course_a)}
    with client.app.state.database.session_factory() as db:
        db.add(LearningRecord(user_id=user_id, course_id=course_a, duration_seconds=60, occurred_at=datetime(2026, 7, 10, 16, 0, tzinfo=timezone.utc)))
        db.commit()
    assert "weekly_report" in {item["item_type"] for item in _items(client, auth_headers, course_a)}


def test_recommendation_order_limit_stability_and_read_only_behavior(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Stable recommendations")
    before = _record_count(client)
    first = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers, params={"target_date": TARGET.isoformat(), "limit": 20})
    second = client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers, params={"target_date": TARGET.isoformat(), "limit": 20})
    assert first.json()["data"] == second.json()["data"]
    items = first.json()["data"]["items"]
    assert [item["score"] for item in items] == sorted((item["score"] for item in items), reverse=True)
    assert len({(item["item_type"], item["item_id"]) for item in items}) == len(items)
    assert len(_items(client, auth_headers, course_id, limit=1)) == 1
    assert len(_items(client, auth_headers, course_id, limit=3)) <= 3
    assert client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers, params={"limit": 0}).status_code == 422
    assert client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers, params={"limit": 21}).status_code == 422
    assert client.get(f"/api/v1/courses/{course_id}/recommendations/exercises", headers=auth_headers).status_code == 501
    assert _record_count(client) == before
    assert client.get(f"/api/v1/courses/{course_id}/recommendations/history", headers=auth_headers).status_code == 200
    assert _record_count(client) == before


def test_recommendation_course_ownership_and_archive_are_hidden(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Archived recommendation course")
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_id)
        course.archived = True
        db.commit()
    assert client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/courses/999999/recommendations", headers=auth_headers).status_code == 404


def test_diverse_default_selection_exposes_real_categories_and_category_queries(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Diverse recommendations")
    user_id = _user_id(client, course_id)
    with client.app.state.database.session_factory() as db:
        course = db.get(Course, course_id)
        course.exam_date = TARGET
        _, active, _ = _plan_versions(db, user_id, course_id)
        point = KnowledgePoint(course_id=course_id, name="Needs review")
        db.add(point)
        db.flush()
        db.add_all([
            *[_task(active.id, user_id, course_id, f"urgent {index}", point_id=point.id) for index in range(6)],
            KnowledgeMastery(user_id=user_id, course_id=course_id, knowledge_point_id=point.id, score=0.2, attempts=3),
            Document(course_id=course_id, title="ready", file_type="txt", file_path="ready", status="ready"),
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=600, completed=True, occurred_at=datetime(2026, 7, 16, 12, tzinfo=timezone.utc)),
        ])
        db.commit()

    before = _record_count(client)
    default = _recommendations(client, auth_headers, course_id, limit=6)
    assert default["selection"] == {"mode": "diverse", "returned": 6, "candidate_total": 9}
    assert default["category_counts"] == {"all": 9, "task": 6, "mastery": 1, "resource": 1, "plan": 0, "report": 1}
    assert {item["category"] for item in default["items"]} >= {"task", "mastery", "resource", "report"}
    assert sum(item["category"] == "task" for item in default["items"]) == 3
    assert default["items"][0]["item_type"] == "study_task"
    assert all("category" in item and "category_label" in item for item in default["items"])
    assert _record_count(client) == before

    for category, expected_type, expected_count in [
        ("task", "study_task", 6),
        ("mastery", "mastery_review", 1),
        ("resource", "course_chat", 1),
        ("report", "weekly_report", 1),
        ("plan", None, 0),
    ]:
        scoped = _recommendations(client, auth_headers, course_id, category=category, limit=20)
        assert scoped["selection"]["mode"] == "category"
        assert scoped["category_counts"] == default["category_counts"]
        assert len(scoped["items"]) == expected_count
        assert all(item["category"] == category for item in scoped["items"])
        if expected_type is not None:
            assert all(item["item_type"] == expected_type for item in scoped["items"])
    assert client.get(f"/api/v1/courses/{course_id}/recommendations", headers=auth_headers, params={"category": "unknown"}).status_code == 422
    assert _record_count(client) == before


def test_diverse_selector_is_stable_and_only_tasks_can_fill_the_limit() -> None:
    def candidate(item_id: int, score: float, category: str = "task", high: bool = False) -> dict:
        return {
            "recommendation_key": f"rule-v2:1:study_task:{item_id}", "item_type": "study_task",
            "item_id": item_id, "score": score, "category": category,
            "signals": [{"code": "due_today" if high else "upcoming"}],
        }

    only_tasks = [candidate(index, 90 - index, high=index < 3) for index in range(10)]
    assert [item["item_id"] for item in select_diverse_recommendations(only_tasks, 6)] == [0, 1, 3, 4, 5, 6]
    assert select_diverse_recommendations(only_tasks, 6) == select_diverse_recommendations(only_tasks, 6)
    assert [len(select_diverse_recommendations(only_tasks, limit)) for limit in (1, 2, 3, 6, 10)] == [1, 2, 3, 6, 10]

    mixed = only_tasks + [
        {**candidate(100, 60, "mastery"), "item_type": "mastery_review", "recommendation_key": "rule-v2:1:mastery_review:100"},
        {**candidate(101, 59, "resource"), "item_type": "course_chat", "recommendation_key": "rule-v2:1:course_chat:101"},
    ]
    selected = select_diverse_recommendations(mixed, 6)
    assert selected[0]["item_id"] == 0
    assert sum(item["category"] == "task" for item in selected) <= 3
    assert {item["category"] for item in selected} >= {"mastery", "resource"}
