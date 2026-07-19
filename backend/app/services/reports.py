from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import AsyncTask, Course, KnowledgeMastery, KnowledgePoint, LearningRecord, StudyPlan, StudyPlanVersion, StudyTask, User, utcnow
from backend.app.services.async_tasks import mark_task_cancelled
from backend.app.services.timezones import as_utc, local_date_range_utc, resolve_user_timezone


def _cancel_if_requested(db: Session, task: AsyncTask) -> bool:
    db.refresh(task)
    if not task.cancel_requested:
        return False
    mark_task_cancelled(db, task, "cancelled_by_user")
    return True


def _update_progress(db: Session, task: AsyncTask, progress: int, step: str) -> bool:
    if _cancel_if_requested(db, task):
        return False
    task.status, task.progress, task.current_step = "processing", progress, step
    task.started_at = task.started_at or utcnow()
    db.commit()
    return True


def _escape_markdown(value: object) -> str:
    text = str(value if value is not None else "").replace("\\", "\\\\")
    text = text.replace("\r", " ").replace("\n", " ")
    for char in ("|", "`", "[", "]", "<", ">"):
        text = text.replace(char, f"\\{char}")
    return text.lstrip("#").strip()


def render_weekly_report_markdown(result_data: dict[str, Any]) -> str:
    """Render persisted report data only; this function never queries or mutates storage."""
    start, end = _escape_markdown(result_data.get("range_start")), _escape_markdown(result_data.get("range_end"))
    lines = ["# StudyPilot Weekly Report", "", f"Period: {start} to {end}", "", "## Overview", "", "| Learning minutes | Study days | Completed tasks | Planned tasks | Completion rate |", "| ---: | ---: | ---: | ---: | ---: |", f"| {int(result_data.get('total_learning_minutes') or 0)} | {int(result_data.get('study_days') or 0)} | {int(result_data.get('completed_tasks') or 0)} | {int(result_data.get('scheduled_tasks') or 0)} | {float(result_data.get('completion_rate') or 0) * 100:.0f}% |"]
    daily = result_data.get("daily")
    if isinstance(daily, list):
        lines += ["", "## Daily activity", "", "| Date | Minutes | Completed | Planned |", "| --- | ---: | ---: | ---: |"]
        lines += [f"| {_escape_markdown(item.get('date'))} | {int(item.get('learning_minutes') or 0)} | {int(item.get('completed_tasks') or 0)} | {int(item.get('scheduled_tasks') or 0)} |" for item in daily if isinstance(item, dict)]
    breakdown = result_data.get("course_breakdown")
    if isinstance(breakdown, list):
        lines += ["", "## Course breakdown", "", "| Course | Minutes | Completed | Planned | Completion rate |", "| --- | ---: | ---: | ---: | ---: |"]
        lines += [f"| {_escape_markdown(item.get('course_name'))} | {int(item.get('learning_minutes') or 0)} | {int(item.get('completed_tasks') or 0)} | {int(item.get('scheduled_tasks') or 0)} | {float(item.get('completion_rate') or 0) * 100:.0f}% |" for item in breakdown if isinstance(item, dict)]
    weak = result_data.get("weak_points")
    if isinstance(weak, list) and weak:
        lines += ["", "## Weak points", "", "| Knowledge point | Course | Score | Attempts | Confidence |", "| --- | --- | ---: | ---: | ---: |"]
        lines += [f"| {_escape_markdown(item.get('knowledge_point'))} | {_escape_markdown(item.get('course_name'))} | {float(item.get('score') or 0):.2f} | {int(item.get('attempts') or 0)} | {float(item.get('confidence') or 0):.2f} |" for item in weak if isinstance(item, dict)]
    lines += ["", "## Summary", "", _escape_markdown(result_data.get("summary"))]
    return "\n".join(lines) + "\n"


def generate_weekly_report(db: Session, task: AsyncTask) -> dict:
    payload = task.input_data or {}
    start = datetime.fromisoformat(str(payload["start_date"])).date()
    end = datetime.fromisoformat(str(payload["end_date"])).date()
    course_id, user_id = payload.get("course_id"), task.user_id
    if not _update_progress(db, task, 10, "loading_learning_data"):
        return {"cancelled": True}
    user = db.get(User, user_id)
    user_zone, timezone_name = resolve_user_timezone(user.timezone if user else None)
    range_start, range_end = local_date_range_utc(start, end, user_zone)
    valid_courses = select(Course.id).where(Course.owner_id == user_id, Course.archived.is_(False))
    if course_id is not None:
        valid_courses = valid_courses.where(Course.id == course_id)
    records = list(db.scalars(select(LearningRecord).where(LearningRecord.user_id == user_id, LearningRecord.completed.is_(True), LearningRecord.course_id.in_(valid_courses), LearningRecord.occurred_at >= range_start, LearningRecord.occurred_at < range_end)))
    if not _update_progress(db, task, 35, "aggregating_tasks"):
        return {"cancelled": True}
    study_tasks = list(db.scalars(select(StudyTask).join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id).join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id).where(StudyTask.user_id == user_id, StudyTask.course_id.in_(valid_courses), StudyTask.scheduled_date >= start, StudyTask.scheduled_date <= end, StudyPlan.user_id == user_id, StudyPlan.status == "active", StudyPlanVersion.status == "active", StudyPlan.active_version == StudyPlanVersion.version)))
    report_courses = list(db.scalars(select(Course).where(Course.id.in_(valid_courses)).order_by(Course.id)))
    if not _update_progress(db, task, 60, "aggregating_mastery"):
        return {"cancelled": True}
    weakest = list(db.execute(select(KnowledgeMastery, KnowledgePoint, Course).join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id).join(Course, Course.id == KnowledgeMastery.course_id).where(KnowledgeMastery.user_id == user_id, KnowledgeMastery.course_id.in_(valid_courses), KnowledgePoint.course_id == KnowledgeMastery.course_id, KnowledgeMastery.attempts > 0).order_by(KnowledgeMastery.score.asc(), KnowledgeMastery.attempts.desc(), KnowledgeMastery.course_id.asc(), KnowledgePoint.id.asc()).limit(3)))
    if not _update_progress(db, task, 85, "building_report"):
        return {"cancelled": True}
    by_day = { (start + timedelta(days=index)).isoformat(): {"date": (start + timedelta(days=index)).isoformat(), "learning_minutes": 0, "scheduled_tasks": 0, "completed_tasks": 0} for index in range((end - start).days + 1) }
    course_rows = {course.id: {"course_id": course.id, "course_name": course.name, "learning_minutes": 0, "scheduled_tasks": 0, "completed_tasks": 0, "completion_rate": 0.0} for course in report_courses}
    for record in records:
        minutes = round(record.duration_seconds / 60)
        local_day = as_utc(record.occurred_at).astimezone(user_zone).date().isoformat()
        by_day[local_day]["learning_minutes"] += minutes
        course_rows[record.course_id]["learning_minutes"] += minutes
    for item in study_tasks:
        row = by_day[item.scheduled_date.isoformat()]
        row["scheduled_tasks"] += 1
        course_rows[item.course_id]["scheduled_tasks"] += 1
        if item.status == "completed":
            row["completed_tasks"] += 1
            course_rows[item.course_id]["completed_tasks"] += 1
    total_minutes = sum(item["learning_minutes"] for item in by_day.values())
    scheduled = sum(item["scheduled_tasks"] for item in by_day.values())
    completed = sum(item["completed_tasks"] for item in by_day.values())
    course_breakdown = []
    for row in course_rows.values():
        if row["learning_minutes"] or row["scheduled_tasks"]:
            row["completion_rate"] = round(row["completed_tasks"] / row["scheduled_tasks"], 4) if row["scheduled_tasks"] else 0.0
            course_breakdown.append(row)
    course_breakdown.sort(key=lambda item: (-item["learning_minutes"], -item["scheduled_tasks"], item["course_id"]))
    weak_points = [{"knowledge_point_id": point.id, "knowledge_point": point.name, "course_id": course.id, "course_name": course.name, "score": round(min(1.0, max(0.0, mastery.score)), 4), "attempts": mastery.attempts, "confidence": round(min(1.0, max(0.0, mastery.confidence)), 4)} for mastery, point, course in weakest]
    scope_label = report_courses[0].name if course_id is not None and report_courses else "All courses"
    result = {"report_schema_version": 2, "timezone": timezone_name, "scope_label": scope_label, "range_start": start.isoformat(), "range_end": end.isoformat(), "course_id": course_id, "course_names": [course.name for course in report_courses], "total_learning_minutes": total_minutes, "study_days": sum(1 for item in by_day.values() if item["learning_minutes"]), "scheduled_tasks": scheduled, "completed_tasks": completed, "completion_rate": round(completed / scheduled, 4) if scheduled else 0.0, "weak_points": weak_points, "daily": list(by_day.values()), "course_breakdown": course_breakdown, "summary": f"{scope_label}: {total_minutes} learning minutes, {completed}/{scheduled} active-plan tasks completed." + (f" Review {weak_points[0]['knowledge_point']} first." if weak_points else " Keep a steady learning rhythm.")}
    if _cancel_if_requested(db, task):
        return {"cancelled": True}
    task.status, task.progress, task.current_step = "success", 100, "completed"
    task.result_data, task.error_message, task.finished_at = result, None, utcnow()
    db.commit()
    return result
