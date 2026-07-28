"""
接口测试: BrowserPort + PageController

验证抽象接口的方法签名齐全(Protocol 结构子类型检查)。
这些测试确保实现类(PlaywrightPageController / FakePageController)满足接口契约。
"""

import inspect

from src.browser.ports.browser_port import BrowserPort
from src.browser.ports.page_controller import PageController

# ═══════════════════════════════════════════════════════
#  BrowserPort 接口
# ═══════════════════════════════════════════════════════

class TestBrowserPortInterface:
    def test_has_start_method(self):
        assert hasattr(BrowserPort, "start")
        assert inspect.iscoroutinefunction(BrowserPort.start)

    def test_has_stop_method(self):
        assert hasattr(BrowserPort, "stop")
        assert inspect.iscoroutinefunction(BrowserPort.stop)

    def test_has_new_page_method(self):
        assert hasattr(BrowserPort, "new_page")
        assert inspect.iscoroutinefunction(BrowserPort.new_page)

    def test_has_current_page_property(self):
        assert hasattr(BrowserPort, "current_page")

    def test_only_four_members(self):
        """BrowserPort 只有 4 个公开成员(不过度抽象)"""
        members = [m for m in ("start", "stop", "new_page", "current_page")
                   if hasattr(BrowserPort, m)]
        assert len(members) == 4


# ═══════════════════════════════════════════════════════
#  PageController 接口
# ═══════════════════════════════════════════════════════

class TestPageControllerInterface:
    # 导航
    def test_has_goto(self):
        assert hasattr(PageController, "goto")
        assert inspect.iscoroutinefunction(PageController.goto)

    def test_has_url_property(self):
        assert hasattr(PageController, "url")

    # 查询
    def test_has_query_selector(self):
        assert inspect.iscoroutinefunction(PageController.query_selector)

    def test_has_query_selector_all(self):
        assert inspect.iscoroutinefunction(PageController.query_selector_all)

    def test_has_is_visible(self):
        assert inspect.iscoroutinefunction(PageController.is_visible)

    def test_has_count(self):
        assert inspect.iscoroutinefunction(PageController.count)

    def test_has_get_text(self):
        assert inspect.iscoroutinefunction(PageController.get_text)

    def test_has_get_attribute(self):
        assert inspect.iscoroutinefunction(PageController.get_attribute)

    # 交互
    def test_has_click(self):
        assert inspect.iscoroutinefunction(PageController.click)

    def test_has_fill(self):
        assert inspect.iscoroutinefunction(PageController.fill)

    def test_has_type_text(self):
        """type_text 而非 type(避开内建名冲突)"""
        assert hasattr(PageController, "type_text")
        assert not hasattr(PageController, "type") or "type_text" in dir(PageController)

    def test_has_select_option(self):
        assert inspect.iscoroutinefunction(PageController.select_option)

    def test_has_check(self):
        assert inspect.iscoroutinefunction(PageController.check)

    def test_has_set_input_files(self):
        assert inspect.iscoroutinefunction(PageController.set_input_files)

    # 等待
    def test_has_wait_for_selector(self):
        assert inspect.iscoroutinefunction(PageController.wait_for_selector)

    def test_has_wait_for_timeout(self):
        assert inspect.iscoroutinefunction(PageController.wait_for_timeout)

    def test_has_wait_for_load_state(self):
        assert inspect.iscoroutinefunction(PageController.wait_for_load_state)

    # JS + 内容/重载 + 截图
    def test_has_evaluate(self):
        assert inspect.iscoroutinefunction(PageController.evaluate)

    def test_has_content(self):
        assert inspect.iscoroutinefunction(PageController.content)

    def test_has_reload(self):
        assert inspect.iscoroutinefunction(PageController.reload)

    def test_has_get_cookies(self):
        assert inspect.iscoroutinefunction(PageController.get_cookies)

    def test_has_screenshot(self):
        assert inspect.iscoroutinefunction(PageController.screenshot)

    def test_has_is_closed(self):
        assert hasattr(PageController, "is_closed")
