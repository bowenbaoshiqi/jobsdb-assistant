import asyncio
import socket
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import uvicorn

from src.dashboard.app import DashboardDependencies, create_dashboard_app
from src.dashboard.application_service import DashboardApplicationService
from src.dashboard.query_service import DashboardQueryService
from src.domain.job import ApplyType, JobDetailCapture
from src.storage.database import Database
from src.storage.selection_repository import SelectionRepository

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def live_dashboard() -> str:
    database = Database(":memory:")
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="quick-1",
            canonical_url="https://hk.jobsdb.com/job/quick-1",
            title="Head of AI",
            company="Example Corporation",
            location="Hong Kong",
            jd_text="Lead an enterprise AI platform team.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )
    application_service = DashboardApplicationService(
        database,
        runner=AsyncMock(return_value={"success": 1}),
        now=lambda: NOW,
    )
    app = create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(database),
            selection_repository=SelectionRepository(database),
            application_service=application_service,
        )
    )
    server_socket = socket.socket()
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen()
    port = server_socket.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="off",
        )
    )
    task = asyncio.create_task(server.serve(sockets=[server_socket]))
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.01)
    if not server.started:
        server.should_exit = True
        await task
        pytest.fail("local Dashboard did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_selection_and_filters_survive_refresh(
    live_dashboard: str,
    mock_page,
) -> None:
    await mock_page.goto(live_dashboard)
    await mock_page.get_by_label("显示全部职位").check()
    await mock_page.get_by_label("选择 Head of AI").check()
    await mock_page.reload()

    assert await mock_page.get_by_label("显示全部职位").is_checked()
    assert await mock_page.get_by_label("选择 Head of AI").is_checked()
    assert "show=all" in mock_page.url


@pytest.mark.asyncio
async def test_apply_controls_are_type_specific(
    live_dashboard: str,
    mock_page,
) -> None:
    await mock_page.goto(f"{live_dashboard}/?show=all")

    assert await mock_page.get_by_role(
        "button",
        name="使用默认简历直接投递",
    ).is_visible()
    assert await mock_page.locator("#job-list").get_by_text(
        "待评分"
    ).is_visible()
