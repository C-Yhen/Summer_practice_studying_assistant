from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import Course
from backend.app.schemas import CourseCreate, CourseRead, CourseUpdate, ExamDateUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def _owned_course(db: DBSession, course_id: uuid.UUID, owner_id: uuid.UUID) -> Course:
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.owner_id == owner_id)
    )
    if course is None:
        # Returning 404 avoids disclosing another user's course identifiers.
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: DBSession, current_user: CurrentUser) -> Course:
    course = Course(owner_id=current_user.id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(
    db: DBSession,
    current_user: CurrentUser,
    include_archived: bool = Query(False),
) -> list[Course]:
    statement = select(Course).where(Course.owner_id == current_user.id)
    if not include_archived:
        statement = statement.where(Course.archived.is_(False))
    return list(db.scalars(statement.order_by(Course.created_at.desc())))


@router.get("/{course_id}", response_model=CourseRead)
def read_course(course_id: uuid.UUID, db: DBSession, current_user: CurrentUser) -> Course:
    return _owned_course(db, course_id, current_user.id)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: uuid.UUID,
    payload: CourseUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> Course:
    course = _owned_course(db, course_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return course


@router.put("/{course_id}/exam-date", response_model=CourseRead)
def set_exam_date(
    course_id: uuid.UUID,
    payload: ExamDateUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> Course:
    course = _owned_course(db, course_id, current_user.id)
    course.exam_date = payload.exam_date
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: uuid.UUID, db: DBSession, current_user: CurrentUser
) -> Response:
    course = _owned_course(db, course_id, current_user.id)
    db.delete(course)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

