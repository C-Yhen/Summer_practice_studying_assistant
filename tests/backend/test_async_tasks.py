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
from backend.app.services.reports import allocate_rounded_minutes, render_weekly_report_markdown


def _course(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/api/v1/courses", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _weekly(client: TestClient, headers: dict[str, str], **input_data: object):
    return client.post("/api/v1/async-tasks", headers=headers, json={"task_type": "weekly_report", "input_data": input_data})


def _other_user(client: TestClient) -> dict[str, str]:
    payload = {"email": "other-report@example.com", "password": "correct-horse-battery-staple", "full_name": "Other"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def test_allocate_rounded_minutes_handles_half_and_remainder_stably() -> None:
    assert allocate_rounded_minutes({"a": 31, "b": 31}, lambda key: key) == {"a": 1, "b": 0}
    assert allocate_rounded_minutes({"a": 29, "b": 29}, lambda key: key) == {"a": 1, "b": 0}
    assert allocate_rounded_minutes({"only": 30}, lambda key: key) == {"only": 1}
    assert allocate_rounded_minutes({"bad": -90}, lambda key: key) == {"bad": 0}


def test_weekly_report_allocates_seconds_consistently_across_days_and_courses(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_a = _course(client, auth_headers, "Remainder A")
    course_b = _course(client, auth_headers, "Remainder B")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_a))
        db.add_all([
            LearningRecord(user_id=user_id, course_id=course_a, duration_seconds=31, completed=True, occurred_at=datetime(2026, 7, 10, 1, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_b, duration_seconds=31, completed=True, occurred_at=datetime(2026, 7, 11, 1, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_a, duration_seconds=600, completed=False, occurred_at=datetime(2026, 7, 10, 2, tzinfo=timezone.utc)),
        ])
        db.commit()
    response = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-11")
    report = response.json()["data"]["result_data"]
    assert report["total_learning_minutes"] == 1
    assert sum(item["learning_minutes"] for item in report["daily"]) == 1
    assert sum(item["learning_minutes"] for item in report["course_breakdown"]) == 1
    assert report["daily"][0]["learning_minutes"] == 1
    assert report["daily"][1]["learning_minutes"] == 0
    assert report["study_days"] == 2


def test_weekly_report_counts_subminute_study_day_from_real_seconds(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Short study")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        db.add_all([
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=29, completed=True, occurred_at=datetime(2026, 7, 10, 1, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=course_id, duration_seconds=29, completed=True, occurred_at=datetime(2026, 7, 10, 2, tzinfo=timezone.utc)),
        ])
        db.commit()
    report = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-10").json()["data"]["result_data"]
    assert report["total_learning_minutes"] == 1
    assert report["daily"][0]["learning_minutes"] == 1
    assert report["study_days"] == 1


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
            StudyTask(plan_version_id=other_active.id, user_id=user_id, course_id=course_id, scheduled_date=task_date, title="mismatched plan course", task_type="review", estimated_minutes=999, status="completed"),
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
    assert "# StudyPilot 学习周报" in response.text
    assert "- 范围：Markdown \\| course" in response.text
    assert "- 时区：Asia/Shanghai" in response.text
    assert "当前周期没有生效计划任务" in response.text
    assert "Markdown \\| course" in response.text
    assert client.get(f"/api/v1/async-tasks/{task_id}/report.md").status_code == 401
    with client.app.state.database.session_factory() as db:
        task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id))
        assert task is not None and task.status == "success"


def test_weekly_report_markdown_formats_percentages_and_blocks_heading_injection() -> None:
    markdown = render_weekly_report_markdown({
        "range_start": "2026-07-10",
        "range_end": "2026-07-16",
        "scope_label": "课程 | [A]",
        "timezone": "Asia/Shanghai",
        "total_learning_minutes": "not-a-number",
        "study_days": float("nan"),
        "scheduled_tasks": 1,
        "completed_tasks": 1,
        "completion_rate": float("inf"),
        "weak_points": [{
            "knowledge_point": "  # 标题\n`代码`",
            "course_name": "课程 | A",
            "score": 0.42,
            "attempts": 1,
            "confidence": 0.5,
        }],
        "summary": "  # 注入",
    })
    assert "- 范围：课程 \\| \\[A\\]" in markdown
    assert "- 时区：Asia/Shanghai" in markdown
    assert "42.0%" in markdown and "50.0%" in markdown and "1 次真实尝试" in markdown
    assert "\n# 标题" not in markdown and "\n# 注入" not in markdown
    assert "\\# 标题" in markdown and "\\# 注入" in markdown
    assert "nan" not in markdown.lower() and "inf" not in markdown.lower()


def test_weekly_report_excludes_archived_foreign_zero_attempt_and_mismatched_data(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    active_id = _course(client, auth_headers, "Visible report course")
    archived_id = _course(client, auth_headers, "Archived report course")
    other_headers = _other_user(client)
    foreign_id = _course(client, other_headers, "Foreign report course")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == active_id))
        other_id = db.scalar(select(Course.owner_id).where(Course.id == foreign_id))
        archived = db.get(Course, archived_id)
        assert archived is not None
        archived.archived = True
        visible_point = KnowledgePoint(course_id=active_id, name="Visible weak point")
        zero_point = KnowledgePoint(course_id=active_id, name="Zero attempts")
        archived_point = KnowledgePoint(course_id=archived_id, name="Archived mismatch")
        db.add_all([visible_point, zero_point, archived_point]); db.flush()
        active_plan = StudyPlan(user_id=user_id, course_id=active_id, goal="active", start_date=date(2026, 7, 10), end_date=date(2026, 7, 10), active_version=1, status="active")
        archived_plan = StudyPlan(user_id=user_id, course_id=archived_id, goal="archived", start_date=date(2026, 7, 10), end_date=date(2026, 7, 10), active_version=1, status="active")
        db.add_all([active_plan, archived_plan]); db.flush()
        active_version = StudyPlanVersion(plan_id=active_plan.id, version=1, status="active")
        archived_version = StudyPlanVersion(plan_id=archived_plan.id, version=1, status="active")
        db.add_all([active_version, archived_version]); db.flush()
        db.add_all([
            LearningRecord(user_id=user_id, course_id=active_id, duration_seconds=60, completed=True, occurred_at=datetime(2026, 7, 10, 1, tzinfo=timezone.utc)),
            LearningRecord(user_id=user_id, course_id=archived_id, duration_seconds=600, completed=True, occurred_at=datetime(2026, 7, 10, 1, tzinfo=timezone.utc)),
            LearningRecord(user_id=other_id, course_id=foreign_id, duration_seconds=600, completed=True, occurred_at=datetime(2026, 7, 10, 1, tzinfo=timezone.utc)),
            StudyTask(plan_version_id=active_version.id, user_id=user_id, course_id=active_id, scheduled_date=date(2026, 7, 10), title="visible", task_type="review", estimated_minutes=10, status="completed"),
            StudyTask(plan_version_id=archived_version.id, user_id=user_id, course_id=archived_id, scheduled_date=date(2026, 7, 10), title="archived", task_type="review", estimated_minutes=10, status="completed"),
            KnowledgeMastery(user_id=user_id, course_id=active_id, knowledge_point_id=visible_point.id, score=0.4, confidence=0.5, attempts=1),
            KnowledgeMastery(user_id=user_id, course_id=active_id, knowledge_point_id=zero_point.id, score=0.1, confidence=0.5, attempts=0),
            KnowledgeMastery(user_id=user_id, course_id=active_id, knowledge_point_id=archived_point.id, score=0.05, confidence=0.5, attempts=3),
            KnowledgeMastery(user_id=other_id, course_id=active_id, knowledge_point_id=zero_point.id, score=0.01, confidence=0.5, attempts=3),
        ])
        db.commit()
    report = _weekly(client, auth_headers, start_date="2026-07-10", end_date="2026-07-10").json()["data"]["result_data"]
    assert report["total_learning_minutes"] == 1
    assert report["scheduled_tasks"] == 1 and report["completed_tasks"] == 1
    assert [item["course_id"] for item in report["course_breakdown"]] == [active_id]
    assert [item["knowledge_point"] for item in report["weak_points"]] == ["Visible weak point"]


def test_weekly_report_markdown_supports_legacy_and_missing_optional_sections() -> None:
    markdown = render_weekly_report_markdown({
        "range_start": "2026-07-10",
        "range_end": "2026-07-16",
        "course_names": ["Legacy course"],
        "total_learning_minutes": 5,
        "study_days": 1,
        "scheduled_tasks": 0,
        "completed_tasks": 0,
        "completion_rate": 0,
        "weak_points": [],
        "summary": "legacy",
    })
    assert "- 范围：Legacy course" in markdown
    assert "- 时区：UTC" in markdown
    assert "## 每日学习" not in markdown
    assert "## 课程分布" not in markdown
    assert "当前周期没有生效计划任务" in markdown


def test_weekly_report_export_rejects_wrong_status_type_and_owner(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Export contracts")
    other_headers = _other_user(client)
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        pending = [
            AsyncTask(user_id=user_id, task_type="weekly_report", status=status_name, result_data={}, input_data={})
            for status_name in ("queued", "processing", "failed")
        ]
        wrong_type = AsyncTask(user_id=user_id, task_type="document_parse", status="success", result_data={"ok": True}, input_data={})
        db.add_all([*pending, wrong_type]); db.commit()
        ids = [item.public_id for item in pending]
        wrong_type_id = wrong_type.public_id
    for task_id in ids:
        assert client.get(f"/api/v1/async-tasks/{task_id}/report.md", headers=auth_headers).status_code == 409
    assert client.get(f"/api/v1/async-tasks/{wrong_type_id}/report.md", headers=auth_headers).status_code == 400
    assert client.get(f"/api/v1/async-tasks/{ids[0]}/report.md", headers=other_headers).status_code == 404


def test_weekly_report_export_uses_safe_fallback_filename_and_is_read_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    course_id = _course(client, auth_headers, "Safe export")
    with client.app.state.database.session_factory() as db:
        user_id = db.scalar(select(Course.owner_id).where(Course.id == course_id))
        task = AsyncTask(
            user_id=user_id,
            task_type="weekly_report",
            status="success",
            input_data={"email": "secret@example.com", "token": "secret-token"},
            result_data={
                "range_start": "../../bad\r\nname",
                "range_end": "2026-99-99",
                "total_learning_minutes": "bad",
                "study_days": None,
                "scheduled_tasks": "bad",
                "completed_tasks": float("nan"),
                "completion_rate": float("inf"),
                "weak_points": [],
                "summary": "safe",
            },
        )
        db.add(task); db.commit(); db.refresh(task)
        task_id, updated_at = task.public_id, task.updated_at
        task_count = len(list(db.scalars(select(AsyncTask))))
        record_count = len(list(db.scalars(select(LearningRecord))))
    response = client.get(f"/api/v1/async-tasks/{task_id}/report.md", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="studypilot-weekly-report.md"'
    assert "secret@example.com" not in response.text and "secret-token" not in response.text
    assert "nan" not in response.text.lower() and "inf" not in response.text.lower()
    with client.app.state.database.session_factory() as db:
        persisted = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id))
        assert persisted is not None and persisted.updated_at == updated_at
        assert len(list(db.scalars(select(AsyncTask)))) == task_count
        assert len(list(db.scalars(select(LearningRecord)))) == record_count
