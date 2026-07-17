from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.models import AsyncTask, Course, KnowledgeMastery, KnowledgePoint, LearningRecord, StudyPlan, StudyPlanVersion, StudyTask
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
        plan = StudyPlan(user_id=user_id, course_id=course_id, goal="report", start_date=date(2026, 7, 10), end_date=date(2026, 7, 16))
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
    assert report["weak_points"] == [{"knowledge_point": "事务隔离", "score": 0.42}]
    with client.app.state.database.session_factory() as db:
        assert len(list(db.scalars(select(LearningRecord)))) == record_total
        assert len(list(db.scalars(select(KnowledgeMastery)))) == mastery_total


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
