import asyncio
from unittest.mock import AsyncMock

import pytest

from src.application.approved_worker import ApprovedApplicationWorker


@pytest.mark.asyncio
async def test_worker_polls_execution_service_and_closes_runtime() -> None:
    service = AsyncMock()
    calls = 0

    async def run_next() -> bool:
        nonlocal calls
        calls += 1
        return calls == 1

    service.run_next.side_effect = run_next
    runtime = AsyncMock()
    worker = ApprovedApplicationWorker(
        service=service,
        runtime=runtime,
        idle_poll_seconds=0.01,
    )

    await worker.start()
    await asyncio.sleep(0.03)
    await worker.close()

    assert service.run_next.await_count >= 2
    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_start_is_idempotent() -> None:
    service = AsyncMock()
    service.run_next.return_value = False
    runtime = AsyncMock()
    worker = ApprovedApplicationWorker(
        service=service,
        runtime=runtime,
        idle_poll_seconds=0.01,
    )

    await worker.start()
    task = worker.task
    await worker.start()

    assert worker.task is task
    await worker.close()
