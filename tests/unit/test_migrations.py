import sqlite3
from pathlib import Path

import pytest

from src.storage.database import Database
from src.storage.migrations import Migration, MigrationRunner


def test_runner_applies_ordered_migrations_once(tmp_path: Path) -> None:
    db_path = tmp_path / "jobsdb.db"

    def create_example(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    runner = MigrationRunner(str(db_path))
    first = runner.apply([Migration(1, "create example", create_example)])
    second = runner.apply([Migration(1, "create example", create_example)])

    assert first == [1]
    assert second == []


def test_runner_rolls_back_failed_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "jobsdb.db"

    def fail_after_create(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE should_rollback (id INTEGER)")
        raise RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        MigrationRunner(str(db_path)).apply(
            [Migration(1, "failing migration", fail_after_create)]
        )

    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'should_rollback'"
        ).fetchone()
        recorded = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = 1"
        ).fetchone()

    assert table is None
    assert recorded is None


def test_runner_rejects_duplicate_versions(tmp_path: Path) -> None:
    migration = Migration(1, "one", lambda conn: None)

    with pytest.raises(ValueError, match="duplicate migration version: 1"):
        MigrationRunner(str(tmp_path / "jobsdb.db")).apply([migration, migration])


def test_database_applies_agent_work_migration(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "jobsdb.db"))

    with database._connect() as conn:
        version = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 8"
        ).fetchone()
        tables = {
            row["name"]
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'agent_%'
                """
            ).fetchall()
        }

    assert version["name"] == "v0.8 agent work protocol"
    assert tables == {"agent_sessions", "agent_work_items"}


def test_database_upgrades_historical_v08_agent_work_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "historical-v08.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (8, 'v0.8 agent work protocol', '2026-07-29T00:00:00+00:00');

            CREATE TABLE agent_sessions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                heartbeat_at TEXT NOT NULL,
                stopped_at TEXT
            );
            CREATE TABLE agent_work_items (
                id TEXT PRIMARY KEY,
                internal_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                task_path TEXT NOT NULL,
                result_path TEXT NOT NULL,
                capability_paths_json TEXT NOT NULL,
                session_id TEXT REFERENCES agent_sessions(id),
                attempt INTEGER NOT NULL DEFAULT 0,
                lease_expires_at TEXT,
                result_hash TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            """
        )

    database = Database(str(db_path))

    with database._connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(agent_work_items)"
            ).fetchall()
        }
        version = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 9"
        ).fetchone()

    assert "metadata_json" in columns
    assert version["name"] == "repair v0.8 agent work metadata"
