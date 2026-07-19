from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import KnowledgeMastery


def apply_mastery_evidence(
    db: Session,
    *,
    user_id: int,
    course_id: int,
    knowledge_point_id: int,
    correct: bool,
    score_strength: float,
    confidence_strength: float,
    occurred_at: datetime,
) -> KnowledgeMastery:
    """Apply one learning signal without committing the caller's transaction."""
    mastery = db.scalar(
        select(KnowledgeMastery).where(
            KnowledgeMastery.user_id == user_id,
            KnowledgeMastery.knowledge_point_id == knowledge_point_id,
        )
    )
    if mastery is None:
        mastery = KnowledgeMastery(
            user_id=user_id,
            course_id=course_id,
            knowledge_point_id=knowledge_point_id,
            score=0.3,
            confidence=0.2,
            attempts=0,
            correct_attempts=0,
        )
        db.add(mastery)

    if correct:
        mastery.score += score_strength * (1.0 - mastery.score)
        mastery.confidence += confidence_strength
        mastery.correct_attempts += 1
    else:
        mastery.score -= score_strength * mastery.score
        mastery.confidence -= confidence_strength

    mastery.score = round(max(0.0, min(1.0, mastery.score)), 4)
    mastery.confidence = round(max(0.0, min(1.0, mastery.confidence)), 4)
    mastery.attempts += 1
    mastery.last_studied_at = occurred_at
    return mastery
