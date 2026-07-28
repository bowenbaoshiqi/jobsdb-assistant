import asyncio
import json
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
async def material_dashboard() -> str:
    database = Database(":memory:")
    database.save_discovered_job(
        JobDetailCapture(
            jobsdb_job_id="job-1",
            canonical_url="https://hk.jobsdb.com/job/job-1",
            title="Head of AI",
            company="Large Corporation",
            location="Hong Kong",
            jd_text="Lead enterprise AI.",
            apply_type=ApplyType.QUICK_APPLY,
        ),
        captured_at=NOW,
    )
    app = create_dashboard_app(
        DashboardDependencies(
            database=database,
            query_service=DashboardQueryService(database),
            selection_repository=SelectionRepository(database),
            application_service=DashboardApplicationService(
                database,
                runner=AsyncMock(),
            ),
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
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_batch_control_requires_selection_and_never_polls(
    material_dashboard: str,
    mock_page,
) -> None:
    await mock_page.goto(f"{material_dashboard}/?show=all")
    button = mock_page.get_by_role(
        "button",
        name="为已选职位生成定制材料",
    )
    assert await button.is_disabled()

    await mock_page.get_by_label("选择 Head of AI").check()
    assert await button.is_enabled()
    javascript = await (
        await mock_page.request.get(f"{material_dashboard}/static/dashboard.js")
    ).text()
    assert "setInterval" not in javascript


@pytest.mark.asyncio
async def test_material_page_previews_and_reviews_without_submit(
    material_dashboard: str,
    mock_page,
) -> None:
    calls: list[str] = []
    payload = {
        "id": "package-1",
        "job_id": "job-1",
        "evaluation_id": "evaluation-1",
        "profile_version": 1,
        "version": 1,
        "resume": {"path": "private", "sha256": "a" * 64},
        "cover_letter": {"path": "private", "sha256": "b" * 64},
        "cover_letter_word_count": 120,
        "cover_letter_text": "Tailored English cover letter.",
        "reviewer": {"passed": False, "findings": ["建议强化领导力"]},
        "ats": {"passed": False, "findings": ["建议加入 LLM 关键词"]},
        "facts": {"passed": False, "findings": ["团队规模需要确认"]},
        "review_status": "pending_review_with_fact_warning",
        "created_at": NOW.isoformat(),
        "reviewer_passed": False,
        "ats_passed": False,
        "facts_passed": False,
        "versions": [],
        "review_events": [],
    }

    async def api_handler(route):
        calls.append(route.request.url)
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload),
            )
        else:
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "action": "approve",
                        "resulting_status": "approved_with_fact_override",
                    }
                ),
            )

    await mock_page.route("**/api/materials/package-1", api_handler)
    await mock_page.goto(f"{material_dashboard}/materials/package-1")

    assert await mock_page.locator("#fact-warning").get_by_text(
        "团队规模需要确认"
    ).is_visible()
    assert await mock_page.get_by_text("建议强化领导力").is_visible()
    assert await mock_page.get_by_text("建议加入 LLM 关键词").is_visible()
    await mock_page.get_by_label("我确认覆盖事实风险警告").check()
    await mock_page.get_by_role("button", name="批准材料").click()
    assert all("quick-apply" not in url for url in calls)
