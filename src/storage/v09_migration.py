"""Repair historical v0.8 Agent work tables created before metadata support."""

import sqlite3


def add_v09_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(agent_work_items)"
        ).fetchall()
    }
    if "metadata_json" not in columns:
        conn.execute(
            "ALTER TABLE agent_work_items "
            "ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
        )
