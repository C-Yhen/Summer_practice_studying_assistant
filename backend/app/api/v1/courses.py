from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import Course
from backend.app.responses import ok
from backend.app.schemas import CourseCreate, CourseRead, CourseUpdate, ExamDateUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def _owned_course(db: DBSession, course_id: int, owner_id: int) -> Course:
    course = db.scalar(
        select(Course).where(
            Course.id == course_id,
            Course.owner_id == owner_id,
            Course.archived.is_(False),
        )
    )
    if course is None:
        # Returning 404 avoids disclosing another user's course identifiers.
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("", status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, db: DBSession, current_user: CurrentUser) -> dict:
    course = Course(owner_id=current_user.id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return ok(CourseRead.model_validate(course).model_dump(mode="json"), "created")


@router.get("")
def list_courses(
    db: DBSession,
    current_user: CurrentUser,
    include_archived: bool = Query(False),
) -> dict:
    statement = select(Course).where(Course.owner_id == current_user.id)
    if not include_archived:
        statement = statement.where(Course.archived.is_(False))
    items = [
        CourseRead.model_validate(item).model_dump(mode="json")
        for item in db.scalars(statement.order_by(Course.created_at.desc()))
    ]
    return ok({"items": items, "total": len(items)})


@router.get("/{course_id}")
def read_course(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    return ok(CourseRead.model_validate(course).model_dump(mode="json"))


@router.patch("/{course_id}")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return ok(CourseRead.model_validate(course).model_dump(mode="json"))


@router.put("/{course_id}/exam-date")
def set_exam_date(
    course_id: int,
    payload: ExamDateUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    course.exam_date = payload.resolved_date()
    db.commit()
    db.refresh(course)
    return ok(CourseRead.model_validate(course).model_dump(mode="json"))


@router.delete("/{course_id}")
def delete_course(
    course_id: int, db: DBSession, current_user: CurrentUser
) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    course.archived = True
    db.commit()
    return ok({"id": course.id, "status": "archived"})
