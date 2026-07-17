from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import AsyncTask, Course, KnowledgeMastery, KnowledgePoint, LearningRecord, StudyTask, utcnow
from backend.app.services.async_tasks import mark_task_cancelled


def _cancel_if_requested(db: Session, task: AsyncTask) -> bool:
    db.refresh(task)
    if not task.cancel_requested:
        return False
    mark_task_cancelled(db, task, "cancelled_by_user")
    return True


def _update_progress(db: Session, task: AsyncTask, progress: int, step: str) -> bool:
    if _cancel_if_requested(db, task):
        return False
    task.status = "processing"
    task.progress = progress
    task.current_step = step
    task.started_at = task.started_at or utcnow()
    db.commit()
    return True


def generate_weekly_report(db: Session, task: AsyncTask) -> dict:
    """Aggregate only the task owner's persisted learning data into a weekly report."""
    payload = task.input_data or {}
    start = datetime.fromisoformat(str(payload["start_date"])).date()
    end = datetime.fromisoformat(str(payload["end_date"])).date()
    course_id = payload.get("course_id")
    user_id = task.user_id
    if not _update_progress(db, task, 10, "loading_learning_data"):
        return {"cancelled": True}

    range_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end, time.max, tzinfo=timezone.utc)
    records_query = select(LearningRecord).where(
        LearningRecord.course_id.in_(select(Course.id).where(Course.owner_id == user_id)),
        LearningRecord.occurred_at >= range_start,
        LearningRecord.occurred_at <= range_end,
    )
    tasks_query = select(StudyTask).where(
        StudyTask.user_id == user_id,
        StudyTask.scheduled_date >= start,
        StudyTask.scheduled_date <= end,
    )
    courses_query = select(Course).where(Course.owner_id == user_id, Course.archived.is_(False))
    if course_id is not None:
        records_query = records_query.where(LearningRecord.course_id == course_id)
        tasks_query = tasks_query.where(StudyTask.course_id == course_id)
        courses_query = courses_query.where(Course.id == course_id)

    records = list(db.scalars(records_query))
    if not _update_progress(db, task, 35, "aggregating_tasks"):
        return {"cancelled": True}
    study_tasks = list(db.scalars(tasks_query))
    report_courses = list(db.scalars(courses_query))
    if not _update_progress(db, task, 60, "aggregating_mastery"):
        return {"cancelled": True}

    mastery_query = (
        select(KnowledgeMastery, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
        .where(KnowledgeMastery.user_id == user_id)
    )
    if course_id is not None:
        mastery_query = mastery_query.where(KnowledgeMastery.course_id == course_id)
    weakest = list(db.execute(mastery_query.order_by(KnowledgeMastery.score.asc()).limit(3)))
    if not _update_progress(db, task, 85, "building_report"):
        return {"cancelled": True}

    total_minutes = round(sum(record.duration_seconds for record in records) / 60)
    study_days = len({record.occurred_at.date() for record in records})
    scheduled = len(study_tasks)
    completed = sum(item.status == "completed" for item in study_tasks)
    rate = round(completed / scheduled, 4) if scheduled else 0.0
    weak_points = [{"knowledge_point": point.name, "score": round(mastery.score, 4)} for mastery, point in weakest]
    scope = "该课程" if course_id is not None else "全部课程"
    summary = (
        f"本周期{scope}完成 {completed}/{scheduled} 个学习任务，累计学习 {total_minutes} 分钟。"
        + (f"建议优先复习{weak_points[0]['knowledge_point']}。" if weak_points else "建议保持当前学习节奏。")
    )
    result = {
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "course_id": course_id,
        "course_names": [course.name for course in report_courses],
        "total_learning_minutes": total_minutes,
        "study_days": study_days,
        "scheduled_tasks": scheduled,
        "completed_tasks": completed,
        "completion_rate": rate,
        "weak_points": weak_points,
        "summary": summary,
    }
    task.status = "success"
    task.progress = 100
    task.current_step = "completed"
    task.result_data = result
    task.error_message = None
    task.finished_at = utcnow()
    db.commit()
    return result
