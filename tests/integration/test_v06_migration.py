import sqlite3
from pathlib import Path

from src.storage.database import Database


def test_database_applies_v06_schema_once(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"

    Database(str(path))
    Database(str(path))

    with sqlite3.connect(path) as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        execution_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(application_executions)"
            ).fetchall()
        }
        event_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(application_execution_events)"
            ).fetchall()
        }

    assert versions[-1] == (9,)
    assert versions.count((6,)) == 1
    assert {
        "id",
        "idempotency_key",
        "job_id",
        "package_id",
        "status",
        "payload_json",
    } <= execution_columns
    assert {"execution_id", "from_status", "to_status", "created_at"} <= (
        event_columns
    )
