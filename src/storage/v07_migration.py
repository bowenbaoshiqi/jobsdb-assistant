"""v0.7 local job-batch schema."""

import sqlite3


def add_v07_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS job_batches (
            id TEXT PRIMARY KEY,
            keyword TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            archived_at TEXT,
            error_code TEXT,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS job_batch_jobs (
            batch_id TEXT NOT NULL REFERENCES job_batches(id),
            job_id TEXT NOT NULL REFERENCES jobs(id),
            position INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (batch_id, job_id),
            UNIQUE (batch_id, position)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_current_job_batch
        ON job_batches((1))
        WHERE archived_at IS NULL;

        CREATE INDEX IF NOT EXISTS idx_job_batch_jobs_job
        ON job_batch_jobs(job_id);
        """
    )
