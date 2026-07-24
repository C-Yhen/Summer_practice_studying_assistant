from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import ChatMessage, ChatSession, Document, utcnow
from backend.app.providers.llm import get_llm_provider
from backend.app.responses import ok
from backend.app.schemas import (
    ChatAsk,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
    RagSearch,
)
from backend.app.services.rag import RagProviderError, answer_from_sources, retrieve

router = APIRouter(tags=["rag"])


def _owned_session(db: DBSession, public_id: str, user_id: int) -> ChatSession:
    session = db.scalar(
        select(ChatSession).where(
            ChatSession.public_id == public_id,
            ChatSession.user_id == user_id,
            ChatSession.is_deleted.is_(False),
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="SESSION_NOT_FOUND")
    return session


def _validated_document_ids(
    db: DBSession, course_id: int, document_ids: list[int]
) -> list[int]:
    if not document_ids:
        return []
    unique_ids = list(dict.fromkeys(document_ids))
    documents = list(
        db.scalars(
            select(Document).where(
                Document.course_id == course_id,
                Document.id.in_(unique_ids),
                Document.is_deleted.is_(False),
            )
        )
    )
    if len(documents) != len(unique_ids):
        raise HTTPException(status_code=400, detail="DOCUMENT_SCOPE_INVALID")
    if any(document.status != "ready" for document in documents):
        raise HTTPException(status_code=409, detail="DOCUMENT_NOT_READY")
    return unique_ids


def _session_payload(session: ChatSession) -> dict:
    return ChatSessionRead(
        session_id=session.public_id,
        course_id=session.course_id,
        title=session.title,
        mode=session.mode,
        document_ids=session.document_ids,
        created_at=session.created_at,
        updated_at=session.updated_at,
    ).model_dump(mode="json")


@router.post("/courses/{course_id}/chat-sessions", status_code=status.HTTP_201_CREATED)
def create_chat_session(
    course_id: int,
    payload: ChatSessionCreate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    document_ids = _validated_document_ids(db, course_id, payload.document_ids)
    session = ChatSession(
        user_id=current_user.id,
        course_id=course_id,
        title=payload.title,
        mode=payload.mode,
        document_ids=document_ids,
    )
    db.add(session)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="CHAT_SESSION_CREATE_FAILED") from None
    db.refresh(session)
    return ok(_session_payload(session), "created")


@router.get("/courses/{course_id}/chat-sessions")
def list_chat_sessions(
    course_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    sessions = list(
        db.scalars(
            select(ChatSession)
            .where(
                ChatSession.course_id == course_id,
                ChatSession.user_id == current_user.id,
                ChatSession.is_deleted.is_(False),
            )
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        )
    )
    return ok({"items": [_session_payload(item) for item in sessions], "total": len(sessions)})


@router.post("/chat-sessions/{session_id}/messages")
async def ask_question(
    session_id: str,
    payload: ChatAsk,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> dict:
    session = _owned_session(db, session_id, current_user.id)
    document_ids = payload.document_ids or session.document_ids
    document_ids = _validated_document_ids(db, session.course_id, document_ids)
    try:
        provider = get_llm_provider(settings)
        sources = await retrieve(
            db,
            provider,
            course_id=session.course_id,
            query=payload.question,
            document_ids=document_ids,
            top_k=payload.top_k,
        )
        mode = payload.mode or session.mode
        answer, sufficient = await answer_from_sources(provider, payload.question, sources, mode)
    except (RagProviderError, ValueError):
        db.rollback()
        raise HTTPException(status_code=503, detail="RAG_PROVIDER_UNAVAILABLE") from None
    citations = [{"source_id": f"S{index}", **source} for index, source in enumerate(sources, 1)] if sufficient else []
    db.add(ChatMessage(session_id=session.id, role="user", content=payload.question))
    assistant = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        sufficient_evidence=sufficient,
        citations=citations,
    )
    db.add(assistant)
    if session.title == "新对话":
        session.title = payload.question[:50]
    session.updated_at = utcnow()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="CHAT_PERSISTENCE_FAILED") from None
    db.refresh(assistant)
    return ok({
        "message_id": assistant.public_id,
        "answer": answer,
        "sufficient_evidence": sufficient,
        "citations": citations,
    })


@router.get("/chat-sessions/{session_id}/messages")
def list_messages(session_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    session = _owned_session(db, session_id, current_user.id)
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
    )
    items = [
        ChatMessageRead(
            id=item.public_id,
            role=item.role,
            content=item.content,
            citations=item.citations or [],
            sufficient_evidence=item.sufficient_evidence,
            created_at=item.created_at,
        ).model_dump(mode="json")
        for item in messages
    ]
    return ok({"items": items, "next_cursor": None})


@router.get("/chat-messages/{message_id}/citations")
def read_citations(message_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    message = db.scalar(
        select(ChatMessage)
        .join(ChatSession)
        .where(
            ChatMessage.public_id == message_id,
            ChatSession.user_id == current_user.id,
            ChatSession.is_deleted.is_(False),
        )
    )
    if message is None:
        raise HTTPException(status_code=404, detail="MESSAGE_NOT_FOUND")
    return ok({"items": message.citations})


@router.post("/rag/search")
async def search_material(
    payload: RagSearch,
    db: DBSession,
    current_user: CurrentUser,
    settings: AppSettings,
) -> dict:
    _owned_course(db, payload.course_id, current_user.id)
    document_ids = _validated_document_ids(db, payload.course_id, payload.document_ids)
    try:
        sources = await retrieve(
            db,
            get_llm_provider(settings),
            course_id=payload.course_id,
            query=payload.query,
            document_ids=document_ids,
            top_k=payload.top_k,
        )
    except (RagProviderError, ValueError):
        raise HTTPException(status_code=503, detail="RAG_PROVIDER_UNAVAILABLE") from None
    return ok({"items": sources, "sufficient_evidence": bool(sources and sources[0]["score"] >= 0.08)})
