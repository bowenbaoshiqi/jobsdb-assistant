"""
FakePageController — PageController 接口的纯内存假实现

测试专用:不起浏览器,用 dict 预设 selector → element 的状态。
让 jobsdb/* 的逻辑能用 FakePageController 单测,毫秒级。

用法:
    fake = FakePageController()
    fake.set_element(SELECTOR, FakeElement(text="hello", visible=True))
    assert await fake.get_text(SELECTOR) == "hello"
"""

from typing import Any, Optional


class FakeElement:
    """内存元素:模拟 Playwright ElementHandle 的常用方法"""

    def __init__(self, text: Optional[str] = None, visible: bool = True,
                 checked: bool = False, attributes: Optional[dict] = None):
        self._text = text
        self._visible = visible
        self._checked = checked
        self._attributes = attributes or {}
        self.click = AsyncMockLike()
        self.fill = AsyncMockLike()
        self.text_content = AsyncMockLike(return_value=text)
        self.get_attribute = AsyncMockLike(return_func=self._get_attr)
        self.is_visible = AsyncMockLike(return_value=visible)
        self.is_checked = AsyncMockLike(return_value=checked)

    def _get_attr(self, *args, **kwargs):
        # args[0] 是 attr name,但我们通过 get_attribute(attr) 调用
        return None

    def set_attribute(self, name: str, value: str):
        self._attributes[name] = value
        # 更新 get_attribute 的行为
        self.get_attribute = AsyncMockLike(return_func=lambda attr=name: self._attributes.get(attr))


class AsyncMockLike:
    """简易 async mock:记录调用,返回预设值"""

    def __init__(self, return_value=None, return_func=None):
        self._return_value = return_value
        self._return_func = return_func
        self.call_count = 0
        self.call_args = None

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.call_args = (args, kwargs)
        if self._return_func is not None:
            return self._return_func(*args, **kwargs)
        return self._return_value


class FakePageController:
    """PageController 的内存假实现。"""

    def __init__(self, url: str = "https://fake.example.com/page"):
        self._url = url
        self._elements: dict[str, Optional[FakeElement]] = {}
        self._element_lists: dict[str, list] = {}
        self._closed = False
        self._goto_calls: list[str] = []
        self._eval_results: dict[str, Any] = {}
        self._screenshot_paths: list[str] = []
        self._cookies: list = []
        self._input_files: list[tuple[str, str]] = []
        # ScrollSimulator 读 page.viewport_size["height"];给个合理默认让假实现可滚动
        self.viewport_size: dict = {"width": 1280, "height": 800}

    # --- 预设 API(测试用) ---
    def set_element(self, selector: str, element: Optional[FakeElement]) -> None:
        """预设 selector 对应的元素(None = 不存在)"""
        if element is None:
            self._elements.pop(selector, None)
        else:
            self._elements[selector] = element

    def set_elements(self, selector: str, elements: list) -> None:
        """预设 query_selector_all 的返回"""
        self._element_lists[selector] = elements

    def set_visible(self, selector: str, visible: bool) -> None:
        """便利:预设 selector 可见性(自动建元素)"""
        elem = self._elements.get(selector) or FakeElement()
        elem._visible = visible
        elem.is_visible = AsyncMockLike(return_value=visible)
        self._elements[selector] = elem

    def set_text(self, selector: str, text: Optional[str]) -> None:
        """便利:预设 selector 的文本"""
        elem = self._elements.get(selector) or FakeElement()
        elem._text = text
        elem.text_content = AsyncMockLike(return_value=text)
        self._elements[selector] = elem

    def set_attribute(self, selector: str, attr: str, value: Optional[str]) -> None:
        elem = self._elements.get(selector) or FakeElement()
        elem.set_attribute(attr, value)
        self._elements[selector] = elem

    def set_body_text(self, text: str) -> None:
        """预设 body 文本(供 _check_success 的文本匹配)"""
        self._body_text = text

    # --- 导航 ---
    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        self._url = url
        self._goto_calls.append(url)

    @property
    def url(self) -> str:
        return self._url

    # --- 查询 ---
    async def query_selector(self, selector: str):
        return self._elements.get(selector)

    async def query_selector_all(self, selector: str) -> list:
        return self._element_lists.get(selector, [])

    async def is_visible(self, selector: str) -> bool:
        elem = self._elements.get(selector)
        if elem is None:
            return False
        return await elem.is_visible()

    async def count(self, selector: str) -> int:
        return len(self._element_lists.get(selector, []))

    async def get_text(self, selector: str) -> Optional[str]:
        elem = self._elements.get(selector)
        if elem is None:
            return None
        return await elem.text_content()

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        elem = self._elements.get(selector)
        if elem is None:
            return None
        return await elem.get_attribute(attr)

    # --- 交互 ---
    async def click(self, selector: str, timeout: float = 30.0) -> None:
        elem = self._elements.get(selector)
        if elem:
            await elem.click()

    async def fill(self, selector: str, value: str) -> None:
        elem = self._elements.get(selector)
        if elem:
            await elem.fill(value)

    async def type_text(self, selector: str, value: str, delay: int = 50) -> None:
        pass  # 假实现不模拟打字

    async def select_option(self, selector: str, value: str) -> None:
        pass

    async def check(self, selector: str) -> None:
        pass

    async def set_input_files(self, selector: str, path: str) -> None:
        self._input_files.append((selector, path))

    # --- 等待 ---
    async def wait_for_selector(self, selector: str, timeout: float = 30.0) -> None:
        pass  # 假实现立即返回

    async def wait_for_timeout(self, ms: int) -> None:
        pass  # 不真等待

    async def wait_for_load_state(self, state: str = "load", timeout: float = 30.0) -> None:
        pass  # 假实现立即返回

    # --- JS ---
    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        # Playwright Page.evaluate(expression, arg) 可带参;假实现忽略 arg,按 expression 返回预设
        return self._eval_results.get(expression)

    def set_eval_result(self, expression: str, result: Any) -> None:
        self._eval_results[expression] = result

    # --- 页面内容/重载 ---
    async def content(self) -> str:
        return getattr(self, "_body_text", "")

    async def reload(self, wait_until: str = "domcontentloaded") -> None:
        pass  # 假实现不真重载

    # --- Cookie(登录态检测用) ---
    async def get_cookies(self) -> list:
        return list(self._cookies)

    def set_cookies(self, cookies: list) -> None:
        """预设 cookies(供登录态检测测试)"""
        self._cookies = cookies

    # --- 截图 ---
    async def screenshot(self, path: str, full_page: bool = False) -> None:
        self._screenshot_paths.append(path)

    def is_closed(self) -> bool:
        return self._closed

    async def text_content(self, selector: str = "body") -> Optional[str]:
        """模拟 page.text_content('body') — 必须是 async 以匹配真实 Playwright Page

        v1.0 _check_success 用 `await self.page.text_content("body")`:
        真实 Page.text_content 是协程;若此处是同步方法,await 一个 str 会抛
        TypeError,被 _check_success 的 bare except 吞掉 → 永远返回 False。
        """
        if selector == "body":
            return getattr(self, "_body_text", "")
        elem = self._elements.get(selector)
        return elem._text if elem else None
