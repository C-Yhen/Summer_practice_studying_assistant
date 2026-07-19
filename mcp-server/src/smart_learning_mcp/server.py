"""MCP tool facade for learning, recommendation, planning, and calendars."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Awaitable, Callable

from mcp.server.fastmcp import FastMCP

from .client import BackendClient
from .confirmation import ConfirmationError, ConfirmationManager

mcp = FastMCP("Smart Learning Assistant")
client = BackendClient()
confirmations = ConfirmationManager(
    secret=os.getenv("MCP_CONFIRMATION_SECRET", "development-only-secret"),
    ttl_seconds=int(os.getenv("MCP_CONFIRMATION_TTL_SECONDS", "300")),
)


async def _run(
    *,
    tool_name: str,
    user_id: int,
    input_data: dict[str, Any],
    operation: Callable[[], Awaitable[Any]],
    agent_run_id: str = "",
) -> dict[str, Any]:
    run_id = agent_run_id or str(uuid.uuid4())
    started_at = time.perf_counter()
    try:
        result = await operation()
        await client.audit(
            user_id=user_id,
            agent_run_id=run_id,
            tool_name=tool_name,
            input_data=input_data,
            output_data=result,
            status="success",
            error=None,
            started_at=started_at,
        )
        return {"ok": True, "data": result, "agent_run_id": run_id}
    except Exception as exc:
        await client.audit(
            user_id=user_id,
            agent_run_id=run_id,
            tool_name=tool_name,
            input_data=input_data,
            output_data=None,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        return {"ok": False, "error": str(exc), "agent_run_id": run_id}


async def _write_with_confirmation(
    *,
    tool_name: str,
    user_id: int,
    payload: dict[str, Any],
    confirmation_token: str,
    operation: Callable[[], Awaitable[Any]],
    agent_run_id: str = "",
) -> dict[str, Any]:
    if not confirmation_token:
        started_at = time.perf_counter()
        result = {
            "ok": False,
            "status": "confirmation_required",
            "message": "这是写操作。请向用户展示 preview，得到明确同意后携带 confirmation_token 再调用。",
            "preview": payload,
            "confirmation_token": confirmations.issue(
                user_id=user_id, tool_name=tool_name, payload=payload
            ),
            "expires_in_seconds": confirmations.ttl_seconds,
        }
        await client.audit(
            user_id=user_id,
            agent_run_id=agent_run_id or str(uuid.uuid4()),
            tool_name=tool_name,
            input_data=payload,
            output_data=result,
            status="waiting_for_user",
            error=None,
            started_at=started_at,
        )
        return result
    try:
        confirmations.verify(
            confirmation_token,
            user_id=user_id,
            tool_name=tool_name,
            payload=payload,
        )
    except ConfirmationError as exc:
        started_at = time.perf_counter()
        result = {"ok": False, "status": "invalid_confirmation", "error": str(exc)}
        await client.audit(
            user_id=user_id,
            agent_run_id=agent_run_id or str(uuid.uuid4()),
            tool_name=tool_name,
            input_data=payload,
            output_data=result,
            status="failed",
            error=str(exc),
            started_at=started_at,
        )
        return result
    return await _run(
        tool_name=tool_name,
        user_id=user_id,
        input_data=payload,
        operation=operation,
        agent_run_id=agent_run_id,
    )


async def _calendar_preview(*, tool_name: str, user_id: int, payload: dict[str, Any], path: str, access_token: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calendar writes use the backend's confirmation token, never MCP-local tokens."""
    started_at = time.perf_counter()
    try:
        result = await client.request("POST", path, user_id=user_id, access_token=access_token, json=json or payload)
        data = result.get("data", result) if isinstance(result, dict) else result
        safe_output = dict(data) if isinstance(data, dict) else {"preview": data}
        await client.audit(user_id=user_id, agent_run_id=str(uuid.uuid4()), tool_name=tool_name, input_data=payload, output_data=safe_output, status="waiting_for_user", error=None, started_at=started_at)
        return {"ok": False, "status": "confirmation_required", "preview": safe_output.get("preview", safe_output), "confirmation_token": safe_output.get("confirmation_token"), "expires_in_seconds": safe_output.get("expires_in_seconds", 300)}
    except Exception as exc:
        await client.audit(user_id=user_id, agent_run_id=str(uuid.uuid4()), tool_name=tool_name, input_data=payload, output_data=None, status="failed", error=str(exc), started_at=started_at)
        return {"ok": False, "error": str(exc)}


@mcp.tool()
async def get_user_courses(user_id: int, access_token: str = "") -> dict[str, Any]:
    """查询当前用户有权访问的课程。只读，不需要确认。"""
    return await _run(tool_name="get_user_courses", user_id=user_id, input_data={}, operation=lambda: client.request("GET", "/courses", user_id=user_id, access_token=access_token))


@mcp.tool()
async def get_user_profile(user_id: int, course_id: int | None = None, access_token: str = "") -> dict[str, Any]:
    """查询用户偏好与课程画像。只读，不需要确认。"""
    params = {"course_id": course_id} if course_id else {}
    return await _run(tool_name="get_user_profile", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/users/me/profile", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def get_learning_history(user_id: int, course_id: int, limit: int = 30, access_token: str = "") -> dict[str, Any]:
    """查询课程学习历史。只读，不需要确认。"""
    params = {"course_id": course_id, "limit": min(max(limit, 1), 100)}
    return await _run(tool_name="get_learning_history", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/learning-records", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def get_knowledge_mastery(user_id: int, course_id: int, access_token: str = "") -> dict[str, Any]:
    """查询课程知识点掌握度。只读，不需要确认。"""
    params = {"course_id": course_id}
    return await _run(tool_name="get_knowledge_mastery", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/mastery", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def get_study_plan(user_id: int, course_id: int, access_token: str = "") -> dict[str, Any]:
    """查询当前有效学习计划和版本。只读，不需要确认。"""
    params = {"course_id": course_id}
    return await _run(tool_name="get_study_plan", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/plans/current", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def get_today_tasks(user_id: int, course_id: int | None = None, access_token: str = "") -> dict[str, Any]:
    """查询今日任务。只读，不需要确认。"""
    params = {"course_id": course_id} if course_id else {}
    return await _run(tool_name="get_today_tasks", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/plans/tasks/today", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def create_study_task(user_id: int, plan_id: int, task: dict[str, Any], confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """创建学习任务。写操作，必须先向用户展示预览并二次确认。"""
    payload = {"plan_id": plan_id, "task": task}
    return await _write_with_confirmation(tool_name="create_study_task", user_id=user_id, payload=payload, confirmation_token=confirmation_token, operation=lambda: client.request("POST", f"/plans/{plan_id}/tasks", user_id=user_id, access_token=access_token, json=task, idempotency_key=idempotency_key))


@mcp.tool()
async def update_task_status(user_id: int, task_id: int, status: str, actual_minutes: int | None = None, confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """更新任务状态。写操作，必须二次确认；幂等键防止重复提交。"""
    payload = {"task_id": task_id, "status": status, "actual_minutes": actual_minutes}
    return await _write_with_confirmation(tool_name="update_task_status", user_id=user_id, payload=payload, confirmation_token=confirmation_token, operation=lambda: client.request("PATCH", f"/plans/tasks/{task_id}", user_id=user_id, access_token=access_token, json=payload, idempotency_key=idempotency_key))


@mcp.tool()
async def get_wrong_questions(user_id: int, course_id: int, only_unmastered: bool = True, access_token: str = "") -> dict[str, Any]:
    """查询错题本。只读，不需要确认。"""
    params = {"course_id": course_id, "only_unmastered": only_unmastered}
    return await _run(tool_name="get_wrong_questions", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/wrong-questions", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def recommend_resources(user_id: int, course_id: int, limit: int = 5, access_token: str = "") -> dict[str, Any]:
    """按掌握度、难度、偏好和质量推荐资料，并返回理由。"""
    params = {"course_id": course_id, "limit": min(max(limit, 1), 20)}
    return await _run(tool_name="recommend_resources", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/recommendations/resources", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def recommend_exercises(user_id: int, course_id: int, limit: int = 5, access_token: str = "") -> dict[str, Any]:
    """推荐匹配薄弱知识点的练习题，并返回可解释分数。"""
    params = {"course_id": course_id, "limit": min(max(limit, 1), 20)}
    return await _run(tool_name="recommend_exercises", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/recommendations/exercises", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def search_course_material(user_id: int, course_id: int, query: str, top_k: int = 5, access_token: str = "") -> dict[str, Any]:
    """检索课程资料，返回文档、页码、章节和原文片段。"""
    payload = {"course_id": course_id, "query": query, "top_k": min(max(top_k, 1), 20), "strict": True}
    return await _run(tool_name="search_course_material", user_id=user_id, input_data=payload, operation=lambda: client.request("POST", "/rag/search", user_id=user_id, access_token=access_token, json=payload))


@mcp.tool()
async def get_available_time(user_id: int, start_at: str, end_at: str, minimum_minutes: int = 30, access_token: str = "") -> dict[str, Any]:
    """查询指定时间范围的日历空闲时段。只读，不需要确认。"""
    params = {"start_at": start_at, "end_at": end_at, "minimum_minutes": min(max(minimum_minutes, 1), 1440)}
    return await _run(tool_name="get_available_time", user_id=user_id, input_data=params, operation=lambda: client.request("GET", "/calendar/availability", user_id=user_id, access_token=access_token, params=params))


@mcp.tool()
async def create_calendar_event(user_id: int, event: dict[str, Any], confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """创建日历事件。写第三方服务前必须二次确认，且要求幂等键。"""
    payload = {**event, **({"idempotency_key": idempotency_key} if idempotency_key else {})}
    if not confirmation_token:
        return await _calendar_preview(tool_name="create_calendar_event", user_id=user_id, payload=payload, path="/calendar/events/preview", access_token=access_token)
    return await _run(tool_name="create_calendar_event", user_id=user_id, input_data=payload, operation=lambda: client.request("POST", "/calendar/events", user_id=user_id, access_token=access_token, json=payload, idempotency_key=idempotency_key, confirmation_token=confirmation_token))


@mcp.tool()
async def update_calendar_event(user_id: int, event_id: int, changes: dict[str, Any], confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """修改日历事件。写第三方服务前必须二次确认。"""
    payload = {"event_id": event_id, "changes": changes}
    if not confirmation_token:
        return await _calendar_preview(tool_name="update_calendar_event", user_id=user_id, payload=payload, path=f"/calendar/events/{event_id}/preview-update", access_token=access_token, json=changes)
    return await _run(tool_name="update_calendar_event", user_id=user_id, input_data=payload, operation=lambda: client.request("PATCH", f"/calendar/events/{event_id}", user_id=user_id, access_token=access_token, json=changes, idempotency_key=idempotency_key, confirmation_token=confirmation_token))


@mcp.tool()
async def delete_calendar_event(user_id: int, event_id: int, confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """删除日历事件。破坏性写操作，必须二次确认。"""
    payload = {"event_id": event_id}
    if not confirmation_token:
        return await _calendar_preview(tool_name="delete_calendar_event", user_id=user_id, payload=payload, path=f"/calendar/events/{event_id}/preview-delete", access_token=access_token)
    return await _run(tool_name="delete_calendar_event", user_id=user_id, input_data=payload, operation=lambda: client.request("DELETE", f"/calendar/events/{event_id}", user_id=user_id, access_token=access_token, idempotency_key=idempotency_key, confirmation_token=confirmation_token))


@mcp.tool()
async def reschedule_study_plan(user_id: int, plan_id: int, reason: str, available_minutes_per_day: int | None = None, confirmation_token: str = "", idempotency_key: str = "", access_token: str = "") -> dict[str, Any]:
    """生成新的计划版本，不覆盖旧版。执行前必须展示差异并二次确认。"""
    payload = {"reason": reason, "available_minutes_per_day": available_minutes_per_day}
    return await _write_with_confirmation(tool_name="reschedule_study_plan", user_id=user_id, payload={"plan_id": plan_id, **payload}, confirmation_token=confirmation_token, operation=lambda: client.request("POST", f"/plans/{plan_id}/reschedule", user_id=user_id, access_token=access_token, json=payload, idempotency_key=idempotency_key))


@mcp.tool()
async def generate_weekly_report(user_id: int, course_id: int, week_start: str, access_token: str = "") -> dict[str, Any]:
    """提交学习周报长时任务，返回可查询进度的 task_id。"""
    payload = {"task_type": "weekly_report", "course_id": course_id, "week_start": week_start}
    return await _run(tool_name="generate_weekly_report", user_id=user_id, input_data=payload, operation=lambda: client.request("POST", "/tasks", user_id=user_id, access_token=access_token, json=payload, idempotency_key=f"weekly-report:{user_id}:{course_id}:{week_start}"))


def main() -> None:
    """Run the MCP server over stdio (the default desktop integration transport)."""
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
