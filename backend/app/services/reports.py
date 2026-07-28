from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Mapping
from datetime import datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    utcnow,
)
from backend.app.services.async_tasks import mark_task_cancelled
from backend.app.services.timezones import as_utc, local_date_range_utc, resolve_user_timezone

Key = TypeVar("Key", bound=Hashable)


def allocate_rounded_minutes(
    seconds_by_key: Mapping[Key, int],
    stable_key: Callable[[Key], object],
) -> dict[Key, int]:
    """Allocate rounded total minutes deterministically using largest remainders."""
    clean = {key: max(0, int(seconds)) for key, seconds in seconds_by_key.items()}
    result = {key: seconds // 60 for key, seconds in clean.items()}
    total_minutes = (sum(clean.values()) + 30) // 60
    remaining = total_minutes - sum(result.values())
    ranked = sorted(clean, key=lambda key: (-(clean[key] % 60), stable_key(key)))
    for key in ranked[:remaining]:
        result[key] += 1
    return result


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


def _safe_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(0, number)


def _safe_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _escape_markdown(value: object) -> str:
    text = str(value if value is not None else "").replace("\\", "\\\\")
    text = text.replace("\r", " ").replace("\n", " ")
    for char in ("|", "`", "[", "]", "<", ">"):
        text = text.replace(char, f"\\{char}")
    stripped = text.lstrip()
    if stripped.startswith("#"):
        text = text[: len(text) - len(stripped)] + "\\" + stripped
    return text.strip()


def render_weekly_report_markdown(result_data: dict[str, Any]) -> str:
    """Render persisted report data only; this function never queries or mutates storage."""
    start = _escape_markdown(result_data.get("range_start"))
    end = _escape_markdown(result_data.get("range_end"))
    course_names = result_data.get("course_names")
    fallback_scope = (
        course_names[0]
        if isinstance(course_names, list) and len(course_names) == 1
        else "全部课程"
    )
    scope = _escape_markdown(result_data.get("scope_label") or fallback_scope)
    timezone_name = _escape_markdown(result_data.get("timezone") or "UTC")
    scheduled = _safe_int(result_data.get("scheduled_tasks"))
    completed = _safe_int(result_data.get("completed_tasks"))
    completion_rate = min(1.0, max(0.0, _safe_float(result_data.get("completion_rate"))))
    lines = [
        "# StudyPilot 学习周报",
        "",
        f"- 周期：{start} 至 {end}",
        f"- 范围：{scope}",
        f"- 时区：{timezone_name}",
        "",
        "## 总览",
        "",
        f"- 学习时长：{_safe_int(result_data.get('total_learning_minutes'))} 分钟",
        f"- 学习天数：{_safe_int(result_data.get('study_days'))} 天",
        f"- 完成任务：{completed} / {scheduled}",
    ]
    if scheduled:
        lines.append(f"- 完成率：{completion_rate * 100:.1f}%")
    else:
        lines.append("- 当前周期没有生效计划任务")

    daily = result_data.get("daily")
    if isinstance(daily, list):
        lines += ["", "## 每日学习", "", "| 日期 | 分钟 | 完成 | 计划 |", "| --- | ---: | ---: | ---: |"]
        lines += [
            f"| {_escape_markdown(item.get('date'))} | {_safe_int(item.get('learning_minutes'))} | {_safe_int(item.get('completed_tasks'))} | {_safe_int(item.get('scheduled_tasks'))} |"
            for item in daily
            if isinstance(item, dict)
        ]

    breakdown = result_data.get("course_breakdown")
    if isinstance(breakdown, list):
        lines += ["", "## 课程分布", "", "| 课程 | 分钟 | 完成 | 计划 | 完成率 |", "| --- | ---: | ---: | ---: | ---: |"]
        for item in breakdown:
            if not isinstance(item, dict):
                continue
            item_scheduled = _safe_int(item.get("scheduled_tasks"))
            rate_text = f"{min(1.0, max(0.0, _safe_float(item.get('completion_rate')))) * 100:.1f}%" if item_scheduled else "—"
            lines.append(
                f"| {_escape_markdown(item.get('course_name'))} | {_safe_int(item.get('learning_minutes'))} | {_safe_int(item.get('completed_tasks'))} | {item_scheduled} | {rate_text} |"
            )

    weak = result_data.get("weak_points")
    if isinstance(weak, list) and weak:
        lines += ["", "## 薄弱知识点", "", "| 知识点 | 课程 | 掌握度 | 真实尝试 | 置信度 |", "| --- | --- | ---: | ---: | ---: |"]
        for item in weak:
            if not isinstance(item, dict):
                continue
            score = min(1.0, max(0.0, _safe_float(item.get("score"))))
            confidence = min(1.0, max(0.0, _safe_float(item.get("confidence"))))
            lines.append(
                f"| {_escape_markdown(item.get('knowledge_point'))} | {_escape_markdown(item.get('course_name'))} | {score * 100:.1f}% | {_safe_int(item.get('attempts'))} 次真实尝试 | {confidence * 100:.1f}% |"
            )

    lines += ["", "## 总结", "", _escape_markdown(result_data.get("summary"))]
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
    records = list(
        db.scalars(
            select(LearningRecord).where(
                LearningRecord.user_id == user_id,
                LearningRecord.completed.is_(True),
                LearningRecord.course_id.in_(valid_courses),
                LearningRecord.occurred_at >= range_start,
                LearningRecord.occurred_at < range_end,
            )
        )
    )
    if not _update_progress(db, task, 35, "aggregating_tasks"):
        return {"cancelled": True}
    study_tasks = list(
        db.scalars(
            select(StudyTask)
            .join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id)
            .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
            .where(
                StudyTask.user_id == user_id,
                StudyTask.course_id.in_(valid_courses),
                StudyTask.scheduled_date >= start,
                StudyTask.scheduled_date <= end,
                StudyPlan.user_id == user_id,
                StudyPlan.course_id == StudyTask.course_id,
                StudyPlan.status == "active",
                StudyPlanVersion.status == "active",
                StudyPlan.active_version == StudyPlanVersion.version,
            )
        )
    )
    report_courses = list(db.scalars(select(Course).where(Course.id.in_(valid_courses)).order_by(Course.id)))
    if not _update_progress(db, task, 60, "aggregating_mastery"):
        return {"cancelled": True}
    weakest = list(
        db.execute(
            select(KnowledgeMastery, KnowledgePoint, Course)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
            .join(Course, Course.id == KnowledgeMastery.course_id)
            .where(
                KnowledgeMastery.user_id == user_id,
                KnowledgeMastery.course_id.in_(valid_courses),
                KnowledgePoint.course_id == KnowledgeMastery.course_id,
                KnowledgeMastery.attempts > 0,
            )
            .order_by(
                KnowledgeMastery.score.asc(),
                KnowledgeMastery.attempts.desc(),
                KnowledgeMastery.course_id.asc(),
                KnowledgePoint.id.asc(),
            )
            .limit(3)
        )
    )
    if not _update_progress(db, task, 85, "building_report"):
        return {"cancelled": True}

    by_day = {
        (start + timedelta(days=index)).isoformat(): {
            "date": (start + timedelta(days=index)).isoformat(),
            "learning_minutes": 0,
            "scheduled_tasks": 0,
            "completed_tasks": 0,
        }
        for index in range((end - start).days + 1)
    }
    course_rows = {
        course.id: {
            "course_id": course.id,
            "course_name": course.name,
            "learning_minutes": 0,
            "scheduled_tasks": 0,
            "completed_tasks": 0,
            "completion_rate": 0.0,
        }
        for course in report_courses
    }
    seconds_by_day = {key: 0 for key in by_day}
    seconds_by_course = {key: 0 for key in course_rows}
    for record in records:
        seconds = max(0, int(record.duration_seconds))
        local_day = as_utc(record.occurred_at).astimezone(user_zone).date().isoformat()
        seconds_by_day[local_day] += seconds
        seconds_by_course[record.course_id] += seconds
    minutes_by_day = allocate_rounded_minutes(seconds_by_day, lambda key: key)
    minutes_by_course = allocate_rounded_minutes(seconds_by_course, lambda key: key)
    for key, minutes in minutes_by_day.items():
        by_day[key]["learning_minutes"] = minutes
    for key, minutes in minutes_by_course.items():
        course_rows[key]["learning_minutes"] = minutes

    for item in study_tasks:
        row = by_day[item.scheduled_date.isoformat()]
        row["scheduled_tasks"] += 1
        course_rows[item.course_id]["scheduled_tasks"] += 1
        if item.status == "completed":
            row["completed_tasks"] += 1
            course_rows[item.course_id]["completed_tasks"] += 1
    total_minutes = (sum(seconds_by_day.values()) + 30) // 60
    scheduled = sum(item["scheduled_tasks"] for item in by_day.values())
    completed = sum(item["completed_tasks"] for item in by_day.values())
    course_breakdown = []
    for row in course_rows.values():
        has_real_learning = seconds_by_course[row["course_id"]] > 0
        has_active_tasks = row["scheduled_tasks"] > 0
        if has_real_learning or has_active_tasks:
            row["completion_rate"] = round(row["completed_tasks"] / row["scheduled_tasks"], 4) if row["scheduled_tasks"] else 0.0
            course_breakdown.append(row)
    course_breakdown.sort(key=lambda item: (-item["learning_minutes"], -item["scheduled_tasks"], item["course_id"]))
    weak_points = [
        {
            "knowledge_point_id": point.id,
            "knowledge_point": point.name,
            "course_id": course.id,
            "course_name": course.name,
            "score": round(min(1.0, max(0.0, mastery.score)), 4),
            "attempts": mastery.attempts,
            "confidence": round(min(1.0, max(0.0, mastery.confidence)), 4),
        }
        for mastery, point, course in weakest
    ]
    scope_label = report_courses[0].name if course_id is not None and report_courses else "全部课程"
    result = {
        "report_schema_version": 2,
        "timezone": timezone_name,
        "scope_label": scope_label,
        "range_start": start.isoformat(),
        "range_end": end.isoformat(),
        "course_id": course_id,
        "course_names": [course.name for course in report_courses],
        "total_learning_minutes": total_minutes,
        "study_days": sum(seconds > 0 for seconds in seconds_by_day.values()),
        "scheduled_tasks": scheduled,
        "completed_tasks": completed,
        "completion_rate": round(completed / scheduled, 4) if scheduled else 0.0,
        "weak_points": weak_points,
        "daily": list(by_day.values()),
        "course_breakdown": course_breakdown,
        "summary": f"{scope_label}：学习 {total_minutes} 分钟，完成 {completed}/{scheduled} 个生效计划任务。"
        + (f" 建议优先复习“{weak_points[0]['knowledge_point']}”。" if weak_points else " 建议保持稳定学习节奏。"),
    }
    if _cancel_if_requested(db, task):
        return {"cancelled": True}
    task.status, task.progress, task.current_step = "success", 100, "completed"
    task.result_data, task.error_message, task.finished_at = result, None, utcnow()
    db.commit()
    return result
