from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import (
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    StudyTask,
)
from backend.app.responses import ok
from backend.app.schemas import LearningRecordCreate

router = APIRouter(tags=["learning"])


@router.post("/learning-records")
def create_learning_record(payload: LearningRecordCreate, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, payload.course_id, current_user.id)
    if payload.knowledge_point_id is not None:
        point = db.scalar(select(KnowledgePoint).where(KnowledgePoint.id == payload.knowledge_point_id, KnowledgePoint.course_id == payload.course_id))
        if point is None:
            raise HTTPException(status_code=404, detail="KNOWLEDGE_POINT_NOT_FOUND")
    record = LearningRecord(
        user_id=current_user.id,
        course_id=payload.course_id,
        task_id=payload.task_id,
        knowledge_point_id=payload.knowledge_point_id,
        duration_seconds=payload.duration_seconds,
        record_type=payload.record_type,
        completed=payload.completed,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return ok({"record_id": record.id, "accepted": True})


@router.get("/courses/{course_id}/learning-records")
def list_learning_records(course_id: int, db: DBSession, current_user: CurrentUser, limit: int = 50) -> dict:
    _owned_course(db, course_id, current_user.id)
    rows = list(
        db.execute(
            select(LearningRecord, StudyTask.title, KnowledgePoint.name)
            .outerjoin(StudyTask, StudyTask.id == LearningRecord.task_id)
            .outerjoin(
                KnowledgePoint,
                KnowledgePoint.id == LearningRecord.knowledge_point_id,
            )
            .where(
                LearningRecord.user_id == current_user.id,
                LearningRecord.course_id == course_id,
            )
            .order_by(LearningRecord.occurred_at.desc())
            .limit(min(max(limit, 1), 100))
        )
    )
    return ok({
        "items": [
            {
                "id": record.id,
                "task_id": record.task_id,
                "task_title": task_title,
                "knowledge_point_id": record.knowledge_point_id,
                "knowledge_point": knowledge_point,
                "record_type": record.record_type,
                "duration_seconds": record.duration_seconds,
                "completed": record.completed,
                "occurred_at": record.occurred_at.isoformat(),
            }
            for record, task_title, knowledge_point in rows
        ],
        "total": len(rows),
        "summary": {
            "minutes": round(sum(record.duration_seconds for record, _, _ in rows) / 60)
        },
    })


@router.get("/courses/{course_id}/knowledge-mastery")
def knowledge_mastery(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    points = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))
    mastery_by_point = {item.knowledge_point_id: item for item in db.scalars(select(KnowledgeMastery).where(KnowledgeMastery.user_id == current_user.id, KnowledgeMastery.course_id == course_id))}
    items = []
    for point in points:
        mastery = mastery_by_point.get(point.id)
        items.append({
            "knowledge_point_id": point.id,
            "knowledge_point": point.name,
            "score": mastery.score if mastery else None,
            "confidence": mastery.confidence if mastery else None,
            "attempts": mastery.attempts if mastery else 0,
            "trend": None,
            "has_record": mastery is not None,
        })
    return ok({"items": items})
