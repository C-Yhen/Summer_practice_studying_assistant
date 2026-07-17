from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import LearningRecord, StudyTask, User, UserPreference
from backend.app.responses import ok
from backend.app.schemas import (
    LoginRequest,
    PreferenceRead,
    PreferenceUpdate,
    TokenResponse,
    UserRead,
    UserRegister,
    UserUpdate,
)
from backend.app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["authentication"])


def _preference_for_user(db: DBSession, user_id: int) -> UserPreference:
    preference = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if preference is None:
        preference = UserPreference(user_id=user_id)
        db.add(preference)
        db.flush()
    return preference


def _preference_payload(preference: UserPreference) -> dict:
    return PreferenceRead.model_validate(preference).model_dump()


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


@router.patch("/users/me")
def update_me(payload: UserUpdate, db: DBSession, current_user: CurrentUser) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if "timezone" in updates:
        try:
            ZoneInfo(updates["timezone"])
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="INVALID_TIMEZONE") from exc
    for field, value in updates.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return ok(UserRead.model_validate(current_user).model_dump(mode="json"))


@router.patch("/users/me/preferences")
def update_preferences(
    payload: PreferenceUpdate, db: DBSession, current_user: CurrentUser
) -> dict:
    preference = _preference_for_user(db, current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    session_minutes = updates.get("session_minutes", preference.session_minutes)
    daily_minutes = updates.get("daily_minutes", preference.daily_minutes)
    if session_minutes > daily_minutes:
        raise HTTPException(status_code=422, detail="SESSION_MINUTES_EXCEEDS_DAILY_MINUTES")
    for field, value in updates.items():
        setattr(preference, field, value)
    db.commit()
    db.refresh(preference)
    return ok(_preference_payload(preference))


@router.get("/users/me/profile")
def read_profile(db: DBSession, current_user: CurrentUser, course_id: int | None = None) -> dict:
    preference = _preference_for_user(db, current_user.id)
    db.commit()
    db.refresh(preference)
    return ok({
        "user": UserRead.model_validate(current_user).model_dump(mode="json"),
        "course_id": course_id,
        "preferences": _preference_payload(preference),
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
