from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def apply_schema_migrations(engine: Engine) -> None:
    """Apply the small idempotent migrations used by the current create_all setup."""

    with engine.begin() as connection:
        preference_columns = {
            column["name"] for column in inspect(connection).get_columns("user_preferences")
        }
        if "onboarding_seen_version" not in preference_columns:
            connection.execute(
                text(
                    "ALTER TABLE user_preferences "
                    "ADD COLUMN onboarding_seen_version INTEGER NOT NULL DEFAULT 0"
                )
            )
        if "onboarding_completed_at" not in preference_columns:
            completed_type = (
                "TIMESTAMP WITH TIME ZONE"
                if engine.dialect.name == "postgresql"
                else "DATETIME"
            )
            connection.execute(
                text(
                    "ALTER TABLE user_preferences "
                    f"ADD COLUMN onboarding_completed_at {completed_type}"
                )
            )
        connection.execute(
            text(
                """
                DELETE FROM learning_records
                WHERE task_id IS NOT NULL
                  AND id NOT IN (
                    SELECT MIN(id)
                    FROM learning_records
                    WHERE task_id IS NOT NULL
                    GROUP BY task_id
                  )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_records_task_id
                ON learning_records (task_id)
                WHERE task_id IS NOT NULL
                """
            )
        )
