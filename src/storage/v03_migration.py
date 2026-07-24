"""SQLite schema for candidate and evaluation workflows."""

import sqlite3


def add_v03_schema(conn: sqlite3.Connection) -> None:
    """Add immutable profile, checkpoint, and evaluation records."""
    conn.executescript("""
        CREATE TABLE integration_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id TEXT NOT NULL,
            expected_commit TEXT NOT NULL,
            observed_commit TEXT,
            status TEXT NOT NULL,
            observed_at TEXT NOT NULL
        );

        CREATE TABLE workflow_runs (
            id TEXT PRIMARY KEY,
            keyword TEXT NOT NULL,
            stage TEXT NOT NULL,
            condition TEXT NOT NULL,
            warning TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE workflow_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            from_stage TEXT NOT NULL,
            event TEXT NOT NULL,
            to_stage TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE candidate_profile_proposals (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            payload_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        );

        CREATE TABLE candidate_profiles (
            id TEXT PRIMARY KEY,
            version INTEGER NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            confirmed_at TEXT NOT NULL
        );

        CREATE TABLE ai_tasks (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            contract_version TEXT NOT NULL,
            integration_id TEXT NOT NULL,
            integration_commit TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE ai_task_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES ai_tasks(id),
            attempt INTEGER NOT NULL,
            result_hash TEXT,
            error_category TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, attempt)
        );

        CREATE TABLE job_evaluations (
            id TEXT PRIMARY KEY,
            job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots(id),
            profile_version INTEGER NOT NULL,
            cache_key TEXT NOT NULL UNIQUE,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE evaluation_run_jobs (
            run_id TEXT NOT NULL REFERENCES workflow_runs(id),
            job_snapshot_id INTEGER NOT NULL REFERENCES job_snapshots(id),
            evaluation_id TEXT REFERENCES job_evaluations(id),
            status TEXT NOT NULL,
            error_category TEXT,
            PRIMARY KEY(run_id, job_snapshot_id)
        );

        CREATE INDEX idx_workflow_runs_condition
        ON workflow_runs(condition);
        CREATE INDEX idx_ai_tasks_run_status
        ON ai_tasks(run_id, status);
        CREATE UNIQUE INDEX idx_candidate_profiles_one_active
        ON candidate_profiles(is_active) WHERE is_active = 1;
        CREATE INDEX idx_job_evaluations_cache_key
        ON job_evaluations(cache_key);
    """)
