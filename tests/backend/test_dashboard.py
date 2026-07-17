from datetime import date, datetime, time, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.models import (
    AsyncTask,
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


def _overview(
    client: TestClient,
    headers: dict[str, str],
    target_date: date,
    *,
    days: int = 7,
    course_id: int | None = None,
):
    params: dict[str, str | int] = {
        "target_date": target_date.isoformat(),
        "days": days,
    }
    if course_id is not None:
        params["course_id"] = course_id
    return client.get("/api/v1/dashboard/overview", headers=headers, params=params)


def _second_user(client: TestClient) -> tuple[dict[str, str], int]:
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "dashboard-second@example.com",
            "password": "dashboard-second-password",
            "display_name": "Dashboard Second",
        },
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "dashboard-second@example.com",
            "password": "dashboard-second-password",
        },
    )
    assert login.status_code == 200
    return (
        {"Authorization": f"Bearer {login.json()['data']['access_token']}"},
        registered.json()["data"]["id"],
    )


def test_dashboard_requires_auth_and_validates_query(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    endpoint = "/api/v1/dashboard/overview"
    assert client.get(endpoint, params={"target_date": "2026-07-15"}).status_code == 401
    assert client.get(endpoint, headers=auth_headers).status_code == 422
    assert client.get(
        endpoint, headers=auth_headers, params={"target_date": "not-a-date"}
    ).status_code == 422
    assert client.get(
        endpoint, headers=auth_headers, params={"target_date": "2026-07-15", "days": 0}
    ).status_code == 422
    assert client.get(
        endpoint, headers=auth_headers, params={"target_date": "2026-07-15", "days": 31}
    ).status_code == 422


def test_new_user_gets_complete_honest_empty_overview(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    target = date(2026, 7, 15)
    response = _overview(client, auth_headers, target)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_date"] == "2026-07-15"
    assert data["range_start"] == "2026-07-09"
    assert data["range_end"] == "2026-07-15"
    assert data["timezone"] == "Asia/Shanghai"
    assert data["course_count"] == data["ready_document_count"] == 0
    assert data["focus_course"] is None
    assert data["today"] == {
        "items": [],
        "total_count": 0,
        "completed_count": 0,
        "pending_count": 0,
        "planned_minutes": 0,
        "actual_minutes": 0,
        "completion_rate": 0.0,
    }
    assert data["metrics"] == {
        "today_focus_minutes": 0,
        "today_completion_rate": 0.0,
        "average_mastery": None,
        "active_course_count": 0,
        "ready_document_count": 0,
        "study_days_in_range": 0,
    }
    assert len(data["trend"]) == 7
    assert [point["date"] for point in data["trend"]] == [
        (target - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)
    ]
    assert all(
        point["learning_minutes"] == point["scheduled_tasks"]
        == point["completed_tasks"]
        == 0
        and point["completion_rate"] == 0.0
        for point in data["trend"]
    )
    assert data["weak_points"] == []
    assert data["recent_async_tasks"] == []
    assert data["next_action"]["type"] == "course"
    assert data["next_action"]["route"] == "/courses"


def test_dashboard_aggregates_real_data_is_isolated_and_read_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    target = date.today()
    with client.app.state.database.session_factory() as db:
        owner = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert owner is not None
        focus = Course(
            owner_id=owner.id,
            name="Dashboard Focus",
            code="DASH-1",
            exam_date=target + timedelta(days=5),
        )
        later = Course(
            owner_id=owner.id,
            name="Dashboard Later",
            code="DASH-2",
            exam_date=target + timedelta(days=20),
        )
        archived = Course(owner_id=owner.id, name="Dashboard Archived", archived=True)
        db.add_all([focus, later, archived])
        db.flush()

        db.add_all(
            [
                Document(
                    course_id=focus.id,
                    title="Ready focus",
                    file_type="pdf",
                    file_path="ready-focus.pdf",
                    status="ready",
                ),
                Document(
                    course_id=later.id,
                    title="Ready later",
                    file_type="pdf",
                    file_path="ready-later.pdf",
                    status="ready",
                ),
                Document(
                    course_id=focus.id,
                    title="Failed",
                    file_type="pdf",
                    file_path="failed.pdf",
                    status="failed",
                ),
                Document(
                    course_id=focus.id,
                    title="Deleted",
                    file_type="pdf",
                    file_path="deleted.pdf",
                    status="ready",
                    is_deleted=True,
                ),
                Document(
                    course_id=archived.id,
                    title="Archived ready",
                    file_type="pdf",
                    file_path="archived.pdf",
                    status="ready",
                ),
            ]
        )

        weak = KnowledgePoint(course_id=focus.id, name="Weak point")
        stronger = KnowledgePoint(course_id=focus.id, name="Stronger point")
        db.add_all([weak, stronger])
        db.flush()
        db.add_all(
            [
                KnowledgeMastery(
                    user_id=owner.id,
                    course_id=focus.id,
                    knowledge_point_id=weak.id,
                    score=0.2,
                    confidence=0.4,
                    attempts=0,
                ),
                KnowledgeMastery(
                    user_id=owner.id,
                    course_id=focus.id,
                    knowledge_point_id=stronger.id,
                    score=0.8,
                    confidence=0.9,
                    attempts=3,
                ),
            ]
        )

        plan = StudyPlan(
            user_id=owner.id,
            course_id=focus.id,
            goal="Dashboard plan",
            start_date=target - timedelta(days=6),
            end_date=target + timedelta(days=6),
            active_version=2,
            status="active",
        )
        later_plan = StudyPlan(
            user_id=owner.id,
            course_id=later.id,
            goal="Later plan",
            start_date=target,
            end_date=target + timedelta(days=20),
            active_version=1,
            status="active",
        )
        db.add_all([plan, later_plan])
        db.flush()
        superseded = StudyPlanVersion(plan_id=plan.id, version=1, status="superseded")
        active = StudyPlanVersion(plan_id=plan.id, version=2, status="active")
        candidate = StudyPlanVersion(plan_id=plan.id, version=3, status="candidate")
        later_active = StudyPlanVersion(plan_id=later_plan.id, version=1, status="active")
        db.add_all([superseded, active, candidate, later_active])
        db.flush()
        highest = StudyTask(
            plan_version_id=active.id,
            user_id=owner.id,
            course_id=focus.id,
            knowledge_point_id=weak.id,
            scheduled_date=target,
            title="Priority dashboard task",
            task_type="review",
            estimated_minutes=40,
            priority=0.9,
            difficulty="basic",
        )
        second = StudyTask(
            plan_version_id=active.id,
            user_id=owner.id,
            course_id=focus.id,
            knowledge_point_id=stronger.id,
            scheduled_date=target,
            title="Second dashboard task",
            task_type="practice",
            estimated_minutes=20,
            priority=0.5,
            difficulty="advanced",
        )
        old = StudyTask(
            plan_version_id=superseded.id,
            user_id=owner.id,
            course_id=focus.id,
            scheduled_date=target,
            title="Superseded dashboard task",
            task_type="review",
            estimated_minutes=999,
            priority=1.0,
            difficulty="basic",
        )
        unconfirmed = StudyTask(
            plan_version_id=candidate.id,
            user_id=owner.id,
            course_id=focus.id,
            scheduled_date=target,
            title="Candidate dashboard task",
            task_type="review",
            estimated_minutes=999,
            priority=1.0,
            difficulty="basic",
        )
        db.add_all([highest, second, old, unconfirmed])
        db.flush()
        highest_id = highest.id
        focus_id = focus.id
        later_id = later.id

        for index in range(4):
            db.add(
                AsyncTask(
                    public_id=f"dashboard-task-{index}",
                    user_id=owner.id,
                    task_type="document_process",
                    status="succeeded" if index < 3 else "running",
                    progress=100 if index < 3 else 60,
                    current_step=f"step-{index}",
                    created_at=datetime.now(timezone.utc) + timedelta(minutes=index),
                )
            )
        db.commit()

    second_headers, second_user_id = _second_user(client)
    with client.app.state.database.session_factory() as db:
        foreign_course = Course(owner_id=second_user_id, name="Foreign dashboard course")
        db.add(foreign_course)
        db.flush()
        db.add(
            AsyncTask(
                public_id="foreign-dashboard-task",
                user_id=second_user_id,
                task_type="foreign",
                status="running",
                progress=10,
            )
        )
        db.commit()

    before = _overview(client, auth_headers, target)
    assert before.status_code == 200
    before_data = before.json()["data"]
    assert before_data["course_count"] == 2
    assert before_data["ready_document_count"] == 2
    assert before_data["focus_course"]["id"] == focus_id
    assert before_data["focus_course"]["days_until_exam"] == 5
    assert before_data["focus_course"]["has_active_plan"] is True
    assert before_data["today"]["total_count"] == 2
    assert before_data["today"]["planned_minutes"] == 60
    assert [item["title"] for item in before_data["today"]["items"]] == [
        "Priority dashboard task",
        "Second dashboard task",
    ]
    assert before_data["metrics"]["average_mastery"] == 0.5
    assert before_data["weak_points"][0]["knowledge_point"] == "Weak point"
    assert before_data["next_action"]["type"] == "today_task"
    assert before_data["next_action"]["route"] == f"/today?courseId={focus_id}"
    assert len(before_data["recent_async_tasks"]) == 3
    assert [item["task_id"] for item in before_data["recent_async_tasks"]] == [
        "dashboard-task-3",
        "dashboard-task-2",
        "dashboard-task-1",
    ]

    completed = client.post(
        f"/api/v1/study-tasks/{highest_id}/complete",
        headers=auth_headers,
        json={"actual_minutes": 35},
    )
    assert completed.status_code == 200
    after_data = _overview(client, auth_headers, target).json()["data"]
    assert after_data["today"]["completed_count"] == 1
    assert after_data["today"]["completion_rate"] == 0.5
    assert after_data["today"]["actual_minutes"] == 35
    assert after_data["metrics"]["today_focus_minutes"] == 35
    assert after_data["metrics"]["today_completion_rate"] == 0.5
    assert after_data["metrics"]["study_days_in_range"] == 1
    assert after_data["trend"][-1] == {
        "date": target.isoformat(),
        "label": after_data["trend"][-1]["label"],
        "learning_minutes": 35,
        "scheduled_tasks": 2,
        "completed_tasks": 1,
        "completion_rate": 0.5,
    }
    assert after_data["metrics"]["average_mastery"] > 0.5

    explicit = _overview(client, auth_headers, target, course_id=later_id)
    assert explicit.status_code == 200
    assert explicit.json()["data"]["focus_course"]["id"] == later_id
    assert explicit.json()["data"]["course_count"] == 1
    assert explicit.json()["data"]["ready_document_count"] == 1
    assert explicit.json()["data"]["metrics"]["active_course_count"] == 1
    assert explicit.json()["data"]["today"]["total_count"] == 0
    assert explicit.json()["data"]["next_action"]["type"] == "study_plan"

    assert _overview(client, second_headers, target, course_id=focus_id).status_code == 404
    second_data = _overview(client, second_headers, target).json()["data"]
    assert second_data["course_count"] == 1
    assert second_data["ready_document_count"] == 0
    assert [task["task_id"] for task in second_data["recent_async_tasks"]] == [
        "foreign-dashboard-task"
    ]

    with client.app.state.database.session_factory() as db:
        tracked_models = [
            RecommendationRecord,
            StudyTask,
            LearningRecord,
            KnowledgeMastery,
            AsyncTask,
        ]
        counts_before = {
            model.__name__: db.scalar(select(func.count(model.id))) for model in tracked_models
        }
    assert _overview(client, auth_headers, target).status_code == 200
    assert _overview(client, auth_headers, target, days=30).status_code == 200
    with client.app.state.database.session_factory() as db:
        counts_after = {
            model.__name__: db.scalar(select(func.count(model.id))) for model in tracked_models
        }
    assert counts_after == counts_before


def test_timezone_boundary_and_rule_fallbacks(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    target = date(2026, 7, 15)
    with client.app.state.database.session_factory() as db:
        owner = db.scalar(select(User).where(User.email == "learner@example.com"))
        assert owner is not None
        owner.timezone = "Asia/Shanghai"
        empty_course = Course(owner_id=owner.id, name="No ready documents")
        ready_course = Course(owner_id=owner.id, name="Ready without plan")
        db.add_all([empty_course, ready_course])
        db.flush()
        db.add(
            Document(
                course_id=ready_course.id,
                title="Ready",
                file_type="pdf",
                file_path="ready.pdf",
                status="ready",
            )
        )
        db.add(
            LearningRecord(
                user_id=owner.id,
                course_id=ready_course.id,
                record_type="study",
                duration_seconds=12 * 60,
                completed=True,
                occurred_at=datetime.combine(
                    target - timedelta(days=1), time(16, 30), timezone.utc
                ),
            )
        )
        db.commit()
        empty_id = empty_course.id
        ready_id = ready_course.id

    empty_data = _overview(client, auth_headers, target, course_id=empty_id).json()["data"]
    assert empty_data["next_action"]["type"] == "upload"
    ready_data = _overview(client, auth_headers, target, course_id=ready_id).json()["data"]
    assert ready_data["next_action"]["type"] == "study_plan"
    assert ready_data["metrics"]["today_focus_minutes"] == 12
    assert ready_data["trend"][-1]["learning_minutes"] == 12
