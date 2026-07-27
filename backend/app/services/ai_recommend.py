"""AI-powered recommendation engine with user behavior weighting."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    PracticeAttempt,
    StudyPlan,
    StudyTask,
    User,
    UserBehavior,
)
from backend.app.providers.llm import LLMProvider
from backend.app.services.rag import retrieve
from backend.app.services.timezones import local_date_range_utc, resolve_user_timezone

logger = logging.getLogger(__name__)

RECOMMENDATION_PROMPT = """你是一位学习顾问。根据用户的学习数据，给出3-5条个性化学习建议。

用户数据：
- 今日日期：{today}
- 课程：{course_name}
- 考试日期：{exam_date}
- 学习记录（近7天）：{recent_records}
- 任务状态：{task_status}
- 练习题表现：{practice_stats}
- 知识点掌握度：{mastery_summary}
- 行为偏好权重：{behavior_weights}

请按JSON格式返回（不要其他内容）：
{{
  "recommendations": [
    {{
      "item_type": "study_task|mastery_review|course_chat|create_plan|upload_document|weekly_report",
      "title": "建议标题",
      "reason": "基于数据分析的具体理由",
      "priority": 0.85,
      "estimated_minutes": 30,
      "action_label": "操作按钮文字"
    }}
  ],
  "summary": "整体学习状况一句话总结"
}}

要求：优先推荐薄弱知识点复习，其次推荐未完成任务，结合用户行为偏好（常看什么就多推荐什么）。"""


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError("No JSON in response")
    return json.loads(text[start:end + 1])


_ALLOWED_RECOMMENDATION_TYPES = {
    "study_task", "mastery_review", "course_chat", "create_plan", "upload_document", "weekly_report",
}


def validate_recommendation_result(value: Any) -> dict[str, Any]:
    """Keep provider output in a small, presentation-safe recommendation contract."""
    if not isinstance(value, dict) or not isinstance(value.get("recommendations"), list):
        raise ValueError("AI_RECOMMENDATIONS_INVALID")
    valid: list[dict[str, Any]] = []
    rejected = 0
    for raw in value["recommendations"][:5]:
        if not isinstance(raw, dict):
            rejected += 1
            continue
        title = str(raw.get("title", "")).strip()
        reason = str(raw.get("reason", "")).strip()
        item_type = str(raw.get("item_type", "")).strip()
        try:
            priority = float(raw.get("priority"))
            estimated_minutes = int(raw.get("estimated_minutes"))
        except (TypeError, ValueError):
            rejected += 1
            continue
        if (
            not title or not reason or len(title) > 160 or len(reason) > 1200
            or item_type not in _ALLOWED_RECOMMENDATION_TYPES
            or not 0 <= priority <= 1 or not 5 <= estimated_minutes <= 480
        ):
            rejected += 1
            continue
        valid.append({
            "title": title,
            "reason": reason,
            "priority": priority,
            "estimated_minutes": estimated_minutes,
            "item_type": item_type,
        })
    summary = str(value.get("summary", "")).strip()[:1200]
    warnings = ["AI_RECOMMENDATIONS_REJECTED"] if rejected else []
    return {"summary": summary, "recommendations": valid, "warnings": warnings}


async def generate_recommendations(
    db: Session,
    provider: LLMProvider,
    *,
    user_id: int,
    course_id: int,
    course_name: str,
    exam_date: date | None,
    target_date: date,
    timeout_seconds: int = 12,
) -> dict[str, Any]:
    """AI-powered recommendation generation with behavior weighting."""

    today = target_date
    user = db.get(User, user_id)
    zone, _ = resolve_user_timezone(user.timezone if user is not None else None)

    # --- Gather user behavior weights ---
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    behaviors = list(db.scalars(
        select(UserBehavior).where(
            UserBehavior.user_id == user_id,
            UserBehavior.course_id == course_id,
            UserBehavior.created_at >= recent_cutoff,
        ).order_by(UserBehavior.created_at.desc()).limit(50)
    ))

    # Calculate behavior weights by target_type
    behavior_weights: dict[str, float] = {}
    for b in behaviors:
        key = b.target_type
        behavior_weights[key] = behavior_weights.get(key, 0) + b.weight * (1 + b.dwell_seconds / 120)

    # Normalize
    total = sum(behavior_weights.values()) or 1
    behavior_weights = {k: round(v / total, 2) for k, v in behavior_weights.items()}

    # --- Learning records (7 days) ---
    week_ago = today - timedelta(days=6)
    range_start_utc, range_end_utc = local_date_range_utc(week_ago, today, zone)
    records = list(db.scalars(
        select(LearningRecord).where(
            LearningRecord.user_id == user_id,
            LearningRecord.course_id == course_id,
            LearningRecord.occurred_at >= range_start_utc,
            LearningRecord.occurred_at < range_end_utc,
        ).order_by(LearningRecord.occurred_at.desc()).limit(20)
    ))
    recent_records = "\n".join(
        f"- {r.record_type}: {r.duration_seconds // 60}分钟 {'完成' if r.completed else '进行中'}"
        for r in records[:10]
    ) or "（暂无学习记录）"

    # --- Task status ---
    tasks = list(db.scalars(
        select(StudyTask).where(
            StudyTask.user_id == user_id,
            StudyTask.course_id == course_id,
        ).order_by(StudyTask.scheduled_date.desc()).limit(15)
    ))
    todo = [t for t in tasks if t.status == "todo"]
    done = [t for t in tasks if t.status == "done"]
    overdue = [t for t in todo if t.scheduled_date < today]
    task_status = (
        f"待完成: {len(todo)}个 (其中逾期{len(overdue)}个), "
        f"已完成: {len(done)}个"
    )

    # --- Practice stats ---
    total_attempts = db.scalar(
        select(func.count()).select_from(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.course_id == course_id,
        )
    ) or 0
    correct = db.scalar(
        select(func.count()).select_from(PracticeAttempt).where(
            PracticeAttempt.user_id == user_id,
            PracticeAttempt.course_id == course_id,
            PracticeAttempt.is_correct.is_(True),
        )
    ) or 0
    accuracy = f"{correct}/{total_attempts} ({round(correct/total_attempts*100, 1)}%)" if total_attempts else "暂无练习"
    practice_stats = f"总答题: {total_attempts}, 正确率: {accuracy}"

    # --- Mastery summary ---
    masteries = list(db.scalars(
        select(KnowledgeMastery, KnowledgePoint).join(
            KnowledgePoint, KnowledgeMastery.knowledge_point_id == KnowledgePoint.id
        ).where(
            KnowledgeMastery.user_id == user_id,
            KnowledgeMastery.course_id == course_id,
        ).order_by(KnowledgeMastery.score)
    ))
    mastery_parts = []
    for m, kp in masteries[:8]:
        label = "薄弱" if m.score < 0.5 else "一般" if m.score < 0.8 else "良好"
        mastery_parts.append(f"- {kp.name}: {label} (得分{m.score:.0%}, 尝试{m.attempts}次)")
    mastery_summary = "\n".join(mastery_parts) or "（暂无掌握度数据）"

    # --- Call LLM ---
    behavior_text = ", ".join(f"{k}偏好×{v}" for k, v in behavior_weights.items()) if behavior_weights else "无偏好数据"
    prompt = RECOMMENDATION_PROMPT.format(
        today=today.isoformat(),
        course_name=course_name,
        exam_date=exam_date.isoformat() if exam_date else "未设置",
        recent_records=recent_records,
        task_status=task_status,
        practice_stats=practice_stats,
        mastery_summary=mastery_summary,
        behavior_weights=behavior_text,
    )

    try:
        response = await provider.chat(
            [
                {"role": "system", "content": "你是学习顾问。严格按JSON格式输出建议。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=1500,
            _timeout=timeout_seconds,
        )
        return validate_recommendation_result(_extract_json(response))
    except Exception as e:
        logger.warning("ai_recommendation_failed course_id=%s error_type=%s", course_id, type(e).__name__)
        raise RuntimeError("AI_RECOMMENDATION_FAILED") from e
