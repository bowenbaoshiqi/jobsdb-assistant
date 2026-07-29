"""v0.8 durable Agent session and work-item schema."""

import sqlite3


def add_v08_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL
                CHECK (status IN ('active', 'stopped', 'failed')),
            started_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            stopped_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_work_items (
            id TEXT PRIMARY KEY,
            internal_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'queued', 'claimed', 'human_required',
                        'completed', 'failed'
                    )
                ),
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

        CREATE INDEX IF NOT EXISTS idx_agent_work_claim
        ON agent_work_items(status, created_at);
        """
    )
