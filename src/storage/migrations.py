"""Ordered, transactional SQLite schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime

# Bump alongside the newest migration registered by ``Database``.
CURRENT_SCHEMA_VERSION = 10


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


class MigrationRunner:
    def __init__(self, database_path: str, *, uri: bool = False):
        self.database_path = database_path
        self.uri = uri

    def apply(self, migrations: Sequence[Migration]) -> list[int]:
        versions = [migration.version for migration in migrations]
        duplicates = sorted(
            {version for version in versions if versions.count(version) > 1}
        )
        if duplicates:
            raise ValueError(f"duplicate migration version: {duplicates[0]}")

        applied: list[int] = []
        with closing(sqlite3.connect(self.database_path, uri=self.uri)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            conn.commit()
            existing = {
                row[0]
                for row in conn.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            for migration in sorted(migrations, key=lambda item: item.version):
                if migration.version in existing:
                    continue
                try:
                    conn.execute("BEGIN")
                    migration.apply(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) "
                        "VALUES (?, ?, ?)",
                        (
                            migration.version,
                            migration.name,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                applied.append(migration.version)
        return applied
