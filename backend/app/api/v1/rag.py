from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import ChatMessage, ChatSession, Document
from backend.app.providers.llm import get_llm_provider
from backend.app.responses import ok
from backend.app.schemas import ChatAsk, ChatSessionCreate, RagSearch
from backend.app.services.rag import answer_from_sources, retrieve

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


def _validate_documents(
    db: DBSession, course_id: int, document_ids: list[int]
) -> None:
    if not document_ids:
        return
    count = len(
        list(
            db.scalars(
                select(Document.id).where(
                    Document.course_id == course_id,
                    Document.id.in_(document_ids),
                    Document.is_deleted.is_(False),
                )
            )
        )
    )
    if count != len(set(document_ids)):
        raise HTTPException(status_code=400, detail="DOCUMENT_SCOPE_INVALID")


@router.post("/courses/{course_id}/chat-sessions", status_code=status.HTTP_201_CREATED)
def create_chat_session(
    course_id: int,
    payload: ChatSessionCreate,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    _owned_course(db, course_id, current_user.id)
    _validate_documents(db, course_id, payload.document_ids)
    session = ChatSession(
        user_id=current_user.id,
        course_id=course_id,
        title=payload.title,
        mode=payload.mode,
        document_ids=payload.document_ids,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return ok({"session_id": session.public_id, "mode": session.mode})


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
    _validate_documents(db, session.course_id, document_ids)
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
    db.commit()
    db.refresh(assistant)
    return ok({
        "message_id": assistant.public_id,
        "answer": answer,
        "sufficient_evidence": sufficient,
        "citations": citations,
        "cached": False,
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
    return ok({"items": [{"id": item.public_id, "role": item.role, "content": item.content, "citations": item.citations, "created_at": item.created_at.isoformat()} for item in messages], "next_cursor": None})


@router.get("/chat-messages/{message_id}/citations")
def read_citations(message_id: str, db: DBSession, current_user: CurrentUser) -> dict:
    message = db.scalar(
        select(ChatMessage)
        .join(ChatSession)
        .where(ChatMessage.public_id == message_id, ChatSession.user_id == current_user.id)
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
    _validate_documents(db, payload.course_id, payload.document_ids)
    sources = await retrieve(
        db,
        get_llm_provider(settings),
        course_id=payload.course_id,
        query=payload.query,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
    )
    return ok({"items": sources, "sufficient_evidence": bool(sources and sources[0]["score"] >= 0.08)})
