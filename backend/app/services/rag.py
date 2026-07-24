from __future__ import annotations

import math
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Document, DocumentChunk
from backend.app.providers.llm import LLMProvider, text_terms


class RagProviderError(RuntimeError):
    """A provider failed or returned an unusable response."""


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
    rows = list(db.execute(statement))
    if not rows:
        return []
    try:
        embeddings = await provider.embed([query])
        if len(embeddings) != 1 or not embeddings[0]:
            raise ValueError("invalid embedding response")
        query_embedding = embeddings[0]
    except Exception as exc:
        raise RagProviderError("embedding provider unavailable") from exc
    scored: list[dict[str, Any]] = []
    for chunk, document in rows:
        lexical = lexical_score(query, chunk.content)
        semantic = max(0.0, cosine(query_embedding, chunk.embedding))
        score = 0.3 * lexical + 0.7 * semantic
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


import re
from collections import Counter


def _text_readability(text: str) -> float:
    """Return 0-1 score: 1=clean text, 0=garbled. Checks CJK/ASCII ratio and repetition."""
    stripped = re.sub(r"\s+", "", text)
    if len(stripped) < 20:
        return 0.0
    cjk_ascii = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9]", stripped))
    ratio = cjk_ascii / len(stripped) if stripped else 0
    # Penalize high repetition (garbled OCR often repeats chars)
    chars = list(stripped)
    unique_ratio = len(set(chars)) / len(chars) if chars else 1
    return round(ratio * 0.7 + unique_ratio * 0.3, 3)


async def answer_from_sources(
    provider: LLMProvider,
    question: str,
    sources: list[dict[str, Any]],
    mode: str,
) -> tuple[str, bool]:
    sufficient = bool(sources and sources[0]["score"] >= 0.025)

    # Even if score passes, check text quality — garbled OCR should be ignored
    if sufficient and sources:
        top_text = sources[0].get("quote", "")
        readability = _text_readability(top_text)
        if readability < 0.35:
            sufficient = False  # Treat garbled text as no evidence

    if sufficient:
        context = "\n\n".join(
            f"[S{index}] {source['document_name']} 第{source['page_number'] or '?'}页：{source['quote']}"
            for index, source in enumerate(sources, 1)
        )
        mode_instructions = {
            "strict": "严格依据资料作答。资料没有明确支持的内容不要推测。",
            "exam": "按考试答题风格组织答案，先给结论，再列关键得分点。",
            "teacher": "像教师一样循序解释概念，并指出容易混淆的地方。",
            "basic": "简洁、直接地回答问题。",
        }
        instruction = mode_instructions.get(mode, mode_instructions["basic"])
        system_prompt = (
            "你是 StudyPilot 的课程资料助手。课程资料可能包含 OCR 识别错误"
            "（如错别字、乱码公式、错误术语），你必须根据上下文和专业知识修正这些错误。"
            "数学公式必须使用 LaTeX 格式：行内公式用 $...$，独立公式用 $$...$$。"
            "严格依据资料的知识内容回答，每个关键结论标注对应的 [S编号]。"
            "输出格式：纯文本段落，禁止 Markdown 符号，用中文序号组织。"
        )
        user_prompt = f"回答要求：{instruction}\n问题：{question}\n\n课程资料：\n{context}"
    else:
        # No course evidence — fall back to general knowledge with disclaimer
        system_prompt = (
            "你是 StudyPilot 的学习助手。当前课程资料的文本识别质量较差或没有相关内容，"
            "请基于你的通用知识库（训练数据中包含的教材、百科、论文等公开资料）帮助学生理解。"
            "请在回答开头注明「📌 以下回答基于 AI 知识库，未使用课程资料」，"
            "然后给出清晰、有教育意义的解释。"
            "输出格式：纯文本段落，禁止 Markdown 符号，用中文序号组织要点。"
        )
        user_prompt = f"问题：{question}"
        context = ""

    try:
        answer = await provider.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3 if sufficient else 0.6,
            max_tokens=1200,
        )
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("invalid chat response")
        return answer, sufficient
    except Exception as exc:
        raise RagProviderError("chat provider unavailable") from exc
