from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import CalendarEvent
from backend.app.responses import ok
from backend.app.schemas import CalendarEventCreate
from backend.app.services.confirmation import issue_confirmation, verify_confirmation

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/availability")
def availability(start_at: datetime, end_at: datetime, db: DBSession, current_user: CurrentUser, minimum_minutes: int = 30) -> dict:
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="INVALID_TIME_RANGE")
    events = list(db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == current_user.id, CalendarEvent.start_at < end_at, CalendarEvent.end_at > start_at).order_by(CalendarEvent.start_at)))
    cursor = start_at
    slots = []
    for event in events:
        if event.start_at > cursor and (event.start_at - cursor).total_seconds() >= minimum_minutes * 60:
            slots.append({"start_at": cursor.isoformat(), "end_at": event.start_at.isoformat(), "source": "local-calendar"})
        cursor = max(cursor, event.end_at)
    if end_at > cursor and (end_at - cursor).total_seconds() >= minimum_minutes * 60:
        slots.append({"start_at": cursor.isoformat(), "end_at": end_at.isoformat(), "source": "local-calendar"})
    return ok({"timezone": current_user.timezone, "slots": slots})


@router.post("/events/preview")
def preview_event(payload: CalendarEventCreate, current_user: CurrentUser, settings: AppSettings) -> dict:
    content = payload.model_dump(mode="json")
    token = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="create_calendar_event", resource_id="new", payload=content)
    return ok({"status": "confirmation_required", "preview": content, "confirmation_token": token, "provider": "local"})


@router.post("/events")
def create_event(payload: CalendarEventCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings, confirmation_token: str = Header("", alias="X-Confirmation-Token")) -> dict:
    content = payload.model_dump(mode="json")
    try:
        verify_confirmation(confirmation_token, settings.jwt_secret, user_id=current_user.id, action="create_calendar_event", resource_id="new", payload=content)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if payload.idempotency_key:
        existing = db.scalar(select(CalendarEvent).where(CalendarEvent.user_id == current_user.id, CalendarEvent.idempotency_key == payload.idempotency_key))
        if existing:
            return ok({"event_id": existing.id, "sync_status": existing.sync_status, "idempotent_replay": True})
    event = CalendarEvent(user_id=current_user.id, **payload.model_dump(), provider="local", sync_status="local")
    db.add(event)
    db.commit()
    db.refresh(event)
    return ok({"event_id": event.id, "sync_status": event.sync_status, "provider": event.provider, "idempotent_replay": False})


@router.get("/events")
def list_events(db: DBSession, current_user: CurrentUser) -> dict:
    events = list(db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == current_user.id).order_by(CalendarEvent.start_at)))
    return ok({"items": [{"id": item.id, "title": item.title, "start_at": item.start_at.isoformat(), "end_at": item.end_at.isoformat(), "provider": item.provider, "sync_status": item.sync_status} for item in events], "total": len(events)})
