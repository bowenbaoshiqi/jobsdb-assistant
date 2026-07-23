from unittest.mock import AsyncMock

import pytest

from src.browser.fake.fake_page import FakePageController
from src.jobsdb.apply.flow import ApplyFlow, ApplyStep
from src.storage.models import ApplyStatus


@pytest.fixture
def no_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.jobsdb.apply.flow.asyncio.sleep", AsyncMock())


def patch_entry(
    monkeypatch: pytest.MonkeyPatch,
    *,
    captcha: bool = False,
    step: ApplyStep = ApplyStep.UNKNOWN,
) -> None:
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.check_captcha",
        AsyncMock(return_value=captcha),
    )
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.detect_current_step",
        AsyncMock(return_value=step),
    )
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.get_error_message",
        AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_success_detected_on_first_loop(
    monkeypatch: pytest.MonkeyPatch,
    no_delays: None,
) -> None:
    patch_entry(monkeypatch, step=ApplyStep.SUBMITTED)

    result = await ApplyFlow(FakePageController()).apply("synthetic-1")

    assert result.status is ApplyStatus.SUBMITTED
    assert result.duration_seconds is not None


@pytest.mark.asyncio
async def test_captcha_detected_before_step_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_entry(monkeypatch, captcha=True)
    detect = AsyncMock(return_value=ApplyStep.SUBMITTED)
    monkeypatch.setattr("src.jobsdb.apply.flow.detect_current_step", detect)

    result = await ApplyFlow(FakePageController()).apply("synthetic-1")

    assert result.status is ApplyStatus.CAPTCHA
    detect.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_step_exhausts_attempts(
    monkeypatch: pytest.MonkeyPatch,
    no_delays: None,
) -> None:
    patch_entry(monkeypatch)
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.check_success",
        AsyncMock(return_value=False),
    )
    flow = ApplyFlow(FakePageController(), max_steps=2)

    result = await flow.apply("synthetic-1")

    assert flow.step_count == 2
    assert result.error_message == "Max steps exceeded"


@pytest.mark.asyncio
async def test_handler_false_returns_step_failure(
    monkeypatch: pytest.MonkeyPatch,
    no_delays: None,
) -> None:
    patch_entry(monkeypatch, step=ApplyStep.REVIEW)
    flow = ApplyFlow(FakePageController())
    monkeypatch.setattr(flow, "_handle_step", AsyncMock(return_value=False))

    result = await flow.apply("synthetic-1")

    assert result.status is ApplyStatus.FAILED
    assert result.error_message == "Failed at step: review"


@pytest.mark.asyncio
async def test_handler_exception_is_returned_with_screenshot(
    monkeypatch: pytest.MonkeyPatch,
    no_delays: None,
) -> None:
    patch_entry(monkeypatch, step=ApplyStep.REVIEW)
    flow = ApplyFlow(FakePageController())
    monkeypatch.setattr(
        flow,
        "_handle_step",
        AsyncMock(side_effect=RuntimeError("synthetic handler failure")),
    )
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.capture_screenshot",
        AsyncMock(return_value="synthetic-error.png"),
    )

    result = await flow.apply("synthetic-1")

    assert result.status is ApplyStatus.FAILED
    assert result.error_message == "synthetic handler failure"
    assert result.screenshot_path == "synthetic-error.png"


@pytest.mark.asyncio
async def test_max_step_exhaustion_records_screenshot(
    monkeypatch: pytest.MonkeyPatch,
    no_delays: None,
) -> None:
    patch_entry(monkeypatch)
    monkeypatch.setattr(
        "src.jobsdb.apply.flow.check_success",
        AsyncMock(return_value=False),
    )
    capture = AsyncMock(return_value="max-steps.png")
    monkeypatch.setattr("src.jobsdb.apply.flow.capture_screenshot", capture)

    result = await ApplyFlow(FakePageController(), max_steps=1).apply("synthetic-1")

    assert result.screenshot_path == "max-steps.png"
    capture.assert_awaited_once()
