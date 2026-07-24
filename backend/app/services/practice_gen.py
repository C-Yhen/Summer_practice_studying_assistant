"""AI-powered practice question generation from course materials."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.app.providers.llm import LLMProvider
from backend.app.services.rag import retrieve

QUESTION_GENERATION_PROMPT = """你是一位出题专家。请根据以下课程资料，为知识点"{knowledge_point}"生成一道单项选择题。

要求：
1. 题目必须严格基于提供的课程资料内容（标注引用来源）
2. 题目类型：单选题（4个选项，A/B/C/D）
3. 难度：{difficulty}
4. 题目要有区分度，能够检验学生是否真正理解该知识点
5. 干扰项要有一定迷惑性，但不能是明显无关的选项
6. 给出正确答案和详细解析

请严格按以下JSON格式返回：
{{
  "stem": "题目题干",
  "options": [
    {{"label": "A", "text": "选项A内容"}},
    {{"label": "B", "text": "选项B内容"}},
    {{"label": "C", "text": "选项C内容"}},
    {{"label": "D", "text": "选项D内容"}}
  ],
  "correct_option": "A",
  "explanation": "解析说明，解释为什么选这个，为什么不选其他选项",
  "source_quote": "引用的资料原文片段"
}}

课程资料：
{context}"""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found: {text[:200]}")
    return json.loads(text[start:end + 1])


async def generate_question(
    db: Session,
    provider: LLMProvider,
    *,
    course_id: int,
    knowledge_point: str,
    difficulty: str = "basic",
    document_ids: list[int] | None = None,
) -> dict[str, Any] | None:
    """Use LLM + RAG to generate a multiple-choice practice question."""

    query = f"关于 {knowledge_point} 的核心概念、原理和应用"
    sources = await retrieve(
        db, provider,
        course_id=course_id,
        query=query,
        document_ids=document_ids,
        top_k=8,
    )

    if not sources:
        return None

    context_parts: list[str] = []
    seen = set()
    for s in sources:
        key = s["quote"][:100]
        if key not in seen:
            seen.add(key)
            context_parts.append(
                f"[{s['document_name']} 第{s['page_number'] or '?'}页]: {s['quote']}"
            )

    context = "\n\n".join(context_parts[:8])
    if len(context) < 80:
        return None

    prompt = QUESTION_GENERATION_PROMPT.format(
        knowledge_point=knowledge_point,
        difficulty=difficulty,
        context=context[:8000],
    )

    try:
        response = await provider.chat(
            [
                {"role": "system", "content": "你是一位出题专家，擅长基于课程内容设计高质量的测试题目。请严格按JSON格式回复。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        data = _extract_json(response)
        # Validate required fields
        required = ["stem", "options", "correct_option", "explanation"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing field: {field}")
        if not isinstance(data["options"], list) or len(data["options"]) < 2:
            raise ValueError("Invalid options")
        return data
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[Practice Gen] Question generation failed: {e}")
        return None


async def generate_questions_batch(
    db: Session,
    provider: LLMProvider,
    *,
    course_id: int,
    knowledge_points: list[tuple[str, str]],  # (name, difficulty)
    document_ids: list[int] | None = None,
    max_questions: int = 10,
) -> list[dict[str, Any]]:
    """Generate multiple questions for different knowledge points."""
    questions: list[dict[str, Any]] = []
    for kp_name, difficulty in knowledge_points[:max_questions]:
        question = await generate_question(
            db, provider,
            course_id=course_id,
            knowledge_point=kp_name,
            difficulty=difficulty,
            document_ids=document_ids,
        )
        if question:
            question["_knowledge_point"] = kp_name
            question["_difficulty"] = difficulty
            questions.append(question)
    return questions
