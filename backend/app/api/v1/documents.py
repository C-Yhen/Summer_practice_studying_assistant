from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from backend.app.api.v1.courses import _owned_course
from backend.app.api.v1.async_tasks import task_payload
from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import AsyncTask, Document, DocumentVersion
from backend.app.providers.llm import get_llm_provider
from backend.app.responses import ok
from backend.app.schemas import DocumentRead
from backend.app.services.confirmation import issue_confirmation, verify_confirmation
from backend.app.services.documents import process_document

router = APIRouter(tags=["documents"])
ALLOWED_TYPES = {"pdf", "txt", "md", "markdown"}
DOCUMENT_TASK_TYPES = {"document_parse", "document_process"}


def _owned_document(db: DBSession, document_id: int, owner_id: int) -> Document:
    document = db.scalar(
        select(Document)
        .join(Document.course)
        .where(
            Document.id == document_id,
            Document.course.has(owner_id=owner_id, archived=False),
        )
    )
    if document is None or document.is_deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _owned_document_task(
    db: DBSession, document_id: int, task_id: str, owner_id: int
) -> AsyncTask:
    """Return a document processing task only when it belongs to this document.

    The endpoint deliberately uses one 404 response for every failed link in the
    document -> task chain, so a caller cannot use it to discover another
    document's task identifiers.
    """
    try:
        document = _owned_document(db, document_id, owner_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status_code=404, detail="TASK_NOT_FOUND") from exc
        raise

    task = db.scalar(
        select(AsyncTask).where(
            AsyncTask.public_id == task_id,
            AsyncTask.user_id == owner_id,
            AsyncTask.resource_type == "document",
            AsyncTask.resource_id == str(document.id),
            AsyncTask.task_type.in_(DOCUMENT_TASK_TYPES),
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    return task


@router.post("/courses/{course_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    course_id: int,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
    file: UploadFile = File(...),
    title: Annotated[str | None, Form(max_length=255)] = None,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    filename = Path((file.filename or "document").replace("\\", "/")).name or "document"
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="FILE_TYPE_UNSUPPORTED")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
    if not content:
        raise HTTPException(status_code=422, detail="FILE_EMPTY")
    resolved_title = (title or filename).strip() or filename
    if len(resolved_title) > 255:
        raise HTTPException(status_code=422, detail="DOCUMENT_TITLE_TOO_LONG")
    directory = settings.upload_dir / str(course_id)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid.uuid4().hex}.{extension}"
    document = Document(
        course_id=course_id,
        title=resolved_title,
        file_type="md" if extension == "markdown" else extension,
        file_path=str(target.resolve()),
        status="uploaded",
    )
    try:
        target.write_bytes(content)
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_no=1,
            file_path=document.file_path,
            status="uploaded",
        )
        db.add(version)
        task = AsyncTask(
            user_id=current_user.id,
            task_type="document_parse",
            resource_type="document",
            resource_id=str(document.id),
            input_data={"document_id": document.id, "version": document.current_version},
        )
        db.add(task)
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    db.refresh(document)
    db.refresh(task)
    if settings.sync_document_processing or db.bind.dialect.name == "sqlite":
        try:
            await process_document(db, document, task, get_llm_provider(settings))
        except Exception:
            # process_document persists a consistent failed document/version/task state.
            db.refresh(document)
            db.refresh(task)
    else:
        from backend.app.tasks.jobs import process_document_job

        try:
            process_document_job.delay(document.id, task.public_id)
        except Exception as exc:
            document.status = "failed"
            document.error_message = f"TASK_DISPATCH_FAILED: {exc}"
            version.status = "failed"
            version.error_message = document.error_message
            task.status = "failed"
            task.current_step = "dispatch_failed"
            task.error_message = document.error_message
            db.commit()
            db.refresh(document)
            db.refresh(task)
    return ok({
        "document": DocumentRead.model_validate(document).model_dump(mode="json"),
        "async_task_id": task.public_id,
    }, "uploaded")


@router.get("/courses/{course_id}/documents")
def list_documents(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id, Document.is_deleted.is_(False))
            .order_by(Document.created_at.desc())
        )
    )
    items = [DocumentRead.model_validate(item).model_dump(mode="json") for item in documents]
    return ok({"items": items, "total": len(items)})


@router.get("/documents/{document_id}")
def read_document(document_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    document = _owned_document(db, document_id, current_user.id)
    return ok(DocumentRead.model_validate(document).model_dump(mode="json"))


@router.post("/documents/{document_id}/reparse")
async def reparse_document(
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> dict:
    document = _owned_document(db, document_id, current_user.id)
    target_version = document.current_version + 1
    db.add(
        DocumentVersion(
            document_id=document.id,
            version_no=target_version,
            file_path=document.file_path,
            status="uploaded",
        )
    )
    task = AsyncTask(
        user_id=current_user.id,
        task_type="document_parse",
        resource_type="document",
        resource_id=str(document.id),
        input_data={"document_id": document.id, "version": target_version},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if settings.sync_document_processing or db.bind.dialect.name == "sqlite":
        await process_document(db, document, task, get_llm_provider(settings))
    else:
        from backend.app.tasks.jobs import process_document_job

        process_document_job.delay(document.id, task.public_id)
    return ok({"document_id": document.id, "version": target_version, "async_task_id": task.public_id})


@router.get("/documents/{document_id}/versions")
def list_document_versions(
    document_id: int, db: DBSession, current_user: CurrentUser
) -> dict:
    document = _owned_document(db, document_id, current_user.id)
    versions = list(
        db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_no.desc())
        )
    )
    return ok({
        "items": [
            {
                "version": item.version_no,
                "status": item.status,
                "page_count": item.page_count,
                "chunk_count": item.chunk_count,
                "error_message": item.error_message,
                "is_current": item.version_no == document.current_version,
                "created_at": item.created_at.isoformat(),
            }
            for item in versions
        ],
        "total": len(versions),
    })


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
    preview_only: bool = Query(True),
    confirmation_token: str = Header("", alias="X-Confirmation-Token"),
) -> dict:
    document = _owned_document(db, document_id, current_user.id)
    if preview_only:
        token = issue_confirmation(
            settings.jwt_secret,
            user_id=current_user.id,
            action="delete_document",
            resource_id=str(document.id),
        )
        return ok({"status": "confirmation_required", "preview": {"document_id": document.id, "title": document.title}, "confirmation_token": token})
    try:
        verify_confirmation(
            confirmation_token,
            settings.jwt_secret,
            user_id=current_user.id,
            action="delete_document",
            resource_id=str(document.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    document.is_deleted = True
    document.status = "deleted"
    db.commit()
    return ok({"document_id": document.id, "status": "deleted"})


@router.get("/documents/{document_id}/tasks/latest")
def latest_document_task(document_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    document = _owned_document(db, document_id, current_user.id)
    task = db.scalar(
        select(AsyncTask)
        .where(
            AsyncTask.user_id == current_user.id,
            AsyncTask.resource_type == "document",
            AsyncTask.resource_id == str(document.id),
        )
        .order_by(AsyncTask.created_at.desc())
    )
    if task is None:
        raise HTTPException(status_code=404, detail="TASK_NOT_FOUND")
    return ok({"task_id": task.public_id, "status": task.status, "progress": task.progress, "current_step": task.current_step})


@router.get("/documents/{document_id}/tasks/{task_id}")
def read_document_task(
    document_id: int, task_id: str, db: DBSession, current_user: CurrentUser
) -> dict:
    return ok(task_payload(_owned_document_task(db, document_id, task_id, current_user.id)))
