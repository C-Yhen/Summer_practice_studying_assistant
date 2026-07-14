from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import (
    AsyncTask,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
)
from backend.app.planning.engine import PlanInput, PlanningPoint, build_plan, reschedule
from backend.app.responses import ok
from backend.app.schemas import AdjustmentCreate, PlanConfirm, PlanGenerate, TaskComplete
from backend.app.services.confirmation import issue_confirmation, verify_confirmation

router = APIRouter(tags=["study-plans"])


def _owned_plan(db: DBSession, plan_id: int, user_id: int) -> StudyPlan:
    plan = db.scalar(select(StudyPlan).where(StudyPlan.id == plan_id, StudyPlan.user_id == user_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")
    return plan


def _seed_points(db: DBSession, course_id: int) -> list[KnowledgePoint]:
    points = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))
    if points:
        return points
    seeds = [
        ("核心概念", 0.9, "basic", 45, []),
        ("重点原理", 0.85, "basic", 45, []),
        ("综合应用", 0.8, "intermediate", 60, []),
    ]
    for name, importance, difficulty, minutes, dependencies in seeds:
        db.add(KnowledgePoint(course_id=course_id, name=name, importance=importance, difficulty=difficulty, estimated_minutes=minutes, prerequisite_ids=dependencies))
    db.flush()
    return list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))


def _version_payload(version: StudyPlanVersion) -> dict:
    tasks = sorted(version.tasks, key=lambda item: (item.scheduled_date, -item.priority))
    return {
        "version": version.version,
        "status": version.status,
        "reason": version.reason,
        "summary": version.summary,
        "risks": version.risks,
        "diff": version.diff,
        "tasks": [
            {
                "id": task.id,
                "scheduled_date": task.scheduled_date.isoformat(),
                "knowledge_point_id": task.knowledge_point_id,
                "title": task.title,
                "task_type": task.task_type,
                "estimated_minutes": task.estimated_minutes,
                "actual_minutes": task.actual_minutes,
                "priority": task.priority,
                "difficulty": task.difficulty,
                "status": task.status,
            }
            for task in tasks
        ],
    }


@router.post("/courses/{course_id}/study-plans/generate")
def generate_plan(
    course_id: int,
    payload: PlanGenerate,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    points = _seed_points(db, course_id)
    masteries = {
        item.knowledge_point_id: item.score
        for item in db.scalars(
            select(KnowledgeMastery).where(
                KnowledgeMastery.user_id == current_user.id,
                KnowledgeMastery.course_id == course_id,
            )
        )
    }
    input_data = PlanInput(
        start_date=payload.start_date,
        end_date=payload.end_date,
        default_daily_minutes=payload.daily_availability.get("default_minutes", 120),
        session_minutes=payload.session_minutes,
        unavailable_dates=set(payload.unavailable_dates),
        daily_overrides={date.fromisoformat(key): value for key, value in payload.daily_availability.items() if key != "default_minutes"},
    )
    skeleton = build_plan(
        input_data,
        [
            PlanningPoint(
                id=point.id,
                name=point.name,
                importance=point.importance,
                mastery=masteries.get(point.id, 0.3),
                estimated_minutes=point.estimated_minutes,
                difficulty=point.difficulty,
                prerequisite_ids=point.prerequisite_ids,
            )
            for point in points
        ],
    )
    plan = StudyPlan(user_id=current_user.id, course_id=course_id, goal=payload.goal, start_date=payload.start_date, end_date=payload.end_date)
    db.add(plan)
    db.flush()
    version = StudyPlanVersion(plan_id=plan.id, version=1, status="candidate", reason="首次生成", summary=f"共安排 {len(skeleton['tasks'])} 项任务。", risks=skeleton["risks"])
    db.add(version)
    db.flush()
    for item in skeleton["tasks"]:
        db.add(StudyTask(plan_version_id=version.id, user_id=current_user.id, course_id=course_id, knowledge_point_id=item["knowledge_point_id"], scheduled_date=item["scheduled_date"], title=item["title"], task_type=item["task_type"], estimated_minutes=item["estimated_minutes"], priority=item["priority"], difficulty=item["difficulty"]))
    task = AsyncTask(user_id=current_user.id, task_type="plan_generation", resource_type="study_plan", resource_id=str(plan.id), status="success", progress=100, current_step="completed", result_data={"plan_id": plan.id, "version": 1})
    db.add(task)
    db.commit()
    db.refresh(version)
    token = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="confirm_plan", resource_id=f"{plan.id}:1", payload={"base_version": 0})
    return ok({"async_task_id": task.public_id, "plan_id": plan.id, "candidate_version": _version_payload(version), "confirmation_token": token})


@router.get("/courses/{course_id}/study-plans/current")
def current_plan(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    plan = db.scalar(select(StudyPlan).where(StudyPlan.course_id == course_id, StudyPlan.user_id == current_user.id).order_by(StudyPlan.created_at.desc()))
    if plan is None:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")
    target_version = plan.active_version or max((item.version for item in plan.versions), default=0)
    version = next((item for item in plan.versions if item.version == target_version), None)
    if version is None:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")
    return ok({"plan_id": plan.id, "active_version": plan.active_version, "status": plan.status, **_version_payload(version)})


@router.post("/study-plans/{plan_id}/versions/{version_number}/confirm")
def confirm_plan(plan_id: int, version_number: int, payload: PlanConfirm, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    plan = _owned_plan(db, plan_id, current_user.id)
    if plan.active_version != payload.expected_base_version:
        raise HTTPException(status_code=409, detail="PLAN_VERSION_CONFLICT")
    candidate = db.scalar(select(StudyPlanVersion).where(StudyPlanVersion.plan_id == plan.id, StudyPlanVersion.version == version_number))
    if candidate is None or candidate.status not in {"candidate", "active"}:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")
    try:
        verify_confirmation(payload.confirmation_token, settings.jwt_secret, user_id=current_user.id, action="confirm_plan", resource_id=f"{plan.id}:{version_number}", payload={"base_version": payload.expected_base_version})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    previous = plan.active_version
    for item in plan.versions:
        if item.status == "active":
            item.status = "superseded"
    candidate.status = "active"
    plan.active_version = version_number
    plan.status = "active"
    db.commit()
    return ok({"plan_id": plan.id, "active_version": version_number, "previous_version": previous})


@router.post("/study-plans/{plan_id}/adjustments")
def adjust_plan(plan_id: int, payload: AdjustmentCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    plan = _owned_plan(db, plan_id, current_user.id)
    if plan.active_version != payload.base_version:
        raise HTTPException(status_code=409, detail="PLAN_VERSION_CONFLICT")
    base = db.scalar(select(StudyPlanVersion).where(StudyPlanVersion.plan_id == plan.id, StudyPlanVersion.version == payload.base_version))
    if base is None:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")
    raw_tasks = [{"id": item.id, "scheduled_date": item.scheduled_date, "knowledge_point_id": item.knowledge_point_id, "title": item.title, "task_type": item.task_type, "estimated_minutes": item.estimated_minutes, "priority": item.priority, "difficulty": item.difficulty} for item in base.tasks if item.status != "completed"]
    result = reschedule(raw_tasks, start_date=date.today(), end_date=plan.end_date, daily_minutes=int(payload.constraints.get("daily_minutes", 60)))
    next_number = max(item.version for item in plan.versions) + 1
    candidate = StudyPlanVersion(plan_id=plan.id, version=next_number, status="candidate", reason=payload.reason, summary=f"根据新约束重新安排 {len(result['tasks'])} 项任务。", risks=result["risks"], diff=result["diff"])
    db.add(candidate)
    db.flush()
    for item in result["tasks"]:
        db.add(StudyTask(plan_version_id=candidate.id, user_id=current_user.id, course_id=plan.course_id, knowledge_point_id=item["knowledge_point_id"], scheduled_date=item["scheduled_date"], title=item["title"], task_type=item["task_type"], estimated_minutes=item["estimated_minutes"], priority=item["priority"], difficulty=item["difficulty"]))
    db.commit()
    db.refresh(candidate)
    token = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="confirm_plan", resource_id=f"{plan.id}:{next_number}", payload={"base_version": payload.base_version})
    return ok({"plan_id": plan.id, "candidate_version": _version_payload(candidate), "confirmation_token": token})


@router.get("/study-plans/{plan_id}/versions")
def plan_versions(plan_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    plan = _owned_plan(db, plan_id, current_user.id)
    return ok({"items": [{"version": item.version, "status": item.status, "reason": item.reason, "created_at": item.created_at.isoformat()} for item in sorted(plan.versions, key=lambda item: item.version, reverse=True)], "total": len(plan.versions)})


@router.get("/study-tasks/today")
def today_tasks(db: DBSession, current_user: CurrentUser, course_id: int | None = None, target_date: date | None = None) -> dict:
    day = target_date or date.today()
    statement = select(StudyTask).where(StudyTask.user_id == current_user.id, StudyTask.scheduled_date == day)
    if course_id is not None:
        statement = statement.where(StudyTask.course_id == course_id)
    tasks = list(db.scalars(statement.order_by(StudyTask.priority.desc())))
    return ok({"items": [{"id": item.id, "course_id": item.course_id, "title": item.title, "task_type": item.task_type, "estimated_minutes": item.estimated_minutes, "priority": item.priority, "difficulty": item.difficulty, "status": item.status, "scheduled_date": item.scheduled_date.isoformat()} for item in tasks], "total": len(tasks)})


@router.post("/study-tasks/{task_id}/complete")
def complete_task(task_id: int, payload: TaskComplete, db: DBSession, current_user: CurrentUser) -> dict:
    task = db.scalar(select(StudyTask).where(StudyTask.id == task_id, StudyTask.user_id == current_user.id))
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    if task.status == "completed":
        return ok({"task_id": task.id, "status": task.status, "idempotent_replay": True})
    task.status = "completed"
    task.actual_minutes = payload.actual_minutes
    task.completed_at = payload.completed_at or datetime.now(timezone.utc)
    db.add(LearningRecord(user_id=current_user.id, course_id=task.course_id, task_id=task.id, knowledge_point_id=task.knowledge_point_id, duration_seconds=payload.actual_minutes * 60, completed=True))
    mastery_score = None
    if task.knowledge_point_id:
        mastery = db.scalar(select(KnowledgeMastery).where(KnowledgeMastery.user_id == current_user.id, KnowledgeMastery.knowledge_point_id == task.knowledge_point_id))
        if mastery is None:
            mastery = KnowledgeMastery(
                user_id=current_user.id,
                course_id=task.course_id,
                knowledge_point_id=task.knowledge_point_id,
                score=0.3,
                confidence=0.2,
                attempts=0,
                correct_attempts=0,
            )
            db.add(mastery)
        mastery.score = round(min(1.0, mastery.score + 0.15 * (1 - mastery.score)), 4)
        mastery.confidence = round(min(1.0, mastery.confidence + 0.1), 4)
        mastery.attempts += 1
        mastery.correct_attempts += 1
        mastery.last_studied_at = task.completed_at
        mastery_score = mastery.score
    db.commit()
    return ok({"task_id": task.id, "status": task.status, "mastery_score": mastery_score, "idempotent_replay": False})
