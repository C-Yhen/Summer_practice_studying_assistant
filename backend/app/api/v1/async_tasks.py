from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import AsyncTask, Course, Document, utcnow
from backend.app.responses import ok
from backend.app.schemas import AsyncTaskCreate, WeeklyReportInput
from backend.app.security import decode_access_token
from backend.app.services.async_tasks import (
    DOCUMENT_TASK_TYPES,
    dispatch_async_task,
    mark_task_cancelled,
    task_payload,
)

router = APIRouter(tags=["async-tasks"])
TASK_STATUSES = {"queued", "processing", "cancelling", "success", "failed", "cancelled"}
TASK_TYPES = {"document_parse", "weekly_report", "plan_generation"}


def _owned_task(db: DBSession, task_id: str, user_id: int) -> AsyncTask:
    task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id, AsyncTask.user_id == user_id))
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    return task


def _retryable_resource_exists(db: DBSession, task: AsyncTask, user_id: int) -> bool:
    if task.task_type == "weekly_report":
        if task.resource_type == "user":
            return task.resource_id == str(user_id)
        if task.resource_type == "course":
            return db.scalar(select(Course.id).where(
                Course.id == task.resource_id,
                Course.owner_id == user_id,
                Course.archived.is_(False),
            )) is not None
        return False
    if task.task_type in DOCUMENT_TASK_TYPES:
        try:
            document_id = int(task.resource_id or "")
        except ValueError:
            return False
        return db.scalar(select(Document.id).join(Document.course).where(
            Document.id == document_id,
            Document.is_deleted.is_(False),
            Document.course.has(owner_id=user_id, archived=False),
        )) is not None
    return False


@router.post("/async-tasks", status_code=status.HTTP_201_CREATED)
async def create_async_task(
    payload: AsyncTaskCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings
) -> dict:
    if payload.task_type != "weekly_report":
        raise HTTPException(status_code=400, detail="TASK_TYPE_NOT_IMPLEMENTED")
    try:
        report_input = WeeklyReportInput.model_validate(payload.input_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="WEEKLY_REPORT_INPUT_INVALID") from exc
    resource_type = "user"
    resource_id = str(current_user.id)
    if report_input.course_id is not None:
        course = db.scalar(select(Course).where(
            Course.id == report_input.course_id,
            Course.owner_id == current_user.id,
            Course.archived.is_(False),
        ))
        if course is None:
            raise HTTPException(status_code=404, detail="COURSE_NOT_FOUND")
        resource_type = "course"
        resource_id = str(course.id)
    task = AsyncTask(
        user_id=current_user.id,
        task_type="weekly_report",
        resource_type=resource_type,
        resource_id=resource_id,
        input_data=report_input.model_dump(mode="json"),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    await dispatch_async_task(db, task, settings)
    db.refresh(task)
    return ok(task_payload(task), "created")


@router.get("/async-tasks")
def list_async_tasks(
    db: DBSession,
    current_user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
    task_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    if status_filter is not None and status_filter not in TASK_STATUSES:
        raise HTTPException(status_code=422, detail="TASK_STATUS_INVALID")
    if task_type is not None and task_type not in TASK_TYPES:
        raise HTTPException(status_code=422, detail="TASK_TYPE_INVALID")
    statement = select(AsyncTask).where(AsyncTask.user_id == current_user.id)
    if status_filter is not None:
        statement = statement.where(AsyncTask.status == status_filter)
    if task_type is not None:
        statement = statement.where(AsyncTask.task_type == task_type)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    tasks = list(db.scalars(statement.order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc()).offset(offset).limit(limit)))
    return ok({"items": [task_payload(item) for item in tasks], "total": total})


@router.get("/async-tasks/{task_id}")
def read_async_task(task_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    return ok(task_payload(_owned_task(db, task_id, current_user.id)))


@router.get("/async-tasks/{task_id}/progress")
def task_progress(task_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    task = _owned_task(db, task_id, current_user.id)
    return ok({"progress": task.progress, "message": task.current_step, "updated_at": task.updated_at.isoformat()})


@router.post("/async-tasks/{task_id}/cancel")
def cancel_task(task_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    task = _owned_task(db, task_id, current_user.id)
    if task.status in {"success", "failed", "cancelled", "cancelling"}:
        raise HTTPException(status_code=409, detail="TASK_NOT_CANCELLABLE")
    task.cancel_requested = True
    if task.status == "queued":
        mark_task_cancelled(db, task, "cancelled_before_start")
    else:
        task.status = "cancelling"
        task.current_step = "cancellation_requested"
        db.commit()
    return ok(task_payload(task))


@router.post("/async-tasks/{task_id}/retry")
async def retry_task(task_id: str, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    task = _owned_task(db, task_id, current_user.id)
    if task.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="TASK_NOT_RETRYABLE")
    if task.retry_count >= 3:
        raise HTTPException(status_code=409, detail="MAX_RETRIES_REACHED")
    if not _retryable_resource_exists(db, task, current_user.id):
        raise HTTPException(status_code=404, detail="TASK_RESOURCE_NOT_FOUND")
    task.retry_count += 1
    task.status = "queued"
    task.progress = 0
    task.current_step = "queued_for_retry"
    task.error_message = None
    task.result_data = {}
    task.cancel_requested = False
    task.started_at = None
    task.finished_at = None
    db.commit()
    await dispatch_async_task(db, task, settings)
    db.refresh(task)
    return ok(task_payload(task))


@router.websocket("/ws/async-tasks")
async def async_task_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    task_id = websocket.query_params.get("task_id", "")
    settings = websocket.app.state.settings
    database = websocket.app.state.database
    try:
        user_id = decode_access_token(token, settings.jwt_secret, settings.jwt_algorithm)
    except ValueError:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while True:
            with database.session_factory() as db:
                task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id, AsyncTask.user_id == user_id))
                if task is None:
                    await websocket.send_json({"error": "TASK_NOT_FOUND"})
                    await websocket.close(code=4404)
                    return
                await websocket.send_json(task_payload(task))
                if task.status in {"success", "failed", "cancelled"}:
                    await websocket.close(code=1000)
                    return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
