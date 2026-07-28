"""Small, shared safeguards for course-content quality.

The early rule-first implementation stored three generic labels while a course
had no extracted content.  They are historical data now, so deleting them
would damage references in old plans and attempts.  This module gives every
new-content flow one consistent way to ignore that legacy data instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import KnowledgePoint, PracticeQuestion


LEGACY_PLACEHOLDER_POINT_NAMES = frozenset({"核心概念", "重点原理", "综合应用"})


def is_legacy_placeholder_point(point: KnowledgePoint | str | None) -> bool:
    """Return whether a point is one of the old non-source-grounded seeds."""
    name = point if isinstance(point, str) else (point.name if point is not None else "")
    return str(name).strip() in LEGACY_PLACEHOLDER_POINT_NAMES


def usable_knowledge_points(db: Session, course_id: int) -> list[KnowledgePoint]:
    """Return only source-grounded points eligible for newly generated content."""
    return list(
        db.scalars(
            select(KnowledgePoint)
            .where(
                KnowledgePoint.course_id == course_id,
                KnowledgePoint.name.not_in(LEGACY_PLACEHOLDER_POINT_NAMES),
            )
            .order_by(KnowledgePoint.id)
        )
    )


def deactivate_legacy_placeholder_questions(db: Session, course_id: int) -> int:
    """Hide legacy placeholder questions without deleting history or rows."""
    placeholder_ids = list(
        db.scalars(
            select(KnowledgePoint.id).where(
                KnowledgePoint.course_id == course_id,
                KnowledgePoint.name.in_(LEGACY_PLACEHOLDER_POINT_NAMES),
            )
        )
    )
    if not placeholder_ids:
        return 0
    questions = list(
        db.scalars(
            select(PracticeQuestion).where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.knowledge_point_id.in_(placeholder_ids),
                PracticeQuestion.is_active.is_(True),
            )
        )
    )
    for question in questions:
        question.is_active = False
    return len(questions)


def normalise_content_text(value: object) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE).lower()


def quote_is_grounded(quote: object, source_quotes: Iterable[object]) -> bool:
    """Require a meaningful quote to be traceable to retrieved course text."""
    needle = normalise_content_text(quote)
    if len(needle) < 8:
        return False
    return any(needle in normalise_content_text(source) for source in source_quotes)


def persist_extracted_knowledge_points(
    db: Session, course_id: int, raw_points: Iterable[dict]
) -> list[KnowledgePoint]:
    """Persist only validated, source-grounded extracted points.

    KnowledgePoint has no provenance columns in the released schema.  Keep the
    concise source locator and quote in ``description`` so each generated plan
    and rule question still has a human-verifiable origin without a migration.
    """
    existing = {point.name.strip(): point for point in usable_knowledge_points(db, course_id)}
    saved: list[KnowledgePoint] = []
    for raw in raw_points:
        name = str(raw.get("name", "")).strip()
        description = str(raw.get("description", "")).strip()
        quote = str(raw.get("source_quote", "")).strip()
        if not name or len(name) > 160 or is_legacy_placeholder_point(name):
            continue
        if len(normalise_content_text(name)) < 3 or not description or not quote:
            continue
        source_text = str(raw.get("source_text", quote))
        if not quote_is_grounded(quote, [source_text]):
            continue
        difficulty = str(raw.get("difficulty", "basic")).strip()
        if difficulty not in {"basic", "intermediate", "advanced"}:
            difficulty = "basic"
        try:
            importance = min(1.0, max(0.0, float(raw.get("importance", 0.5))))
            estimated_minutes = min(90, max(15, int(raw.get("estimated_minutes", 45))))
        except (TypeError, ValueError):
            continue
        source_name = str(raw.get("source_document_name", "课程资料")).strip() or "课程资料"
        page = raw.get("source_page_number")
        locator = f"来源：{source_name}" + (f" 第{page}页" if page else "")
        stored_description = f"{description}\n{locator}。依据：{quote[:500]}"
        point = existing.get(name)
        if point is None:
            point = KnowledgePoint(
                course_id=course_id,
                name=name,
                description=stored_description,
                importance=importance,
                difficulty=difficulty,
                estimated_minutes=estimated_minutes,
                prerequisite_ids=[],
            )
            db.add(point)
            existing[name] = point
        else:
            point.description = stored_description
            point.importance = importance
            point.difficulty = difficulty
            point.estimated_minutes = estimated_minutes
        saved.append(point)
    db.flush()
    return saved
