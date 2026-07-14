from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import Document, KnowledgeMastery, KnowledgePoint, RecommendationRecord
from backend.app.recommendation.engine import RecommendationFeatures, explain_recommendation, score_recommendation
from backend.app.responses import ok
from backend.app.schemas import RecommendationFeedback

router = APIRouter(tags=["recommendations"])


def _weakest_points(db: DBSession, user_id: int, course_id: int) -> list[tuple[KnowledgePoint, float]]:
    points = list(db.scalars(select(KnowledgePoint).where(KnowledgePoint.course_id == course_id)))
    mastery = {item.knowledge_point_id: item.score for item in db.scalars(select(KnowledgeMastery).where(KnowledgeMastery.user_id == user_id, KnowledgeMastery.course_id == course_id))}
    return sorted(((point, mastery.get(point.id, 0.3)) for point in points), key=lambda item: item[1])


@router.get("/courses/{course_id}/recommendations/resources")
def recommend_resources(course_id: int, db: DBSession, current_user: CurrentUser, limit: int = 5) -> dict:
    _owned_course(db, course_id, current_user.id)
    documents = list(db.scalars(select(Document).where(Document.course_id == course_id, Document.status == "ready", Document.is_deleted.is_(False)).limit(min(max(limit, 1), 20))))
    weakest = _weakest_points(db, current_user.id, course_id)
    default_point = weakest[0] if weakest else (None, 0.3)
    items = []
    for document in documents:
        point, mastery = default_point
        score, breakdown = score_recommendation(RecommendationFeatures(knowledge_match=0.75, weakness=1-mastery, difficulty_match=0.85, preference_match=0.5, resource_quality=0.8, time_match=0.8))
        point_name = point.name if point else "课程核心内容"
        reason = explain_recommendation(knowledge_name=point_name, mastery=mastery, difficulty="基础", item_type="资料")
        record = RecommendationRecord(user_id=current_user.id, course_id=course_id, item_type="resource", item_id=document.id, score=score, reason=reason, score_breakdown=breakdown)
        db.add(record)
        db.flush()
        items.append({"record_id": record.id, "resource_id": document.id, "title": document.title, "score": score, "reason": reason, "score_breakdown": breakdown, "knowledge_point": point_name})
    db.commit()
    return ok({"items": items})


@router.get("/courses/{course_id}/recommendations/exercises")
def recommend_exercises(course_id: int, db: DBSession, current_user: CurrentUser, count: int = 5) -> dict:
    _owned_course(db, course_id, current_user.id)
    items = []
    for point, mastery in _weakest_points(db, current_user.id, course_id)[: min(max(count, 1), 20)]:
        score, breakdown = score_recommendation(RecommendationFeatures(knowledge_match=1.0, weakness=1-mastery, difficulty_match=0.9, preference_match=0.5, resource_quality=0.75, time_match=0.8))
        reason = explain_recommendation(knowledge_name=point.name, mastery=mastery, difficulty=point.difficulty, item_type="练习")
        record = RecommendationRecord(user_id=current_user.id, course_id=course_id, item_type="exercise", item_id=point.id, score=score, reason=reason, score_breakdown=breakdown)
        db.add(record)
        db.flush()
        items.append({"record_id": record.id, "question_id": point.id, "knowledge_point": point.name, "difficulty": point.difficulty, "score": score, "reason": reason, "score_breakdown": breakdown})
    db.commit()
    return ok({"items": items})


def _owned_record(db: DBSession, record_id: int, user_id: int) -> RecommendationRecord:
    record = db.scalar(select(RecommendationRecord).where(RecommendationRecord.id == record_id, RecommendationRecord.user_id == user_id))
    if record is None:
        raise HTTPException(status_code=404, detail="RECOMMENDATION_NOT_FOUND")
    return record


@router.post("/recommendations/{record_id}/feedback")
def recommendation_feedback(record_id: int, payload: RecommendationFeedback, db: DBSession, current_user: CurrentUser) -> dict:
    record = _owned_record(db, record_id, current_user.id)
    record.feedback_action = payload.action
    record.feedback_rating = payload.rating
    db.commit()
    return ok({"record_id": record.id, "accepted": True})


@router.get("/recommendations/{record_id}/reason")
def recommendation_reason(record_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    record = _owned_record(db, record_id, current_user.id)
    return ok({"reason": record.reason, "score": record.score, "score_breakdown": record.score_breakdown, "algorithm_version": record.algorithm_version})


@router.get("/courses/{course_id}/recommendations/history")
def recommendation_history(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    records = list(db.scalars(select(RecommendationRecord).where(RecommendationRecord.user_id == current_user.id, RecommendationRecord.course_id == course_id).order_by(RecommendationRecord.created_at.desc()).limit(100)))
    clicked = sum(1 for item in records if item.feedback_action == "clicked")
    completed = sum(1 for item in records if item.feedback_action == "completed")
    return ok({"items": [{"record_id": item.id, "item_type": item.item_type, "item_id": item.item_id, "score": item.score, "reason": item.reason, "feedback_action": item.feedback_action, "created_at": item.created_at.isoformat()} for item in records], "total": len(records), "metrics": {"ctr": clicked / len(records) if records else 0, "completion_rate": completed / len(records) if records else 0}})
