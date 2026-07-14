from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import AsyncTask
from backend.app.responses import ok
from backend.app.schemas import AsyncTaskCreate
from backend.app.security import decode_access_token

router = APIRouter(tags=["async-tasks"])


def task_payload(task: AsyncTask) -> dict:
    return {
        "task_id": task.public_id,
        "task_type": task.task_type,
        "status": task.status,
        "progress": task.progress,
        "current_step": task.current_step,
        "result_data": task.result_data,
        "error_message": task.error_message,
        "retry_count": task.retry_count,
        "cancel_requested": task.cancel_requested,
        "created_at": task.created_at.isoformat(),
    }


def _owned_task(db: DBSession, task_id: str, user_id: int) -> AsyncTask:
    task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_id, AsyncTask.user_id == user_id))
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    return task


@router.post("/async-tasks")
def create_async_task(payload: AsyncTaskCreate, db: DBSession, current_user: CurrentUser, settings: AppSettings) -> dict:
    allowed = {"weekly_report", "stage_report", "batch_questions", "calendar_sync"}
    if payload.task_type not in allowed:
        raise HTTPException(status_code=400, detail="TASK_TYPE_NOT_ALLOWED")
    task = AsyncTask(user_id=current_user.id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    if settings.sync_document_processing:
        task.status = "success"
        task.progress = 100
        task.current_step = "completed"
        task.result_data = {"message": f"{task.task_type} 已在本地演示模式完成"}
        db.commit()
    else:
        from backend.app.tasks.jobs import generate_weekly_report_job

        generate_weekly_report_job.delay(task.public_id)
    return ok(task_payload(task))


@router.get("/async-tasks")
def list_async_tasks(db: DBSession, current_user: CurrentUser) -> dict:
    tasks = list(db.scalars(select(AsyncTask).where(AsyncTask.user_id == current_user.id).order_by(AsyncTask.created_at.desc()).limit(100)))
    return ok({"items": [task_payload(item) for item in tasks], "total": len(tasks)})


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
    if task.status in {"success", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="TASK_NOT_CANCELLABLE")
    task.cancel_requested = True
    task.status = "cancelled"
    task.current_step = "cancelled_by_user"
    db.commit()
    return ok(task_payload(task))


@router.post("/async-tasks/{task_id}/retry")
def retry_task(task_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    task = _owned_task(db, task_id, current_user.id)
    if task.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="TASK_NOT_RETRYABLE")
    if task.retry_count >= 3:
        raise HTTPException(status_code=409, detail="MAX_RETRIES_REACHED")
    task.retry_count += 1
    task.status = "queued"
    task.progress = 0
    task.current_step = "queued_for_retry"
    task.error_message = None
    task.cancel_requested = False
    db.commit()
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
