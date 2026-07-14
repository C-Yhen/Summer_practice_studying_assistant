from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import LearningRecord, StudyTask, User, UserPreference
from backend.app.responses import ok
from backend.app.schemas import LoginRequest, PreferenceUpdate, TokenResponse, UserRead, UserRegister
from backend.app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["authentication"])


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: DBSession) -> dict:
    email = str(payload.email).strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from None
    db.refresh(user)
    preference = UserPreference(user_id=user.id)
    db.add(preference)
    db.commit()
    return ok(UserRead.model_validate(user).model_dump(mode="json"), "registered")


@router.post("/auth/login")
def login(payload: LoginRequest, db: DBSession, settings: AppSettings) -> dict:
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        user.id,
        settings.jwt_secret,
        settings.jwt_algorithm,
        settings.access_token_expire_minutes,
    )
    response = TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )
    return ok(response.model_dump(mode="json"))


@router.get("/users/me")
def read_me(current_user: CurrentUser) -> dict:
    return ok(UserRead.model_validate(current_user).model_dump(mode="json"))


@router.patch("/users/me/preferences")
def update_preferences(
    payload: PreferenceUpdate, db: DBSession, current_user: CurrentUser
) -> dict:
    preference = db.scalar(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    if preference is None:
        preference = UserPreference(user_id=current_user.id)
        db.add(preference)
    for field, value in payload.model_dump().items():
        setattr(preference, field, value)
    db.commit()
    db.refresh(preference)
    return ok({
        "user_id": current_user.id,
        **payload.model_dump(),
        "updated_at": preference.updated_at.isoformat(),
    })


@router.get("/users/me/profile")
def read_profile(db: DBSession, current_user: CurrentUser, course_id: int | None = None) -> dict:
    preference = db.scalar(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    return ok({
        "user": UserRead.model_validate(current_user).model_dump(mode="json"),
        "course_id": course_id,
        "preferences": PreferenceUpdate.model_validate(preference, from_attributes=True).model_dump()
        if preference
        else PreferenceUpdate().model_dump(),
    })


@router.get("/users/me/statistics")
def read_statistics(db: DBSession, current_user: CurrentUser, course_id: int | None = None) -> dict:
    record_filter = [LearningRecord.user_id == current_user.id]
    task_filter = [StudyTask.user_id == current_user.id]
    if course_id is not None:
        record_filter.append(LearningRecord.course_id == course_id)
        task_filter.append(StudyTask.course_id == course_id)
    seconds = db.scalar(
        select(func.coalesce(func.sum(LearningRecord.duration_seconds), 0)).where(*record_filter)
    ) or 0
    task_total = db.scalar(select(func.count(StudyTask.id)).where(*task_filter)) or 0
    task_done = db.scalar(
        select(func.count(StudyTask.id)).where(*task_filter, StudyTask.status == "completed")
    ) or 0
    return ok({
        "study_minutes": round(seconds / 60),
        "task_completion_rate": round(task_done / task_total, 4) if task_total else 0,
        "task_total": task_total,
        "task_completed": task_done,
    })
