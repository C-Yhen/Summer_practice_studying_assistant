from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def apply_schema_migrations(engine: Engine) -> None:
    """Apply the small idempotent migrations used by the current create_all setup."""

    with engine.begin() as connection:
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
