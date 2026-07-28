from unittest.mock import AsyncMock, Mock

import pytest

from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.material_wizard import JobsDBMaterialWizard
from src.storage.models import ApplyResult, ApplyStatus


def _context() -> ApplicationMaterialContext:
    return ApplicationMaterialContext(
        job_id="92358982",
        package_id="package-1",
        resume_filename="JBA_92358982_v1_12345678.pdf",
        resume_sha256="a" * 64,
        cover_letter_text=" ".join(["focused"] * 100),
        cover_letter_sha256="b" * 64,
    )


@pytest.mark.asyncio
async def test_prepare_opens_job_clicks_quick_apply_and_stops_at_review(
    monkeypatch,
) -> None:
    page = AsyncMock()
    button = AsyncMock()
    detail = AsyncMock()
    detail.is_already_applied.return_value = False
    detail.get_apply_button.return_value = button
    flow = AsyncMock()
    flow.apply.return_value = ApplyResult(
        status=ApplyStatus.READY_FOR_REVIEW,
        job_id="92358982",
    )
    flow_type = Mock(return_value=flow)
    monkeypatch.setattr(
        "src.jobsdb.material_wizard.JobDetailPage",
        Mock(return_value=detail),
    )
    monkeypatch.setattr(
        "src.jobsdb.material_wizard.ApplyFlow",
        flow_type,
    )
    wizard = JobsDBMaterialWizard(
        page=page,
        human=None,
        job_url=lambda _job_id: "https://hk.jobsdb.com/job/92358982",
    )

    result = await wizard.prepare(_context())

    detail.navigate_with_simulation.assert_awaited_once()
    button.click.assert_awaited_once()
    assert result.status is ApplyStatus.READY_FOR_REVIEW
    assert flow_type.call_args.kwargs["submit_confirmed"] is False


@pytest.mark.asyncio
async def test_submit_reuses_current_review_page(monkeypatch) -> None:
    page = AsyncMock()
    flow = AsyncMock()
    flow.apply.return_value = ApplyResult(
        status=ApplyStatus.SUBMITTED,
        job_id="92358982",
    )
    flow_type = Mock(return_value=flow)
    monkeypatch.setattr(
        "src.jobsdb.material_wizard.ApplyFlow",
        flow_type,
    )
    wizard = JobsDBMaterialWizard(
        page=page,
        human=None,
        job_url=lambda _job_id: "https://hk.jobsdb.com/job/92358982",
    )

    result = await wizard.submit(_context())

    assert result.status is ApplyStatus.SUBMITTED
    page.goto.assert_not_awaited()
    assert flow_type.call_args.kwargs["submit_confirmed"] is True
