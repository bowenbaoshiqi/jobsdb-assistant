import sqlite3

from src.storage.database import Database


def test_database_applies_parallel_pool_schema_once(tmp_path) -> None:
    path = tmp_path / "jobs.db"

    Database(str(path))
    Database(str(path))

    with sqlite3.connect(path) as conn:
        version = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 10"
        ).fetchone()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert version[0] == "v0.9 parallel evaluation pool"
    assert {
        "agent_pools",
        "agent_pool_slots",
        "agent_evaluation_batch_tasks",
    } <= tables

