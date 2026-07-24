from unittest.mock import AsyncMock, mock_open, patch

import pytest

from src.browser.fake.fake_page import FakePageController
from src.jobsdb.homepage import EXTRACTION_SCRIPT, HomepageScraper


class AsyncNoOp:
    async def __call__(self, *_args: object, **_kwargs: object) -> None:
        return None


def job_data(job_id: str) -> dict:
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "company": "Synthetic",
        "location": "HK",
        "url": f"https://hk.jobsdb.com/job/{job_id}",
    }


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


@pytest.mark.asyncio
async def test_search_scraper_collects_until_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.homepage.asyncio.sleep", AsyncNoOp())
    page = FakePageController()
    extraction_results = iter([
        [job_data("1")],
        [job_data("1"), job_data("2")],
    ])

    async def evaluate(expression: str):
        if expression == EXTRACTION_SCRIPT:
            return next(extraction_results)
        return None

    page.evaluate = AsyncMock(side_effect=evaluate)

    jobs = await HomepageScraper(page).get_search_jobs(
        max_jobs=2,
        no_growth_limit=2,
    )

    assert [job.id for job in jobs] == ["1", "2"]
    extraction_calls = [
        call for call in page.evaluate.await_args_list
        if call.args == (EXTRACTION_SCRIPT,)
    ]
    assert len(extraction_calls) == 2


@pytest.mark.asyncio
async def test_search_scraper_stops_after_bounded_no_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.homepage.asyncio.sleep", AsyncNoOp())
    page = FakePageController()

    async def evaluate(expression: str):
        if expression == EXTRACTION_SCRIPT:
            return [job_data("1")]
        return None

    page.evaluate = AsyncMock(side_effect=evaluate)

    jobs = await HomepageScraper(page).get_search_jobs(
        max_jobs=50,
        no_growth_limit=2,
    )

    assert [job.id for job in jobs] == ["1"]
    extraction_calls = [
        call for call in page.evaluate.await_args_list
        if call.args == (EXTRACTION_SCRIPT,)
    ]
    assert len(extraction_calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_jobs", "no_growth_limit", "message"),
    [
        (0, 2, "max_jobs must be at least 1"),
        (50, 0, "no_growth_limit must be at least 1"),
    ],
)
async def test_search_scraper_rejects_invalid_bounds(
    max_jobs: int,
    no_growth_limit: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await HomepageScraper(FakePageController()).get_search_jobs(
            max_jobs=max_jobs,
            no_growth_limit=no_growth_limit,
        )
