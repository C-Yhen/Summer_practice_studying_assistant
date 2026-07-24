from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
    UserPreference,
)
from backend.app.planning.engine import PlanInput, PlanningPoint, build_plan, reschedule
from backend.app.planning.ai_planner import generate_plan_one_shot
from backend.app.providers.llm import get_llm_provider
from backend.app.responses import ok
from backend.app.schemas import AdjustmentCreate, PlanConfirm, PlanGenerate, TaskComplete
from backend.app.services.confirmation import issue_confirmation, verify_confirmation
from backend.app.services.mastery import apply_mastery_evidence

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


def _plan_payload(plan: StudyPlan, version: StudyPlanVersion) -> dict:
    return {
        "plan_id": plan.id,
        "course_id": plan.course_id,
        "goal": plan.goal,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "active_version": plan.active_version,
        "plan_status": plan.status,
        **_version_payload(version),
    }


@router.post("/courses/{course_id}/study-plans/generate")
async def generate_plan(
    course_id: int,
    payload: PlanGenerate,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    preference = db.scalar(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    if preference is None:
        preference = UserPreference(user_id=current_user.id)
        db.add(preference)
        db.flush()
    masteries = {
        item.knowledge_point_id: item
        for item in db.scalars(
            select(KnowledgeMastery).where(
                KnowledgeMastery.user_id == current_user.id,
                KnowledgeMastery.course_id == course_id,
            )
        )
    }
    daily_override = "default_minutes" in payload.daily_availability
    session_override = "session_minutes" in payload.model_fields_set
    daily_minutes = payload.daily_availability.get("default_minutes", preference.daily_minutes)
    session_minutes = payload.session_minutes if session_override else preference.session_minutes
    if session_minutes is None or session_minutes > daily_minutes:
        raise HTTPException(status_code=422, detail="SESSION_MINUTES_EXCEEDS_DAILY_MINUTES")
    generation_context = {
        "daily_minutes": daily_minutes,
        "session_minutes": session_minutes,
        "foundation_level": preference.foundation_level,
        "learning_order": preference.learning_order,
        "preferred_difficulty": preference.preferred_difficulty,
        "preferred_resource_types": list(preference.preferred_resource_types or []),
        "needs_exam_focus": preference.needs_exam_focus,
        "needs_error_points": preference.needs_error_points,
        "needs_derivation": preference.needs_derivation,
        "overrides": {"daily_minutes": daily_override, "session_minutes": session_override},
    }

    skeleton: dict = {"tasks": [], "risks": [], "summary": ""}
    plan_mode = "rule"

    # ---- Try AI-powered one-shot generation (single LLM call) ----
    llm_provider = get_llm_provider(settings)
    is_mock = settings.llm_provider.strip().lower() == "mock"
    if not is_mock:
        try:
            ai_plan = await generate_plan_one_shot(
                db, llm_provider, course_id=course_id,
                goal=payload.goal,
                start_date=payload.start_date, end_date=payload.end_date,
                daily_minutes=daily_minutes, session_minutes=session_minutes,
                foundation_level=preference.foundation_level,
                learning_order=preference.learning_order,
                preferred_difficulty=preference.preferred_difficulty,
                needs_exam_focus=preference.needs_exam_focus,
                needs_error_points=preference.needs_error_points,
                unavailable_dates=list(payload.unavailable_dates),
            )
            if ai_plan.get("tasks"):
                skeleton = ai_plan
                plan_mode = "ai"
                generation_context["ai_one_shot"] = True
        except Exception:
            pass

    if not skeleton.get("tasks"):
        # ---- Fallback: rule-based generation ----
        points = _seed_points(db, course_id)
        input_data = PlanInput(
            start_date=payload.start_date,
            end_date=payload.end_date,
            default_daily_minutes=daily_minutes,
            session_minutes=session_minutes,
            unavailable_dates=set(payload.unavailable_dates),
            daily_overrides={date.fromisoformat(key): value for key, value in payload.daily_availability.items() if key != "default_minutes"},
            foundation_level=preference.foundation_level,
            learning_order=preference.learning_order,
            preferred_difficulty=preference.preferred_difficulty,
            needs_exam_focus=preference.needs_exam_focus,
            needs_error_points=preference.needs_error_points,
            needs_derivation=preference.needs_derivation,
        )
        skeleton = build_plan(
            input_data,
            [
                PlanningPoint(
                    id=point.id,
                    name=point.name,
                    importance=point.importance,
                    mastery=masteries[point.id].score if point.id in masteries else None,
                    has_mastery_record=point.id in masteries and masteries[point.id].attempts > 0,
                    estimated_minutes=point.estimated_minutes,
                    difficulty=point.difficulty,
                    prerequisite_ids=point.prerequisite_ids,
                )
                for point in points
            ],
        )
        plan_mode = "rule"

    # Refresh points for task mapping
    db_points = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))
    kp_name_to_id = {p.name: p.id for p in db_points}

    try:
        plan = StudyPlan(user_id=current_user.id, course_id=course_id, goal=payload.goal, start_date=payload.start_date, end_date=payload.end_date)
        db.add(plan)
        db.flush()
        summary = skeleton.get("summary") or f"共安排 {len(skeleton['tasks'])} 项任务。"
        version = StudyPlanVersion(plan_id=plan.id, version=1, status="candidate", reason=f"AI 生成" if plan_mode == "ai" else "首次生成", summary=summary, risks=skeleton.get("risks", []), diff={"generation_context": generation_context, "plan_mode": plan_mode})
        db.add(version)
        db.flush()
        for item in skeleton["tasks"]:
            kp_id = None
            if "knowledge_point_index" in item and ai_kps:
                idx = item["knowledge_point_index"]
                if 0 <= idx < len(ai_kps):
                    kp_name = ai_kps[idx]["name"]
                    kp_id = kp_name_to_id.get(kp_name)
            elif item.get("knowledge_point_id"):
                kp_id = item["knowledge_point_id"]
            db.add(StudyTask(plan_version_id=version.id, user_id=current_user.id, course_id=course_id, knowledge_point_id=kp_id, scheduled_date=date.fromisoformat(item["scheduled_date"]) if isinstance(item["scheduled_date"], str) else item["scheduled_date"], title=item["title"], task_type=item.get("task_type", "focused_study"), estimated_minutes=item["estimated_minutes"], priority=item.get("priority", 0.5), difficulty=item.get("difficulty", "basic")))
        task = AsyncTask(user_id=current_user.id, task_type="plan_generation", resource_type="study_plan", resource_id=str(plan.id), status="success", progress=100, current_step="completed", result_data={"plan_id": plan.id, "version": 1, "plan_mode": plan_mode})
        db.add(task)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="PLAN_GENERATION_FAILED") from None
    db.refresh(version)
    token = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="confirm_plan", resource_id=f"{plan.id}:1", payload={"base_version": 0})
    return ok({"async_task_id": task.public_id, "plan_id": plan.id, "course_id": course_id, "goal": plan.goal, "start_date": plan.start_date.isoformat(), "end_date": plan.end_date.isoformat(), "expected_base_version": 0, "candidate_version": _version_payload(version), "confirmation_token": token})


@router.get("/courses/{course_id}/study-plans/current")
def current_plan(course_id: int, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    _owned_course(db, course_id, current_user.id)
    plan = db.scalar(select(StudyPlan).where(StudyPlan.course_id == course_id, StudyPlan.user_id == current_user.id).order_by(StudyPlan.created_at.desc()))
    if plan is None:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")
    candidates = [item for item in plan.versions if item.status == "candidate"]
    if candidates:
        version = max(candidates, key=lambda item: item.version)
    else:
        version = next((item for item in plan.versions if item.version == plan.active_version), None)
    if version is None:
        raise HTTPException(status_code=404, detail="VERSION_NOT_FOUND")
    response = _plan_payload(plan, version)
    if version.status == "candidate":
        response["expected_base_version"] = plan.active_version
        response["confirmation_token"] = issue_confirmation(
            settings.jwt_secret,
            user_id=current_user.id,
            action="confirm_plan",
            resource_id=f"{plan.id}:{version.version}",
            payload={"base_version": plan.active_version},
        )
    else:
        response["expected_base_version"] = None
        response["confirmation_token"] = None
    return ok(response)


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
    other_plans = list(
        db.scalars(
            select(StudyPlan).where(
                StudyPlan.user_id == current_user.id,
                StudyPlan.course_id == plan.course_id,
                StudyPlan.id != plan.id,
                StudyPlan.status == "active",
            )
        )
    )
    for other_plan in other_plans:
        other_plan.status = "superseded"
        for item in other_plan.versions:
            if item.status == "active":
                item.status = "superseded"
    candidate.status = "active"
    plan.active_version = version_number
    plan.status = "active"
    db.commit()
    return ok({"plan_id": plan.id, "active_version": version_number, "previous_version": previous, "status": plan.status, "version_status": candidate.status})


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
    if course_id is not None:
        _owned_course(db, course_id, current_user.id)
    statement = (
        select(StudyTask)
        .join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .where(
            StudyTask.user_id == current_user.id,
            StudyTask.scheduled_date == day,
            StudyPlan.user_id == current_user.id,
            StudyPlan.status == "active",
            StudyPlanVersion.status == "active",
            StudyPlan.active_version == StudyPlanVersion.version,
        )
    )
    if course_id is not None:
        statement = statement.where(StudyTask.course_id == course_id)
    tasks = list(db.scalars(statement.order_by(StudyTask.priority.desc())))
    return ok({"items": [{"id": item.id, "course_id": item.course_id, "knowledge_point_id": item.knowledge_point_id, "title": item.title, "task_type": item.task_type, "estimated_minutes": item.estimated_minutes, "actual_minutes": item.actual_minutes, "priority": item.priority, "difficulty": item.difficulty, "status": item.status, "scheduled_date": item.scheduled_date.isoformat()} for item in tasks], "total": len(tasks)})


@router.post("/study-tasks/{task_id}/complete")
def complete_task(task_id: int, payload: TaskComplete, db: DBSession, current_user: CurrentUser) -> dict:
    task = db.scalar(
        select(StudyTask)
        .where(StudyTask.id == task_id, StudyTask.user_id == current_user.id)
        .with_for_update()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    active = db.scalar(
        select(StudyTask.id)
        .join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id)
        .join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id)
        .where(
            StudyTask.id == task.id,
            StudyPlan.user_id == current_user.id,
            StudyPlan.status == "active",
            StudyPlanVersion.status == "active",
            StudyPlan.active_version == StudyPlanVersion.version,
        )
    )
    if active is None:
        raise HTTPException(status_code=409, detail="TASK_NOT_ACTIVE")
    if task.status == "completed":
        mastery_score = db.scalar(
            select(KnowledgeMastery.score).where(
                KnowledgeMastery.user_id == current_user.id,
                KnowledgeMastery.knowledge_point_id == task.knowledge_point_id,
            )
        ) if task.knowledge_point_id else None
        return ok({"task_id": task.id, "status": task.status, "actual_minutes": task.actual_minutes, "mastery_score": mastery_score, "idempotent_replay": True})
    task.status = "completed"
    task.actual_minutes = payload.actual_minutes
    task.completed_at = payload.completed_at or datetime.now(timezone.utc)
    db.add(LearningRecord(user_id=current_user.id, course_id=task.course_id, task_id=task.id, knowledge_point_id=task.knowledge_point_id, duration_seconds=payload.actual_minutes * 60, completed=True))
    mastery_score = None
    if task.knowledge_point_id:
        mastery = apply_mastery_evidence(
            db,
            user_id=current_user.id,
            course_id=task.course_id,
            knowledge_point_id=task.knowledge_point_id,
            correct=True,
            score_strength=0.15,
            confidence_strength=0.1,
            occurred_at=task.completed_at,
        )
        mastery_score = mastery.score
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        persisted = db.scalar(
            select(StudyTask).where(
                StudyTask.id == task_id,
                StudyTask.user_id == current_user.id,
            )
        )
        if persisted is not None and persisted.status == "completed":
            persisted_mastery_score = db.scalar(
                select(KnowledgeMastery.score).where(
                    KnowledgeMastery.user_id == current_user.id,
                    KnowledgeMastery.knowledge_point_id == persisted.knowledge_point_id,
                )
            ) if persisted.knowledge_point_id else None
            return ok({"task_id": persisted.id, "status": persisted.status, "actual_minutes": persisted.actual_minutes, "mastery_score": persisted_mastery_score, "idempotent_replay": True})
        raise HTTPException(status_code=500, detail="TASK_COMPLETION_FAILED") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="TASK_COMPLETION_FAILED") from None
    return ok({"task_id": task.id, "status": task.status, "actual_minutes": task.actual_minutes, "mastery_score": mastery_score, "idempotent_replay": False})
