import sqlite3
from pathlib import Path

import pytest

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
