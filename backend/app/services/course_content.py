"""Small, shared safeguards for course-content quality.

The early rule-first implementation stored three generic labels while a course
had no extracted content.  They are historical data now, so deleting them
would damage references in old plans and attempts.  This module gives every
new-content flow one consistent way to ignore that legacy data instead.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    AsyncTask,
    Course,
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgePoint,
    PracticeQuestion,
)


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


def primary_knowledge_points(
    db: Session, course_id: int, *, limit: int = 12
) -> list[KnowledgePoint]:
    """Return a stable, deduplicated set of the course's main grounded points."""
    selected: list[KnowledgePoint] = []
    seen_names: set[str] = set()
    ranked = sorted(
        usable_knowledge_points(db, course_id),
        key=lambda point: (
            -float(point.importance or 0),
            -int(point.estimated_minutes or 0),
            point.id,
        ),
    )
    for point in ranked:
        name_key = normalise_content_text(point.name)
        if not name_key or name_key in seen_names:
            continue
        seen_names.add(name_key)
        selected.append(point)
        if len(selected) >= limit:
            break
    return selected


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


def current_document_snapshot(db: Session, course_id: int) -> list[dict[str, int]]:
    """Return the active document/version identity used by preparation idempotency."""
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id, Document.is_deleted.is_(False))
            .order_by(Document.id)
        )
    )
    return [
        {"document_id": document.id, "version": document.current_version}
        for document in documents
    ]


def all_course_documents_ready(db: Session, course_id: int) -> bool:
    documents = list(
        db.scalars(
            select(Document).where(
                Document.course_id == course_id,
                Document.is_deleted.is_(False),
            )
        )
    )
    if not documents or any(document.status != "ready" for document in documents):
        return False
    ready_versions = {
        (document_id, version_no)
        for document_id, version_no in db.execute(
            select(DocumentVersion.document_id, DocumentVersion.version_no)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.course_id == course_id,
                Document.is_deleted.is_(False),
                DocumentVersion.status == "ready",
            )
        )
    }
    for document in documents:
        if (document.id, document.current_version) in ready_versions:
            continue
        # Older test/seed data predates DocumentVersion but still has an active
        # current-version chunk. Production uploads always use DocumentVersion.
        legacy_chunk = db.scalar(
            select(DocumentChunk.id).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.document_version == document.current_version,
                DocumentChunk.is_active.is_(True),
            )
        )
        if legacy_chunk is None:
            return False
    return True


def _next_rule_seed(db: Session, course_id: int, point_id: int) -> str:
    prefix = f"rule_source:kp:{point_id}"
    version = 1
    while db.scalar(
        select(PracticeQuestion.id).where(
            PracticeQuestion.course_id == course_id,
            PracticeQuestion.seed_key == (
                prefix if version == 1 else f"{prefix}:v{version}"
            ),
        )
    ) is not None:
        version += 1
    return prefix if version == 1 else f"{prefix}:v{version}"


def source_chunk_for_point(
    db: Session, course_id: int, point: KnowledgePoint
) -> DocumentChunk | None:
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.course_id == course_id,
                DocumentChunk.is_active.is_(True),
                DocumentChunk.document_version == Document.current_version,
                Document.status == "ready",
                Document.is_deleted.is_(False),
            )
            .order_by(DocumentChunk.id)
        )
    )
    description = point.description or ""
    match = re.search(r"来源：(.+?) 第(\d+)页", description)
    if match is not None:
        title, page = match.group(1), int(match.group(2))
        located = next(
            (
                chunk
                for chunk in chunks
                if chunk.page_number == page and chunk.document.title == title
            ),
            None,
        )
        if located is not None:
            return located
    return next((chunk for chunk in chunks if point.name in chunk.content), None)


def _point_description(point: KnowledgePoint) -> str:
    return (point.description or point.name).split("来源：", 1)[0].strip()


def _exact_quote_from_chunk(
    point: KnowledgePoint, source: DocumentChunk
) -> str | None:
    """Select an unchanged substring from the authoritative chunk text."""
    content = source.content or ""
    description = point.description or ""
    if "依据：" in description:
        persisted_quote = description.split("依据：", 1)[1]
        if persisted_quote and persisted_quote in content:
            return persisted_quote

    position = content.find(point.name)
    if position < 0:
        return None
    left_boundary = max(
        content.rfind(delimiter, 0, position)
        for delimiter in ("。", "！", "？", "\n")
    )
    start = left_boundary + 1 if left_boundary >= 0 else max(0, position - 160)
    right_boundaries = [
        boundary
        for delimiter in ("。", "！", "？", "\n")
        if (boundary := content.find(delimiter, position + len(point.name))) >= 0
    ]
    end = min(right_boundaries) + 1 if right_boundaries else min(
        len(content), position + len(point.name) + 340
    )
    quote = content[start:end]
    if not quote or quote not in content:
        return None
    return quote


def question_has_exact_grounding(db: Session, question: PracticeQuestion) -> bool:
    """Verify that a question quote is an exact substring of its live source."""
    if (
        question.source_document_id is None
        or question.source_page_number is None
        or not question.source_quote
    ):
        return False
    chunks = db.scalars(
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.document_id == question.source_document_id,
            DocumentChunk.course_id == question.course_id,
            DocumentChunk.page_number == question.source_page_number,
            DocumentChunk.document_version == Document.current_version,
            DocumentChunk.is_active.is_(True),
            Document.status == "ready",
            Document.is_deleted.is_(False),
        )
    )
    return any(question.source_quote in chunk.content for chunk in chunks)


def grounded_rule_question(
    db: Session,
    *,
    course_id: int,
    point: KnowledgePoint,
    source: DocumentChunk,
    distractors: list[KnowledgePoint],
) -> PracticeQuestion | None:
    """Build a persisted, source-traceable question without canned learning prose."""
    quote = _exact_quote_from_chunk(point, source)
    if quote is None or quote not in source.content:
        return None
    correct_text = _point_description(point)[:150] or quote[:150]
    alternatives = [
        _point_description(other)[:150]
        for other in distractors
        if other.id != point.id and _point_description(other) != correct_text
    ]
    # Six or more extracted points normally provide enough real distractors.
    # If the course has fewer, use distinct source-backed contrasts rather than
    # generic "skip this point" filler.
    source_sentences = [
        sentence.strip()
        for sentence in re.split(r"[。！？!?；;]", quote)
        if len(normalise_content_text(sentence)) >= 8 and sentence.strip() != correct_text
    ]
    alternatives.extend(
        sentence[:150] for sentence in source_sentences if sentence[:150] not in alternatives
    )
    while len(alternatives) < 3:
        alternatives.append(f"{point.name}仅涉及资料中未提到的结论 {len(alternatives) + 1}")
    answer_key = "ABCD"[(point.id - 1) % 4]
    alternative_iter = iter(alternatives[:3])
    options = [
        {
            "key": key,
            "text": correct_text if key == answer_key else next(alternative_iter),
        }
        for key in "ABCD"
    ]
    chapter = source.chapter_name or f"第{source.page_number or '?'}页"
    return PracticeQuestion(
        course_id=course_id,
        knowledge_point_id=point.id,
        seed_key=_next_rule_seed(db, course_id, point.id),
        stem=f"根据“{chapter}”中关于“{point.name}”的内容，下列哪项表述与资料一致？",
        options=options,
        correct_option=answer_key,
        explanation=f"资料依据：{quote}",
        difficulty=point.difficulty,
        origin="rule_source",
        source_document_id=source.document_id,
        source_page_number=source.page_number,
        source_quote=quote,
        is_active=True,
    )


def ensure_grounded_rule_questions(
    db: Session, course_id: int, *, minimum: int = 6
) -> dict[str, int]:
    """Create one grounded rule question per usable point until a batch exists."""
    points = primary_knowledge_points(db, course_id)
    point_ids = {point.id for point in points}
    created = existing = skipped = 0
    active_questions = list(
        db.scalars(
            select(PracticeQuestion)
            .join(
                KnowledgePoint,
                KnowledgePoint.id == PracticeQuestion.knowledge_point_id,
            )
            .where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.is_active.is_(True),
                KnowledgePoint.name.not_in(LEGACY_PLACEHOLDER_POINT_NAMES),
            )
        )
    )
    for question in active_questions:
        if (
            question.knowledge_point_id not in point_ids
            or not question_has_exact_grounding(db, question)
        ):
            question.is_active = False
    db.flush()

    for point in points:
        active = db.scalar(
            select(PracticeQuestion).where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.knowledge_point_id == point.id,
                PracticeQuestion.is_active.is_(True),
            )
        )
        if active is not None and question_has_exact_grounding(db, active):
            existing += 1
            continue
        source = source_chunk_for_point(db, course_id, point)
        if source is None:
            skipped += 1
            continue
        question = grounded_rule_question(
            db,
            course_id=course_id,
            point=point,
            source=source,
            distractors=points,
        )
        if question is None:
            skipped += 1
            continue
        db.add(question)
        created += 1
    db.flush()
    valid_questions = [
        question
        for question in db.scalars(
            select(PracticeQuestion).where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.knowledge_point_id.in_(point_ids),
                PracticeQuestion.is_active.is_(True),
            )
        )
        if question_has_exact_grounding(db, question)
    ]
    total = len({question.knowledge_point_id for question in valid_questions})
    required = min(minimum, len(points)) if points else minimum
    return {
        "created_count": created,
        "existing_count": existing,
        "skipped_count": skipped,
        "question_count": total,
        "required_count": required,
    }


def _grounded_question_state(
    db: Session, course_id: int, point_ids: set[int]
) -> tuple[int, int]:
    active_questions = list(
        db.scalars(
            select(PracticeQuestion)
            .join(
                KnowledgePoint,
                KnowledgePoint.id == PracticeQuestion.knowledge_point_id,
            )
            .where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.is_active.is_(True),
                KnowledgePoint.name.not_in(LEGACY_PLACEHOLDER_POINT_NAMES),
            )
        )
    )
    valid = [
        question
        for question in active_questions
        if question.knowledge_point_id in point_ids
        and question_has_exact_grounding(db, question)
    ]
    invalid_count = len(active_questions) - len(valid)
    return len({question.knowledge_point_id for question in valid}), invalid_count


def course_content_readiness(
    db: Session, course_id: int, *, user_id: int
) -> dict[str, Any]:
    """Derive the user-visible course preparation state from persisted data."""
    course = db.scalar(
        select(Course).where(
            Course.id == course_id,
            Course.owner_id == user_id,
            Course.archived.is_(False),
        )
    )
    if course is None:
        raise LookupError("COURSE_NOT_FOUND")
    snapshot = current_document_snapshot(db, course_id)
    documents_ready = all_course_documents_ready(db, course_id)
    points = primary_knowledge_points(db, course_id)
    point_count = len(points)
    question_count, invalid_question_count = _grounded_question_state(
        db, course_id, {point.id for point in points}
    )
    required_questions = min(6, point_count) if point_count else 6
    ready = (
        bool(snapshot)
        and documents_ready
        and point_count > 0
        and question_count >= required_questions
        and invalid_question_count == 0
    )
    task = db.scalar(
        select(AsyncTask)
        .where(
            AsyncTask.user_id == user_id,
            AsyncTask.task_type == "knowledge_point_extraction",
            AsyncTask.resource_type == "course",
            AsyncTask.resource_id == str(course_id),
        )
        .order_by(AsyncTask.id.desc())
    )
    if ready:
        status = "ready"
        stage = "completed"
    elif not snapshot:
        status = "empty"
        stage = "waiting_for_documents"
    elif not documents_ready:
        status = "processing"
        stage = "processing_documents"
    elif task is not None and task.status in {"queued", "processing", "cancelling"}:
        status = "processing"
        stage = task.current_step
    elif task is not None and task.status in {"failed", "cancelled"}:
        status = task.status
        stage = task.current_step
    else:
        status = "pending"
        stage = "waiting_for_course_preparation"
    return {
        "course_id": course_id,
        "status": status,
        "ready": ready,
        "stage": stage,
        "progress": 100 if ready else (task.progress if task is not None else 0),
        "task_id": task.public_id if task is not None else None,
        "failure_type": (
            (task.result_data or {}).get("failure_type") or task.error_message
            if task is not None and task.status == "failed"
            else None
        ),
        "document_count": len(snapshot),
        "documents_ready": documents_ready,
        "knowledge_point_count": point_count,
        "question_count": question_count,
        "invalid_question_count": invalid_question_count,
        "document_versions": snapshot,
        "can_retry": bool(
            documents_ready and task is not None and task.status in {"failed", "cancelled"}
        ),
    }


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
