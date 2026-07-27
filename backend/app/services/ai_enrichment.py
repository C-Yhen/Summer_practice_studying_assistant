"""Background-only AI enhancement jobs for interactive learning flows.

The API routes create their deterministic rule result first.  These helpers use
the existing ``AsyncTask``/Celery pipeline only to enrich already usable data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import AsyncTask, Course, StudyPlanVersion, utcnow
from backend.app.providers.llm import OpenAICompatibleProvider, get_llm_provider, llm_runtime_status
from backend.app.services.ai_recommend import generate_recommendations
from backend.app.services.async_tasks import dispatch_async_task, mark_task_cancelled
from backend.app.services.practice_gen import generate_questions_batch, persist_ai_questions
from backend.app.planning.ai_planner import generate_plan_one_shot

logger = logging.getLogger(__name__)

AI_ENRICHMENT_TASK_TYPES = {
    "ai_recommendation",
    "plan_ai_enhancement",
    "practice_ai_enhancement",
}


def stable_input_hash(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


async def queue_ai_enhancement(
    db: Session,
    settings: Any,
    *,
    task_type: str,
    user_id: int,
    course_id: int,
    input_data: dict[str, Any],
    dedupe_data: dict[str, Any] | None = None,
) -> AsyncTask | None:
    """Create/reuse one persistent AI task without delaying an API response."""
    if settings.llm_provider.strip().lower() == "mock":
        return None
    # Some jobs (notably candidate plans) need a transient resource id to
    # write their enhancement, but that id must not defeat deduplication of an
    # otherwise identical user request.
    hash_data = dedupe_data if dedupe_data is not None else input_data
    key = stable_input_hash(task_type, {"user_id": user_id, "course_id": course_id, **hash_data})
    task = db.scalar(select(AsyncTask).where(AsyncTask.idempotency_key == key))
    created = task is None
    if task is None:
        task = AsyncTask(
            user_id=user_id,
            task_type=task_type,
            resource_type="course",
            resource_id=str(course_id),
            input_data=input_data,
            idempotency_key=key,
            current_step="queued_for_ai_enhancement",
        )
        db.add(task)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            task = db.scalar(select(AsyncTask).where(AsyncTask.idempotency_key == key))
            if task is None:
                raise
            created = False
    if created:
        await dispatch_async_task(db, task, settings)
    db.refresh(task)
    return task


def ai_enhancement_payload(task: AsyncTask | None) -> dict[str, Any] | None:
    if task is None:
        return None
    result = task.result_data if isinstance(task.result_data, dict) else {}
    return {
        "task_id": task.public_id,
        "status": task.status,
        "current_step": task.current_step,
        "summary": result.get("summary") if task.status == "success" else None,
        "suggestions": result.get("suggestions", []) if task.status == "success" else [],
        "failure_type": result.get("failure_type") if task.status == "failed" else None,
    }


def _start(db: Session, task: AsyncTask) -> bool:
    if task.status in {"success", "failed", "cancelled"}:
        return False
    if task.cancel_requested:
        mark_task_cancelled(db, task, "cancelled_before_start")
        return False
    task.status = "processing"
    task.progress = 15
    task.current_step = "running_ai_enhancement"
    task.started_at = utcnow()
    db.commit()
    return True


def _safe_failure_type(exc: Exception) -> str:
    name = type(exc).__name__.upper()
    if "TIMEOUT" in name:
        return "AI_TIMEOUT"
    if "HTTP" in name or "CONNECT" in name:
        return "AI_HTTP_ERROR"
    if "VALID" in name or "JSON" in name or "VALUE" in name:
        return "AI_RESPONSE_INVALID"
    return "AI_ENHANCEMENT_FAILED"


async def process_ai_enhancement(db: Session, task: AsyncTask, settings: Any) -> dict[str, Any]:
    """Run one enhancement in a worker. Rule data is never rolled back here."""
    if task.task_type not in AI_ENRICHMENT_TASK_TYPES:
        raise ValueError("unsupported AI enhancement task")
    if not _start(db, task):
        return task.result_data or {"cancelled": task.status == "cancelled"}

    started = perf_counter()
    provider = None
    try:
        provider = get_llm_provider(settings)
        course_id = int(task.resource_id or "")
        course = db.scalar(select(Course).where(Course.id == course_id, Course.owner_id == task.user_id, Course.archived.is_(False)))
        if course is None:
            raise ValueError("AI_RESOURCE_NOT_FOUND")

        if task.task_type == "ai_recommendation":
            data = await generate_recommendations(
                db, provider, user_id=task.user_id, course_id=course.id,
                course_name=course.name, exam_date=course.exam_date,
                timeout_seconds=settings.ai_recommend_timeout_seconds,
            )
            suggestions = data.get("recommendations", []) if isinstance(data, dict) else []
            result = {
                "summary": str(data.get("summary", "")).strip()[:1200] if isinstance(data, dict) else "",
                "suggestions": suggestions[:3] if isinstance(suggestions, list) else [],
            }
        elif task.task_type == "plan_ai_enhancement":
            plan_id = int(task.input_data.get("plan_id", 0))
            version_number = int(task.input_data.get("version", 0))
            version = db.scalar(select(StudyPlanVersion).where(StudyPlanVersion.plan_id == plan_id, StudyPlanVersion.version == version_number))
            if version is None:
                raise ValueError("AI_PLAN_VERSION_NOT_FOUND")
            data = await generate_plan_one_shot(
                db, provider, course_id=course.id, goal=str(task.input_data["goal"]),
                start_date=datetime.fromisoformat(str(task.input_data["start_date"])).date(),
                end_date=datetime.fromisoformat(str(task.input_data["end_date"])).date(),
                daily_minutes=int(task.input_data["daily_minutes"]),
                session_minutes=int(task.input_data["session_minutes"]),
                foundation_level=str(task.input_data.get("foundation_level", "basic")),
                learning_order=str(task.input_data.get("learning_order", "explain_first")),
                preferred_difficulty=str(task.input_data.get("preferred_difficulty", "adaptive")),
                needs_exam_focus=bool(task.input_data.get("needs_exam_focus", True)),
                needs_error_points=bool(task.input_data.get("needs_error_points", True)),
                unavailable_dates=[],
                timeout_seconds=settings.ai_plan_timeout_seconds,
            )
            summary = str(data.get("summary", "")).strip()[:1200] if isinstance(data, dict) else ""
            risks = data.get("risks", []) if isinstance(data, dict) else []
            # Candidate task scheduling remains rule-authoritative. Only enrich
            # explanatory fields, and only after a valid AI result is available.
            if summary:
                version.summary = summary
            if isinstance(risks, list):
                version.risks = [str(item)[:300] for item in risks[:8] if str(item).strip()]
            result = {"summary": summary, "suggestions": [], "risks": version.risks}
        else:
            point_ids = [int(item) for item in task.input_data.get("knowledge_point_ids", [])]
            generated = await generate_questions_batch(
                db, provider, course_id=course.id, knowledge_point_ids=point_ids,
                timeout_seconds=settings.ai_practice_timeout_seconds,
            )
            persisted = persist_ai_questions(db, course_id=course.id, questions=generated)
            result = {"summary": "", "suggestions": [], **persisted}

        if task.cancel_requested:
            mark_task_cancelled(db, task, "cancelled_before_commit")
            return {"cancelled": True}
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        task.status = "success"
        task.progress = 100
        task.current_step = "completed"
        task.result_data = {**result, "duration_ms": elapsed_ms, "runtime": llm_runtime_status(settings)}
        task.finished_at = utcnow()
        db.commit()
        logger.info("ai_enhancement_completed task_type=%s task_id=%s duration_ms=%s", task.task_type, task.public_id, elapsed_ms)
        return task.result_data
    except Exception as exc:
        db.rollback()
        managed = db.get(AsyncTask, task.id)
        if managed is not None:
            managed.status = "failed"
            managed.progress = min(managed.progress, 99)
            managed.current_step = "ai_enhancement_failed"
            managed.error_message = _safe_failure_type(exc)
            managed.result_data = {"failure_type": _safe_failure_type(exc), "duration_ms": round((perf_counter() - started) * 1000, 1)}
            managed.finished_at = utcnow()
            db.commit()
        logger.warning("ai_enhancement_failed task_type=%s task_id=%s failure_type=%s", task.task_type, task.public_id, _safe_failure_type(exc))
        return {"failed": True, "failure_type": _safe_failure_type(exc)}
    finally:
        if isinstance(provider, OpenAICompatibleProvider):
            await provider.aclose()
