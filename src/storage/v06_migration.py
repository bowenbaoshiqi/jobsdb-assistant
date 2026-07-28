"""SQLite schema for v0.6 approved-material application execution."""

import sqlite3


def add_v06_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE application_executions (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            package_id TEXT NOT NULL,
            account_alias TEXT NOT NULL,
            status TEXT NOT NULL CHECK(
                status IN (
                    'queued',
                    'preparing_resume',
                    'waiting_for_confirmation',
                    'submitting',
                    'waiting_for_human',
                    'submission_uncertain',
                    'submitted',
                    'failed',
                    'manual_handoff'
                )
            ),
            remote_resume_filename TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            error_code TEXT,
            error_message TEXT,
            screenshot_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE application_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL
                REFERENCES application_executions(id),
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_application_execution_runnable
        ON application_executions(status, created_at);

        CREATE INDEX idx_application_execution_job_account
        ON application_executions(job_id, account_alias, created_at);

        CREATE INDEX idx_application_execution_events
        ON application_execution_events(execution_id, created_at);
    """)
