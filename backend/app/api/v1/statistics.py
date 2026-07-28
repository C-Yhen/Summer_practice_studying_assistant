from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import StringIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.app.dependencies import CurrentUser, DBSession
from backend.app.responses import ok
from backend.app.services.statistics import build_statistics_overview
from backend.app.services.timezones import resolve_user_timezone

router = APIRouter(prefix="/statistics", tags=["statistics"])


def _end_date(end_date: date | None, timezone_name: str | None) -> date:
    if end_date is not None:
        return end_date
    user_zone, _ = resolve_user_timezone(timezone_name)
    return datetime.now(timezone.utc).astimezone(user_zone).date()


def _overview_or_404(db: DBSession, current_user: CurrentUser, days: int, course_id: int | None, end_date: date | None) -> dict:
    payload = build_statistics_overview(
        db,
        user_id=current_user.id,
        timezone_name=current_user.timezone,
        days=days,
        end=_end_date(end_date, current_user.timezone),
        course_id=course_id,
    )
    if payload.get("not_found"):
        raise HTTPException(status_code=404, detail="Course not found")
    return payload


@router.get("/overview")
def overview(
    db: DBSession,
    current_user: CurrentUser,
    days: int = Query(7, ge=1, le=90),
    course_id: int | None = Query(None, gt=0),
    end_date: date | None = None,
) -> dict:
    return ok(_overview_or_404(db, current_user, days, course_id, end_date))


def _safe_csv_cell(value: object) -> str:
    text = str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


@router.get("/export.csv")
def export_csv(
    db: DBSession,
    current_user: CurrentUser,
    days: int = Query(7, ge=1, le=90),
    course_id: int | None = Query(None, gt=0),
    end_date: date | None = None,
) -> Response:
    payload = _overview_or_404(db, current_user, days, course_id, end_date)
    scope_name = payload["scope"]["course_name"] or "全部未归档课程"
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["日期", "课程范围", "实际学习分钟", "计划学习分钟", "完成任务数", "任务总数", "练习次数", "正确次数", "练习正确率"])
    for item in payload["daily"]:
        accuracy = "" if item["practice_accuracy"] is None else f"{item['practice_accuracy']:.4f}"
        writer.writerow([
            item["date"],
            _safe_csv_cell(scope_name),
            round(item["actual_learning_seconds"] / 60, 2),
            item["planned_minutes"],
            item["task_completed"],
            item["task_total"],
            item["practice_attempts"],
            item["practice_correct"],
            accuracy,
        ])
    range_info = payload["range"]
    filename = f"study-statistics-{range_info['start_date']}-to-{range_info['end_date']}.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
