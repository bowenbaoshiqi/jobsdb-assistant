"""Durable state for the v0.9 parallel evaluation worker pool."""

import sqlite3


def add_v10_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_pools (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES agent_sessions(id),
            kind TEXT NOT NULL,
            batch_key TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_concurrency INTEGER NOT NULL
                CHECK (requested_concurrency = 3),
            actual_concurrency INTEGER NOT NULL
                CHECK (actual_concurrency BETWEEN 0 AND 3),
            capability_context_id TEXT NOT NULL,
            profile_context_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_pool_slots (
            pool_id TEXT NOT NULL REFERENCES agent_pools(id),
            slot_token TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 1 AND 3),
            status TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1,
            current_work_id TEXT REFERENCES agent_work_items(id),
            assignment_count INTEGER NOT NULL DEFAULT 0,
            heartbeat_at TEXT,
            PRIMARY KEY (pool_id, slot_token),
            UNIQUE (pool_id, ordinal)
        );

        CREATE TABLE IF NOT EXISTS agent_evaluation_batch_tasks (
            pool_id TEXT NOT NULL REFERENCES agent_pools(id),
            work_id TEXT NOT NULL REFERENCES agent_work_items(id),
            ordinal INTEGER NOT NULL,
            slot_ordinal INTEGER NOT NULL CHECK (slot_ordinal BETWEEN 1 AND 3),
            PRIMARY KEY (pool_id, work_id),
            UNIQUE (pool_id, ordinal)
        );

        CREATE INDEX IF NOT EXISTS idx_agent_pools_session
            ON agent_pools(session_id, status);
        CREATE INDEX IF NOT EXISTS idx_agent_pool_slots_work
            ON agent_pool_slots(current_work_id);
        CREATE INDEX IF NOT EXISTS idx_agent_batch_tasks_slot
            ON agent_evaluation_batch_tasks(pool_id, slot_ordinal, ordinal);
        """
    )
