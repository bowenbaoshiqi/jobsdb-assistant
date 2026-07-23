from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.accounts.registry import Account
from src.factory import FakeFactory
from src.jobsdb.exceptions import CaptchaDetectedError, SessionExpiredError
from src.orchestrator import Orchestrator
from src.storage.models import ApplyResult, ApplyStatus, JobListing, SessionStatus


def make_orchestrator() -> Orchestrator:
    return Orchestrator(
        account=Account(alias="synthetic", email="person@example.invalid", password=""),
        factory=FakeFactory(),
    )


def make_job(job_id: str = "synthetic-1") -> JobListing:
    return JobListing(
        id=job_id,
        title="Synthetic Engineer",
        company="Example Limited",
        url=f"https://hk.jobsdb.com/job/{job_id}",
    )


@pytest.mark.asyncio
async def test_run_with_zero_scraped_jobs_returns_empty_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    monkeypatch.setattr(orchestrator, "_ensure_login", AsyncMock(return_value=True))
    monkeypatch.setattr(orchestrator, "_scrape_jobs", AsyncMock(return_value=[]))

    report = await orchestrator.run()

    assert report["total"] == 0
    assert orchestrator.factory.last_browser.current_page is None


@pytest.mark.asyncio
async def test_run_with_filtered_queue_returns_empty_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    monkeypatch.setattr(orchestrator, "_ensure_login", AsyncMock(return_value=True))
    monkeypatch.setattr(
        orchestrator,
        "_scrape_jobs",
        AsyncMock(return_value=[make_job()]),
    )
    monkeypatch.setattr(orchestrator.queue_manager, "build_queue", Mock(return_value=[]))

    report = await orchestrator.run()

    assert report["message"] == "No jobs to apply"
    assert orchestrator.factory.last_browser.current_page is None


@pytest.mark.asyncio
async def test_process_queue_counts_submitted_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    orchestrator.session_id = "session-synthetic"
    orchestrator.human = SimpleNamespace(random_distractor=AsyncMock())
    orchestrator.tracker = SimpleNamespace(
        record_application=Mock(),
        end_session=Mock(),
    )
    monkeypatch.setattr(
        orchestrator.rate_limiter,
        "wait_if_needed",
        AsyncMock(),
    )
    monkeypatch.setattr(
        orchestrator,
        "_apply_to_job",
        AsyncMock(
            return_value=ApplyResult(
                status=ApplyStatus.SUBMITTED,
                job_id="synthetic-1",
            )
        ),
    )

    await orchestrator._process_queue([make_job()])

    assert orchestrator.jobs_processed == 1
    assert orchestrator.jobs_succeeded == 1
    orchestrator.tracker.end_session.assert_called_once_with(
        "session-synthetic",
        SessionStatus.COMPLETED,
    )


@pytest.mark.asyncio
async def test_process_queue_aborts_when_detection_threshold_was_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    orchestrator.session_id = "session-synthetic"
    orchestrator.detection_suspected = True
    orchestrator.consecutive_failures = (
        orchestrator.config.monitoring.suspicion_threshold
    )
    orchestrator.tracker = SimpleNamespace(end_session=Mock())
    apply_job = AsyncMock()
    monkeypatch.setattr(orchestrator, "_apply_to_job", apply_job)
    monkeypatch.setattr(
        orchestrator.rate_limiter,
        "wait_if_needed",
        AsyncMock(),
    )

    await orchestrator._process_queue([make_job()])

    apply_job.assert_not_awaited()
    orchestrator.tracker.end_session.assert_called_once_with(
        "session-synthetic",
        SessionStatus.ABORTED,
        "Detection suspected",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (SessionExpiredError("expired"), ApplyStatus.FAILED),
        (CaptchaDetectedError("captcha"), ApplyStatus.FAILED),
        (RuntimeError("unexpected"), ApplyStatus.FAILED),
    ],
)
async def test_apply_to_job_maps_navigation_failures_and_captures_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: ApplyStatus,
) -> None:
    orchestrator = make_orchestrator()
    orchestrator.page_controller = SimpleNamespace()
    navigate = AsyncMock(side_effect=error)
    monkeypatch.setattr(
        "src.orchestrator.JobDetailPage.navigate_with_simulation",
        navigate,
    )
    monkeypatch.setattr(
        "src.orchestrator.capture_screenshot",
        AsyncMock(return_value="diagnostic.png"),
    )

    result = await orchestrator._apply_to_job(make_job())

    assert result.status is expected_status
    assert result.error_message == str(error)
    assert result.screenshot_path == "diagnostic.png"
