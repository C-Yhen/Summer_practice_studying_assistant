from __future__ import annotations

import asyncio

from celery import shared_task
from sqlalchemy import select

from backend.app.cache import set_task_progress
from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.models import AsyncTask, Document
from backend.app.providers.llm import get_llm_provider
from backend.app.services.async_tasks import mark_dispatch_failed, mark_task_cancelled
from backend.app.services.documents import process_document
from backend.app.services.reports import generate_weekly_report


@shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, max_retries=3)
def process_document_job(self, document_id: int, task_public_id: str) -> dict:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session_factory() as db:
            document = db.get(Document, document_id)
            task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_public_id))
            if document is None or task is None:
                raise ValueError("document or task no longer exists")
            if task.status in {"success", "failed", "cancelled"}:
                return task.result_data
            if task.cancel_requested:
                mark_task_cancelled(db, task, "cancelled_before_start")
                return {"cancelled": True}
            asyncio.run(process_document(db, document, task, get_llm_provider(settings), settings))
            db.refresh(task)
            set_task_progress(task.public_id, {"status": task.status, "progress": task.progress, "current_step": task.current_step})
            return task.result_data
    finally:
        database.engine.dispose()


@shared_task(bind=True, max_retries=2)
def generate_weekly_report_job(self, task_public_id: str) -> dict:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session_factory() as db:
            task = db.scalar(select(AsyncTask).where(AsyncTask.public_id == task_public_id))
            if task is None:
                raise ValueError("task no longer exists")
            if task.status in {"success", "failed", "cancelled"}:
                return task.result_data
            if task.cancel_requested:
                mark_task_cancelled(db, task, "cancelled_before_start")
                return {"cancelled": True}
            try:
                result = generate_weekly_report(db, task)
            except Exception:
                mark_dispatch_failed(db, task, "WEEKLY_REPORT_FAILED")
                return {"failed": True}
            db.refresh(task)
            set_task_progress(task.public_id, {"status": task.status, "progress": task.progress, "current_step": task.current_step})
            return result
    finally:
        database.engine.dispose()
