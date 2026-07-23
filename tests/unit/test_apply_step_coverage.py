from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.apply.steps.questions_step import QuestionsStep
from src.jobsdb.apply.steps.resume_step import ResumeStep
from src.jobsdb.apply.steps.review_step import ReviewStep
from src.jobsdb.selectors import (
    ADDITIONAL_QUESTIONS,
    DEFAULT_RESUME_RADIO,
    NEXT_STEP_BUTTON,
    RESUME_DROPDOWN,
    SUBMIT_APPLICATION_BUTTON,
)


def question(**selectors: object) -> SimpleNamespace:
    return SimpleNamespace(
        query_selector=AsyncMock(
            side_effect=lambda selector: selectors.get(selector)
        ),
        query_selector_all=AsyncMock(
            side_effect=lambda selector: selectors.get(selector, [])
        ),
    )


@pytest.mark.asyncio
async def test_questions_fills_select_text_radio_and_checkbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePageController()
    next_button = FakeElement(visible=True)
    page.set_element(NEXT_STEP_BUTTON, next_button)
    monkeypatch.setattr("src.jobsdb.apply.steps.questions_step.asyncio.sleep", AsyncMock())

    empty_option = SimpleNamespace(get_attribute=AsyncMock(return_value=""))
    valid_option = SimpleNamespace(get_attribute=AsyncMock(return_value="yes"))
    select = SimpleNamespace(
        query_selector_all=AsyncMock(return_value=[empty_option, valid_option]),
        select_option=AsyncMock(),
    )
    years = SimpleNamespace(fill=AsyncMock())
    salary = SimpleNamespace(fill=AsyncMock())
    plain = SimpleNamespace(fill=AsyncMock())
    label_years = SimpleNamespace(
        text_content=AsyncMock(return_value="Years of experience")
    )
    label_salary = SimpleNamespace(
        text_content=AsyncMock(return_value="Expected salary")
    )
    radio = SimpleNamespace(click=AsyncMock())
    checkbox = SimpleNamespace(click=AsyncMock())
    page.set_elements(
        ADDITIONAL_QUESTIONS,
        [
            question(select=select),
            question(
                **{
                    'input[type="text"], textarea': years,
                    "label, .question-label": label_years,
                }
            ),
            question(
                **{
                    'input[type="text"], textarea': salary,
                    "label, .question-label": label_salary,
                }
            ),
            question(**{'input[type="text"], textarea': plain}),
            question(**{'input[type="radio"]': [radio]}),
            question(**{'input[type="checkbox"]': [checkbox]}),
        ],
    )

    assert await QuestionsStep().handle(page) is True
    select.select_option.assert_awaited_once_with(index=1)
    years.fill.assert_awaited_once_with("3")
    salary.fill.assert_awaited_once_with("Negotiable")
    plain.fill.assert_awaited_once_with("N/A")
    radio.click.assert_awaited_once()
    checkbox.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_questions_exception_returns_false() -> None:
    page = FakePageController()
    page.query_selector_all = AsyncMock(side_effect=RuntimeError("synthetic"))
    assert await QuestionsStep().handle(page) is False


@pytest.mark.asyncio
async def test_resume_radio_dropdown_human_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.apply.steps.resume_step.asyncio.sleep", AsyncMock())
    page = FakePageController()
    next_button = FakeElement(visible=True)
    page.set_element(NEXT_STEP_BUTTON, next_button)
    radio = FakeElement(checked=False)
    page.set_element(DEFAULT_RESUME_RADIO, radio)
    human = SimpleNamespace(mouse=SimpleNamespace(click_element=AsyncMock()))
    assert await ResumeStep().handle(page, human) is True
    assert human.mouse.click_element.await_count == 2
    assert human.mouse.click_element.await_args_list[0].args == (radio,)

    page = FakePageController()
    page.set_element(NEXT_STEP_BUTTON, FakeElement(visible=True))
    dropdown = SimpleNamespace(
        query_selector_all=AsyncMock(return_value=[object()]),
        select_option=AsyncMock(),
    )
    page.set_element(RESUME_DROPDOWN, dropdown)
    assert await ResumeStep().handle(page) is True
    dropdown.select_option.assert_awaited_once_with(index=0)

    page.query_selector = AsyncMock(side_effect=RuntimeError("synthetic"))
    assert await ResumeStep().handle(page) is False


@pytest.mark.asyncio
async def test_review_human_url_success_hidden_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.jobsdb.apply.steps.review_step.asyncio.sleep", AsyncMock())
    monkeypatch.setattr(
        "src.jobsdb.apply.steps.review_step.check_success",
        AsyncMock(return_value=False),
    )
    page = FakePageController(url="https://hk.jobsdb.com/job/1/apply/review")
    button = FakeElement(visible=True)
    page.set_element(SUBMIT_APPLICATION_BUTTON, button)
    human = SimpleNamespace(click_apply_button=AsyncMock())

    async def change_url(_button: object) -> None:
        page._url = "https://hk.jobsdb.com/job/1/application-success"

    human.click_apply_button.side_effect = change_url
    assert await ReviewStep().handle(page, human) is True

    page = FakePageController()
    page.set_element(SUBMIT_APPLICATION_BUTTON, FakeElement(visible=False))
    assert await ReviewStep().handle(page) is False

    page.query_selector = AsyncMock(side_effect=RuntimeError("synthetic"))
    assert await ReviewStep().handle(page) is False
