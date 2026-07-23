from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.settings import BrowserConfig
from src.browser.engine import BrowserEngine


class AsyncContextDouble:
    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.added = cookies


class FailingPageDouble:
    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        raise RuntimeError("synthetic page close failure")


class ClosingDouble:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class StoppingDouble:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class PageDouble:
    def __init__(self) -> None:
        self.url = "https://example.invalid"
        self.add_init_script = AsyncMock()
        self.goto = AsyncMock()


class PersistentContextDouble:
    def __init__(self, *, with_page: bool) -> None:
        self.pages = [PageDouble()] if with_page else []
        self.new_page = AsyncMock(side_effect=self._new_page)
        self.add_cookies = AsyncMock()
        self.cookies = AsyncMock(return_value=[{"name": "synthetic"}])
        self.close = AsyncMock()

    async def _new_page(self) -> PageDouble:
        page = PageDouble()
        self.pages.append(page)
        return page


class ChromiumDouble:
    def __init__(self, context: PersistentContextDouble) -> None:
        self.context = context
        self.launch_persistent_context = AsyncMock(return_value=context)


@pytest.mark.asyncio
async def test_new_page_requires_started_browser() -> None:
    with pytest.raises(RuntimeError, match="Browser not started"):
        await BrowserEngine(BrowserConfig()).new_page()


@pytest.mark.asyncio
async def test_goto_requires_started_page() -> None:
    with pytest.raises(RuntimeError, match="Browser not started"):
        await BrowserEngine(BrowserConfig()).goto("https://example.invalid")


@pytest.mark.asyncio
async def test_cookie_load_normalizes_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = BrowserEngine(BrowserConfig())
    engine.page = object()
    context = AsyncContextDouble()
    engine.context = context
    monkeypatch.setattr(
        engine.cookie_store,
        "load",
        lambda: [
            {
                "name": "session",
                "value": "synthetic",
                "domain": ".jobsdb.com",
            }
        ],
    )

    await engine._load_cookies()

    assert context.added[0]["sameSite"] == "Lax"
    assert context.added[0]["path"] == "/"


@pytest.mark.asyncio
async def test_stop_attempts_all_cleanup_when_page_close_fails() -> None:
    engine = BrowserEngine(BrowserConfig())
    engine.page = FailingPageDouble()
    browser = ClosingDouble()
    playwright = StoppingDouble()
    engine.browser = browser
    engine.playwright = playwright

    await engine.stop()

    assert browser.closed is True
    assert playwright.stopped is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("headless", "with_page"), [(True, True), (False, False)])
async def test_start_builds_persistent_context_without_real_chromium(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    headless: bool,
    with_page: bool,
) -> None:
    context = PersistentContextDouble(with_page=with_page)
    chromium = ChromiumDouble(context)
    playwright = SimpleNamespace(chromium=chromium)
    starter = SimpleNamespace(start=AsyncMock(return_value=playwright))
    monkeypatch.setattr("src.browser.engine.async_playwright", Mock(return_value=starter))
    monkeypatch.setattr("src.browser.engine.get_combined_script", Mock(return_value="js"))

    config = BrowserConfig(
        headless=headless,
        user_data_dir=str(tmp_path / "profile"),
        geolocation={},
        proxy="http://proxy.invalid",
    )
    engine = BrowserEngine(config, account_alias="synthetic")
    monkeypatch.setattr(engine.cookie_store, "load", Mock(return_value=[]))

    page = await engine.start()

    assert page is engine.page
    kwargs = chromium.launch_persistent_context.await_args.kwargs
    assert kwargs["headless"] is headless
    assert kwargs["proxy"] == {"server": "http://proxy.invalid"}
    assert ("--headless=new" in kwargs["args"]) is headless
    page.add_init_script.assert_awaited_once_with("js")


@pytest.mark.asyncio
async def test_save_restart_and_navigation_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = BrowserEngine(BrowserConfig())
    page = PageDouble()
    context = PersistentContextDouble(with_page=True)
    engine.page = page
    engine.context = context
    save = Mock()
    monkeypatch.setattr(engine.cookie_store, "save", save)

    await engine._save_cookies()
    await engine.goto("https://example.invalid/job", wait_until="load")
    assert engine.current_page is page
    save.assert_called_once_with([{"name": "synthetic"}])
    page.goto.assert_awaited_once_with(
        "https://example.invalid/job",
        wait_until="load",
    )

    monkeypatch.setattr(engine, "stop", AsyncMock())
    monkeypatch.setattr(engine, "start", AsyncMock(return_value=page))
    assert await engine.restart() is page


@pytest.mark.asyncio
async def test_stealth_and_cookie_failures_are_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = BrowserEngine(BrowserConfig())
    page = PageDouble()
    page.add_init_script.side_effect = RuntimeError("synthetic stealth failure")
    await engine._apply_stealth_to_page(page)

    engine.page = page
    context = PersistentContextDouble(with_page=True)
    context.add_cookies.side_effect = RuntimeError("synthetic cookie failure")
    engine.context = context
    monkeypatch.setattr(
        engine.cookie_store,
        "load",
        Mock(return_value=[{"name": "n", "value": "v", "domain": "d"}]),
    )
    await engine._load_cookies()

    context.cookies.side_effect = RuntimeError("synthetic save failure")
    await engine._save_cookies()
