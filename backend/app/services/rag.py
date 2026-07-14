from __future__ import annotations

import math
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Document, DocumentChunk
from backend.app.providers.llm import LLMProvider, text_terms


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right, strict=True)) / denominator if denominator else 0.0


def lexical_score(query: str, content: str) -> float:
    query_terms = Counter(text_terms(query))
    content_terms = Counter(text_terms(content))
    if not query_terms:
        return 0.0
    overlap = sum(min(count, content_terms.get(term, 0)) for term, count in query_terms.items())
    return overlap / sum(query_terms.values())


async def retrieve(
    db: Session,
    provider: LLMProvider,
    *,
    course_id: int,
    query: str,
    document_ids: list[int] | None,
    top_k: int,
) -> list[dict[str, Any]]:
    statement = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.course_id == course_id,
            DocumentChunk.is_active.is_(True),
            Document.is_deleted.is_(False),
            Document.status == "ready",
            DocumentChunk.document_version == Document.current_version,
        )
    )
    if document_ids:
        statement = statement.where(Document.id.in_(document_ids))
    query_embedding = (await provider.embed([query]))[0]
    scored: list[dict[str, Any]] = []
    for chunk, document in db.execute(statement):
        lexical = lexical_score(query, chunk.content)
        semantic = max(0.0, cosine(query_embedding, chunk.embedding))
        score = 0.65 * lexical + 0.35 * semantic
        scored.append(
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_name": document.title,
                "document_version": chunk.document_version,
                "page_number": chunk.page_number,
                "chapter_name": chunk.chapter_name,
                "quote": chunk.content[:800],
                "score": round(score, 6),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


async def answer_from_sources(
    provider: LLMProvider,
    question: str,
    sources: list[dict[str, Any]],
    mode: str,
) -> tuple[str, bool]:
    sufficient = bool(sources and sources[0]["score"] >= 0.08)
    if not sufficient:
        return "当前课程资料中没有找到足够证据，无法可靠回答这个问题。", False
    context = "\n\n".join(
        f"[S{index}] {source['document_name']} 第{source['page_number'] or '?'}页：{source['quote']}"
        for index, source in enumerate(sources, 1)
    )
    if mode == "strict":
        # The deterministic form makes the no-key MVP auditable and citation-safe.
        return f"根据课程资料，相关内容如下：\n\n{sources[0]['quote']}\n\n依据：[S1]", True
    prompt = (
        f"回答模式：{mode}。只能使用以下资料回答，并在结论后标注 [S编号]。\n"
        f"问题：{question}\n资料：\n{context}"
    )
    return await provider.chat([{"role": "user", "content": prompt}]), True
