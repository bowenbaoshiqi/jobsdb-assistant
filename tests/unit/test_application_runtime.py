from unittest.mock import AsyncMock

import pytest

from src.application.approved_runtime import ApprovedApplicationRuntime


@pytest.mark.asyncio
async def test_runtime_initializes_browser_once_and_closes_it() -> None:
    orchestrator = AsyncMock()
    orchestrator.page_controller = object()
    orchestrator.human = object()
    orchestrator._ensure_login.return_value = True
    runtime = ApprovedApplicationRuntime(
        orchestrator=orchestrator,
        job_url=lambda job_id: f"https://hk.jobsdb.com/job/{job_id}",
    )

    first = await runtime.components()
    second = await runtime.components()
    await runtime.close()

    assert first == second
    orchestrator._init_browser.assert_awaited_once()
    orchestrator._ensure_login.assert_awaited_once()
    orchestrator._cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_refuses_to_continue_when_login_fails() -> None:
    orchestrator = AsyncMock()
    orchestrator._ensure_login.return_value = False
    runtime = ApprovedApplicationRuntime(
        orchestrator=orchestrator,
        job_url=lambda _job_id: "https://hk.jobsdb.com/job/1",
    )

    with pytest.raises(RuntimeError, match="login"):
        await runtime.components()

    orchestrator._cleanup.assert_awaited_once()
