"""Immutable SQLite persistence for native career-ops evaluations."""

import sqlite3

from src.domain.evaluation import EvaluationCacheKey, JobEvaluation
from src.storage.database import Database


class EvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(
        self,
        evaluation: JobEvaluation,
        cache_key: EvaluationCacheKey,
    ) -> None:
        if evaluation.created_at is None:
            raise ValueError("evaluation created_at is required")
        try:
            with self.database._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO job_evaluations (
                        id, job_snapshot_id, profile_version, cache_key,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evaluation.id,
                        int(evaluation.job_snapshot_id),
                        evaluation.profile_version,
                        cache_key.digest(),
                        evaluation.model_dump_json(),
                        evaluation.created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "job_evaluations.cache_key" in str(exc):
                raise ValueError(
                    "evaluation cache key already exists"
                ) from exc
            raise

    def find_by_cache_key(
        self,
        cache_key: EvaluationCacheKey,
    ) -> JobEvaluation | None:
        with self.database._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM job_evaluations WHERE cache_key = ?",
                (cache_key.digest(),),
            ).fetchone()
        if row is None:
            return None
        return JobEvaluation.model_validate_json(row["payload_json"])
