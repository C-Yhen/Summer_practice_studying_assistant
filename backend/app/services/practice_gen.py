"""Validated, background AI enrichment for rule-first practice questions."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import KnowledgePoint, PracticeQuestion
from backend.app.providers.llm import LLMProvider
from backend.app.services.rag import retrieve

logger = logging.getLogger(__name__)


class AIQuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1, max_length=600)


class AIQuestionPayload(BaseModel):
    """Strict contract before any remote question is allowed into the database."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    knowledge_point_id: int
    stem: str = Field(min_length=1, max_length=3000)
    options: list[AIQuestionOption] = Field(min_length=4, max_length=4)
    correct_option: Literal["A", "B", "C", "D"]
    explanation: str = Field(min_length=1, max_length=4000)
    source_quote: str = Field(min_length=1, max_length=4000)
    difficulty: Literal["basic", "intermediate", "advanced"]

    @field_validator("options")
    @classmethod
    def require_exact_option_labels(cls, options: list[AIQuestionOption]) -> list[AIQuestionOption]:
        if [item.label for item in options] != ["A", "B", "C", "D"]:
            raise ValueError("options must contain exactly A/B/C/D in order")
        return options


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AI_JSON_OBJECT_MISSING")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("AI_JSON_OBJECT_INVALID")
    return value


def _context_from_sources(sources: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for source in sources:
        quote = str(source.get("quote") or "").strip()
        if len(quote) < 20 or quote[:100] in seen:
            continue
        seen.add(quote[:100])
        parts.append(f"[{source.get('document_name', 'course material')}] {quote[:700]}")
    return "\n\n".join(parts[:10])[:8000]


async def generate_questions_batch(
    db: Session,
    provider: LLMProvider,
    *,
    course_id: int,
    knowledge_point_ids: list[int],
    timeout_seconds: int = 18,
) -> list[dict[str, Any]]:
    """One retrieval plus one LLM call for a bounded collection of questions."""
    points = list(db.scalars(select(KnowledgePoint).where(
        KnowledgePoint.course_id == course_id,
        KnowledgePoint.id.in_(knowledge_point_ids[:3]),
    ).order_by(KnowledgePoint.id)))
    if not points:
        return []
    source_context = await retrieve(
        db,
        provider,
        course_id=course_id,
        query=" ".join(point.name for point in points),
        top_k=12,
    )
    context = _context_from_sources(source_context)
    if not context:
        return []
    expected = [
        {"knowledge_point_id": point.id, "knowledge_point": point.name, "difficulty": point.difficulty}
        for point in points
    ]
    prompt = (
        "Generate one single-choice question for each requested knowledge point using only the course context. "
        "Return JSON only: {\"questions\":[{knowledge_point_id,stem,options:[{label,text}],"
        "correct_option,explanation,source_quote,difficulty}]}. Options must be exactly A,B,C,D, "
        "all texts non-empty, and source_quote must be copied from the context.\n"
        f"Requested points: {json.dumps(expected, ensure_ascii=False)}\nContext:\n{context}"
    )
    response = await provider.chat(
        [{"role": "system", "content": "Return only valid JSON matching the requested schema."}, {"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=3000,
        _timeout=timeout_seconds,
    )
    payload = _extract_json(response)
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise ValueError("AI_QUESTIONS_ARRAY_INVALID")
    valid_point_ids = {point.id for point in points}
    questions: list[dict[str, Any]] = []
    for raw in raw_questions[: len(points)]:
        try:
            question = AIQuestionPayload.model_validate(raw)
        except ValidationError as exc:
            logger.warning("ai_practice_question_rejected reason=validation")
            continue
        if question.knowledge_point_id not in valid_point_ids:
            logger.warning("ai_practice_question_rejected reason=knowledge_point_scope")
            continue
        questions.append(question.model_dump())
    return questions


def _next_seed_key(db: Session, course_id: int, prefix: str) -> str:
    version = 3
    while db.scalar(select(PracticeQuestion.id).where(
        PracticeQuestion.course_id == course_id,
        PracticeQuestion.seed_key == f"{prefix}:v{version}",
    )) is not None:
        version += 1
    return f"{prefix}:v{version}"


def persist_ai_questions(db: Session, *, course_id: int, questions: list[dict[str, Any]]) -> dict[str, int | str]:
    """Persist each validated question in a savepoint; never delete history."""
    created = failed = 0
    for raw in questions:
        try:
            question = AIQuestionPayload.model_validate(raw)
            point = db.scalar(select(KnowledgePoint).where(
                KnowledgePoint.id == question.knowledge_point_id,
                KnowledgePoint.course_id == course_id,
            ))
            if point is None:
                raise ValueError("AI_KNOWLEDGE_POINT_SCOPE_INVALID")
            active = db.scalar(select(PracticeQuestion.id).where(
                PracticeQuestion.course_id == course_id,
                PracticeQuestion.knowledge_point_id == point.id,
                PracticeQuestion.origin == "ai_gen",
                PracticeQuestion.is_active.is_(True),
            ))
            if active is not None:
                continue
            with db.begin_nested():
                db.add(PracticeQuestion(
                    course_id=course_id,
                    knowledge_point_id=point.id,
                    seed_key=_next_seed_key(db, course_id, f"ai_gen:kp:{point.id}"),
                    stem=question.stem,
                    options=[{"key": option.label, "text": option.text} for option in question.options],
                    correct_option=question.correct_option,
                    explanation=question.explanation,
                    difficulty=question.difficulty,
                    origin="ai_gen",
                    source_quote=question.source_quote,
                    is_active=True,
                ))
                db.flush()
            created += 1
        except Exception as exc:
            failed += 1
            logger.warning("ai_practice_question_persist_failed error_type=%s", type(exc).__name__)
    return {"generation_mode": "ai_background", "ai_created_count": created, "failed_count": failed}
