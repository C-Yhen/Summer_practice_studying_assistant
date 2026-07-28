"""AI-powered knowledge mastery assessment."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    ChatMessage,
    ChatSession,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    PracticeAttempt,
    WrongQuestionEntry,
)
from backend.app.providers.llm import LLMProvider

MASTERY_PROMPT = """你是一位学习评估专家。根据学生的学习数据，评估其对知识点的掌握程度。

知识点：{point_name}
学习数据：
- 练习题：{practice_data}
- 错题记录：{wrong_data}
- 学习时长：{study_time} 分钟
- 最近学习：{last_studied}
- 问答互动：{chat_data}

请按JSON格式评估（不要其他内容）：
{{
  "score": 0.75,
  "confidence": 0.8,
  "level": "良好",
  "strengths": ["掌握较好的方面"],
  "weaknesses": ["需要加强的方面"],
  "suggestion": "具体学习建议，1-2句话"
}}

评分标准：0-0.3未掌握，0.3-0.6初步理解，0.6-0.8基本掌握，0.8-1.0熟练掌握。"""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("No JSON in response")
    return json.loads(text[start:end + 1])


async def assess_mastery(
    db: Session,
    provider: LLMProvider,
    *,
    user_id: int,
    course_id: int,
    knowledge_point_id: int,
) -> dict[str, Any] | None:
    """AI-powered holistic mastery assessment for a knowledge point."""

    point = db.get(KnowledgePoint, knowledge_point_id)
    if not point:
        return None

    # Practice data
    attempts = list(db.scalars(
        select(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.course_id == course_id,
        ).order_by(PracticeAttempt.submitted_at.desc()).limit(20)
    ))
    total = len(attempts)
    correct = sum(1 for a in attempts if a.is_correct)
    avg_time = sum(a.elapsed_seconds for a in attempts) / total if total else 0
    practice_data = (
        f"答题{total}次, 正确{correct}次 ({round(correct/total*100,1)}%正确率), "
        f"平均用时{avg_time:.0f}秒"
    ) if total else "暂无练习记录"

    # Wrong question records
    wrong_count = db.scalar(
        select(func.count()).select_from(WrongQuestionEntry).where(
            WrongQuestionEntry.user_id == user_id,
            WrongQuestionEntry.course_id == course_id,
        )
    ) or 0
    wrong_data = f"错题本中有{wrong_count}道待复习题" if wrong_count else "暂无错题"

    # Study time
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    study_minutes = db.scalar(
        select(func.coalesce(func.sum(LearningRecord.duration_seconds), 0))
        .where(
            LearningRecord.user_id == user_id,
            LearningRecord.course_id == course_id,
            LearningRecord.occurred_at >= month_ago,
        )
    ) or 0
    study_time = round(study_minutes / 60)

    # Last studied
    last = db.scalar(
        select(LearningRecord.occurred_at).where(
            LearningRecord.user_id == user_id,
            LearningRecord.course_id == course_id,
        ).order_by(LearningRecord.occurred_at.desc())
    )
    last_studied = last.strftime("%Y-%m-%d") if last else "从未学习"

    # Chat interactions
    chat_count = db.scalar(
        select(func.count()).select_from(ChatMessage).join(ChatSession).where(
            ChatSession.user_id == user_id,
            ChatSession.course_id == course_id,
            ChatMessage.role == "user",
        )
    ) or 0
    chat_data = f"提问{chat_count}次" if chat_count else "暂无问答互动"

    # --- Call LLM ---
    prompt = MASTERY_PROMPT.format(
        point_name=point.name,
        practice_data=practice_data,
        wrong_data=wrong_data,
        study_time=study_time,
        last_studied=last_studied,
        chat_data=chat_data,
    )

    try:
        response = await provider.chat(
            [
                {"role": "system", "content": "你是学习评估专家。严格按JSON格式输出评估。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        return _extract_json(response)
    except Exception as e:
        print(f"[AI Mastery] Failed for {point.name}: {e}")
        return None


async def assess_all_masteries(
    db: Session,
    provider: LLMProvider,
    *,
    user_id: int,
    course_id: int,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Assess mastery for weakest knowledge points first."""

    masteries = list(db.scalars(
        select(KnowledgeMastery, KnowledgePoint).join(
            KnowledgePoint, KnowledgeMastery.knowledge_point_id == KnowledgePoint.id
        ).where(
            KnowledgeMastery.user_id == user_id,
            KnowledgeMastery.course_id == course_id,
        ).order_by(KnowledgeMastery.score).limit(limit)
    ))

    results = []
    for mastery, point in masteries:
        assessment = await assess_mastery(
            db, provider,
            user_id=user_id,
            course_id=course_id,
            knowledge_point_id=point.id,
        )
        if assessment:
            assessment["knowledge_point_id"] = point.id
            assessment["knowledge_point"] = point.name
            results.append(assessment)

    return results
