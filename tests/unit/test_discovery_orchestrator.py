from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.accounts.registry import Account
from src.browser.fake.fake_page import FakePageController
from src.domain.job import (
    ApplyType,
    DiscoveryPersistenceState,
    JobDetailCapture,
)
from src.factory import FakeFactory
from src.orchestrator import Orchestrator
from src.storage.models import JobListing


def make_orchestrator() -> Orchestrator:
    return Orchestrator(
        account=Account(
            alias="synthetic",
            email="person@example.invalid",
            password="",
        ),
        factory=FakeFactory(),
    )


def listing(job_id: str) -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Job {job_id}",
        company="Synthetic Ltd",
        url=f"https://hk.jobsdb.com/job/{job_id}",
    )


def capture(job_id: str = "123") -> JobDetailCapture:
    return JobDetailCapture(
        jobsdb_job_id=job_id,
        canonical_url=f"https://hk.jobsdb.com/job/{job_id}",
        title=f"Job {job_id}",
        company="Synthetic Ltd",
        location="Hong Kong",
        jd_text="Complete JD",
        apply_type=ApplyType.QUICK_APPLY,
    )


@pytest.mark.asyncio
async def test_discover_searches_captures_and_never_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    orchestrator.page_controller = FakePageController()
    orchestrator.human = None
    orchestrator.scraper = SimpleNamespace(
        get_search_jobs=AsyncMock(return_value=[listing("123")])
    )
    orchestrator.db.save_discovered_job = Mock(
        return_value=DiscoveryPersistenceState.NEW
    )
    orchestrator._process_queue = AsyncMock()
    monkeypatch.setattr(
        "src.orchestrator.JobDetailPage.navigate_with_simulation",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "src.orchestrator.JobDetailPage.capture_for_discovery",
        AsyncMock(return_value=capture()),
    )

    report = await orchestrator._discover_loaded("Product Manager", limit=50)

    assert report["keyword"] == "Product Manager"
    assert report["found"] == 1
    assert report["captured"] == 1
    assert report["new"] == 1
    assert report["apply_types"]["quick_apply"] == 1
    assert orchestrator.page_controller._goto_calls == [
        "https://hk.jobsdb.com/product-manager-jobs"
    ]
    orchestrator.scraper.get_search_jobs.assert_awaited_once_with(max_jobs=50)
    orchestrator._process_queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_discover_keeps_safe_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    orchestrator.page_controller = FakePageController()
    orchestrator.human = None
    orchestrator.scraper = SimpleNamespace(
        get_search_jobs=AsyncMock(
            return_value=[listing("bad"), listing("123")]
        )
    )
    orchestrator.db.save_discovered_job = Mock(
        return_value=DiscoveryPersistenceState.CHANGED
    )
    monkeypatch.setattr(
        "src.orchestrator.JobDetailPage.navigate_with_simulation",
        AsyncMock(side_effect=[RuntimeError("private detail"), None]),
    )
    monkeypatch.setattr(
        "src.orchestrator.JobDetailPage.capture_for_discovery",
        AsyncMock(return_value=capture()),
    )

    report = await orchestrator._discover_loaded("Product Manager", limit=50)

    assert report["captured"] == 1
    assert report["changed"] == 1
    assert report["failures"] == [
        {"job_id": "bad", "reason": "detail_capture_failed"}
    ]
    assert "private detail" not in str(report)


@pytest.mark.asyncio
async def test_public_discover_never_invokes_login() -> None:
    orchestrator = make_orchestrator()
    orchestrator._init_browser = AsyncMock()
    orchestrator._ensure_login = AsyncMock(
        side_effect=AssertionError(
            "public discovery must not invoke login"
        )
    )
    orchestrator._discover_loaded = AsyncMock(
        return_value={
            "keyword": "AI Architect",
            "found": 0,
            "captured": 0,
        }
    )
    orchestrator._cleanup = AsyncMock()

    report = await orchestrator.discover("AI Architect", limit=50)

    assert report["keyword"] == "AI Architect"
    orchestrator._init_browser.assert_awaited_once()
    orchestrator._ensure_login.assert_not_awaited()
    orchestrator._discover_loaded.assert_awaited_once_with(
        "AI Architect",
        50,
    )
    orchestrator._cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_discover_login_failure_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = make_orchestrator()
    monkeypatch.setattr(
        orchestrator,
        "_ensure_login",
        AsyncMock(return_value=False),
    )

    report = await orchestrator.discover("Product Manager")

    assert report["error"] == "login_failed"
    assert orchestrator.factory.last_browser.current_page is None
