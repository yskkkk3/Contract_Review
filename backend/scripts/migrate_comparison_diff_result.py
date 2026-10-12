"""Expand comparison_tasks.diff_result for large comparison JSON payloads.

This migration is idempotent and only changes MySQL databases. SQLite does not
need it because its TEXT storage is not limited to 64 KiB.
"""

from sqlalchemy import text

from app.core.db import engine


def migrate() -> bool:
    """Return True when the column was altered, False when no change was needed."""
    if engine.dialect.name != "mysql":
        print(f"skip: dialect {engine.dialect.name} does not require LONGTEXT")
        return False

    with engine.begin() as connection:
        data_type = connection.execute(
            text(
                """
                SELECT DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'comparison_tasks'
                  AND COLUMN_NAME = 'diff_result'
                """
            )
        ).scalar_one_or_none()

        if data_type is None:
            raise RuntimeError("comparison_tasks.diff_result does not exist")
        if data_type.lower() == "longtext":
            print("ok: comparison_tasks.diff_result is already LONGTEXT")
            return False

        connection.execute(
            text(
                "ALTER TABLE comparison_tasks "
                "MODIFY COLUMN diff_result LONGTEXT NOT NULL"
            )
        )
        print(f"migrated: comparison_tasks.diff_result {data_type.upper()} -> LONGTEXT")
        return True


if __name__ == "__main__":
    migrate()
