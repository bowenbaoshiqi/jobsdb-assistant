"""SQLite schema for immutable v0.5 tailored application materials."""

import sqlite3


def add_v05_schema(conn: sqlite3.Connection) -> None:
    """Add material generation tasks, versioned packages, and review events."""
    conn.executescript("""
        CREATE TABLE material_tasks (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            snapshot_id INTEGER NOT NULL REFERENCES job_snapshots(id),
            profile_version INTEGER NOT NULL CHECK(profile_version > 0),
            evaluation_id TEXT NOT NULL,
            target_version INTEGER NOT NULL CHECK(target_version > 0),
            status TEXT NOT NULL CHECK(
                status IN (
                    'waiting_for_agent',
                    'generating',
                    'generated',
                    'failed'
                )
            ),
            feedback TEXT,
            payload_json TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE material_packages (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL UNIQUE REFERENCES material_tasks(id),
            job_id TEXT NOT NULL REFERENCES jobs(id),
            version INTEGER NOT NULL CHECK(version > 0),
            review_status TEXT NOT NULL CHECK(
                review_status IN (
                    'pending_review',
                    'pending_review_with_fact_warning',
                    'approved',
                    'approved_with_fact_override',
                    'rejected',
                    'superseded'
                )
            ),
            is_current_approved INTEGER NOT NULL DEFAULT 0
                CHECK(is_current_approved IN (0, 1)),
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(job_id, version)
        );

        CREATE TABLE material_review_events (
            id TEXT PRIMARY KEY,
            package_id TEXT NOT NULL REFERENCES material_packages(id),
            action TEXT NOT NULL CHECK(
                action IN ('approve', 'reject', 'regenerate')
            ),
            feedback TEXT,
            fact_warning_overridden INTEGER NOT NULL DEFAULT 0
                CHECK(fact_warning_overridden IN (0, 1)),
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_material_tasks_batch
        ON material_tasks(batch_id, created_at);

        CREATE INDEX idx_material_tasks_job_status
        ON material_tasks(job_id, status, created_at);

        CREATE INDEX idx_material_packages_job_version
        ON material_packages(job_id, version);

        CREATE UNIQUE INDEX idx_material_one_current_approved
        ON material_packages(job_id)
        WHERE is_current_approved = 1;

        CREATE INDEX idx_material_review_package
        ON material_review_events(package_id, created_at);
    """)
