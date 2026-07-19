from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import (
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    PracticeAttempt,
    PracticeQuestion,
    WrongQuestionEntry,
)
from backend.app.responses import ok
from backend.app.schemas import PracticeAttemptCreate, WrongBookUpdate
from backend.app.services.mastery import apply_mastery_evidence

router = APIRouter(tags=["practice"])


def _summary(db: DBSession, user_id: int, course_id: int) -> dict:
    total, correct = db.execute(
        select(
            func.count(PracticeAttempt.id),
            func.count(PracticeAttempt.id).filter(PracticeAttempt.is_correct.is_(True)),
        ).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.course_id == course_id,
        )
    ).one()
    pending = db.scalar(
        select(func.count())
        .select_from(WrongQuestionEntry)
        .where(
            WrongQuestionEntry.user_id == user_id,
            WrongQuestionEntry.course_id == course_id,
            WrongQuestionEntry.status == "pending",
        )
    ) or 0
    point_count = db.scalar(
        select(func.count())
        .select_from(KnowledgePoint)
        .where(KnowledgePoint.course_id == course_id)
    ) or 0
    total = int(total or 0)
    correct = int(correct or 0)
    return {
        "total_attempts": total,
        "correct_attempts": correct,
        "wrong_attempts": total - correct,
        "accuracy": round(correct / total, 4) if total else 0,
        "pending_wrong_count": pending,
        "knowledge_point_count": point_count,
    }


def _question(
    question: PracticeQuestion,
    point: KnowledgePoint | None = None,
    *,
    reveal: bool = False,
) -> dict:
    data = {
        "id": question.id,
        "knowledge_point_id": question.knowledge_point_id,
        "knowledge_point": point.name if point else None,
        "question_type": question.question_type,
        "stem": question.stem,
        "options": question.options,
        "difficulty": question.difficulty,
        "origin": question.origin,
        "source_document_id": question.source_document_id,
        "source_page_number": question.source_page_number,
        "source_quote": question.source_quote,
    }
    if reveal:
        data.update(
            {
                "correct_option": question.correct_option,
                "explanation": question.explanation,
            }
        )
    return data


def _validate_replay(
    attempt: PracticeAttempt,
    *,
    course_id: int,
    question_id: int,
    payload: PracticeAttemptCreate,
) -> None:
    if (
        attempt.course_id != course_id
        or attempt.question_id != question_id
        or attempt.selected_option != payload.selected_option
        or attempt.elapsed_seconds != payload.elapsed_seconds
    ):
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")


def _attempt_response(
    db: DBSession,
    attempt: PracticeAttempt,
    question: PracticeQuestion,
    *,
    replay: bool,
) -> dict:
    point = db.get(KnowledgePoint, question.knowledge_point_id) if question.knowledge_point_id else None
    mastery_score = (
        db.scalar(
            select(KnowledgeMastery.score).where(
                KnowledgeMastery.user_id == attempt.user_id,
                KnowledgeMastery.knowledge_point_id == question.knowledge_point_id,
            )
        )
        if question.knowledge_point_id
        else None
    )
    return {
        "attempt_id": attempt.id,
        "question_id": question.id,
        "selected_option": attempt.selected_option,
        "is_correct": attempt.is_correct,
        "idempotent_replay": replay,
        **_question(question, point, reveal=True),
        "mastery_score": mastery_score,
        "wrong_book_updated": not attempt.is_correct,
        "summary": _summary(db, attempt.user_id, attempt.course_id),
    }


def _persisted_replay(
    db: DBSession,
    *,
    user_id: int,
    course_id: int,
    question_id: int,
    payload: PracticeAttemptCreate,
) -> dict | None:
    persisted = db.scalar(
        select(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.submission_id == payload.submission_id,
        )
    )
    if persisted is None:
        return None
    _validate_replay(
        persisted,
        course_id=course_id,
        question_id=question_id,
        payload=payload,
    )
    question = db.scalar(
        select(PracticeQuestion).where(
            PracticeQuestion.id == persisted.question_id,
            PracticeQuestion.course_id == persisted.course_id,
        )
    )
    if question is None:
        raise HTTPException(status_code=500, detail="PRACTICE_ATTEMPT_FAILED")
    return _attempt_response(db, persisted, question, replay=True)


@router.post("/courses/{course_id}/practice/questions/bootstrap")
def bootstrap(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    points = list(
        db.scalars(
            select(KnowledgePoint)
            .where(KnowledgePoint.course_id == course.id)
            .order_by(KnowledgePoint.id)
            .limit(10)
        )
    )
    created = existing = 0
    for point in points:
        key = f"rule_seed:kp:{point.id}"
        if db.scalar(
            select(PracticeQuestion.id).where(
                PracticeQuestion.course_id == course.id,
                PracticeQuestion.seed_key == key,
            )
        ):
            existing += 1
            continue
        name = point.name
        db.add(
            PracticeQuestion(
                course_id=course.id,
                knowledge_point_id=point.id,
                seed_key=key,
                stem=f'关于知识点“{name}”，下列哪项最符合完成该知识点学习后的要求？',
                options=[
                    {
                        "key": "A",
                        "text": f"能够用自己的话解释“{name}”的核心含义，并说明基本适用场景。",
                    },
                    {"key": "B", "text": "只浏览任务标题即可。"},
                    {"key": "C", "text": "只累计学习时长而无需理解。"},
                    {"key": "D", "text": "跳过该知识点并直接标记完成。"},
                ],
                correct_option="A",
                explanation=point.description
                or f"这是课程“{course.name}”中“{name}”的规则化基础自测题。",
                difficulty=point.difficulty,
                origin="rule_seed",
            )
        )
        created += 1
    db.commit()
    return ok(
        {
            "created_count": created,
            "existing_count": existing,
            "total": created + existing,
            "reason": "NO_KNOWLEDGE_POINTS" if not points else None,
        }
    )


@router.get("/courses/{course_id}/practice/questions")
def questions(
    course_id: int,
    db: DBSession,
    current_user: CurrentUser,
    mode: str = Query("all", pattern="^(all|wrong)$"),
    limit: int = Query(20, ge=1, le=100),
    knowledge_point_id: int | None = None,
) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    if knowledge_point_id is not None:
        point = db.scalar(
            select(KnowledgePoint).where(
                KnowledgePoint.id == knowledge_point_id,
                KnowledgePoint.course_id == course.id,
            )
        )
        if point is None:
            raise HTTPException(status_code=404, detail="KNOWLEDGE_POINT_NOT_FOUND")

    query = (
        select(PracticeQuestion, KnowledgePoint)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == PracticeQuestion.knowledge_point_id)
        .where(
            PracticeQuestion.course_id == course.id,
            PracticeQuestion.is_active.is_(True),
        )
    )
    if knowledge_point_id is not None:
        query = query.where(PracticeQuestion.knowledge_point_id == knowledge_point_id)
    if mode == "wrong":
        query = query.join(
            WrongQuestionEntry,
            WrongQuestionEntry.question_id == PracticeQuestion.id,
        ).where(
            WrongQuestionEntry.user_id == current_user.id,
            WrongQuestionEntry.course_id == course.id,
            WrongQuestionEntry.status == "pending",
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(db.execute(query.order_by(PracticeQuestion.id).limit(limit)))
    return ok(
        {
            "course": {"id": course.id, "name": course.name},
            "items": [_question(question, point) for question, point in rows],
            "total": total,
            "summary": _summary(db, current_user.id, course.id),
        }
    )


@router.post("/courses/{course_id}/practice/questions/{question_id}/attempts")
def attempt(
    course_id: int,
    question_id: int,
    payload: PracticeAttemptCreate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    replay = _persisted_replay(
        db,
        user_id=current_user.id,
        course_id=course_id,
        question_id=question_id,
        payload=payload,
    )
    if replay is not None:
        return ok(replay)

    question = db.scalar(
        select(PracticeQuestion).where(
            PracticeQuestion.id == question_id,
            PracticeQuestion.course_id == course_id,
            PracticeQuestion.is_active.is_(True),
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="QUESTION_NOT_FOUND")
    if payload.selected_option not in {str(option.get("key")) for option in question.options}:
        raise HTTPException(status_code=422, detail="INVALID_OPTION")

    correct = payload.selected_option == question.correct_option
    now = datetime.now(timezone.utc)
    mastery = None
    entry = None
    if not correct:
        entry = db.scalar(
            select(WrongQuestionEntry).where(
                WrongQuestionEntry.user_id == current_user.id,
                WrongQuestionEntry.question_id == question.id,
            )
        )

    row = PracticeAttempt(
        submission_id=payload.submission_id,
        user_id=current_user.id,
        course_id=course_id,
        question_id=question.id,
        selected_option=payload.selected_option,
        is_correct=correct,
        elapsed_seconds=payload.elapsed_seconds,
        submitted_at=now,
    )
    try:
        db.add(row)
        if question.knowledge_point_id:
            mastery = apply_mastery_evidence(
                db,
                user_id=current_user.id,
                course_id=course_id,
                knowledge_point_id=question.knowledge_point_id,
                correct=correct,
                score_strength=0.12 if correct else 0.10,
                confidence_strength=0.08 if correct else 0.04,
                occurred_at=now,
            )
        db.add(
            LearningRecord(
                user_id=current_user.id,
                course_id=course_id,
                knowledge_point_id=question.knowledge_point_id,
                duration_seconds=payload.elapsed_seconds,
                record_type="practice",
                completed=True,
                occurred_at=now,
            )
        )
        if not correct:
            if entry:
                entry.status = "pending"
                entry.wrong_count += 1
                entry.last_selected_option = payload.selected_option
                entry.last_wrong_at = now
                entry.mastered_at = None
            else:
                entry = WrongQuestionEntry(
                    user_id=current_user.id,
                    course_id=course_id,
                    question_id=question.id,
                    last_selected_option=payload.selected_option,
                    last_wrong_at=now,
                )
                db.add(entry)
        db.commit()
    except IntegrityError:
        db.rollback()
        replay = _persisted_replay(
            db,
            user_id=current_user.id,
            course_id=course_id,
            question_id=question_id,
            payload=payload,
        )
        if replay is not None:
            return ok(replay)
        raise HTTPException(status_code=500, detail="PRACTICE_ATTEMPT_FAILED") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="PRACTICE_ATTEMPT_FAILED") from None

    db.refresh(row)
    return ok(
        {
            "attempt_id": row.id,
            "question_id": question.id,
            "selected_option": row.selected_option,
            "is_correct": correct,
            "idempotent_replay": False,
            **_question(
                question,
                db.get(KnowledgePoint, question.knowledge_point_id)
                if question.knowledge_point_id
                else None,
                reveal=True,
            ),
            "mastery_score": mastery.score if mastery else None,
            "wrong_book_updated": entry is not None,
            "summary": _summary(db, current_user.id, course_id),
        }
    )


@router.get("/courses/{course_id}/wrong-book")
def wrong_book(
    course_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str = Query("all", pattern="^(all|pending|mastered)$"),
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    _owned_course(db, course_id, current_user.id)
    base = (
        select(
            WrongQuestionEntry,
            PracticeQuestion,
            KnowledgePoint,
            KnowledgeMastery,
        )
        .join(PracticeQuestion, PracticeQuestion.id == WrongQuestionEntry.question_id)
        .outerjoin(KnowledgePoint, KnowledgePoint.id == PracticeQuestion.knowledge_point_id)
        .outerjoin(
            KnowledgeMastery,
            (KnowledgeMastery.user_id == current_user.id)
            & (KnowledgeMastery.knowledge_point_id == PracticeQuestion.knowledge_point_id),
        )
        .where(
            WrongQuestionEntry.user_id == current_user.id,
            WrongQuestionEntry.course_id == course_id,
            WrongQuestionEntry.status != "removed",
        )
    )
    filtered = base
    if status != "all":
        filtered = filtered.where(WrongQuestionEntry.status == status)
    search = q.strip()
    if search:
        filtered = filtered.where(
            or_(
                PracticeQuestion.stem.ilike(f"%{search}%"),
                KnowledgePoint.name.ilike(f"%{search}%"),
            )
        )

    total = db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
    rows = list(
        db.execute(
            filtered.order_by(
                WrongQuestionEntry.last_wrong_at.desc(),
                WrongQuestionEntry.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    )
    items = [
        {
            "id": entry.id,
            "status": entry.status,
            "wrong_count": entry.wrong_count,
            "last_selected_option": entry.last_selected_option,
            "last_wrong_at": entry.last_wrong_at.isoformat(),
            "question": _question(question, point, reveal=True),
            "mastery_score": mastery.score if mastery else None,
        }
        for entry, question, point, mastery in rows
    ]
    summary_rows = db.execute(
        select(
            WrongQuestionEntry.status,
            func.count(WrongQuestionEntry.id),
        )
        .where(
            WrongQuestionEntry.user_id == current_user.id,
            WrongQuestionEntry.course_id == course_id,
            WrongQuestionEntry.status.in_(("pending", "mastered")),
        )
        .group_by(WrongQuestionEntry.status)
    )
    counts = {"pending": 0, "mastered": 0}
    counts.update({status_name: count for status_name, count in summary_rows})
    repeated = db.scalar(
        select(func.count())
        .select_from(WrongQuestionEntry)
        .where(
            WrongQuestionEntry.user_id == current_user.id,
            WrongQuestionEntry.course_id == course_id,
            WrongQuestionEntry.status != "removed",
            WrongQuestionEntry.wrong_count > 1,
        )
    ) or 0
    return ok(
        {
            "items": items,
            "total": total,
            "summary": {**counts, "repeated_wrong": repeated},
        }
    )


@router.patch("/courses/{course_id}/wrong-book/{entry_id}")
def update_wrong(
    entry_id: int,
    course_id: int,
    payload: WrongBookUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    entry = db.scalar(
        select(WrongQuestionEntry).where(
            WrongQuestionEntry.id == entry_id,
            WrongQuestionEntry.user_id == current_user.id,
            WrongQuestionEntry.course_id == course_id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="WRONG_ENTRY_NOT_FOUND")
    if entry.status == payload.status:
        return ok({"id": entry.id, "status": entry.status})
    entry.status = payload.status
    entry.mastered_at = (
        datetime.now(timezone.utc) if payload.status == "mastered" else None
    )
    db.commit()
    return ok({"id": entry.id, "status": entry.status})
