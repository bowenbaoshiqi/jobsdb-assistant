"""Run one persisted public-discovery job batch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.storage.job_batch_repository import JobBatchRepository

DiscoveryRunner = Callable[
    [str, int, set[str]],
    Awaitable[dict],
]
ScoringPreparer = Callable[[str, list[str]], Awaitable[None]]


class JobBatchDiscoveryService:
    def __init__(
        self,
        repository: JobBatchRepository,
        *,
        runner: DiscoveryRunner,
        scoring_preparer: ScoringPreparer | None = None,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.scoring_preparer = scoring_preparer

    async def run_next(self) -> bool:
        batch = self.repository.current()
        if batch is None:
            return False
        if batch.status == "waiting_for_scoring":
            if self.scoring_preparer is None:
                return False
            try:
                await self.scoring_preparer(
                    batch.id,
                    self.repository.current_job_ids(),
                )
                self.repository.mark_scoring(batch.id)
            except Exception as exc:
                self.repository.mark_failed(batch.id, str(exc))
            return True
        if batch.status != "discovering":
            return False
        try:
            report = await self.runner(
                batch.keyword,
                15,
                self.repository.historical_job_ids(),
            )
            job_ids = list(dict.fromkeys(report.get("job_ids", [])))[:15]
            if report.get("error") or not job_ids:
                self.repository.mark_failed(
                    batch.id,
                    report.get("error") or "no eligible jobs found",
                )
                return True
            self.repository.add_jobs(
                batch.id,
                job_ids,
                now=datetime.now(UTC),
            )
            self.repository.mark_ready(batch.id)
        except Exception as exc:
            self.repository.mark_failed(batch.id, str(exc))
        return True
