from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import (
    AsyncTask,
    Course,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
    User,
)
from backend.app.services.async_tasks import dispatch_async_task


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _weekly(client: TestClient, headers: dict[str, str], **input_data: object):
    return client.post("/api/v1/async-tasks", headers=headers, json={"task_type": "weekly_report", "input_data": input_data})


def test_weekly_report_aggregates_owner_data_without_mutating_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Async report")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        point = KnowledgePoint(course_id=course_id, name="事务隔离")
        db.add(point)
        db.flush()
        plan = StudyPlan(user_id=user_id, course_id=course_id, goal="report", start_date=date(2026, 7, 10), end_date=date(2026, 7, 16), active_version=1, status="active")
        db.add(plan); db.flush()
        version = StudyPlanVersion(plan_id=plan.id, version=1, status="active")
        db.add(version); db.flush()
        db.add_all([
            StudyTask(plan_version_id=version.id, user_id=user_id, course_id=course_id, knowledge_point_id=point.id, scheduled_date=date(2026, 7, 12), title="复习事务", task_type="review", estimated_minutes=30, status="completed", actual_minutes=25),
            StudyTask(plan_version_id=version.id, user_id=user_id, course_id=course_id, knowledge_point_id=point.id, scheduled_date=date(2026, 7, 13), title="练习隔离级别", task_type="practice", estimated_minutes=30),
            LearningRecord(user_id=user_id, course_id=course_id, knowledge_point_id=point.id, duration_seconds=1500, completed=True, occurred_at=datetime(2026, 7, 12, 12, tzinfo=timezone.utc)),
            KnowledgeMastery(user_id=user_id, course_id=course_id, knowledge_point_id=point.id, score=0.42, confidence=0.5, attempts=1),
        ])
        db.commit()
        record_total = len(list(db.scalars(select(LearningRecord))))
        mastery_total = len(list(db.scalars(select(KnowledgeMastery))))

    response = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-16", course_id=course_id)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "success"
    assert data["resource_type"] == "course"
    report = data["result_data"]
    assert report["total_learning_minutes"] == 25
    assert report["study_days"] == 1
    assert report["scheduled_tasks"] == 2
    assert report["completed_tasks"] == 1
    assert report["completion_rate"] == 0.5
    assert report["report_schema_version"] == 2
    assert report["weak_points"] == [{"knowledge_point_id": point.id, "knowledge_point": "事务隔离", "course_id": course_id, "course_name": "Async report", "score": 0.42, "attempts": 1, "confidence": 0.5}]
    assert report["daily"][2] == {"date": "2026-07-12", "learning_minutes": 25, "scheduled_tasks": 1, "completed_tasks": 1}
    assert report["course_breakdown"] == [{"course_id": course_id, "course_name": "Async report", "learning_minutes": 25, "scheduled_tasks": 2, "completed_tasks": 1, "completion_rate": 0.5}]
    with client.app.state.database.session_factory() as db:
        assert len(list(db.scalars(select(LearningRecord)))) == record_total
        assert len(list(db.scalars(select(KnowledgeMastery)))) == mastery_total


def test_weekly_report_only_counts_active_plan_version_tasks(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Active report scope")
    other_course_id = _course(client, auth_headers, "Other active report scope")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        plan = StudyPlan(
            user_id=user_id,
            course_id=course_id,
            goal="version scope",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 16),
            active_version=2,
            status="active",
        )
        other_plan = StudyPlan(
            user_id=user_id,
            course_id=other_course_id,
            goal="other course",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 16),
            active_version=1,
            status="active",
        )
        db.add_all([plan, other_plan]); db.flush()
        superseded = StudyPlanVersion(plan_id=plan.id, version=1, status="superseded")
        active = StudyPlanVersion(plan_id=plan.id, version=2, status="active")
        candidate = StudyPlanVersion(plan_id=plan.id, version=3, status="candidate")
        other_active = StudyPlanVersion(plan_id=other_plan.id, version=1, status="active")
        db.add_all([superseded, active, candidate, other_active]); db.flush()
        task_date = date(2026, 7, 12)
        db.add_all([
            StudyTask(plan_version_id=active.id, user_id=user_id, course_id=course_id, scheduled_date=task_date, title="active complete", task_type="review", estimated_minutes=20, status="completed"),
            StudyTask(plan_version_id=active.id, user_id=user_id, course_id=course_id, scheduled_date=task_date, title="active todo", task_type="practice", estimated_minutes=20),
            StudyTask(plan_version_id=superseded.id, user_id=user_id, course_id=course_id, scheduled_date=task_date, title="old version", task_type="review", estimated_minutes=999, status="completed"),
            StudyTask(plan_version_id=candidate.id, user_id=user_id, course_id=course_id, scheduled_date=task_date, title="candidate version", task_type="review", estimated_minutes=999, status="completed"),
            StudyTask(plan_version_id=other_active.id, user_id=user_id, course_id=other_course_id, scheduled_date=task_date, title="other active", task_type="review", estimated_minutes=999, status="completed"),
        ])
        db.commit()

    response = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-16", course_id=course_id)
    assert response.status_code == 201
    report = response.json()["data"]["result_data"]
    assert report["scheduled_tasks"] == 2
    assert report["completed_tasks"] == 1
    assert report["completion_rate"] == 0.5


def test_weekly_report_uses_user_timezone_for_boundaries_and_study_days(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Timezone report")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        user = db.get(User, user_id)
        assert user is not None
        user.timezone = "Asia/Shanghai"
        db.add_all([
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=20 * 60, completed=True, occurred_at=datetime(2026, 7, 11, 16, 30, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=10 * 60, completed=True, occurred_at=datetime(2026, 7, 12, 15, 59, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=99 * 60, completed=True, occurred_at=datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc)),
        ])
        db.commit()

    response = _weekly(client, auth_headers, start_date="2026-07-12", end_date="2026-07-12", course_id=course_id)
    assert response.status_code == 201
    report = response.json()["data"]["result_data"]
    assert report["total_learning_minutes"] == 30
    assert report["study_days"] == 1

    with client.app.state.database.session_factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.timezone = "Invalid/Timezone"
        db.add(LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=5 * 60, completed=True, occurred_at=datetime(2026, 7, 12, 0, tzinfo=timezone.utc)))
        db.commit()
    fallback = _weekly(client, auth_headers, start_date="2026-07-12", end_date="2026-07-12", course_id=course_id)
    assert fallback.status_code == 201
    assert fallback.json()["data"]["result_data"]["total_learning_minutes"] == 114


def test_weekly_report_final_cancel_check_prevents_success(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    from backend.app.services import reports

    course_id = _course(client, auth_headers, "Cancelable report")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        task = AsyncTask(
            user_id=user_id,
            task_type="weekly_report",
            resource_type="course",
            resource_id=str(course_id),
            input_data={"start_date": "2026-07-10", "end_date": "2026-07-16", "course_id": course_id},
        )
        db.add(task); db.commit()
        original_update_progress = reports._update_progress

        def request_cancel_after_building(db_session, report_task, progress, step):
            updated = original_update_progress(db_session, report_task, progress, step)
            if updated and step == "building_report":
                report_task.cancel_requested = True
                db_session.commit()
            return updated

        monkeypatch.setattr(reports, "_update_progress", request_cancel_after_building)
        assert reports.generate_weekly_report(db, task) == {"cancelled": True}
        db.refresh(task)
        assert task.status == "cancelled"
        assert task.current_step == "cancelled_by_user"
        assert not task.result_data


def test_weekly_report_retry_rejects_invalid_foreign_and_archived_courses(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Retry owner course")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        foreign_user = User(email="retry-foreign@example.com", display_name="Foreign", password_hash="unused")
        db.add(foreign_user); db.flush()
        foreign_course = Course(owner_id=foreign_user.id, name="Foreign retry course")
        archived_course = Course(owner_id=user_id, name="Archived retry course", archived=True)
        db.add_all([foreign_course, archived_course]); db.flush()
        shared_input = {"start_date": "2026-07-10", "end_date": "2026-07-16"}
        user_report = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="user", resource_id=str(user_id), status="failed", input_data=shared_input)
        invalid = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id="not-a-number", status="failed", input_data=shared_input)
        foreign = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(foreign_course.id), status="failed", input_data=shared_input)
        archived = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(archived_course.id), status="failed", input_data=shared_input)
        db.add_all([user_report, invalid, foreign, archived]); db.commit()
        ids = (user_report.public_id, invalid.public_id, foreign.public_id, archived.public_id)

    assert client.post(f"/api/v1/async-tasks/{ids[0]}/retry", headers=auth_headers).status_code == 200
    for task_id in ids[1:]:
        response = client.post(f"/api/v1/async-tasks/{task_id}/retry", headers=auth_headers)
        assert response.status_code == 404


def test_task_list_filters_paginates_and_hides_other_users(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Task filters")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        db.add_all([
            AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(course_id), status="queued", input_data={"start_date": "2026-07-10", "end_date": "2026-07-16"}),
            AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(course_id), status="failed", input_data={"start_date": "2026-07-10", "end_date": "2026-07-16"}),
        ])
        db.commit()
    listed = client.get("/api/v1/async-tasks?task_type=weekly_report&limit=1&offset=0", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 2
    assert len(listed.json()["data"]["items"]) == 1
    assert client.get("/api/v1/async-tasks?status=unknown", headers=auth_headers).status_code == 422
    assert client.get("/api/v1/async-tasks").status_code == 401


def test_task_validation_cancel_retry_and_dispatch_contract(
    client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    course_id = _course(client, auth_headers, "Task lifecycle")
    assert _weekly(client, auth_headers, start_date="2026-07-16", end_date="2026-07-10").status_code == 422
    assert _weekly(client, auth_headers, start_date="2026-07-01", end_date="2026-08-02").status_code == 422
    unsupported = client.post("/api/v1/async-tasks", headers=auth_headers, json={"task_type": "stage_report", "input_data": {}})
    assert unsupported.status_code == 400 and unsupported.json()["detail"] == "TASK_TYPE_NOT_IMPLEMENTED"

    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        queued = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(course_id), status="queued", input_data={"start_date": "2026-07-10", "end_date": "2026-07-16"})
        failed = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(course_id), status="failed", input_data={"start_date": "2026-07-10", "end_date": "2026-07-16"})
        db.add_all([queued, failed]); db.commit(); db.refresh(queued); db.refresh(failed)
        queued_id, failed_id = queued.public_id, failed.public_id
    cancelled = client.post(f"/api/v1/async-tasks/{queued_id}/cancel", headers=auth_headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert cancelled.json()["data"]["finished_at"] is not None
    retried = client.post(f"/api/v1/async-tasks/{failed_id}/retry", headers=auth_headers)
    assert retried.status_code == 200
    assert retried.json()["data"]["retry_count"] == 1
    assert retried.json()["data"]["status"] == "success"  # sync mode executes the real report service
    assert client.post(f"/api/v1/async-tasks/{failed_id}/cancel", headers=auth_headers).status_code == 409

    called: list[tuple[str, object]] = []
    from backend.app.tasks.jobs import generate_weekly_report_job
    monkeypatch.setattr(generate_weekly_report_job, "delay", lambda task_id: called.append(("weekly_report", task_id)))
    with client.app.state.database.session_factory() as db:
        task = AsyncTask(user_id=user_id, task_type="weekly_report", resource_type="course", resource_id=str(course_id), input_data={"start_date": "2026-07-10", "end_date": "2026-07-16"})
        db.add(task); db.commit()
        client.app.state.settings.sync_document_processing = False
        asyncio.run(dispatch_async_task(db, task, client.app.state.settings))
    assert called == [("weekly_report", task.public_id)]


def test_weekly_report_markdown_export_is_owned_read_only_and_escaped(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Markdown | course")
    created = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-10", course_id=course_id)
    assert created.status_code == 201
    task_id = created.json()["data"]["task_id"]
    response = client.get(f"/api/v1/async-tasks/{task_id}/report.md", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "studypilot-weekly-report-2026-07-10-to-2026-07-10.md" in response.headers["content-disposition"]
    assert "# StudyPilot Weekly Report" in response.text
    assert "Markdown \\| course" in response.text
    assert client.get(f"/api/v1/async-tasks/{task_id}/report.md").status_code == 401
    with client.app.state.database.session_factory() as db:
        task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id))
        assert task is not None and task.status == "success"
