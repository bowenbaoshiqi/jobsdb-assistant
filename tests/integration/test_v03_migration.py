import sqlite3
from pathlib import Path

from src.storage.database import Database


def test_migration_three_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "jobs.db"

    Database(str(path))
    Database(str(path))

    with sqlite3.connect(path) as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert versions == [(1,), (2,), (3,)]
    assert {
        "integration_observations",
        "workflow_runs",
        "workflow_transitions",
        "candidate_profile_proposals",
        "candidate_profiles",
        "ai_tasks",
        "ai_task_attempts",
        "job_evaluations",
        "evaluation_run_jobs",
    } <= tables
