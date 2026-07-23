from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.settings import JobsDBConfig
from src.accounts.registry import Account
from src.jobsdb.exceptions import CaptchaDetectedError, LoginError
from src.jobsdb.login import LoginHandler


def page_double() -> SimpleNamespace:
    field = SimpleNamespace(fill=AsyncMock(), click=AsyncMock(), text_content=AsyncMock())
    return SimpleNamespace(
        url="https://hk.jobsdb.com/",
        goto=AsyncMock(),
        query_selector=AsyncMock(return_value=None),
        wait_for_selector=AsyncMock(return_value=field),
        wait_for_load_state=AsyncMock(),
        get_cookies=AsyncMock(return_value=[]),
        content=AsyncMock(return_value=""),
        reload=AsyncMock(),
        field=field,
    )


def handler(page: SimpleNamespace, human=None) -> LoginHandler:
    return LoginHandler(
        page,
        JobsDBConfig(),
        human=human,
        account=Account(
            alias="synthetic",
            email="person@example.invalid",
            password="synthetic-password",
        ),
    )


@pytest.fixture
def no_login_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.jobsdb.login.asyncio.sleep", AsyncMock())


@pytest.mark.asyncio
async def test_auto_login_success_without_human(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    page = page_double()
    login = handler(page)
    monkeypatch.setattr(login, "_check_for_captcha", AsyncMock(return_value=False))
    monkeypatch.setattr(login, "_is_logged_in", AsyncMock(return_value=True))

    assert await login._do_login() is True
    assert page.field.fill.await_count == 2
    page.field.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_login_uses_human_and_extra_wait_success(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    page = page_double()
    signin = SimpleNamespace(click=AsyncMock())
    page.query_selector.return_value = signin
    human = SimpleNamespace(
        fill_form_field=AsyncMock(),
        mouse=SimpleNamespace(click_element=AsyncMock()),
    )
    login = handler(page, human)
    monkeypatch.setattr(login, "_check_for_captcha", AsyncMock(return_value=False))
    monkeypatch.setattr(
        login,
        "_is_logged_in",
        AsyncMock(side_effect=[False, True]),
    )
    monkeypatch.setattr(login, "_get_login_error", AsyncMock(return_value=None))

    assert await login._do_login() is True
    assert human.fill_form_field.await_count == 2
    assert human.mouse.click_element.await_count == 2


@pytest.mark.asyncio
async def test_auto_login_maps_captcha(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    login = handler(page_double())
    monkeypatch.setattr(login, "_check_for_captcha", AsyncMock(return_value=True))

    with pytest.raises(CaptchaDetectedError):
        await login._do_login()


@pytest.mark.asyncio
async def test_auto_login_reports_form_and_server_errors(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    page = page_double()
    login = handler(page)
    monkeypatch.setattr(login, "_check_for_captcha", AsyncMock(return_value=False))
    page.wait_for_selector.return_value = None
    with pytest.raises(LoginError, match="Email input not found"):
        await login._do_login()

    page = page_double()
    login = handler(page)
    monkeypatch.setattr(login, "_check_for_captcha", AsyncMock(return_value=False))
    monkeypatch.setattr(login, "_is_logged_in", AsyncMock(return_value=False))
    monkeypatch.setattr(
        login,
        "_get_login_error",
        AsyncMock(return_value="synthetic rejection"),
    )
    with pytest.raises(LoginError, match="synthetic rejection"):
        await login._do_login()


@pytest.mark.asyncio
async def test_auto_login_unexpected_error_is_wrapped_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    page = page_double()
    page.goto.side_effect = RuntimeError("synthetic navigation")
    login = handler(page)
    capture = AsyncMock(return_value="login-error.png")
    monkeypatch.setattr("src.jobsdb.login.capture_screenshot", capture)

    with pytest.raises(LoginError, match="synthetic navigation"):
        await login._do_login()
    capture.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selector_value", "cookies", "content", "expected"),
    [
        (object(), [], "", True),
        (None, [{"name": "AccessToken", "domain": ".jobsdb.com"}], "", True),
        (None, [], "My jobs", True),
        (None, [], "", False),
    ],
)
async def test_logged_in_fallback_signals(
    selector_value: object,
    cookies: list[dict[str, str]],
    content: str,
    expected: bool,
) -> None:
    page = page_double()
    page.query_selector.side_effect = [None, selector_value, None, None]
    page.get_cookies.return_value = cookies
    page.content.return_value = content

    assert await handler(page)._is_logged_in() is expected


@pytest.mark.asyncio
async def test_login_helpers_and_session_refresh(
    monkeypatch: pytest.MonkeyPatch,
    no_login_delays: None,
) -> None:
    page = page_double()
    login = handler(page)
    page.query_selector.return_value = object()
    assert await login._check_for_captcha() is True

    error = SimpleNamespace(text_content=AsyncMock(return_value="bad login"))
    page.query_selector.return_value = error
    assert await login._get_login_error() == "bad login"

    monkeypatch.setattr(login, "_do_login", AsyncMock(return_value=True))
    assert await login.handle_session_refresh() is True
    page.reload.assert_awaited_once()
