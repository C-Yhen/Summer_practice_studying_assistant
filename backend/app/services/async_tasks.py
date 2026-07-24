from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import AsyncTask, utcnow

ACTIVE_TASK_STATUSES = {"queued", "processing", "cancelling"}
TERMINAL_TASK_STATUSES = {"success", "failed", "cancelled"}
DOCUMENT_TASK_TYPES = {"document_parse", "document_process"}


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def task_payload(task: AsyncTask) -> dict[str, Any]:
    """One safe, persistent representation for task list/detail/socket APIs."""
    return {
        "task_id": task.public_id,
        "task_type": task.task_type,
        "resource_type": task.resource_type,
        "resource_id": task.resource_id,
        "status": task.status,
        "progress": task.progress,
        "current_step": task.current_step,
        "input_data": task.input_data or {},
        "result_data": task.result_data or None,
        "error_message": task.error_message,
        "retry_count": task.retry_count,
        "cancel_requested": task.cancel_requested,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "started_at": iso_or_none(task.started_at),
        "finished_at": iso_or_none(task.finished_at),
        "can_cancel": task.status in {"queued", "processing"} and not task.cancel_requested,
        "can_retry": task.status in {"failed", "cancelled"} and task.retry_count < 3,
    }


def mark_task_cancelled(db: Session, task: AsyncTask, step: str) -> None:
    task.status = "cancelled"
    task.progress = min(task.progress, 99)
    task.current_step = step
    task.cancel_requested = True
    task.finished_at = utcnow()
    db.commit()


def mark_dispatch_failed(db: Session, task: AsyncTask, reason: str = "TASK_DISPATCH_FAILED") -> None:
    task.status = "failed"
    task.current_step = "dispatch_failed"
    task.error_message = reason[:240]
    task.finished_at = utcnow()
    db.commit()


async def dispatch_async_task(db: Session, task: AsyncTask, settings: Any) -> None:
    """Dispatch a supported task, or execute its same service synchronously in tests.

    Database state is authoritative. A broker failure is terminally persisted instead
    of leaving an unusable queued task behind.
    """
    if task.task_type == "document_parse":
        try:
            document_id = int(task.resource_id or "")
        except ValueError:
            mark_dispatch_failed(db, task, "TASK_RESOURCE_INVALID")
            return
        if settings.sync_document_processing:
            from backend.app.models import Document
            from backend.app.providers.llm import get_llm_provider
            from backend.app.services.documents import process_document

            document = db.get(Document, document_id)
            if document is None:
                mark_dispatch_failed(db, task, "TASK_RESOURCE_NOT_FOUND")
                return
            try:
                await process_document(db, document, task, get_llm_provider(settings), settings)
            except Exception:
                # process_document records the safe failed/cancelled state itself.
                return
            return
        try:
            from backend.app.tasks.jobs import process_document_job

            process_document_job.delay(document_id, task.public_id)
        except Exception:
            mark_dispatch_failed(db, task)
        return

    if task.task_type == "weekly_report":
        if settings.sync_document_processing:
            from backend.app.services.reports import generate_weekly_report

            try:
                generate_weekly_report(db, task)
            except Exception:
                mark_dispatch_failed(db, task, "WEEKLY_REPORT_FAILED")
            return
        try:
            from backend.app.tasks.jobs import generate_weekly_report_job

            generate_weekly_report_job.delay(task.public_id)
        except Exception:
            mark_dispatch_failed(db, task)
        return

    mark_dispatch_failed(db, task, "TASK_TYPE_NOT_IMPLEMENTED")
