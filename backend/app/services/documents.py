from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.models import AsyncTask, Document, DocumentChunk, DocumentVersion, utcnow
from backend.app.providers.llm import LLMProvider


def extract_pages(path: Path, file_type: str) -> list[tuple[int, str]]:
    if file_type == "pdf":
        reader = PdfReader(str(path))
        return [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    text = path.read_text(encoding="utf-8", errors="replace")
    return [(1, text)]


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def chapter_for(text: str) -> str | None:
    for line in text.splitlines():
        candidate = line.strip().lstrip("#").strip()
        if 1 < len(candidate) <= 80:
            return candidate
    return None


async def process_document(
    db: Session,
    document: Document,
    task: AsyncTask,
    provider: LLMProvider,
) -> None:
    target_version = int(task.input_data.get("version", document.current_version))
    version = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_no == target_version,
        )
    )
    if version is None:
        version = DocumentVersion(
            document_id=document.id,
            version_no=target_version,
            file_path=document.file_path,
        )
        db.add(version)
        db.flush()
    try:
        task.status = "processing"
        task.progress = 10
        task.current_step = "extracting"
        task.started_at = utcnow()
        version.status = "parsing"
        if target_version == document.current_version:
            document.status = "parsing"
        db.commit()

        pages = extract_pages(Path(document.file_path), document.file_type)
        task.progress = 35
        task.current_step = "chunking"
        version.page_count = len(pages)
        pending: list[tuple[int, str, str | None]] = []
        for page_number, raw in pages:
            cleaned = clean_text(raw)
            for chunk in split_text(cleaned):
                pending.append((page_number, chunk, chapter_for(chunk)))

        version.status = "embedding"
        if target_version == document.current_version:
            document.status = "embedding"
        task.progress = 60
        task.current_step = "embedding"
        db.commit()
        embeddings = await provider.embed([item[1] for item in pending]) if pending else []

        for index, ((page_number, content, chapter), embedding) in enumerate(
            zip(pending, embeddings, strict=True)
        ):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    course_id=document.course_id,
                    document_version=target_version,
                    chunk_index=index,
                    content=content,
                    page_number=page_number,
                    chapter_name=chapter,
                    token_count=len(content),
                    embedding=embedding,
                    is_active=True,
                )
            )
        db.execute(
            update(DocumentChunk)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.document_version != target_version,
            )
            .values(is_active=False)
        )
        document.current_version = target_version
        document.page_count = len(pages)
        document.status = "ready"
        document.error_message = None
        version.status = "ready"
        version.chunk_count = len(pending)
        version.error_message = None
        task.status = "success"
        task.progress = 100
        task.current_step = "completed"
        task.result_data = {
            "document_id": document.id,
            "version": target_version,
            "chunk_count": len(pending),
        }
        task.finished_at = utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        managed_document = db.get(Document, document.id)
        managed_task = db.get(AsyncTask, task.id)
        managed_version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_no == target_version,
            )
        )
        if managed_document:
            has_ready_version = db.scalar(
                select(DocumentVersion.id).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_no == managed_document.current_version,
                    DocumentVersion.status == "ready",
                )
            )
            managed_document.status = "ready" if has_ready_version else "failed"
            managed_document.error_message = str(exc)
        if managed_version:
            managed_version.status = "failed"
            managed_version.error_message = str(exc)
        if managed_task:
            managed_task.status = "failed"
            managed_task.error_message = str(exc)
            managed_task.finished_at = utcnow()
        db.commit()
        raise
