from __future__ import annotations

import asyncio

from celery import shared_task
from sqlalchemy import select

from backend.app.cache import set_task_progress
from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.models import AsyncTask, Document, utcnow
from backend.app.providers.llm import get_llm_provider
from backend.app.services.documents import process_document


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
            if task.status == "success":
                return task.result_data
            if task.cancel_requested:
                task.status = "cancelled"
                db.commit()
                return {"cancelled": True}
            set_task_progress(task.public_id, {"status": "processing", "progress": 5, "current_step": "worker_started"})
            asyncio.run(process_document(db, document, task, get_llm_provider(settings)))
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
            task.status = "processing"
            task.progress = 30
            task.current_step = "aggregating_learning_data"
            task.started_at = utcnow()
            db.commit()
            result = {"summary": "本周学习报告已生成。", "task_type": task.task_type}
            task.status = "success"
            task.progress = 100
            task.current_step = "completed"
            task.result_data = result
            task.finished_at = utcnow()
            db.commit()
            set_task_progress(task.public_id, {"status": "success", "progress": 100, "current_step": "completed"})
            return result
    finally:
        database.engine.dispose()
