from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import (
    AsyncTask,
    Course,
    Document,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
)
from backend.app.responses import ok
from backend.app.schemas import DashboardOverview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _user_timezone(name: str) -> tuple[ZoneInfo | timezone, str]:
    try:
        return ZoneInfo(name), name
    except (ZoneInfoNotFoundError, ValueError):
        # Records are stored in UTC. UTC is the explicit fallback for an invalid saved timezone.
        return timezone.utc, "UTC"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _focus_course(
    courses: list[Course], active_course_ids: set[int], target_date: date
) -> Course | None:
    if not courses:
        return None
    active_courses = [course for course in courses if course.id in active_course_ids]
    candidates = active_courses or courses
    upcoming = [
        course
        for course in candidates
        if course.exam_date is not None and course.exam_date >= target_date
    ]
    if upcoming:
        return min(upcoming, key=lambda course: (course.exam_date, -course.id))
    return max(candidates, key=lambda course: (course.updated_at, course.id))


@router.get("/overview")
def dashboard_overview(
    db: DBSession,
    current_user: CurrentUser,
    target_date: date,
    days: int = Query(7, ge=1, le=30),
    course_id: int | None = None,
) -> dict:
    range_start = target_date - timedelta(days=days - 1)
    courses = list(
        db.scalars(
            select(Course)
            .where(Course.owner_id == current_user.id, Course.archived.is_(False))
            .order_by(Course.updated_at.desc(), Course.id.desc())
        )
    )
    by_course_id = {course.id: course for course in courses}
    if course_id is not None and course_id not in by_course_id:
        raise HTTPException(status_code=404, detail="Course not found")

    active_course_ids = set(
        db.scalars(
            select(StudyPlan.course_id)
            .join(StudyPlanVersion, StudyPlanVersion.plan_id == StudyPlan.id)
            .where(
                StudyPlan.user_id == current_user.id,
                StudyPlan.status == "active",
                StudyPlanVersion.status == "active",
                StudyPlan.active_version == StudyPlanVersion.version,
            )
        )
    )
    focus = by_course_id.get(course_id) if course_id is not None else _focus_course(
        courses, active_course_ids, target_date
    )

    ready_counts = {
        counted_course_id: count
        for counted_course_id, count in db.execute(
            select(Document.course_id, func.count(Document.id).label("count"))
            .join(Course, Course.id == Document.course_id)
            .where(
                Course.owner_id == current_user.id,
                Course.archived.is_(False),
                Document.status == "ready",
                Document.is_deleted.is_(False),
            )
            .group_by(Document.course_id)
        )
    }
    ready_document_count = (
        ready_counts.get(focus.id, 0)
        if course_id is not None and focus is not None
        else sum(ready_counts.values())
    )
    scoped_course_count = 1 if course_id is not None and focus is not None else len(courses)

    task_scope = [
        StudyTask.user_id == current_user.id,
        StudyTask.scheduled_date >= range_start,
        StudyTask.scheduled_date <= target_date,
        StudyPlan.user_id == current_user.id,
        StudyPlan.status == "active",
        StudyPlanVersion.status == "active",
        StudyPlan.active_version == StudyPlanVersion.version,
    ]
    if focus is not None:
        task_scope.append(StudyTask.course_id == focus.id)
    # Trend task counts use the plan versions that are active at query time.
    range_tasks = list(
        db.scalars(
            select(StudyTask)
            .join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id)
            .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
            .where(*task_scope)
            .order_by(StudyTask.scheduled_date, StudyTask.priority.desc(), StudyTask.id)
        )
    )
    today_tasks = [task for task in range_tasks if task.scheduled_date == target_date]
    today_tasks.sort(key=lambda task: (-task.priority, task.id))
    completed_today = [task for task in today_tasks if task.status == "completed"]
    pending_today = [task for task in today_tasks if task.status != "completed"]
    today_total = len(today_tasks)
    today_completion_rate = len(completed_today) / today_total if today_total else 0.0

    user_zone, timezone_name = _user_timezone(current_user.timezone)
    range_start_utc = datetime.combine(range_start, time.min, user_zone).astimezone(timezone.utc)
    range_end_utc = datetime.combine(
        target_date + timedelta(days=1), time.min, user_zone
    ).astimezone(timezone.utc)
    record_scope = [
        LearningRecord.user_id == current_user.id,
        LearningRecord.completed.is_(True),
        LearningRecord.occurred_at >= range_start_utc,
        LearningRecord.occurred_at < range_end_utc,
    ]
    if focus is not None:
        record_scope.append(LearningRecord.course_id == focus.id)
    records = list(db.scalars(select(LearningRecord).where(*record_scope)))
    learning_seconds_by_day: dict[date, int] = defaultdict(int)
    for record in records:
        local_day = _as_utc(record.occurred_at).astimezone(user_zone).date()
        learning_seconds_by_day[local_day] += record.duration_seconds

    mastery_scope = [KnowledgeMastery.user_id == current_user.id]
    if focus is not None:
        mastery_scope.append(KnowledgeMastery.course_id == focus.id)
    mastery_rows = list(
        db.execute(
            select(KnowledgeMastery, KnowledgePoint, Course)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
            .join(Course, Course.id == KnowledgeMastery.course_id)
            .where(*mastery_scope, Course.owner_id == current_user.id)
            .order_by(KnowledgeMastery.score, KnowledgeMastery.knowledge_point_id)
        )
    )
    average_mastery = (
        round(sum(row[0].score for row in mastery_rows) / len(mastery_rows), 4)
        if mastery_rows
        else None
    )
    weak_points = [
        {
            "knowledge_point_id": mastery.knowledge_point_id,
            "knowledge_point": point.name,
            "course_id": course.id,
            "course_name": course.name,
            "score": mastery.score,
            "attempts": mastery.attempts,
            "confidence": mastery.confidence,
        }
        for mastery, point, course in mastery_rows[:3]
    ]

    tasks_by_day: dict[date, list[StudyTask]] = defaultdict(list)
    for task in range_tasks:
        tasks_by_day[task.scheduled_date].append(task)
    trend = []
    cursor = range_start
    while cursor <= target_date:
        day_tasks = tasks_by_day[cursor]
        completed_count = sum(task.status == "completed" for task in day_tasks)
        scheduled_count = len(day_tasks)
        trend.append(
            {
                "date": cursor,
                "label": WEEKDAY_LABELS[cursor.weekday()],
                "learning_minutes": round(learning_seconds_by_day[cursor] / 60),
                "scheduled_tasks": scheduled_count,
                "completed_tasks": completed_count,
                "completion_rate": completed_count / scheduled_count if scheduled_count else 0.0,
            }
        )
        cursor += timedelta(days=1)

    if pending_today:
        task = pending_today[0]
        next_action = {
            "type": "today_task",
            "title": f"继续完成：{task.title}",
            "reason": "这是今天优先级最高的未完成任务",
            "route": f"/today?courseId={task.course_id}",
        }
    elif weak_points:
        weak = weak_points[0]
        next_action = {
            "type": "weak_point",
            "title": f"巩固薄弱点：{weak['knowledge_point']}",
            "reason": "这是当前已有掌握度记录中分数最低的知识点",
            "route": f"/mastery?courseId={weak['course_id']}",
        }
    elif focus is not None and focus.id in active_course_ids:
        next_action = {
            "type": "study_plan",
            "title": "查看当前学习计划",
            "reason": "当前课程已有生效计划，但今天没有待完成任务",
            "route": f"/plan?courseId={focus.id}",
        }
    elif focus is not None and ready_counts.get(focus.id, 0) == 0:
        next_action = {
            "type": "upload",
            "title": "上传第一份课程资料",
            "reason": "当前课程还没有已就绪资料",
            "route": f"/upload?courseId={focus.id}",
        }
    elif focus is not None:
        next_action = {
            "type": "study_plan",
            "title": "生成学习计划",
            "reason": "课程资料已经就绪，但尚无生效计划",
            "route": f"/plan?courseId={focus.id}",
        }
    else:
        next_action = {
            "type": "course",
            "title": "创建第一门课程",
            "reason": "创建课程后即可上传资料并生成学习计划",
            "route": "/courses",
        }

    recent_async_tasks = list(
        db.scalars(
            select(AsyncTask)
            .where(AsyncTask.user_id == current_user.id)
            .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
            .limit(3)
        )
    )
    response = DashboardOverview(
        target_date=target_date,
        range_start=range_start,
        range_end=target_date,
        timezone=timezone_name,
        course_count=scoped_course_count,
        ready_document_count=ready_document_count,
        focus_course={
            "id": focus.id,
            "name": focus.name,
            "code": focus.code,
            "exam_date": focus.exam_date,
            "days_until_exam": (focus.exam_date - target_date).days
            if focus.exam_date is not None
            else None,
            "has_active_plan": focus.id in active_course_ids,
        }
        if focus is not None
        else None,
        today={
            "items": [
                {
                    "id": task.id,
                    "course_id": task.course_id,
                    "title": task.title,
                    "task_type": task.task_type,
                    "estimated_minutes": task.estimated_minutes,
                    "actual_minutes": task.actual_minutes,
                    "priority": task.priority,
                    "difficulty": task.difficulty,
                    "status": task.status,
                    "scheduled_date": task.scheduled_date,
                }
                for task in today_tasks[:5]
            ],
            "total_count": today_total,
            "completed_count": len(completed_today),
            "pending_count": len(pending_today),
            "planned_minutes": sum(task.estimated_minutes for task in today_tasks),
            "actual_minutes": sum(task.actual_minutes or 0 for task in completed_today),
            "completion_rate": round(today_completion_rate, 4),
        },
        metrics={
            "today_focus_minutes": round(learning_seconds_by_day[target_date] / 60),
            "today_completion_rate": round(today_completion_rate, 4),
            "average_mastery": average_mastery,
            "active_course_count": scoped_course_count,
            "ready_document_count": ready_document_count,
            "study_days_in_range": sum(seconds > 0 for seconds in learning_seconds_by_day.values()),
        },
        trend=trend,
        weak_points=weak_points,
        next_action=next_action,
        recent_async_tasks=[
            {
                "task_id": task.public_id,
                "task_type": task.task_type,
                "status": task.status,
                "progress": task.progress,
                "current_step": task.current_step,
                "created_at": task.created_at,
                "finished_at": task.finished_at,
            }
            for task in recent_async_tasks
        ],
    )
    return ok(response.model_dump(mode="json"))
