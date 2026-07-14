from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class PlanningPoint:
    id: int
    name: str
    importance: float
    mastery: float
    estimated_minutes: int
    difficulty: str = "basic"
    prerequisite_ids: list[int] = field(default_factory=list)
    days_since_review: int = 30


@dataclass(frozen=True)
class PlanInput:
    start_date: date
    end_date: date
    default_daily_minutes: int
    session_minutes: int
    unavailable_dates: set[date] = field(default_factory=set)
    daily_overrides: dict[date, int] = field(default_factory=dict)


def _topological(points: list[PlanningPoint]) -> list[PlanningPoint]:
    by_id = {point.id: point for point in points}
    indegree = {point.id: 0 for point in points}
    outgoing: dict[int, list[int]] = {point.id: [] for point in points}
    for point in points:
        for dependency in point.prerequisite_ids:
            if dependency in by_id:
                indegree[point.id] += 1
                outgoing[dependency].append(point.id)
    available = sorted(
        (point for point in points if indegree[point.id] == 0),
        key=lambda point: (-point.importance * (1 - point.mastery), point.id),
    )
    ordered: list[PlanningPoint] = []
    while available:
        current = available.pop(0)
        ordered.append(current)
        for next_id in outgoing[current.id]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                available.append(by_id[next_id])
                available.sort(key=lambda point: (-point.importance * (1 - point.mastery), point.id))
    if len(ordered) != len(points):
        # A bad dependency graph must not deadlock plan generation.
        remaining = [point for point in points if point.id not in {item.id for item in ordered}]
        ordered.extend(sorted(remaining, key=lambda point: point.id))
    return ordered


def _priority(point: PlanningPoint, urgency: float) -> float:
    weakness = max(0.05, 1 - point.mastery)
    forgetting = min(1.0, 0.3 + point.days_since_review / 30)
    dependency = 1.1 if point.prerequisite_ids else 1.0
    return round(min(1.0, point.importance * weakness * forgetting * dependency * urgency), 4)


def build_plan(plan: PlanInput, points: list[PlanningPoint]) -> dict[str, Any]:
    dates: list[date] = []
    cursor = plan.start_date
    while cursor <= plan.end_date:
        if cursor not in plan.unavailable_dates and plan.daily_overrides.get(cursor, plan.default_daily_minutes) > 0:
            dates.append(cursor)
        cursor += timedelta(days=1)
    if not dates:
        return {"tasks": [], "risks": ["可学习日期为空，无法安排任务。"], "total_minutes": 0}

    capacity = {day: plan.daily_overrides.get(day, plan.default_daily_minutes) for day in dates}
    tasks: list[dict[str, Any]] = []
    ordered = _topological(points)
    urgency = min(1.5, 1 + max(0, 14 - len(dates)) / 28)
    day_index = 0
    risks: list[str] = []

    def allocate(point: PlanningPoint, task_type: str, minutes: int, earliest: int) -> int | None:
        nonlocal day_index
        for index in range(max(day_index, earliest), len(dates)):
            if capacity[dates[index]] >= minutes:
                capacity[dates[index]] -= minutes
                tasks.append(
                    {
                        "scheduled_date": dates[index],
                        "knowledge_point_id": point.id,
                        "knowledge_point": point.name,
                        "title": f"{task_type}：{point.name}",
                        "task_type": task_type,
                        "estimated_minutes": minutes,
                        "priority": _priority(point, urgency),
                        "difficulty": point.difficulty,
                    }
                )
                day_index = index
                return index
        return None

    for point in ordered:
        if point.mastery >= 0.9:
            continue
        minutes = min(max(15, point.estimated_minutes), plan.session_minutes)
        learned_index = allocate(point, "学习新知识", minutes, 0)
        if learned_index is None:
            risks.append(f"时间不足，未能安排知识点“{point.name}”。")
            continue
        review_minutes = min(30, max(15, minutes // 2))
        allocate(point, "间隔复习", review_minutes, learned_index + 2)

    if tasks:
        final_day = dates[-1]
        test_minutes = min(60, plan.default_daily_minutes)
        if capacity[final_day] >= test_minutes:
            capacity[final_day] -= test_minutes
            tasks.append(
                {
                    "scheduled_date": final_day,
                    "knowledge_point_id": None,
                    "knowledge_point": "全课程",
                    "title": "阶段测试与综合复习",
                    "task_type": "阶段测试",
                    "estimated_minutes": test_minutes,
                    "priority": 1.0,
                    "difficulty": "mixed",
                }
            )
        else:
            risks.append("最后一天容量不足，阶段测试需要手动安排。")
    tasks.sort(key=lambda item: (item["scheduled_date"], -item["priority"]))
    return {
        "tasks": tasks,
        "risks": risks,
        "total_minutes": sum(item["estimated_minutes"] for item in tasks),
        "remaining_capacity": sum(capacity.values()),
    }


def reschedule(
    tasks: list[dict[str, Any]],
    *,
    start_date: date,
    end_date: date,
    daily_minutes: int,
) -> dict[str, Any]:
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    capacity = {day: daily_minutes for day in days}
    rescheduled: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for task in sorted(tasks, key=lambda item: (-float(item.get("priority", 0)), item["scheduled_date"])):
        placed = False
        for day in days:
            if capacity[day] >= task["estimated_minutes"]:
                capacity[day] -= task["estimated_minutes"]
                updated = {**task, "scheduled_date": day}
                rescheduled.append(updated)
                if day != task["scheduled_date"]:
                    changes.append({"task_id": task.get("id"), "from": task["scheduled_date"], "to": day})
                placed = True
                break
        if not placed:
            removed.append(task)
    return {"tasks": rescheduled, "diff": {"rescheduled": changes, "removed": removed, "added": []}, "risks": ["部分低优先级任务因容量不足被移出候选计划。"] if removed else []}
