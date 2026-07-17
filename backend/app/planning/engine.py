from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal


@dataclass(frozen=True)
class PlanningPoint:
    id: int
    name: str
    importance: float
    mastery: float | None
    has_mastery_record: bool
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
    foundation_level: Literal["basic", "intermediate", "advanced"] = "basic"
    learning_order: Literal["explain_first", "weakness_first"] = "explain_first"
    preferred_difficulty: Literal["basic", "adaptive", "advanced"] = "adaptive"
    needs_exam_focus: bool = True
    needs_error_points: bool = True
    needs_derivation: bool = False


def _rank(point: PlanningPoint, plan: PlanInput) -> tuple[float, float, int]:
    """Sort only currently dependency-free points; unknown mastery is never weak evidence."""
    weakness = 1 - point.mastery if point.has_mastery_record and point.mastery is not None else -1.0
    if plan.learning_order == "weakness_first" and plan.needs_error_points:
        return (-weakness, -point.importance, point.id)
    return (-point.importance, -weakness if plan.needs_error_points else 0.0, point.id)


def _topological(points: list[PlanningPoint], plan: PlanInput) -> list[PlanningPoint]:
    by_id = {point.id: point for point in points}
    indegree = {point.id: 0 for point in points}
    outgoing: dict[int, list[int]] = {point.id: [] for point in points}
    for point in points:
        for dependency in point.prerequisite_ids:
            if dependency in by_id:
                indegree[point.id] += 1
                outgoing[dependency].append(point.id)
    available = sorted((point for point in points if indegree[point.id] == 0), key=lambda point: _rank(point, plan))
    ordered: list[PlanningPoint] = []
    while available:
        current = available.pop(0)
        ordered.append(current)
        for next_id in outgoing[current.id]:
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                available.append(by_id[next_id])
                available.sort(key=lambda point: _rank(point, plan))
    if len(ordered) != len(points):
        seen = {item.id for item in ordered}
        ordered.extend(sorted((point for point in points if point.id not in seen), key=lambda point: _rank(point, plan)))
    return ordered


def _priority(point: PlanningPoint, plan: PlanInput, urgency: float) -> float:
    weakness = 1 - point.mastery if plan.needs_error_points and point.has_mastery_record and point.mastery is not None else 0.0
    forgetting = min(1.0, 0.3 + point.days_since_review / 30)
    dependency = 1.1 if point.prerequisite_ids else 1.0
    return round(min(1.0, (point.importance + 0.35 * weakness) * forgetting * dependency * urgency), 4)


def _difficulty(point: PlanningPoint, preference: str) -> str:
    if preference == "basic":
        return "basic"
    if preference == "advanced":
        return {"basic": "intermediate", "intermediate": "advanced"}.get(point.difficulty, point.difficulty)
    return point.difficulty


def _initial_task(plan: PlanInput, point: PlanningPoint) -> tuple[str, str]:
    if plan.needs_derivation:
        return "concept_derivation", f"概念推导：{point.name}"
    if plan.foundation_level == "basic":
        return "basic_explanation", f"基础讲解：{point.name}"
    if plan.foundation_level == "advanced":
        return "integrated_application", f"综合应用：{point.name}"
    return "focused_study", f"重点学习：{point.name}"


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
    ordered = _topological(points, plan)
    urgency = min(1.5, 1 + max(0, 14 - len(dates)) / 28)
    risks: list[str] = []

    def allocate(point: PlanningPoint, task_type: str, title: str, minutes: int, earliest: int, difficulty: str) -> int | None:
        for index in range(max(0, earliest), len(dates)):
            if capacity[dates[index]] >= minutes:
                capacity[dates[index]] -= minutes
                tasks.append({
                    "scheduled_date": dates[index], "knowledge_point_id": point.id,
                    "knowledge_point": point.name, "title": title, "task_type": task_type,
                    "estimated_minutes": minutes, "priority": _priority(point, plan, urgency),
                    "difficulty": difficulty,
                })
                return index
        return None

    for point in ordered:
        if point.has_mastery_record and point.mastery is not None and point.mastery >= 0.9:
            continue
        minutes = min(max(15, point.estimated_minutes), plan.session_minutes)
        initial_type, initial_title = _initial_task(plan, point)
        learned_index = allocate(point, initial_type, initial_title, minutes, 0, _difficulty(point, plan.preferred_difficulty))
        if learned_index is None:
            risks.append(f"时间不足，未能安排知识点“{point.name}”。")
            continue
        review_minutes = min(30, max(15, minutes // 2), plan.session_minutes)
        allocate(point, "spaced_review", f"间隔复习：{point.name}", review_minutes, learned_index + 2, _difficulty(point, plan.preferred_difficulty))

    if tasks and plan.needs_exam_focus:
        final_day = dates[-1]
        test_minutes = min(60, plan.default_daily_minutes)
        if capacity[final_day] >= test_minutes:
            capacity[final_day] -= test_minutes
            tasks.append({
                "scheduled_date": final_day, "knowledge_point_id": None, "knowledge_point": "全课程",
                "title": "阶段测试与综合复习", "task_type": "exam_review", "estimated_minutes": test_minutes,
                "priority": 1.0, "difficulty": "mixed",
            })
        else:
            risks.append("最后一天容量不足，阶段测试需要手动安排。")
    tasks.sort(key=lambda item: (item["scheduled_date"], -item["priority"], item["knowledge_point_id"] or 0))
    return {"tasks": tasks, "risks": risks, "total_minutes": sum(item["estimated_minutes"] for item in tasks), "remaining_capacity": sum(capacity.values())}


def reschedule(tasks: list[dict[str, Any]], *, start_date: date, end_date: date, daily_minutes: int) -> dict[str, Any]:
    days: list[date] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    capacity = {day: daily_minutes for day in days}
    rescheduled: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for task in sorted(tasks, key=lambda item: (-float(item.get("priority", 0)), item["scheduled_date"])):
        for day in days:
            if capacity[day] >= task["estimated_minutes"]:
                capacity[day] -= task["estimated_minutes"]
                updated = {**task, "scheduled_date": day}
                rescheduled.append(updated)
                if day != task["scheduled_date"]:
                    changes.append({"task_id": task.get("id"), "from": task["scheduled_date"], "to": day})
                break
        else:
            removed.append(task)
    return {"tasks": rescheduled, "diff": {"rescheduled": changes, "removed": removed, "added": []}, "risks": ["部分低优先级任务因容量不足被移出候选计划。"] if removed else []}
