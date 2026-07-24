from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import AsyncTask, Document, DocumentChunk, DocumentVersion, utcnow
from backend.app.providers.llm import LLMProvider
from backend.app.services.async_tasks import mark_task_cancelled


class DocumentProcessingCancelled(Exception):
    pass


@dataclass(frozen=True)
class PageExtraction:
    page_number: int
    text: str
    source: str


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[PageExtraction]
    native_page_count: int
    ocr_page_count: int


def _raise_if_cancelled(db: Session, document: Document, version: DocumentVersion, task: AsyncTask) -> None:
    db.refresh(task)
    if not task.cancel_requested:
        return
    has_ready_version = db.scalar(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_no != version.version_no,
            DocumentVersion.status == "ready",
        )
    )
    version.status = "cancelled"
    version.error_message = "CANCELLED_BY_USER"
    if not has_ready_version:
        document.status = "uploaded"
        document.error_message = "CANCELLED_BY_USER"
    mark_task_cancelled(db, task, "cancelled_by_user")
    raise DocumentProcessingCancelled()



def _tesseract_languages(command: str) -> set[str]:
    completed = subprocess.run(
        [command, "--list-langs"],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    }


def _resolve_ocr_language(command: str, requested: str) -> str:
    available = _tesseract_languages(command)
    selected = [language for language in requested.split("+") if language in available]
    if not selected:
        raise RuntimeError("PDF_OCR_LANGUAGE_UNAVAILABLE")
    return "+".join(selected)

def _ocr_pdf_pages(
    path: Path,
    page_numbers: list[int],
    *,
    language: str,
    dpi: int,
) -> dict[int, str]:
    command = shutil.which("tesseract")
    if not command:
        raise RuntimeError("PDF_OCR_ENGINE_UNAVAILABLE")
    selected_language = _resolve_ocr_language(command, language)
    scale = max(1.0, dpi / 72)
    recognized: dict[int, str] = {}
    with fitz.open(path) as pdf, tempfile.TemporaryDirectory(prefix="studypilot-ocr-") as temp_dir:
        for page_number in page_numbers:
            page = pdf.load_page(page_number - 1)
            image_path = Path(temp_dir) / f"page-{page_number}.png"
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(image_path)
            # PSM 3 = fully automatic, better for mixed slides than PSM 6
            completed = subprocess.run(
                [command, str(image_path), "stdout", "-l", selected_language, "--psm", "3"],
                capture_output=True,
                check=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            recognized[page_number] = completed.stdout
    return recognized


def _text_quality_ok(text: str, min_chars: int) -> bool:
    """Check if extracted text has enough meaningful content (not just headers/noise)."""
    stripped = re.sub(r"\s+", "", text)
    if len(stripped) < min_chars:
        return False
    # Detect pages that are mostly garbled/non-text (e.g., >50% non-CJK/non-ASCII)
    cjk_ascii = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9]", stripped))
    return cjk_ascii >= len(stripped) * 0.4


def extract_pages(
    path: Path,
    file_type: str,
    settings: Settings | None = None,
    ocr_runner: Callable[..., dict[int, str]] = _ocr_pdf_pages,
) -> ExtractionResult:
    if file_type == "pdf":
        minimum = settings.pdf_ocr_min_text_chars if settings else 80
        pages: list[PageExtraction] = []

        # ---- Primary: PyMuPDF native extraction (handles PPT-exported PDFs) ----
        with fitz.open(path) as pdf:
            for page_index in range(pdf.page_count):
                page_num = page_index + 1
                text = pdf[page_index].get_text("text") or ""
                pages.append(PageExtraction(page_num, text, "native"))

        # ---- OCR fallback for weak/garbled pages ----
        weak_pages = [p.page_number for p in pages if not _text_quality_ok(p.text, minimum)]
        if weak_pages and (settings is None or settings.pdf_ocr_enabled):
            language = settings.pdf_ocr_language if settings else "chi_sim+eng"
            dpi = settings.pdf_ocr_dpi if settings else 300
            ocr_text = ocr_runner(path, weak_pages, language=language, dpi=dpi)
            pages = [
                PageExtraction(p.page_number, ocr_text.get(p.page_number, p.text), "ocr")
                if p.page_number in weak_pages
                else p
                for p in pages
            ]

        return ExtractionResult(
            pages=pages,
            native_page_count=sum(p.source == "native" for p in pages),
            ocr_page_count=sum(p.source == "ocr" for p in pages),
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    return ExtractionResult(
        pages=[PageExtraction(1, text, "native")],
        native_page_count=1,
        ocr_page_count=0,
    )


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
    settings: Settings | None = None,
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
        _raise_if_cancelled(db, document, version, task)
        task.status = "processing"
        task.progress = 10
        task.current_step = "extracting"
        task.started_at = utcnow()
        version.status = "parsing"
        if target_version == document.current_version:
            document.status = "parsing"
        db.commit()

        extraction = extract_pages(Path(document.file_path), document.file_type, settings)
        pages = extraction.pages
        _raise_if_cancelled(db, document, version, task)
        task.progress = 35
        task.current_step = "chunking"
        version.page_count = len(pages)
        pending: list[tuple[int, str, str | None]] = []
        for page in pages:
            cleaned = clean_text(page.text)
            for chunk in split_text(cleaned):
                pending.append((page.page_number, chunk, chapter_for(chunk)))
        if not pending:
            raise ValueError("DOCUMENT_TEXT_EMPTY")
        _raise_if_cancelled(db, document, version, task)

        version.status = "embedding"
        if target_version == document.current_version:
            document.status = "embedding"
        task.progress = 60
        task.current_step = "embedding"
        db.commit()
        embeddings = await provider.embed([item[1] for item in pending]) if pending else []
        _raise_if_cancelled(db, document, version, task)

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
        _raise_if_cancelled(db, document, version, task)
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
            "page_count": len(pages),
            "chunk_count": len(pending),
            "native_page_count": extraction.native_page_count,
            "ocr_page_count": extraction.ocr_page_count,
            "extraction_mode": (
                "ocr" if extraction.ocr_page_count == len(pages)
                else "hybrid" if extraction.ocr_page_count
                else "native"
            ),
        }
        task.finished_at = utcnow()
        db.commit()
    except DocumentProcessingCancelled:
        return
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
