from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.apply.flow import ApplyFlow
from src.jobsdb.apply.steps.cover_letter_step import (
    CoverLetterStep,
    _fill_cover_letter_js,
)
from src.jobsdb.apply.steps.resume_step import ResumeStep, _select_resume_js
from src.jobsdb.apply.steps.review_step import (
    ReviewStep,
    _verify_review_js,
)
from src.jobsdb.selectors import (
    CONTINUE_BUTTON,
    NEXT_STEP_BUTTON,
    RESUME_SELECTION,
    SUBMIT_APPLICATION_BUTTON,
    SUCCESS_MESSAGE,
)
from src.storage.models import ApplyStatus


def _context() -> ApplicationMaterialContext:
    return ApplicationMaterialContext(
        job_id="92358982",
        package_id="package-1",
        resume_filename="JBA_92358982_v1_abcd1234.pdf",
        resume_sha256="a" * 64,
        cover_letter_text=" ".join(["approved"] * 120),
        cover_letter_sha256="b" * 64,
    )


async def test_resume_step_selects_exact_context_filename() -> None:
    page = FakePageController()
    page.set_eval_result(_select_resume_js(_context().resume_filename), True)
    next_button = FakeElement(visible=True)
    page.set_element(NEXT_STEP_BUTTON, next_button)

    assert await ResumeStep(_context()).handle(page)
    assert next_button.click.call_count == 1


async def test_resume_step_stops_when_exact_filename_is_missing() -> None:
    page = FakePageController()
    page.set_eval_result(_select_resume_js(_context().resume_filename), False)
    page.set_element(NEXT_STEP_BUTTON, FakeElement(visible=True))

    assert not await ResumeStep(_context()).handle(page)


async def test_cover_letter_step_includes_exact_approved_text() -> None:
    page = FakePageController()
    page.set_eval_result(
        _fill_cover_letter_js(_context().cover_letter_text),
        {"selected": True, "filled": True},
    )
    continue_button = FakeElement(visible=True)
    page.set_element(CONTINUE_BUTTON, continue_button)

    assert await CoverLetterStep(_context()).handle(page)
    assert continue_button.click.call_count == 1


async def test_cover_letter_step_never_falls_back_to_no_letter() -> None:
    page = FakePageController()
    page.set_eval_result(
        _fill_cover_letter_js(_context().cover_letter_text),
        {"selected": True, "filled": False},
    )
    page.set_element(CONTINUE_BUTTON, FakeElement(visible=True))

    assert not await CoverLetterStep(_context()).handle(page)


async def test_review_verifies_material_without_submitting() -> None:
    page = FakePageController()
    page.set_eval_result(
        _verify_review_js(_context()),
        {"job": True, "resume": True, "cover_letter": True},
    )
    submit = FakeElement(visible=True)
    page.set_element(SUBMIT_APPLICATION_BUTTON, submit)

    assert await ReviewStep(_context(), allow_submit=False).handle(page)
    assert submit.click.call_count == 0


async def test_review_rejects_material_mismatch() -> None:
    page = FakePageController()
    page.set_eval_result(
        _verify_review_js(_context()),
        {"job": True, "resume": False, "cover_letter": True},
    )
    page.set_element(SUBMIT_APPLICATION_BUTTON, FakeElement(visible=True))

    assert not await ReviewStep(_context(), allow_submit=False).handle(page)


async def test_material_flow_stops_at_verified_review() -> None:
    page = FakePageController(
        url="https://hk.jobsdb.com/job/92358982/apply/review"
    )
    page.set_element(SUBMIT_APPLICATION_BUTTON, FakeElement(visible=True))
    page.set_eval_result(
        _verify_review_js(_context()),
        {"job": True, "resume": True, "cover_letter": True},
    )

    result = await ApplyFlow(page, material_context=_context()).apply(
        "92358982"
    )

    assert result.status is ApplyStatus.READY_FOR_REVIEW


async def test_confirmed_material_flow_can_submit() -> None:
    page = FakePageController(
        url="https://hk.jobsdb.com/job/92358982/apply/review"
    )
    submit = FakeElement(visible=True)
    page.set_element(SUBMIT_APPLICATION_BUTTON, submit)
    page.set_element(SUCCESS_MESSAGE, FakeElement())
    page.set_eval_result(
        _verify_review_js(_context()),
        {"job": True, "resume": True, "cover_letter": True},
    )

    result = await ApplyFlow(
        page,
        material_context=_context(),
        submit_confirmed=True,
    ).apply("92358982")

    assert result.status is ApplyStatus.SUBMITTED
