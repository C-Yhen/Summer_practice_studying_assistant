from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import StringIO

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import CalendarEvent, Course, StudyPlan, StudyPlanVersion, StudyTask
from backend.app.responses import ok
from backend.app.schemas import CalendarEventCreate, CalendarEventUpdate, CalendarPlanSyncConfirm, CalendarPlanSyncRequest
from backend.app.services.confirmation import issue_confirmation, verify_confirmation
from backend.app.services.timezones import as_utc, local_date_range_utc, resolve_user_timezone

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _fail(status: int, code: str) -> None:
    raise HTTPException(status_code=status, detail=code)


def _range(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    start, end = as_utc(start_at), as_utc(end_at)
    if end <= start:
        _fail(422, "INVALID_TIME_RANGE")
    return start, end


def _query_range(
    *,
    start_at: datetime | None,
    end_at: datetime | None,
    start_date: date | None,
    end_date: date | None,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    has_datetimes = start_at is not None or end_at is not None
    has_dates = start_date is not None or end_date is not None
    if has_datetimes and has_dates:
        _fail(422, "CALENDAR_RANGE_PARAMETERS_MIXED")
    if has_dates:
        if start_date is None or end_date is None or end_date < start_date:
            _fail(422, "INVALID_DATE_RANGE")
        zone, _ = resolve_user_timezone(timezone_name)
        return local_date_range_utc(start_date, end_date, zone)
    if start_at is None or end_at is None:
        _fail(422, "CALENDAR_RANGE_REQUIRED")
    return _range(start_at, end_at)


def _course(db: DBSession, user_id: int, course_id: int) -> Course:
    item = db.scalar(select(Course).where(Course.id == course_id, Course.owner_id == user_id, Course.archived.is_(False)))
    if not item:
        _fail(404, "COURSE_NOT_FOUND")
    return item


def _event_payload(event: CalendarEvent, task: StudyTask | None = None, course: Course | None = None) -> dict:
    return {
        "id": event.id, "title": event.title, "start_at": as_utc(event.start_at).isoformat(), "end_at": as_utc(event.end_at).isoformat(),
        "provider": event.provider, "sync_status": event.sync_status, "study_task_id": event.study_task_id,
        "course_id": course.id if course else None, "course_name": course.name if course else None,
        "task_type": task.task_type if task else None, "created_at": event.created_at.isoformat(), "updated_at": event.updated_at.isoformat(),
    }


def _event_rows(db: DBSession, user_id: int, start_at: datetime, end_at: datetime, course_id: int | None):
    statement = select(CalendarEvent, StudyTask, Course).outerjoin(StudyTask, StudyTask.id == CalendarEvent.study_task_id).outerjoin(Course, Course.id == StudyTask.course_id).where(
        CalendarEvent.user_id == user_id, CalendarEvent.start_at < end_at, CalendarEvent.end_at > start_at,
    )
    if course_id is not None:
        _course(db, user_id, course_id)
        statement = statement.where(StudyTask.course_id == course_id)
    else:
        statement = statement.where((Course.id.is_(None)) | (Course.archived.is_(False)))
    return statement


def _conflict(db: DBSession, user_id: int, start_at: datetime, end_at: datetime, exclude_id: int | None = None) -> CalendarEvent | None:
    statement = select(CalendarEvent).where(CalendarEvent.user_id == user_id, CalendarEvent.start_at < end_at, CalendarEvent.end_at > start_at)
    if exclude_id is not None:
        statement = statement.where(CalendarEvent.id != exclude_id)
    return db.scalar(statement.order_by(CalendarEvent.start_at, CalendarEvent.id))


def _task_for_event(db: DBSession, user_id: int, task_id: int | None) -> StudyTask | None:
    if task_id is None:
        return None
    task = db.scalar(select(StudyTask).join(Course, Course.id == StudyTask.course_id).where(StudyTask.id == task_id, StudyTask.user_id == user_id, Course.owner_id == user_id, Course.archived.is_(False)))
    if not task:
        _fail(404, "STUDY_TASK_NOT_FOUND")
    return task


def _key(user_id: int, value: str) -> str:
    return f"calendar:{user_id}:{value}"


def _manual_key(user_id: int, value: str) -> str:
    return _key(user_id, f"manual:{value}")


def _create_content(payload: CalendarEventCreate, key: str) -> dict:
    return {"title": payload.title, "start_at": as_utc(payload.start_at).isoformat(), "end_at": as_utc(payload.end_at).isoformat(), "study_task_id": payload.study_task_id, "idempotency_key": key}


@router.get("/availability")
def availability(start_at: datetime, end_at: datetime, db: DBSession, current_user: CurrentUser, minimum_minutes: int = Query(30, ge=1, le=1440)) -> dict:
    start_at, end_at = _range(start_at, end_at)
    events = list(db.scalars(select(CalendarEvent).where(CalendarEvent.user_id == current_user.id, CalendarEvent.start_at < end_at, CalendarEvent.end_at > start_at).order_by(CalendarEvent.start_at, CalendarEvent.id)))
    cursor, slots = start_at, []
    for event in events:
        event_start, event_end = as_utc(event.start_at), as_utc(event.end_at)
        if event_start > cursor and (event_start - cursor).total_seconds() >= minimum_minutes * 60:
            slots.append({"start_at": cursor.isoformat(), "end_at": event_start.isoformat(), "source": "local-calendar"})
        cursor = max(cursor, event_end)
    if end_at > cursor and (end_at - cursor).total_seconds() >= minimum_minutes * 60:
        slots.append({"start_at": cursor.isoformat(), "end_at": end_at.isoformat(), "source": "local-calendar"})
    return ok({"timezone": current_user.timezone, "slots": slots})


@router.get("/events")
def list_events(db: DBSession, current_user: CurrentUser, start_at: datetime | None = None, end_at: datetime | None = None, start_date: date | None = None, end_date: date | None = None, course_id: int | None = Query(None, gt=0), limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)) -> dict:
    start_at, end_at = _query_range(start_at=start_at, end_at=end_at, start_date=start_date, end_date=end_date, timezone_name=current_user.timezone)
    statement = _event_rows(db, current_user.id, start_at, end_at, course_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(statement.order_by(CalendarEvent.start_at, CalendarEvent.id).offset(offset).limit(limit)).all()
    return ok({"items": [_event_payload(event, task, course) for event, task, course in rows], "total": total, "timezone": current_user.timezone})


@router.post("/events/preview")
def preview_event(payload: CalendarEventCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings, idempotency_key: str = Header("", alias="Idempotency-Key")) -> dict:
    task = _task_for_event(db, current_user.id, payload.study_task_id)
    start, end = _range(payload.start_at, payload.end_at)
    if _conflict(db, current_user.id, start, end):
        _fail(409, "CALENDAR_CONFLICT")
    supplied = payload.idempotency_key or idempotency_key
    if payload.idempotency_key and idempotency_key and payload.idempotency_key != idempotency_key:
        _fail(422, "IDEMPOTENCY_KEY_MISMATCH")
    content = _create_content(
        payload,
        _manual_key(current_user.id, supplied or f"{payload.title}:{start.isoformat()}"),
    )
    token = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="create_calendar_event", resource_id="new", payload=content)
    return ok({"status": "confirmation_required", "preview": content, "confirmation_token": token, "provider": "local", "task_id": task.id if task else None})


@router.post("/events")
def create_event(payload: CalendarEventCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings, confirmation_token: str = Header("", alias="X-Confirmation-Token"), header_key: str = Header("", alias="Idempotency-Key")) -> dict:
    supplied = payload.idempotency_key or header_key
    if payload.idempotency_key and header_key and payload.idempotency_key != header_key:
        _fail(422, "IDEMPOTENCY_KEY_MISMATCH")
    key = _manual_key(
        current_user.id,
        supplied or f"{payload.title}:{as_utc(payload.start_at).isoformat()}",
    )
    content = _create_content(payload, key)
    try:
        verify_confirmation(confirmation_token, settings.jwt_secret, user_id=current_user.id, action="create_calendar_event", resource_id="new", payload=content)
    except ValueError as exc:
        _fail(409, "CONFIRMATION_PAYLOAD_MISMATCH")
    _task_for_event(db, current_user.id, payload.study_task_id)
    existing = db.scalar(select(CalendarEvent).where(CalendarEvent.idempotency_key == key))
    if existing:
        if _event_payload(existing)["title"] != payload.title or as_utc(existing.start_at) != as_utc(payload.start_at) or as_utc(existing.end_at) != as_utc(payload.end_at) or existing.study_task_id != payload.study_task_id:
            _fail(409, "IDEMPOTENCY_KEY_REUSED")
        return ok({"event_id": existing.id, "sync_status": existing.sync_status, "provider": existing.provider, "idempotent_replay": True})
    start, end = _range(payload.start_at, payload.end_at)
    if _conflict(db, current_user.id, start, end):
        _fail(409, "CALENDAR_CONFLICT")
    event = CalendarEvent(user_id=current_user.id, title=payload.title, start_at=start, end_at=end, study_task_id=payload.study_task_id, idempotency_key=key, provider="local", sync_status="local")
    try:
        db.add(event); db.commit(); db.refresh(event)
    except IntegrityError:
        db.rollback(); existing = db.scalar(select(CalendarEvent).where(CalendarEvent.idempotency_key == key))
        if existing and existing.title == payload.title and as_utc(existing.start_at) == start and as_utc(existing.end_at) == end and existing.study_task_id == payload.study_task_id:
            return ok({"event_id": existing.id, "sync_status": existing.sync_status, "provider": existing.provider, "idempotent_replay": True})
        _fail(409, "IDEMPOTENCY_KEY_REUSED")
    except SQLAlchemyError:
        db.rollback()
        _fail(409, "CALENDAR_WRITE_FAILED")
    return ok({"event_id": event.id, "sync_status": event.sync_status, "provider": event.provider, "idempotent_replay": False})


def _event_or_404(db: DBSession, user_id: int, event_id: int) -> CalendarEvent:
    event = db.scalar(select(CalendarEvent).where(CalendarEvent.id == event_id, CalendarEvent.user_id == user_id))
    if not event:
        _fail(404, "CALENDAR_EVENT_NOT_FOUND")
    return event


def _snapshot(event: CalendarEvent) -> dict:
    return {"id": event.id, "title": event.title, "start_at": as_utc(event.start_at).isoformat(), "end_at": as_utc(event.end_at).isoformat(), "updated_at": event.updated_at.isoformat()}


@router.post("/events/{event_id}/preview-update")
def preview_update(event_id: int, changes: CalendarEventUpdate, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    event = _event_or_404(db, current_user.id, event_id)
    start, end = _range(changes.start_at or event.start_at, changes.end_at or event.end_at)
    if _conflict(db, current_user.id, start, end, event.id):
        _fail(409, "CALENDAR_CONFLICT")
    content = {"event": _snapshot(event), "changes": changes.model_dump(mode="json", exclude_none=True)}
    return ok({"status": "confirmation_required", "preview": content, "confirmation_token": issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="update_calendar_event", resource_id=str(event.id), payload=content)})


@router.patch("/events/{event_id}")
def update_event(event_id: int, changes: CalendarEventUpdate, db: DBSession, current_user: CurrentUser, settings: AppSettings, confirmation_token: str = Header("", alias="X-Confirmation-Token")) -> dict:
    event = _event_or_404(db, current_user.id, event_id); content = {"event": _snapshot(event), "changes": changes.model_dump(mode="json", exclude_none=True)}
    try: verify_confirmation(confirmation_token, settings.jwt_secret, user_id=current_user.id, action="update_calendar_event", resource_id=str(event.id), payload=content)
    except ValueError: _fail(409, "CALENDAR_EVENT_STALE")
    start, end = _range(changes.start_at or event.start_at, changes.end_at or event.end_at)
    if _conflict(db, current_user.id, start, end, event.id): _fail(409, "CALENDAR_CONFLICT")
    if changes.title is not None: event.title = changes.title
    event.start_at, event.end_at = start, end
    try:
        db.commit(); db.refresh(event)
    except SQLAlchemyError:
        db.rollback()
        _fail(409, "CALENDAR_WRITE_FAILED")
    task = db.get(StudyTask, event.study_task_id) if event.study_task_id else None
    course = db.get(Course, task.course_id) if task else None
    return ok({"event": _event_payload(event, task, course), "idempotent_replay": False})


@router.post("/events/{event_id}/preview-delete")
def preview_delete(event_id: int, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    event = _event_or_404(db, current_user.id, event_id); content = _snapshot(event)
    return ok({"status": "confirmation_required", "preview": content, "confirmation_token": issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="delete_calendar_event", resource_id=str(event.id), payload=content)})


@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: DBSession, current_user: CurrentUser, settings: AppSettings, confirmation_token: str = Header("", alias="X-Confirmation-Token")) -> dict:
    event = _event_or_404(db, current_user.id, event_id); content = _snapshot(event)
    try: verify_confirmation(confirmation_token, settings.jwt_secret, user_id=current_user.id, action="delete_calendar_event", resource_id=str(event.id), payload=content)
    except ValueError: _fail(409, "CALENDAR_EVENT_STALE")
    try:
        db.delete(event); db.commit()
    except SQLAlchemyError:
        db.rollback()
        _fail(409, "CALENDAR_WRITE_FAILED")
    return ok({"id": event_id, "deleted": True})


def _plan_items(db: DBSession, user_id: int, request: CalendarPlanSyncRequest, timezone_name: str) -> tuple[list[dict], str]:
    zone, zone_name = resolve_user_timezone(timezone_name)
    statement = select(StudyTask, Course).join(StudyPlanVersion, StudyPlanVersion.id == StudyTask.plan_version_id).join(StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id).join(Course, Course.id == StudyTask.course_id).where(
        StudyTask.user_id == user_id, StudyTask.status == "todo", StudyTask.scheduled_date >= request.start_date, StudyTask.scheduled_date <= request.end_date,
        Course.owner_id == user_id, Course.archived.is_(False), StudyPlan.user_id == user_id, StudyPlan.status == "active", StudyPlanVersion.status == "active", StudyPlan.active_version == StudyPlanVersion.version,
    )
    if request.course_id is not None:
        _course(db, user_id, request.course_id); statement = statement.where(StudyTask.course_id == request.course_id)
    rows = list(db.execute(statement.order_by(StudyTask.scheduled_date, StudyTask.priority.desc(), StudyTask.course_id, StudyTask.id)))
    if len(rows) > 50: _fail(422, "CALENDAR_PREVIEW_TOO_LARGE")
    cursors: dict[date, datetime] = {}
    items = []
    for task, course in rows:
        local_start = cursors.setdefault(task.scheduled_date, datetime.combine(task.scheduled_date, request.daily_start_time, tzinfo=zone))
        local_end = local_start + timedelta(minutes=task.estimated_minutes)
        for local_value in (local_start, local_end):
            round_trip = local_value.astimezone(timezone.utc).astimezone(zone)
            if round_trip.replace(tzinfo=None) != local_value.replace(tzinfo=None):
                _fail(422, "INVALID_LOCAL_TIME")
        status, reason, conflict_data, existing_id = "ready", None, None, None
        existing = db.scalar(select(CalendarEvent).where(CalendarEvent.user_id == user_id, CalendarEvent.study_task_id == task.id))
        if existing: status, reason, existing_id = "already_synced", "任务已有本地日历事件", existing.id
        elif local_end.date() != task.scheduled_date: status, reason = "outside_day", "任务结束时间跨出本地日期"
        else:
            clash = _conflict(db, user_id, local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc))
            if clash: status, reason, conflict_data = "conflict", "与已有日历事件重叠", {"event_id": clash.id, "title": clash.title, "start_at": as_utc(clash.start_at).isoformat(), "end_at": as_utc(clash.end_at).isoformat()}
        start_utc, end_utc = local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
        items.append({"task_id": task.id, "course_id": course.id, "course_name": course.name, "title": task.title, "task_type": task.task_type, "scheduled_date": task.scheduled_date.isoformat(), "estimated_minutes": task.estimated_minutes, "start_at": start_utc.isoformat(), "end_at": end_utc.isoformat(), "status": status, "reason": reason, "conflict_with": conflict_data, "existing_event_id": existing_id, "idempotency_key": _key(user_id, f"plan-task:{task.id}")})
        cursors[task.scheduled_date] = local_end + timedelta(minutes=request.gap_minutes)
    return items, zone_name


def _same_plan_event(event: CalendarEvent, item: dict, user_id: int) -> bool:
    return (
        event.user_id == user_id
        and event.study_task_id == item["task_id"]
        and event.title == item["title"]
        and as_utc(event.start_at) == datetime.fromisoformat(item["start_at"]).astimezone(timezone.utc)
        and as_utc(event.end_at) == datetime.fromisoformat(item["end_at"]).astimezone(timezone.utc)
        and event.provider == "local"
        and event.sync_status == "local"
        and event.idempotency_key == item["idempotency_key"]
    )


def _replayed_plan_events(
    db: DBSession, user_id: int, expected: list[dict]
) -> list[CalendarEvent] | None:
    events: list[CalendarEvent] = []
    for item in expected:
        event = db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.idempotency_key == item["idempotency_key"]
            )
        )
        if event is None or not _same_plan_event(event, item, user_id):
            return None
        events.append(event)
    return events


@router.post("/plan-sync/preview")
def preview_plan_sync(payload: CalendarPlanSyncRequest, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    items, zone = _plan_items(db, current_user.id, payload, current_user.timezone)
    preview = {"timezone": zone, "scope": payload.model_dump(mode="json"), "items": items}
    for state in ("ready", "conflict", "already_synced", "outside_day"): preview[f"{state}_count"] = sum(item["status"] == state for item in items)
    preview["confirmation_token"] = issue_confirmation(settings.jwt_secret, user_id=current_user.id, action="confirm_calendar_plan_sync", resource_id=f"{payload.start_date}:{payload.end_date}", payload={key: value for key, value in preview.items() if key != "confirmation_token"})
    preview["expires_in_seconds"] = 300
    return ok(preview)


@router.post("/plan-sync/confirm")
def confirm_plan_sync(payload: CalendarPlanSyncConfirm, db: DBSession, current_user: CurrentUser, settings: AppSettings, confirmation_token: str = Header("", alias="X-Confirmation-Token")) -> dict:
    preview = payload.preview; scope = preview.get("scope", {}); start_date = scope.get("start_date"); end_date = scope.get("end_date")
    if not start_date or not end_date: _fail(422, "INVALID_CALENDAR_PREVIEW")
    signed = {key: value for key, value in preview.items() if key not in {"confirmation_token", "expires_in_seconds"}}
    try: verify_confirmation(confirmation_token, settings.jwt_secret, user_id=current_user.id, action="confirm_calendar_plan_sync", resource_id=f"{start_date}:{end_date}", payload=signed)
    except ValueError: _fail(409, "CONFIRMATION_PAYLOAD_MISMATCH")
    request = CalendarPlanSyncRequest.model_validate(scope)
    expected = [item for item in preview.get("items", []) if item.get("status") == "ready"]
    fresh, _ = _plan_items(db, current_user.id, request, current_user.timezone)
    fresh_by_task = {item["task_id"]: item for item in fresh}
    for item in expected:
        current = fresh_by_task.get(item["task_id"])
        if current is None or any(
            current[field] != item[field]
            for field in (
                "course_id",
                "title",
                "task_type",
                "scheduled_date",
                "estimated_minutes",
                "start_at",
                "end_at",
                "idempotency_key",
            )
        ):
            _fail(409, "CALENDAR_PREVIEW_STALE")
        existing_for_task = db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.user_id == current_user.id,
                CalendarEvent.study_task_id == item["task_id"],
            )
        )
        if existing_for_task and not _same_plan_event(
            existing_for_task, item, current_user.id
        ):
            _fail(409, "IDEMPOTENCY_KEY_REUSED")
        clash = _conflict(
            db,
            current_user.id,
            datetime.fromisoformat(item["start_at"]),
            datetime.fromisoformat(item["end_at"]),
            existing_for_task.id if existing_for_task else None,
        )
        if clash:
            _fail(409, "CALENDAR_PREVIEW_STALE")

    if not expected:
        _fail(409, "CALENDAR_PREVIEW_STALE")
    created, replayed, ids = 0, 0, []
    try:
        for item in expected:
            existing = db.scalar(select(CalendarEvent).where(CalendarEvent.idempotency_key == item["idempotency_key"]))
            if existing:
                if not _same_plan_event(existing, item, current_user.id):
                    _fail(409, "IDEMPOTENCY_KEY_REUSED")
                replayed += 1; ids.append(existing.id); continue
            event = CalendarEvent(user_id=current_user.id, study_task_id=item["task_id"], title=item["title"], start_at=datetime.fromisoformat(item["start_at"]), end_at=datetime.fromisoformat(item["end_at"]), provider="local", sync_status="local", idempotency_key=item["idempotency_key"])
            db.add(event); db.flush(); created += 1; ids.append(event.id)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        concurrent = _replayed_plan_events(db, current_user.id, expected)
        if concurrent is None:
            _fail(409, "CALENDAR_SYNC_CONFLICT")
        return ok({
            "created_count": 0,
            "replayed_count": len(concurrent),
            "event_ids": [event.id for event in concurrent],
            "items": expected,
            "idempotent_replay": True,
        })
    except SQLAlchemyError:
        db.rollback()
        _fail(409, "CALENDAR_SYNC_FAILED")
    return ok({"created_count": created, "replayed_count": replayed, "event_ids": ids, "items": expected, "idempotent_replay": bool(replayed and not created)})


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _ics_time(value: datetime) -> str:
    return as_utc(value).strftime("%Y%m%dT%H%M%SZ")


@router.get("/export.ics")
def export_ics(db: DBSession, current_user: CurrentUser, start_at: datetime | None = None, end_at: datetime | None = None, start_date: date | None = None, end_date: date | None = None, course_id: int | None = Query(None, gt=0)) -> Response:
    start_at, end_at = _query_range(start_at=start_at, end_at=end_at, start_date=start_date, end_date=end_date, timezone_name=current_user.timezone)
    rows = db.execute(_event_rows(db, current_user.id, start_at, end_at, course_id).order_by(CalendarEvent.start_at, CalendarEvent.id)).all()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StudyPilot//Learning Calendar//CN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for event, task, course in rows:
        description = "StudyPilot 本地学习日历" + (f"；课程：{course.name}" if course else "") + (f"；任务类型：{task.task_type}" if task else "")
        lines.extend(["BEGIN:VEVENT", f"UID:studypilot-{event.id}@local", f"DTSTAMP:{_ics_time(event.created_at)}", f"DTSTART:{_ics_time(event.start_at)}", f"DTEND:{_ics_time(event.end_at)}", f"SUMMARY:{_ics_escape(event.title)}", f"DESCRIPTION:{_ics_escape(description)}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    filename = f"studypilot-calendar-{start_at.date()}-to-{(end_at - timedelta(microseconds=1)).date()}.ics"
    return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
