"""AI-powered knowledge point extraction and study plan generation."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import Document, DocumentChunk
from backend.app.providers.llm import LLMProvider, ModelResponseTruncatedError
from backend.app.services.course_content import normalise_content_text
from backend.app.services.rag import retrieve

KNOWLEDGE_POINT_EXTRACTION_PROMPT = """请从以下课程资料中提取 6 到 15 个具体、可学习的知识点。

要求：
1. 只允许使用下方资料中出现的具体术语，禁止“核心概念、重点原理、综合应用”等空泛名称。
2. source_id 必须原样使用资料前的 S 编号。
3. description 用一句具体中文说明该知识点学什么，并且必须与 source_id 对应资料直接相关。
4. 不要返回 document_id、page_number、chunk_id、数据库主键或 source_quote；来源原文由服务端确定。
5. 只返回一个 JSON 对象，不要解释、注释或 Markdown。

返回格式：
{{
  "knowledge_points": [
    {{
      "name": "知识点名称",
      "description": "一句具体说明",
      "source_id": "S1"
    }}
  ]
}}

课程资料：
{context}"""


class KnowledgePointExtractionError(RuntimeError):
    """Stable failure category persisted by the course-preparation task."""

    def __init__(self, failure_type: str, message: str = "") -> None:
        self.failure_type = failure_type
        super().__init__(message or failure_type)


class ExtractedKnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=4, max_length=600)
    source_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    quote_hint: str | None = Field(default=None, min_length=2, max_length=160)


class KnowledgePointExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_points: list[ExtractedKnowledgePoint] = Field(min_length=6, max_length=15)

    @model_validator(mode="after")
    def require_unique_concrete_names(self) -> "KnowledgePointExtractionPayload":
        names = [item.name.strip() for item in self.knowledge_points]
        if len(set(names)) != len(names):
            raise ValueError("knowledge point names must be unique")
        if any(name in {"核心概念", "重点原理", "综合应用"} for name in names):
            raise ValueError("placeholder knowledge point name")
        return self


PLAN_GENERATION_PROMPT = """你是一位学习规划专家。请根据以下信息，生成一份个性化学习计划。

用户信息：
- 学习目标：{goal}
- 日期范围：{start_date} 至 {end_date}（共 {total_days} 天，{available_days} 天可学习）
- 每日可用时间：{daily_minutes} 分钟
- 每次学习时长：{session_minutes} 分钟
- 基础水平：{foundation_level}
- 学习顺序偏好：{learning_order}
- 难度偏好：{preferred_difficulty}
- 需要考试重点：{needs_exam_focus}
- 需要错题强化：{needs_error_points}

知识点列表：
{knowledge_points_text}

请按以下JSON格式生成学习计划，每个任务对应一天中的一个学习时段：
{{
  "summary": "计划概要，2-3句话",
  "risks": ["风险提示1", "风险提示2"],
  "tasks": [
    {{
      "scheduled_date": "YYYY-MM-DD",
      "knowledge_point_index": 0,
      "title": "任务标题",
      "task_type": "focused_study|basic_explanation|integrated_application|spaced_review|exam_review|practice_drill",
      "estimated_minutes": 30,
      "priority": 0.85,
      "difficulty": "basic"
    }}
  ]
}}

要求：
- 每天的任务总时长不要超过可用时间
- 先安排基础知识点，再安排进阶内容
- 每个重要知识点安排一次主学习 + 至少一次间隔复习
- 最后一天安排综合测试（如果有考试需求）
- 如果时间不足，优先安排重要性高的知识点
- 对已有掌握度的知识点，已经掌握(mastery>=0.9)的可以跳过，薄弱的需要加强"""


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from LLM response that may contain markdown code blocks."""
    # Try to find JSON in code blocks first
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1)
    # Try to find the outermost JSON object
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(text[start:end + 1])


def _extract_complete_json(text: str) -> dict[str, Any]:
    """Decode a complete JSON object, allowing only BOM/whitespace/full fences."""
    cleaned = str(text or "").lstrip("\ufeff").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("response is not a JSON object")
    return value


def _validated_extraction_payload(text: str) -> KnowledgePointExtractionPayload:
    try:
        value = _extract_complete_json(text)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise KnowledgePointExtractionError("JSON_DECODE_FAILED") from exc
    try:
        return KnowledgePointExtractionPayload.model_validate(value)
    except ValidationError as exc:
        raise KnowledgePointExtractionError("SCHEMA_VALIDATION_FAILED") from exc


_GENERIC_RELEVANCE_FRAGMENTS = {
    "知识点",
    "课程内容",
    "学习内容",
    "理解掌握",
    "基本概念",
    "核心概念",
    "重点原理",
    "综合应用",
    "主要内容",
    "相关知识",
    "具体说明",
}
_SENTENCE_BOUNDARIES = "。！？!?；;\r\n"


def _normalised_text_with_positions(value: str) -> tuple[str, list[int]]:
    characters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(value):
        if character == "_" or not character.isalnum():
            continue
        characters.append(character.lower())
        positions.append(index)
    return "".join(characters), positions


def _best_relevance_match(
    source_normalised: str,
    value: str,
    *,
    minimum_length: int,
) -> tuple[str, int] | None:
    value_normalised = normalise_content_text(value)
    if len(value_normalised) < minimum_length:
        return None
    maximum_length = min(16, len(value_normalised))
    generic = {normalise_content_text(item) for item in _GENERIC_RELEVANCE_FRAGMENTS}
    for length in range(maximum_length, minimum_length - 1, -1):
        for start in range(0, len(value_normalised) - length + 1):
            fragment = value_normalised[start : start + length]
            if fragment in generic or fragment.isdigit():
                continue
            source_index = source_normalised.find(fragment)
            if source_index >= 0:
                return fragment, source_index
    return None


def _grounded_quote_from_chunk(
    *,
    name: str,
    description: str,
    chunk_text: str,
) -> str | None:
    """Select a stable exact source substring around verified course terms."""
    source_normalised, positions = _normalised_text_with_positions(chunk_text)
    if not source_normalised or not positions:
        return None
    name_match = _best_relevance_match(
        source_normalised,
        name,
        minimum_length=2,
    )
    description_match = _best_relevance_match(
        source_normalised,
        description,
        minimum_length=3,
    )
    if name_match is None or description_match is None:
        return None

    # The knowledge-point name is the strongest anchor. Description matching is
    # required independently above so a correct term paired with unrelated prose
    # cannot be accepted.
    fragment, normalised_start = name_match
    normalised_end = normalised_start + len(fragment) - 1
    raw_start = positions[normalised_start]
    raw_end = positions[normalised_end] + 1

    sentence_start = 0
    for boundary in _SENTENCE_BOUNDARIES:
        sentence_start = max(sentence_start, chunk_text.rfind(boundary, 0, raw_start) + 1)
    sentence_end = len(chunk_text)
    following = [
        position
        for boundary in _SENTENCE_BOUNDARIES
        if (position := chunk_text.find(boundary, raw_end)) >= 0
    ]
    if following:
        sentence_end = min(following) + 1
    sentence = chunk_text[sentence_start:sentence_end].strip()
    if (
        8 <= len(normalise_content_text(sentence)) <= 360
        and fragment in normalise_content_text(sentence)
        and sentence in chunk_text
    ):
        return sentence

    # Long OCR paragraphs may not contain reliable sentence punctuation. Use a
    # bounded window around the verified term, never an arbitrary chunk prefix.
    window_start = max(0, raw_start - 100)
    window_end = min(len(chunk_text), raw_end + 180)
    window = chunk_text[window_start:window_end].strip()
    if (
        len(normalise_content_text(window)) >= 8
        and fragment in normalise_content_text(window)
        and window in chunk_text
    ):
        return window
    return None


def _verified_source_binding(
    db: Session,
    *,
    course_id: int,
    source: dict[str, Any],
    document_ids: list[int] | None,
    name: str,
    description: str,
) -> dict[str, Any] | None:
    try:
        chunk_id = int(source.get("chunk_id"))
    except (TypeError, ValueError):
        return None
    statement = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.id == chunk_id,
            DocumentChunk.course_id == course_id,
            DocumentChunk.is_active.is_(True),
            DocumentChunk.document_version == Document.current_version,
            Document.is_deleted.is_(False),
            Document.status == "ready",
        )
    )
    if document_ids:
        statement = statement.where(Document.id.in_(document_ids))
    row = db.execute(statement).one_or_none()
    if row is None:
        return None
    chunk, document = row
    if (
        source.get("document_id") != document.id
        or source.get("document_version") != chunk.document_version
    ):
        return None
    quote = _grounded_quote_from_chunk(
        name=name,
        description=description,
        chunk_text=chunk.content,
    )
    if quote is None or quote not in chunk.content:
        return None
    return {
        "source_quote": quote,
        "source_document_id": document.id,
        "source_document_name": document.title,
        "source_document_version": chunk.document_version,
        "source_page_number": chunk.page_number,
        "source_chunk_id": chunk.id,
        "source_text": chunk.content,
    }


async def extract_knowledge_points(
    db: Session,
    provider: LLMProvider,
    course_id: int,
    document_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Use LLM + RAG to extract knowledge points from course documents."""
    # First get a broad overview of the course content
    query = "列出本课程涵盖的所有核心概念、原理和知识点"
    sources = await retrieve(
        db, provider,
        course_id=course_id,
        query=query,
        document_ids=document_ids,
        top_k=20,
    )
    if not sources:
        raise KnowledgePointExtractionError("SOURCE_VALIDATION_FAILED", "no retrievable sources")

    # Build context from document chunks
    context_parts: list[str] = []
    source_map: dict[str, dict[str, Any]] = {}
    seen = set()
    for s in sources:
        key = s["quote"][:100]
        if key not in seen:
            seen.add(key)
            source_id = f"S{len(source_map) + 1}"
            source_map[source_id] = s
            context_parts.append(f"[{source_id}]\n{s['quote']}")
        if len(source_map) >= 15:
            break

    context = "\n\n---\n\n".join(context_parts)

    if not context.strip():
        raise KnowledgePointExtractionError("SOURCE_VALIDATION_FAILED", "empty source context")

    messages = [
        {
            "role": "system",
            "content": (
                "你是课程知识点抽取器。只能输出符合约定的 JSON，并严格使用提供的 source_id；"
                "不要输出 source_quote 或任何数据库字段。"
            ),
        },
        {"role": "user", "content": KNOWLEDGE_POINT_EXTRACTION_PROMPT.format(context=context[:12000])},
    ]
    response = ""
    payload: KnowledgePointExtractionPayload | None = None
    for attempt in range(2):
        try:
            response = await provider.chat(
                messages,
                temperature=0.2,
                enable_thinking=False,
                response_format={"type": "json_object"},
                max_tokens=1500,
                _require_complete=True,
            )
        except ModelResponseTruncatedError as exc:
            raise KnowledgePointExtractionError("MODEL_RESPONSE_TRUNCATED") from exc
        except Exception as exc:
            raise KnowledgePointExtractionError("MODEL_REQUEST_FAILED") from exc
        try:
            payload = _validated_extraction_payload(response)
            break
        except KnowledgePointExtractionError as exc:
            if exc.failure_type not in {"JSON_DECODE_FAILED", "SCHEMA_VALIDATION_FAILED"}:
                raise
            if attempt:
                raise
            messages = [
                {
                    "role": "system",
                    "content": "把给定内容纠正为严格符合目标结构的纯 JSON；不得添加新知识点或新引用。",
                },
                {
                    "role": "user",
                    "content": (
                        "目标结构为 {\"knowledge_points\":[{\"name\":str,\"description\":str,"
                        "\"source_id\":\"S数字\"}]}，数量 6 到 15。"
                        f"\n待纠正内容：\n{response}"
                    ),
                },
            ]
    if payload is None:
        raise KnowledgePointExtractionError("SCHEMA_VALIDATION_FAILED")

    extracted: list[dict[str, Any]] = []
    for raw in payload.knowledge_points:
        source = source_map.get(raw.source_id)
        if source is None:
            raise KnowledgePointExtractionError(
                "SOURCE_VALIDATION_FAILED",
                f"invalid source binding for {raw.source_id}",
            )
        verified = _verified_source_binding(
            db,
            course_id=course_id,
            source=source,
            document_ids=document_ids,
            name=raw.name,
            description=raw.description,
        )
        if verified is None:
            raise KnowledgePointExtractionError(
                "SOURCE_VALIDATION_FAILED",
                f"unrelated or unavailable source for {raw.source_id}",
            )
        extracted.append(
            {
                "name": raw.name,
                "description": raw.description,
                "source_id": raw.source_id,
                **verified,
                # The released schema still needs these scheduling defaults.
                "importance": 0.8,
                "difficulty": "intermediate",
                "estimated_minutes": 45,
            }
        )
    return extracted


ONE_SHOT_PLAN_PROMPT = """你是一位学习规划专家。请根据课程资料和用户信息，直接生成一份学习计划。

用户信息：
- 学习目标：{goal}
- 日期：{start_date} 至 {end_date}（{available_days} 天可学）
- 每日 {daily_minutes} 分钟，每次 {session_minutes} 分钟
- 水平：{foundation_level}，偏好：{learning_order}，难度：{preferred_difficulty}
- 考试重点：{needs_exam_focus}，错题强化：{needs_error_points}

课程资料：
{context}

请按以下JSON格式返回（不要其他内容）：
{{
  "summary": "2-3句话计划概要",
  "risks": [],
  "tasks": [
    {{
      "scheduled_date": "YYYY-MM-DD",
      "title": "学习：具体知识点名称",
      "task_type": "focused_study",
      "estimated_minutes": 30,
      "priority": 0.8,
      "difficulty": "basic"
    }}
  ]
}}

要求：先基础后进阶，每个知识点主学习+间隔复习，最后一天综合测试，时间不足则优先高重要性内容。"""


PLAN_ENHANCEMENT_PROMPT = """你负责为已经由规则引擎排好的学习计划补充说明，而不是重新安排任务。

课程目标：{goal}
日期范围：{start_date} 至 {end_date}，可学习 {available_days} 天；每天 {daily_minutes} 分钟，每次 {session_minutes} 分钟。
学习偏好：基础 {foundation_level}，顺序 {learning_order}，难度 {preferred_difficulty}。
不可学习日期已经从可学习天数中扣除。请严格依据下面课程资料写 2-3 句摘要和最多 5 条风险提示。

课程资料：
{context}

只返回 JSON，且只能包含：
{{"summary": "具体说明将学习哪些资料内容", "risks": ["基于资料或时间安排的具体风险"]}}
不要返回 tasks、scheduled_date、任务标题或任何新的排程；日期和任务由规则引擎负责。"""


async def generate_plan_one_shot(
    db: Session,
    provider: LLMProvider,
    *,
    course_id: int,
    goal: str,
    start_date: date,
    end_date: date,
    daily_minutes: int,
    session_minutes: int,
    foundation_level: str = "basic",
    learning_order: str = "explain_first",
    preferred_difficulty: str = "adaptive",
    needs_exam_focus: bool = True,
    needs_error_points: bool = True,
    unavailable_dates: list[date] | None = None,
    document_ids: list[int] | None = None,
    timeout_seconds: int = 18,
) -> dict[str, Any]:
    """Single LLM call: retrieve context then generate plan directly."""

    # Step 1: Quick RAG retrieval
    sources = await retrieve(
        db, provider,
        course_id=course_id,
        query="课程大纲 核心知识点 重点内容",
        document_ids=document_ids,
        top_k=10,
    )
    context = ""
    if sources:
        parts = []
        seen = set()
        for s in sources[:8]:
            key = s["quote"][:80]
            if key not in seen:
                seen.add(key)
                parts.append(f"[{s['document_name']}]: {s['quote'][:600]}")
        context = "\n\n".join(parts)[:6000]

    # Step 2: Build availability info
    unavailable = set(unavailable_dates or [])
    total_days = (end_date - start_date).days + 1
    available_days = sum(1 for i in range(total_days) if (start_date + timedelta(days=i)) not in unavailable)

    # Step 3: Single LLM call
    prompt = PLAN_ENHANCEMENT_PROMPT.format(
        goal=goal,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        available_days=available_days,
        daily_minutes=daily_minutes,
        session_minutes=session_minutes,
        foundation_level=foundation_level,
        learning_order=learning_order,
        preferred_difficulty=preferred_difficulty,
        needs_exam_focus="是" if needs_exam_focus else "否",
        needs_error_points="是" if needs_error_points else "否",
        context=context or "（暂无课程资料，请基于通用学习路径生成计划）",
    )

    try:
        response = await provider.chat(
            [
                {"role": "system", "content": "你是学习规划专家。严格按JSON格式输出计划。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            # Rule scheduling remains authoritative; this optional response
            # only adds a compact summary and risks as JSON.
            enable_thinking=False,
            max_tokens=1400,
            _timeout=timeout_seconds,
        )
        return _extract_json(response)
    except Exception as e:
        raise RuntimeError("AI_PLAN_ENHANCEMENT_FAILED") from e

