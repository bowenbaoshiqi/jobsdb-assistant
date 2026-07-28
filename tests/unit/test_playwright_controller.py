"""
单元测试: PlaywrightPageController + PlaywrightBrowser

用 mock Page 验证委托逻辑正确,不起真实浏览器。
真实浏览器集成验证在 tests/e2e/。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.browser.playwright_browser import PlaywrightBrowser
from src.browser.playwright_page_controller import PlaywrightPageController

# ═══════════════════════════════════════════════════════
#  PlaywrightPageController 委托逻辑
# ═══════════════════════════════════════════════════════

class TestPlaywrightPageControllerDelegation:
    def _make(self):
        page = AsyncMock()
        page.url = "https://example.com/page"
        page.is_closed = MagicMock(return_value=False)
        ctrl = PlaywrightPageController(page)
        return ctrl, page

    @pytest.mark.asyncio
    async def test_goto_delegates(self):
        ctrl, page = self._make()
        await ctrl.goto("http://x", wait_until="load")
        page.goto.assert_awaited_once_with("http://x", wait_until="load")

    def test_url_returns_page_url(self):
        ctrl, page = self._make()
        assert ctrl.url == "https://example.com/page"

    @pytest.mark.asyncio
    async def test_query_selector_delegates(self):
        ctrl, page = self._make()
        page.query_selector = AsyncMock(return_value="elem")
        result = await ctrl.query_selector(".x")
        assert result == "elem"
        page.query_selector.assert_awaited_once_with(".x")

    @pytest.mark.asyncio
    async def test_get_text_returns_none_when_no_element(self):
        """元素不存在 → None(收敛 v1.0 三行模式)"""
        ctrl, page = self._make()
        page.query_selector = AsyncMock(return_value=None)
        assert await ctrl.get_text(".x") is None

    @pytest.mark.asyncio
    async def test_get_text_returns_text_when_element_exists(self):
        ctrl, page = self._make()
        elem = AsyncMock()
        elem.text_content = AsyncMock(return_value="hello")
        page.query_selector = AsyncMock(return_value=elem)
        assert await ctrl.get_text(".x") == "hello"

    @pytest.mark.asyncio
    async def test_get_attribute_returns_none_when_no_element(self):
        ctrl, page = self._make()
        page.query_selector = AsyncMock(return_value=None)
        assert await ctrl.get_attribute(".x", "href") is None

    @pytest.mark.asyncio
    async def test_click_delegates_with_timeout_ms(self):
        """timeout 秒 → 毫秒转换"""
        ctrl, page = self._make()
        await ctrl.click(".btn", timeout=5.0)
        page.click.assert_awaited_once_with(".btn", timeout=5000.0)

    @pytest.mark.asyncio
    async def test_fill_delegates(self):
        ctrl, page = self._make()
        await ctrl.fill("#input", "value")
        page.fill.assert_awaited_once_with("#input", "value")

    @pytest.mark.asyncio
    async def test_set_input_files_delegates(self):
        ctrl, page = self._make()
        await ctrl.set_input_files('input[type="file"]', "/tmp/cv.pdf")
        page.set_input_files.assert_awaited_once_with(
            'input[type="file"]',
            "/tmp/cv.pdf",
        )

    @pytest.mark.asyncio
    async def test_type_text_delegates_to_page_type(self):
        """type_text 委托给底层 page.type"""
        ctrl, page = self._make()
        await ctrl.type_text("#input", "abc", delay=30)
        page.type.assert_awaited_once_with("#input", "abc", delay=30)

    @pytest.mark.asyncio
    async def test_wait_for_selector_delegates_with_ms(self):
        ctrl, page = self._make()
        await ctrl.wait_for_selector(".x", timeout=10.0)
        page.wait_for_selector.assert_awaited_once_with(".x", timeout=10000.0)

    @pytest.mark.asyncio
    async def test_wait_for_load_state_delegates_with_ms(self):
        """wait_for_load_state timeout 秒 → 毫秒"""
        ctrl, page = self._make()
        await ctrl.wait_for_load_state("networkidle", timeout=15.0)
        page.wait_for_load_state.assert_awaited_once_with("networkidle", timeout=15000.0)

    @pytest.mark.asyncio
    async def test_evaluate_delegates(self):
        ctrl, page = self._make()
        page.evaluate = AsyncMock(return_value="result")
        assert await ctrl.evaluate("1+1") == "result"

    @pytest.mark.asyncio
    async def test_content_delegates(self):
        ctrl, page = self._make()
        page.content = AsyncMock(return_value="<html>")
        assert await ctrl.content() == "<html>"
        page.content.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reload_delegates(self):
        ctrl, page = self._make()
        await ctrl.reload(wait_until="load")
        page.reload.assert_awaited_once_with(wait_until="load")

    @pytest.mark.asyncio
    async def test_get_cookies_delegates_to_context(self):
        """get_cookies 委托给 page.context.cookies()(登录态检测用)"""
        ctrl, page = self._make()
        page.context = MagicMock()
        page.context.cookies = AsyncMock(return_value=[{"name": "AccessToken"}])
        cookies = await ctrl.get_cookies()
        assert cookies == [{"name": "AccessToken"}]
        page.context.cookies.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screenshot_delegates(self):
        ctrl, page = self._make()
        await ctrl.screenshot("/tmp/x.png")
        page.screenshot.assert_awaited_once_with(path="/tmp/x.png", full_page=False)

    @pytest.mark.asyncio
    async def test_screenshot_full_page_delegates(self):
        ctrl, page = self._make()
        await ctrl.screenshot("/tmp/x.png", full_page=True)
        page.screenshot.assert_awaited_once_with(path="/tmp/x.png", full_page=True)

    def test_is_closed_delegates(self):
        ctrl, page = self._make()
        page.is_closed = MagicMock(return_value=True)
        assert ctrl.is_closed() is True

    def test_raw_page_exposes_underlying(self):
        """过渡期:raw_page 暴露底层 Page"""
        ctrl, page = self._make()
        assert ctrl.raw_page is page


# ═══════════════════════════════════════════════════════
#  PlaywrightBrowser 生命周期(用 mock engine)
# ═══════════════════════════════════════════════════════

class TestPlaywrightBrowser:
    @pytest.mark.asyncio
    async def test_start_returns_page_controller(self):
        """start 返回 PlaywrightPageController(非裸 Page)"""

        browser = PlaywrightBrowser.__new__(PlaywrightBrowser)
        browser._engine = AsyncMock()
        browser._page_controller = None
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        browser._engine.start = AsyncMock(return_value=mock_page)

        ctrl = await browser.start()

        from src.browser.playwright_page_controller import PlaywrightPageController
        assert isinstance(ctrl, PlaywrightPageController)
        assert browser._page_controller is ctrl

    @pytest.mark.asyncio
    async def test_current_page_none_when_not_started(self):
        browser = PlaywrightBrowser.__new__(PlaywrightBrowser)
        browser._page_controller = None
        assert browser.current_page is None

    @pytest.mark.asyncio
    async def test_stop_clears_controller(self):
        browser = PlaywrightBrowser.__new__(PlaywrightBrowser)
        browser._engine = AsyncMock()
        browser._page_controller = MagicMock()
        browser._page_controller.is_closed = MagicMock(return_value=False)

        await browser.stop()

        browser._engine.stop.assert_awaited_once()
        assert browser._page_controller is None
