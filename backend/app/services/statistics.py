from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Course, LearningRecord, PracticeAttempt, StudyPlan, StudyPlanVersion, StudyTask
from backend.app.services.timezones import as_utc, local_date_range_utc, resolve_user_timezone


def _scoped_courses(db: Session, user_id: int, course_id: int | None) -> list[Course]:
    query = select(Course).where(Course.owner_id == user_id, Course.archived.is_(False))
    if course_id is not None:
        query = query.where(Course.id == course_id)
    return list(db.scalars(query.order_by(Course.id)))


def _active_tasks(db: Session, user_id: int, course_ids: list[int], start: date, end: date) -> list[StudyTask]:
    if not course_ids:
        return []
    return list(db.scalars(
        select(StudyTask)
        .join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .where(
            StudyTask.user_id == user_id,
            StudyTask.course_id.in_(course_ids),
            StudyTask.scheduled_date >= start,
            StudyTask.scheduled_date <= end,
            StudyPlan.user_id == user_id,
            StudyPlan.status == "active",
            StudyPlanVersion.status == "active",
            StudyPlan.active_version == StudyPlanVersion.version,
        )
    ))


def _records(db: Session, user_id: int, course_ids: list[int], start_utc: datetime, end_utc: datetime) -> list[LearningRecord]:
    if not course_ids:
        return []
    return list(db.scalars(select(LearningRecord).where(
        LearningRecord.user_id == user_id,
        LearningRecord.course_id.in_(course_ids),
        LearningRecord.completed.is_(True),
        LearningRecord.occurred_at >= start_utc,
        LearningRecord.occurred_at < end_utc,
    )))


def _attempts(db: Session, user_id: int, course_ids: list[int], start_utc: datetime, end_utc: datetime) -> list[PracticeAttempt]:
    if not course_ids:
        return []
    return list(db.scalars(select(PracticeAttempt).where(
        PracticeAttempt.user_id == user_id,
        PracticeAttempt.course_id.in_(course_ids),
        PracticeAttempt.submitted_at >= start_utc,
        PracticeAttempt.submitted_at < end_utc,
    )))


def _rate(completed: int, total: int) -> float | None:
    return round(completed / total, 4) if total else None


def _efficient_period(attempts: list[PracticeAttempt], user_zone) -> dict | None:
    buckets: dict[int, list[PracticeAttempt]] = defaultdict(list)
    for item in attempts:
        buckets[as_utc(item.submitted_at).astimezone(user_zone).hour // 2 * 2].append(item)
    eligible = []
    for start_hour, items in buckets.items():
        if len(items) < 3:
            continue
        correct = sum(item.is_correct for item in items)
        eligible.append((correct / len(items), len(items), start_hour, correct))
    if not eligible:
        return None
    accuracy, count, start_hour, correct = sorted(eligible, key=lambda item: (-item[0], -item[1], item[2]))[0]
    end_hour = start_hour + 2
    return {
        "label": f"{start_hour:02d}:00–{end_hour:02d}:00",
        "start_hour": start_hour,
        "end_hour": end_hour,
        "attempts": count,
        "correct": correct,
        "accuracy": round(accuracy, 4),
    }


def _heatmap(records: list[LearningRecord], end: date, user_zone) -> tuple[list[dict], int]:
    seconds_by_day: dict[date, int] = defaultdict(int)
    for record in records:
        seconds_by_day[as_utc(record.occurred_at).astimezone(user_zone).date()] += record.duration_seconds
    start = end - timedelta(days=48)
    heatmap = []
    cursor = start
    while cursor <= end:
        heatmap.append({"date": cursor.isoformat(), "learning_seconds": seconds_by_day[cursor]})
        cursor += timedelta(days=1)
    longest = streak = 0
    for item in heatmap:
        if item["learning_seconds"] > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    return heatmap, longest


def _insights(summary: dict, distribution: list[dict]) -> list[dict]:
    insights: list[dict] = []
    if summary["total_learning_seconds"]:
        minutes = round(summary["total_learning_seconds"] / 60)
        detail = f"本周期共学习 {minutes} 分钟，覆盖 {summary['learning_days']} 个学习日。"
        if summary["learning_seconds_change"] is not None:
            delta = round(abs(summary["learning_seconds_change"]) / 60)
            detail += f"较上一周期{'增加' if summary['learning_seconds_change'] >= 0 else '减少'} {delta} 分钟。"
        insights.append({"code": "learning_investment", "title": "学习投入", "detail": detail, "evidence": {"minutes": minutes, "learning_days": summary["learning_days"]}})
    if summary["task_total"]:
        insights.append({"code": "task_execution", "title": "任务执行", "detail": f"本周期完成 {summary['task_completed']}/{summary['task_total']} 项计划任务，完成率为 {round(summary['task_completion_rate'] * 100)}%。", "evidence": {"completed": summary["task_completed"], "total": summary["task_total"], "rate": summary["task_completion_rate"]}})
    if summary["practice_attempts"]:
        insights.append({"code": "practice_performance", "title": "练习表现", "detail": f"共完成 {summary['practice_attempts']} 次练习，正确 {summary['practice_correct']} 次，正确率为 {round(summary['practice_accuracy'] * 100)}%。", "evidence": {"attempts": summary["practice_attempts"], "correct": summary["practice_correct"], "accuracy": summary["practice_accuracy"]}})
    if len(insights) < 3 and distribution:
        top = distribution[0]
        insights.append({"code": "course_focus", "title": "课程投入", "detail": f"投入最多的课程是“{top['course_name']}”，占本周期学习时长的 {round(top['percentage'] * 100)}%。", "evidence": {"course_id": top["course_id"], "percentage": top["percentage"]}})
    return insights[:3]


def build_statistics_overview(db: Session, *, user_id: int, timezone_name: str | None, days: int, end: date, course_id: int | None) -> dict:
    user_zone, resolved_timezone = resolve_user_timezone(timezone_name)
    start = end - timedelta(days=days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    courses = _scoped_courses(db, user_id, course_id)
    course_ids = [course.id for course in courses]
    if course_id is not None and not courses:
        return {"not_found": True}
    course_names = {course.id: course.name for course in courses}
    start_utc, end_utc = local_date_range_utc(start, end, user_zone)
    previous_start_utc, previous_end_utc = local_date_range_utc(previous_start, previous_end, user_zone)
    records = _records(db, user_id, course_ids, start_utc, end_utc)
    previous_records = _records(db, user_id, course_ids, previous_start_utc, previous_end_utc)
    attempts = _attempts(db, user_id, course_ids, start_utc, end_utc)
    previous_attempts = _attempts(db, user_id, course_ids, previous_start_utc, previous_end_utc)
    tasks = _active_tasks(db, user_id, course_ids, start, end)
    previous_tasks = _active_tasks(db, user_id, course_ids, previous_start, previous_end)

    learning_by_day: dict[date, int] = defaultdict(int)
    learning_by_course: dict[int, int] = defaultdict(int)
    for record in records:
        learning_by_day[as_utc(record.occurred_at).astimezone(user_zone).date()] += record.duration_seconds
        learning_by_course[record.course_id] += record.duration_seconds
    attempts_by_day: dict[date, list[PracticeAttempt]] = defaultdict(list)
    for item in attempts:
        attempts_by_day[as_utc(item.submitted_at).astimezone(user_zone).date()].append(item)
    tasks_by_day: dict[date, list[StudyTask]] = defaultdict(list)
    for task in tasks:
        tasks_by_day[task.scheduled_date].append(task)

    task_total = len(tasks)
    task_completed = sum(task.status == "completed" for task in tasks)
    previous_task_total = len(previous_tasks)
    previous_task_rate = _rate(sum(task.status == "completed" for task in previous_tasks), previous_task_total)
    practice_correct = sum(item.is_correct for item in attempts)
    previous_practice_correct = sum(item.is_correct for item in previous_attempts)
    practice_accuracy = _rate(practice_correct, len(attempts))
    previous_practice_accuracy = _rate(previous_practice_correct, len(previous_attempts))
    total_seconds = sum(record.duration_seconds for record in records)
    previous_seconds = sum(record.duration_seconds for record in previous_records)
    heat_records = _records(db, user_id, course_ids, *local_date_range_utc(end - timedelta(days=48), end, user_zone))
    heatmap, longest_streak = _heatmap(heat_records, end, user_zone)
    summary = {
        "total_learning_seconds": total_seconds,
        "previous_total_learning_seconds": previous_seconds if previous_records else None,
        "learning_seconds_change": total_seconds - previous_seconds if previous_records else None,
        "learning_days": sum(value > 0 for value in learning_by_day.values()),
        "longest_streak_days": longest_streak,
        "task_total": task_total,
        "task_completed": task_completed,
        "task_completion_rate": _rate(task_completed, task_total),
        "previous_task_completion_rate": previous_task_rate,
        "task_completion_rate_change": round(_rate(task_completed, task_total) - previous_task_rate, 4) if _rate(task_completed, task_total) is not None and previous_task_rate is not None else None,
        "practice_attempts": len(attempts),
        "practice_correct": practice_correct,
        "practice_wrong": len(attempts) - practice_correct,
        "practice_accuracy": practice_accuracy,
        "previous_practice_accuracy": previous_practice_accuracy,
        "practice_accuracy_change": round(practice_accuracy - previous_practice_accuracy, 4) if practice_accuracy is not None and previous_practice_accuracy is not None else None,
        "efficient_period": _efficient_period(attempts, user_zone),
    }
    daily = []
    cursor = start
    while cursor <= end:
        daily_attempts = attempts_by_day[cursor]
        daily_tasks = tasks_by_day[cursor]
        daily_correct = sum(item.is_correct for item in daily_attempts)
        daily.append({
            "date": cursor.isoformat(),
            "actual_learning_seconds": learning_by_day[cursor],
            "planned_minutes": sum(item.estimated_minutes for item in daily_tasks),
            "task_total": len(daily_tasks),
            "task_completed": sum(item.status == "completed" for item in daily_tasks),
            "practice_attempts": len(daily_attempts),
            "practice_correct": daily_correct,
            "practice_accuracy": _rate(daily_correct, len(daily_attempts)),
        })
        cursor += timedelta(days=1)
    distribution = [
        {"course_id": item_course_id, "course_name": course_names[item_course_id], "learning_seconds": seconds, "percentage": round(seconds / total_seconds, 4)}
        for item_course_id, seconds in learning_by_course.items() if seconds > 0
    ]
    distribution.sort(key=lambda item: (-item["learning_seconds"], item["course_id"]))
    return {
        "range": {"start_date": start.isoformat(), "end_date": end.isoformat(), "days": days, "timezone": resolved_timezone},
        "scope": {"course_id": course_id, "course_name": courses[0].name if course_id is not None else None},
        "summary": summary,
        "daily": daily,
        "course_distribution": distribution,
        "heatmap": heatmap,
        "insights": _insights(summary, distribution),
    }
