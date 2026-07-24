from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from backend.app.api.v1.courses import _owned_course
from backend.app.dependencies import AppSettings, CurrentUser, DBSession
from backend.app.models import (
    Course,
    Document,
    KnowledgeMastery,
    KnowledgePoint,
    LearningRecord,
    RecommendationRecord,
    StudyPlan,
    StudyPlanVersion,
    StudyTask,
    UserBehavior,
)
from backend.app.recommendation.engine import (
    ALGORITHM_VERSION,
    CATEGORY_LABELS,
    Signal,
    base_signal,
    category_for_item_type,
    recommendation_key,
    recommendation_sort_key,
    score,
    select_diverse_recommendations,
)
from backend.app.responses import ok
from backend.app.schemas import CourseRecommendationFeedback, UserBehaviorTrack
from backend.app.services.ai_recommend import generate_recommendations as ai_recommend
from backend.app.services.timezones import local_date_range_utc, resolve_user_timezone
from backend.app.providers.llm import get_llm_provider

router = APIRouter(tags=["recommendations"])

RecommendationQueryCategory = Literal["all", "task", "mastery", "resource", "plan", "report"]

CATEGORY_STRATEGY_SUMMARIES = {
    "task": "当前显示全部学习任务，按到期时间、优先级和关联掌握度排序。",
    "mastery": "当前显示已有真实学习记录的薄弱知识点复习建议。",
    "resource": "当前显示资料上传或课程问答相关的可执行建议。",
    "plan": "当前显示学习计划相关建议。",
    "report": "当前显示基于最近学习记录的学习复盘建议。",
}

ACTION_MAP = {
    "study_task": {"type": "open_today_tasks", "label": "进入今日任务"},
    "mastery_review": {"type": "open_mastery", "label": "查看掌握度"},
    "course_chat": {"type": "open_chat", "label": "开始课程问答"},
    "create_plan": {"type": "open_plan", "label": "创建学习计划"},
    "upload_document": {"type": "open_upload", "label": "上传课程资料"},
    "weekly_report": {"type": "open_async_tasks", "label": "前往任务中心"},
}


def _today_for_user(current_user: CurrentUser) -> date:
    from datetime import datetime, timezone

    zone, _ = resolve_user_timezone(current_user.timezone)
    return datetime.now(timezone.utc).astimezone(zone).date()


def _task_signals(task: StudyTask, target_date: date, course: Course, mastery: KnowledgeMastery | None) -> list[Signal]:
    signals = [base_signal("study_task")]
    if task.scheduled_date < target_date:
        overdue_days = (target_date - task.scheduled_date).days
        signals.append(Signal("overdue", "已逾期", min(1.0, overdue_days / 7), 25.0))
    elif task.scheduled_date == target_date:
        signals.append(Signal("due_today", "今日到期", 1.0, 20.0))
    else:
        days_until = (task.scheduled_date - target_date).days
        signals.append(Signal("upcoming", "近期任务", max(0.0, 1 - days_until / 3), 8.0))
    signals.append(Signal("task_priority", "任务优先级", task.priority, 20.0 * task.priority))
    if mastery is not None and mastery.attempts > 0:
        weakness = 1 - mastery.score
        signals.append(Signal("low_mastery", "关联知识点掌握度", weakness, 20.0 * weakness))
    if course.exam_date is not None and course.exam_date >= target_date:
        days = (course.exam_date - target_date).days
        urgency = max(0.0, 1 - days / 30)
        signals.append(Signal("exam_urgency", "考试临近", urgency, 10.0 * urgency))
    return signals


def _item(
    *, course_id: int, item_type: str, item_id: int, title: str, subtitle: str,
    reason: str, signals: list[Signal], action: dict[str, str],
    estimated_minutes: int | None = None, knowledge_point: dict | None = None,
) -> dict:
    item_score, breakdown = score(signals)
    category = category_for_item_type(item_type)
    return {
        "recommendation_key": recommendation_key(course_id, item_type, item_id),
        "item_type": item_type,
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "item_id": item_id,
        "course_id": course_id,
        "title": title,
        "subtitle": subtitle,
        "score": item_score,
        "reason": reason,
        "estimated_minutes": estimated_minutes,
        "knowledge_point": knowledge_point,
        "signals": [signal.payload() for signal in signals],
        "score_breakdown": breakdown,
        "action": action,
    }


def build_course_recommendations(
    db: DBSession,
    user_id: int,
    course_id: int,
    target_date: date,
    limit: int,
    category: RecommendationQueryCategory = "all",
    include_all_candidates: bool = False,
) -> dict:
    """Build deterministic, read-only recommendations from persisted course data."""
    course = _owned_course(db, course_id, user_id)
    active_plan_versions = select(StudyPlanVersion.id).join(
        StudyPlan, StudyPlan.id == StudyPlanVersion.plan_id
    ).where(
        StudyPlan.user_id == user_id,
        StudyPlan.course_id == course_id,
        StudyPlan.status == "active",
        StudyPlanVersion.status == "active",
        StudyPlan.active_version == StudyPlanVersion.version,
    )
    has_active_plan = db.scalar(select(func.count()).select_from(active_plan_versions.subquery())) > 0
    ready_documents = list(db.scalars(select(Document).where(
        Document.course_id == course_id, Document.status == "ready", Document.is_deleted.is_(False)
    )))
    masteries = {
        item.knowledge_point_id: item
        for item in db.scalars(
            select(KnowledgeMastery)
            .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
            .where(
                KnowledgeMastery.user_id == user_id,
                KnowledgeMastery.course_id == course_id,
                KnowledgePoint.course_id == course_id,
            )
        )
    }
    items: list[dict] = []
    task_rows = list(db.execute(
        select(StudyTask, KnowledgePoint)
        .outerjoin(KnowledgePoint, (KnowledgePoint.id == StudyTask.knowledge_point_id) & (KnowledgePoint.course_id == course_id))
        .where(
            StudyTask.user_id == user_id,
            StudyTask.course_id == course_id,
            StudyTask.plan_version_id.in_(active_plan_versions),
            StudyTask.status != "completed",
            StudyTask.scheduled_date <= target_date + timedelta(days=3),
        )
    ))
    for task, point in task_rows:
        mastery = masteries.get(task.knowledge_point_id)
        signals = _task_signals(task, target_date, course, mastery)
        due = "逾期任务" if task.scheduled_date < target_date else ("今日任务" if task.scheduled_date == target_date else "近期任务")
        point_payload = None
        point_text = ""
        if point is not None and mastery is not None and mastery.attempts > 0:
            point_payload = {"id": point.id, "name": point.name, "score": round(mastery.score, 4), "attempts": mastery.attempts}
            point_text = f"，关联知识点“{point.name}”已有 {mastery.attempts} 次学习记录"
        items.append(_item(
            course_id=course_id, item_type="study_task", item_id=task.id, title=task.title,
            subtitle=f"{due} · 预计 {task.estimated_minutes} 分钟",
            reason=f"该任务计划于 {task.scheduled_date.isoformat()} 完成，优先级为 {task.priority:.2f}{point_text}。",
            signals=signals, action=ACTION_MAP["study_task"], estimated_minutes=task.estimated_minutes,
            knowledge_point=point_payload,
        ))
    for mastery, point in db.execute(
        select(KnowledgeMastery, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePoint.id == KnowledgeMastery.knowledge_point_id)
        .where(KnowledgeMastery.user_id == user_id, KnowledgeMastery.course_id == course_id, KnowledgeMastery.attempts > 0, KnowledgePoint.course_id == course_id)
        .order_by(KnowledgeMastery.score, KnowledgeMastery.knowledge_point_id)
        .limit(3)
    ):
        weakness = 1 - mastery.score
        signals = [base_signal("mastery_review"), Signal("low_mastery", "掌握度偏低", weakness, 40 * weakness), Signal("learning_attempts", "已有学习记录", min(1.0, mastery.attempts / 5), min(10.0, mastery.attempts * 2.0))]
        items.append(_item(
            course_id=course_id, item_type="mastery_review", item_id=point.id, title=f"复习：{point.name}",
            subtitle=f"掌握度 {mastery.score * 100:.0f}% · 已学习 {mastery.attempts} 次",
            reason=f"“{point.name}”已有 {mastery.attempts} 次学习记录，当前掌握度为 {mastery.score * 100:.0f}%，建议安排复习。",
            signals=signals, action=ACTION_MAP["mastery_review"],
            knowledge_point={"id": point.id, "name": point.name, "score": round(mastery.score, 4), "attempts": mastery.attempts},
        ))
    if not has_active_plan:
        items.append(_item(course_id=course_id, item_type="create_plan", item_id=course_id, title="创建学习计划", subtitle="当前课程尚无生效学习计划", reason="当前课程尚无生效学习计划，建议先生成一份学习计划。", signals=[base_signal("create_plan")], action=ACTION_MAP["create_plan"]))
    if ready_documents:
        count = len(ready_documents)
        items.append(_item(course_id=course_id, item_type="course_chat", item_id=course_id, title="使用课程问答复习", subtitle=f"已有 {count} 份就绪资料可用于问答", reason=f"当前课程已有 {count} 份就绪资料，可使用课程问答进行复习。", signals=[base_signal("course_chat"), Signal("ready_documents", "可用资料", min(1.0, count / 3), min(15.0, count * 5.0))], action=ACTION_MAP["course_chat"]))
    else:
        items.append(_item(course_id=course_id, item_type="upload_document", item_id=course_id, title="上传学习资料", subtitle="当前课程没有就绪资料", reason="当前课程尚无可用于问答的已就绪资料，建议先上传资料。", signals=[base_signal("upload_document")], action=ACTION_MAP["upload_document"]))
    from backend.app.models import User
    user = db.get(User, user_id)
    zone, _ = resolve_user_timezone(user.timezone if user is not None else None)
    start_utc, end_utc = local_date_range_utc(target_date - timedelta(days=6), target_date, zone)
    record_count = db.scalar(select(func.count()).select_from(LearningRecord).where(LearningRecord.user_id == user_id, LearningRecord.course_id == course_id, LearningRecord.occurred_at >= start_utc, LearningRecord.occurred_at < end_utc)) or 0
    if record_count:
        items.append(_item(course_id=course_id, item_type="weekly_report", item_id=course_id, title="生成学习周报", subtitle=f"最近 7 天有 {record_count} 条学习记录", reason=f"最近 7 天已有 {record_count} 条真实学习记录，可生成学习周报进行回顾。", signals=[base_signal("weekly_report"), Signal("recent_learning_records", "近期学习记录", min(1.0, record_count / 7), min(15.0, record_count * 2.0))], action=ACTION_MAP["weekly_report"]))
    items.sort(key=recommendation_sort_key)
    category_counts = {"all": len(items), **{name: 0 for name in CATEGORY_LABELS}}
    for item in items:
        category_counts[item["category"]] += 1
    if include_all_candidates:
        selected_items = items
        selection_mode = "all_candidates"
    elif category == "all":
        selected_items = select_diverse_recommendations(items, limit)
        selection_mode = "diverse"
    else:
        selected_items = [item for item in items if item["category"] == category][:limit]
        selection_mode = "category"
    strategy_summary = (
        "优先展示紧急学习任务，同时保留薄弱点、资料问答和学习复盘等不同类型的可执行建议。"
        if category == "all"
        else CATEGORY_STRATEGY_SUMMARIES[category]
    )
    return {
        "course": {"id": course.id, "name": course.name}, "target_date": target_date.isoformat(),
        "algorithm_version": ALGORITHM_VERSION,
        "strategy_summary": strategy_summary,
        "items": selected_items,
        "category_counts": category_counts,
        "selection": {
            "mode": selection_mode,
            "returned": len(selected_items),
            "candidate_total": len(items),
        },
    }


@router.get("/courses/{course_id}/recommendations")
async def course_recommendations(
    course_id: int, db: DBSession, current_user: CurrentUser, settings: AppSettings,
    target_date: date | None = None, limit: int = Query(6, ge=1, le=20),
    category: RecommendationQueryCategory = "all",
) -> dict:
    result = build_course_recommendations(db, current_user.id, course_id, target_date or _today_for_user(current_user), limit, category)

    # ---- Blend AI-powered suggestions ----
    llm_provider = get_llm_provider(settings)
    is_mock = settings.llm_provider.strip().lower() == "mock"
    if not is_mock and result.get("items"):
        try:
            course = db.get(Course, course_id)
            ai_result = await ai_recommend(
                db, llm_provider,
                user_id=current_user.id,
                course_id=course_id,
                course_name=course.name if course else "",
                exam_date=course.exam_date if course else None,
            )
            ai_summary = ai_result.get("summary", "")
            ai_items = ai_result.get("recommendations", [])
            if ai_summary:
                result["ai_summary"] = ai_summary
            if ai_items:
                result["ai_suggestions"] = ai_items[:3]
        except Exception:
            pass  # AI failure → keep rule-based only

    return ok(result)


@router.get("/courses/{course_id}/recommendations/resources")
def recommend_resources(course_id: int, db: DBSession, current_user: CurrentUser, limit: int = Query(5, ge=1, le=20)) -> dict:
    result = build_course_recommendations(db, current_user.id, course_id, _today_for_user(current_user), limit, "resource")
    return ok(result)


@router.get("/courses/{course_id}/recommendations/exercises")
def recommend_exercises(course_id: int, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="PRACTICE_RECOMMENDATIONS_NOT_IMPLEMENTED")


@router.post("/courses/{course_id}/behavior", status_code=status.HTTP_201_CREATED)
def track_behavior(course_id: int, payload: UserBehaviorTrack, db: DBSession, current_user: CurrentUser) -> dict:
    """Track user click/dwell behavior for AI recommendation weighting."""
    _owned_course(db, course_id, current_user.id)
    behavior = UserBehavior(
        user_id=current_user.id,
        course_id=course_id,
        action=payload.action,
        target_type=payload.target_type,
        target_id=payload.target_id,
        dwell_seconds=payload.dwell_seconds,
        weight=payload.weight,
    )
    db.add(behavior)
    db.commit()
    return ok({"id": behavior.id, "recorded": True})


@router.post("/courses/{course_id}/recommendations/feedback")
def recommendation_feedback(course_id: int, payload: CourseRecommendationFeedback, db: DBSession, current_user: CurrentUser) -> dict:
    _owned_course(db, course_id, current_user.id)
    candidates = build_course_recommendations(
        db, current_user.id, course_id, _today_for_user(current_user), 20, include_all_candidates=True
    )["items"]
    candidate = next((item for item in candidates if item["recommendation_key"] == payload.recommendation_key), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="RECOMMENDATION_NOT_FOUND")
    record = db.scalar(select(RecommendationRecord).where(
        RecommendationRecord.user_id == current_user.id,
        RecommendationRecord.course_id == course_id,
        RecommendationRecord.item_type == candidate["item_type"],
        RecommendationRecord.item_id == candidate["item_id"],
        RecommendationRecord.algorithm_version == ALGORITHM_VERSION,
        RecommendationRecord.feedback_action == payload.action,
    ))
    if record is None:
        record = RecommendationRecord(user_id=current_user.id, course_id=course_id, item_type=candidate["item_type"], item_id=candidate["item_id"], score=candidate["score"], reason=candidate["reason"], score_breakdown=candidate["score_breakdown"], algorithm_version=ALGORITHM_VERSION, feedback_action=payload.action)
        db.add(record); db.commit(); db.refresh(record)
    return ok({"record_id": record.id, "accepted": True, "action": record.feedback_action})


def _record_title(db: DBSession, record: RecommendationRecord, course: Course) -> str:
    if record.item_type == "study_task":
        task = db.scalar(select(StudyTask).where(StudyTask.id == record.item_id, StudyTask.course_id == course.id))
        return task.title if task is not None else "资源已不存在"
    if record.item_type == "mastery_review":
        point = db.scalar(select(KnowledgePoint).where(KnowledgePoint.id == record.item_id, KnowledgePoint.course_id == course.id))
        return f"复习：{point.name}" if point is not None else "资源已不存在"
    return {"course_chat": "使用课程问答复习", "create_plan": "创建学习计划", "upload_document": "上传学习资料", "weekly_report": "生成学习周报"}.get(record.item_type, "资源已不存在")


@router.get("/courses/{course_id}/recommendations/history")
def recommendation_history(course_id: int, db: DBSession, current_user: CurrentUser, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), action: str | None = Query(None), item_type: str | None = Query(None)) -> dict:
    course = _owned_course(db, course_id, current_user.id)
    statement = select(RecommendationRecord).where(RecommendationRecord.user_id == current_user.id, RecommendationRecord.course_id == course_id)
    if action is not None:
        statement = statement.where(RecommendationRecord.feedback_action == action)
    if item_type is not None:
        statement = statement.where(RecommendationRecord.item_type == item_type)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = list(db.scalars(statement.order_by(RecommendationRecord.updated_at.desc(), RecommendationRecord.id.desc()).offset(offset).limit(limit)))
    all_actions = list(db.scalars(select(RecommendationRecord.feedback_action).where(RecommendationRecord.user_id == current_user.id, RecommendationRecord.course_id == course_id)))
    return ok({"items": [{
        "record_id": item.id,
        "item_type": item.item_type,
        "category": category_for_item_type(item.item_type),
        "category_label": CATEGORY_LABELS[category_for_item_type(item.item_type)],
        "item_id": item.item_id,
        "title": _record_title(db, item, course),
        "score": item.score,
        "reason": item.reason,
        "feedback_action": item.feedback_action,
        "created_at": item.created_at.isoformat(),
    } for item in records], "total": total, "metrics": {name: all_actions.count(name) for name in ("clicked", "saved", "skipped")}})
