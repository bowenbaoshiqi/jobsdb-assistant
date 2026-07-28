import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from src.application.job_batch_discovery import JobBatchDiscoveryService
from src.application.job_batch_worker import JobBatchWorker


async def test_discovery_service_captures_at_most_15_and_marks_ready() -> None:
    repository = MagicMock()
    repository.current.return_value = SimpleNamespace(
        id="batch-1",
        keyword="AI Lead",
        status="discovering",
    )
    repository.historical_job_ids.return_value = {"old"}
    runner = AsyncMock(
        return_value={
            "captured": 20,
            "job_ids": [str(index) for index in range(20)],
        }
    )
    service = JobBatchDiscoveryService(repository, runner=runner)

    assert await service.run_next() is True

    runner.assert_awaited_once_with("AI Lead", 15, {"old"})
    repository.add_jobs.assert_called_once()
    assert len(repository.add_jobs.call_args.args[1]) == 15
    repository.mark_ready.assert_called_once_with("batch-1")


async def test_discovery_service_marks_zero_result_failed() -> None:
    repository = MagicMock()
    repository.current.return_value = SimpleNamespace(
        id="batch-1",
        keyword="AI Lead",
        status="discovering",
    )
    service = JobBatchDiscoveryService(
        repository,
        runner=AsyncMock(return_value={"captured": 0, "job_ids": []}),
    )

    assert await service.run_next() is True

    repository.mark_failed.assert_called_once()


async def test_worker_resumes_discovery_and_stops() -> None:
    service = SimpleNamespace(
        run_next=AsyncMock(side_effect=[True, False, False])
    )
    worker = JobBatchWorker(service=service, idle_poll_seconds=0.01)

    await worker.start()
    await asyncio.sleep(0.03)
    await worker.close()

    assert service.run_next.await_count >= 2
