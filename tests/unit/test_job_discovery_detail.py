import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.domain.job import ApplyType
from src.jobsdb.exceptions import JobNotFoundError
from src.jobsdb.job_detail import JobDetailPage, normalize_jd_text
from src.jobsdb.selectors import (
    JOB_DESCRIPTION,
    JOB_DETAIL_APPLY_LINK,
    JOB_DETAIL_COMPANY,
    JOB_DETAIL_LOCATION,
    JOB_DETAIL_TITLE,
)


def discovery_page(button_text: str | None = None) -> FakePageController:
    page = FakePageController()
    page.set_text(JOB_DETAIL_TITLE, " Product Manager ")
    page.set_text(JOB_DETAIL_COMPANY, " Synthetic Ltd ")
    page.set_text(JOB_DETAIL_LOCATION, " Hong Kong ")
    page.set_text(JOB_DESCRIPTION, " Own the product. ")
    if button_text is not None:
        page.set_element(
            JOB_DETAIL_APPLY_LINK,
            FakeElement(text=button_text, visible=True),
        )
    return page


def test_normalize_jd_text_standardizes_spacing() -> None:
    raw = " Role\r\n\r\n\r\n  Build products  \n\n"

    assert normalize_jd_text(raw) == "Role\n\nBuild products"


def test_company_selector_supports_current_advertiser_name_dom() -> None:
    assert '[data-automation="advertiser-name"]' in JOB_DETAIL_COMPANY


def test_description_selector_supports_current_job_ad_details_dom() -> None:
    assert '[data-automation="jobAdDetails"]' in JOB_DESCRIPTION


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("button_text", "expected"),
    [
        ("Quick apply", ApplyType.QUICK_APPLY),
        ("Apply", ApplyType.APPLY),
        (None, ApplyType.UNKNOWN),
    ],
)
async def test_capture_classifies_apply_type(
    button_text: str | None,
    expected: ApplyType,
) -> None:
    capture = await JobDetailPage(
        discovery_page(button_text)
    ).capture_for_discovery(
        job_id="123",
        canonical_url="https://hk.jobsdb.com/job/123",
    )

    assert capture.apply_type is expected
    assert capture.title == "Product Manager"
    assert capture.company == "Synthetic Ltd"
    assert capture.location == "Hong Kong"
    assert capture.jd_text == "Own the product."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector", "message"),
    [
        (JOB_DETAIL_TITLE, "job title is missing"),
        (JOB_DETAIL_COMPANY, "job company is missing"),
        (JOB_DESCRIPTION, "job description is missing"),
    ],
)
async def test_capture_rejects_missing_required_detail(
    selector: str,
    message: str,
) -> None:
    page = discovery_page()
    page.set_text(selector, " \n ")

    with pytest.raises(JobNotFoundError, match=message):
        await JobDetailPage(page).capture_for_discovery(
            job_id="123",
            canonical_url="https://hk.jobsdb.com/job/123",
        )
