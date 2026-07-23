from unittest.mock import mock_open, patch

import pytest

from src.browser.fake.fake_page import FakePageController
from src.jobsdb.homepage import EXTRACTION_SCRIPT, HomepageScraper


class AsyncNoOp:
    async def __call__(self, *_args: object, **_kwargs: object) -> None:
        return None


@pytest.mark.asyncio
async def test_scraper_limits_and_deduplicates_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.homepage.asyncio.sleep", AsyncNoOp())
    page = FakePageController()
    page.set_eval_result(
        EXTRACTION_SCRIPT,
        [
            {
                "id": "1",
                "title": "One",
                "company": "Synthetic",
                "location": "HK",
                "url": "https://hk.jobsdb.com/job/1",
            },
            {
                "id": "1",
                "title": "Duplicate",
                "company": "Synthetic",
                "location": "HK",
                "url": "https://hk.jobsdb.com/job/1",
            },
            {
                "id": "2",
                "title": "Two",
                "company": "Synthetic",
                "location": None,
                "url": "https://hk.jobsdb.com/job/2",
            },
        ],
    )

    jobs = await HomepageScraper(page).get_recommended_jobs(max_jobs=2)

    assert [job.id for job in jobs] == ["1"]


@pytest.mark.asyncio
async def test_scraper_empty_result_records_debug_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.homepage.asyncio.sleep", AsyncNoOp())
    page = FakePageController()
    page.set_eval_result(EXTRACTION_SCRIPT, [])

    with patch("builtins.open", mock_open()):
        assert await HomepageScraper(page).get_recommended_jobs() == []

    assert page._screenshot_paths == ["./data/debug_no_jobs.png"]
