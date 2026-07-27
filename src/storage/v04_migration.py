"""SQLite schema for the local v0.4 review Dashboard."""

import sqlite3


def add_v04_schema(conn: sqlite3.Connection) -> None:
    """Add current selections and durable direct-application tasks."""
    conn.executescript("""
        CREATE TABLE job_selections (
            job_id TEXT PRIMARY KEY REFERENCES jobs(id),
            status TEXT NOT NULL
                CHECK(status = 'waiting_for_materials'),
            selected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE dashboard_application_tasks (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            status TEXT NOT NULL,
            resume_mode TEXT NOT NULL
                CHECK(resume_mode = 'jobsdb_default'),
            cover_letter_mode TEXT NOT NULL
                CHECK(cover_letter_mode = 'none'),
            session_id TEXT,
            error_message TEXT,
            screenshot_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX idx_dashboard_one_active_application
        ON dashboard_application_tasks((1))
        WHERE status = 'applying';

        CREATE INDEX idx_dashboard_application_job
        ON dashboard_application_tasks(job_id, created_at);
    """)
