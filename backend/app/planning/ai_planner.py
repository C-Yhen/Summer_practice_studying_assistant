"""AI-powered knowledge point extraction and study plan generation."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.models import Document, DocumentChunk
from backend.app.providers.llm import LLMProvider
from backend.app.services.rag import retrieve

KNOWLEDGE_POINT_EXTRACTION_PROMPT = """你是一位课程分析专家。请根据以下课程资料，提取出该课程的核心知识点列表。

要求：
1. 每个知识点包含：名称(name)、简要描述(description)、重要性(importance, 0-1)、难度(difficulty: basic/intermediate/advanced)、建议学习时长(estimated_minutes, 15-90分钟)
2. 按知识点的逻辑顺序排列（先基础后进阶）
3. 标注每个知识点的前置依赖（prerequisite_indices，索引从0开始）

请严格按以下JSON格式返回，不要包含其他内容：
{{
  "knowledge_points": [
    {{
      "name": "知识点名称",
      "description": "简要描述",
      "importance": 0.9,
      "difficulty": "basic",
      "estimated_minutes": 45,
      "prerequisite_indices": []
    }}
  ]
}}

课程资料：
{context}"""


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
        return []

    # Build context from document chunks
    context_parts: list[str] = []
    seen = set()
    for s in sources:
        key = s["quote"][:100]
        if key not in seen:
            seen.add(key)
            context_parts.append(
                f"[来源：{s['document_name']} 第{s['page_number'] or '?'}页]\n{s['quote']}"
            )

    context = "\n\n---\n\n".join(context_parts[:15])

    if not context.strip():
        return []

    try:
        response = await provider.chat(
            [
                {"role": "system", "content": "你是一位课程分析专家，擅长从教材和讲义中提取结构化的知识点。请严格按JSON格式回复。"},
                {"role": "user", "content": KNOWLEDGE_POINT_EXTRACTION_PROMPT.format(context=context[:12000])},
            ],
            temperature=0.3,
            max_tokens=4000,
        )
        data = _extract_json(response)
        return data.get("knowledge_points", [])
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        # Fallback: return empty, caller should use rule-based
        print(f"[AI Planner] Knowledge point extraction failed: {e}")
        return []


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
    prompt = ONE_SHOT_PLAN_PROMPT.format(
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
            max_tokens=3000,
        )
        return _extract_json(response)
    except Exception as e:
        print(f"[AI Planner] One-shot plan failed: {e}")
        return {"tasks": [], "risks": [], "summary": ""}

