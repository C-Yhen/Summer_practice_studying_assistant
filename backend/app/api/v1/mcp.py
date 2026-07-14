from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from backend.app.dependencies import CurrentUser, DBSession
from backend.app.models import MCPToolCall
from backend.app.responses import ok
from backend.app.schemas import MCPToolCallCreate

router = APIRouter(prefix="/mcp", tags=["mcp"])

READ_TOOLS = {
    "get_user_courses", "get_user_profile", "get_learning_history",
    "get_knowledge_mastery", "get_study_plan", "get_today_tasks",
    "get_wrong_questions", "recommend_resources", "recommend_exercises",
    "search_course_material", "get_available_time",
}
WRITE_TOOLS = {
    "create_study_task", "update_task_status", "create_calendar_event",
    "update_calendar_event", "delete_calendar_event", "reschedule_study_plan",
    "generate_weekly_report",
}


@router.get("/tools")
def list_tools(current_user: CurrentUser) -> dict:
    items = [
        {
            "name": name,
            "is_write": name in WRITE_TOOLS,
            "requires_confirmation": name in WRITE_TOOLS,
            "description": "学习助手受控工具",
        }
        for name in sorted(READ_TOOLS | WRITE_TOOLS)
    ]
    return ok({"items": items})


@router.post("/tool-calls")
def create_tool_call(payload: MCPToolCallCreate, db: DBSession, current_user: CurrentUser) -> dict:
    call = MCPToolCall(
        user_id=current_user.id,
        agent_run_id=payload.agent_run_id,
        tool_name=payload.tool_name,
        input_data=payload.input_data,
        output_data=payload.output_data,
        status=payload.status,
        error_message=payload.error_message,
        duration_ms=payload.duration_ms,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return ok({"id": call.id, "status": call.status})


@router.get("/tool-calls")
def list_tool_calls(db: DBSession, current_user: CurrentUser, tool_name: str | None = None) -> dict:
    statement = select(MCPToolCall).where(MCPToolCall.user_id == current_user.id)
    if tool_name:
        statement = statement.where(MCPToolCall.tool_name == tool_name)
    calls = list(db.scalars(statement.order_by(MCPToolCall.created_at.desc()).limit(100)))
    return ok({"items": [{"id": item.id, "agent_run_id": item.agent_run_id, "tool_name": item.tool_name, "status": item.status, "duration_ms": item.duration_ms, "error_message": item.error_message, "created_at": item.created_at.isoformat()} for item in calls], "total": len(calls)})
