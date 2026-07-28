from __future__ import annotations

import json
import os
import sys
from datetime import date

from sqlalchemy import select

sys.path.insert(0, "/app")

from backend.app.database import Database
from backend.app.models import AsyncTask, Course, User


def main() -> None:
    action, email, raw_course_id = sys.argv[1:4]
    database = Database(os.environ["DATABASE_URL"])
    with database.session_factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit("seed owner not found")
        course_id = int(raw_course_id)
        course = db.scalar(
            select(Course).where(
                Course.id == course_id,
                Course.owner_id == user.id,
                Course.archived.is_(False),
            )
        )
        if course is None:
            raise SystemExit("seed owner/course not found")

        if action == "async-states":
            queued = AsyncTask(
                user_id=user.id,
                task_type="weekly_report",
                resource_type="course",
                resource_id=str(course.id),
                status="queued",
                progress=0,
                current_step="queued",
                input_data={
                    "start_date": date.today().isoformat(),
                    "end_date": date.today().isoformat(),
                    "course_id": course.id,
                },
            )
            failed = AsyncTask(
                user_id=user.id,
                task_type="weekly_report",
                resource_type="course",
                resource_id=str(course.id),
                status="failed",
                progress=40,
                current_step="dispatch_failed",
                input_data={
                    "start_date": date.today().isoformat(),
                    "end_date": date.today().isoformat(),
                    "course_id": course.id,
                },
                error_message="E2E_RETRYABLE_FAILURE",
            )
            db.add_all([queued, failed])
            db.commit()
            print(json.dumps({"queued": queued.public_id, "failed": failed.public_id}))
            return

        if action == "legacy-report":
            report = AsyncTask(
                user_id=user.id,
                task_type="weekly_report",
                resource_type="course",
                resource_id=str(course.id),
                status="success",
                progress=100,
                current_step="completed",
                input_data={
                    "start_date": date.today().isoformat(),
                    "end_date": date.today().isoformat(),
                    "course_id": course.id,
                },
                result_data={
                    "range_start": date.today().isoformat(),
                    "range_end": date.today().isoformat(),
                    "total_learning_minutes": 5,
                    "study_days": 1,
                    "scheduled_tasks": 0,
                    "completed_tasks": 0,
                    "completion_rate": 0,
                    "course_names": [course.name],
                    "weak_points": [],
                    "summary": "旧结构周报兼容内容",
                },
            )
            db.add(report)
            db.commit()
            print(json.dumps({"task_id": report.public_id}))
            return
        raise SystemExit(f"unknown seed action: {action}")


if __name__ == "__main__":
    main()
