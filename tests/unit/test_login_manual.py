"""
单元测试: LoginHandler 手动登录模式(manual mode)

验证 brainstorming 设计 docs/superpowers/specs/2026-07-21-manual-login-mode-design.md:
- manual 模式不要求凭证,绕过 _get_credentials
- manual 模式被动轮询 _is_logged_in,登录成功后备份 cookies
- manual 模式超时返回 False(不抛异常)
- auto 模式行为不变(无凭证仍抛 LoginError,回归保护 TC-15)
- login_config 默认 auto(向后兼容)

用 FakePageController 注入,不起浏览器。USER_AVATAR 元素存在 = 已登录。
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from config.settings import JobsDBConfig, LoginConfig
from src.accounts.registry import Account
from src.browser.fake.fake_page import FakeElement, FakePageController
from src.jobsdb.exceptions import LoginError
from src.jobsdb.login import LoginHandler
from src.jobsdb.selectors import USER_AVATAR


def _make_page(logged_in: bool = False, url: str = "https://hk.jobsdb.com/") -> FakePageController:
    """构造 FakePageController:logged_in=True 时预设 USER_AVATAR 元素(=_is_logged_in 命中)。"""
    page = FakePageController(url=url)
    if logged_in:
        page.set_element(USER_AVATAR, FakeElement(visible=True))
    return page


def _make_handler(page, mode: str = "manual", *,
                  manual_wait_minutes: int = 30,
                  poll_interval_seconds: float = 7.5,
                  account: Account = None) -> LoginHandler:
    """构造 LoginHandler,注入指定 login_config。account 默认 None(无凭证)。

    manual_wait_minutes 是 int(与 LoginConfig schema 一致);测试需快速超时时
    配合极小的 poll_interval_seconds + monkeypatch asyncio.sleep 为 no-op。
    """
    config = JobsDBConfig()
    login_config = LoginConfig(
        mode=mode,
        manual_wait_minutes=manual_wait_minutes,
        poll_interval_seconds=poll_interval_seconds,
    )
    return LoginHandler(page, config, human=None, account=account,
                        login_config=login_config)


# ═══════════════════════════════════════════════════════
#  默认配置(向后兼容)
# ═══════════════════════════════════════════════════════

class TestLoginConfigDefaults:
    def test_login_config_defaults_to_auto(self):
        """不传 login_config → 默认 auto(v1.0 行为)"""
        page = _make_page()
        handler = LoginHandler(page, JobsDBConfig())  # 两参构造,向后兼容
        assert handler.login_config.mode == "auto"


# ═══════════════════════════════════════════════════════
#  manual 模式:已登录短路
# ═══════════════════════════════════════════════════════

class TestManualModeAlreadyLoggedIn:
    @pytest.mark.asyncio
    async def test_initial_homepage_navigation_does_not_wait_for_network_idle(
        self,
        monkeypatch,
    ):
        page = AsyncMock()
        page.url = "about:blank"
        handler = _make_handler(page, mode="manual")
        monkeypatch.setattr(
            handler,
            "_is_logged_in",
            AsyncMock(return_value=True),
        )

        result = await handler.ensure_logged_in()

        assert result is True
        page.goto.assert_awaited_once_with(
            handler.config.homepage_url,
            wait_until="domcontentloaded",
        )

    @pytest.mark.asyncio
    async def test_manual_mode_no_credentials_succeeds_when_logged_in(self):
        """manual + profile 已登录 → 返回 True,不要求凭证,不进轮询"""
        page = _make_page(logged_in=True)
        # account=None,无 .env 凭证 → auto 模式会抛 LoginError,manual 不应抛
        handler = _make_handler(page, mode="manual", account=None)

        result = await handler.ensure_logged_in()

        assert result is True

    @pytest.mark.asyncio
    async def test_manual_mode_does_not_call_get_credentials(self, monkeypatch):
        """manual + 无凭证 → 不调用 _get_credentials(否则会抛 LoginError)"""
        page = _make_page(logged_in=True)
        handler = _make_handler(page, mode="manual", account=None)

        # 把 _get_credentials 替换成会抛异常的探针:若被调用,测试必失败
        async def _boom(self):
            raise AssertionError("manual 模式不应调用 _get_credentials")
        monkeypatch.setattr(LoginHandler, "_get_credentials", _boom)

        result = await handler.ensure_logged_in()
        assert result is True


# ═══════════════════════════════════════════════════════
#  manual 模式:轮询直到登录
# ═══════════════════════════════════════════════════════

class TestManualModePolling:
    @pytest.mark.asyncio
    async def test_manual_mode_polls_until_logged_in(self, monkeypatch):
        """manual + 首次未登录 → 轮询 N 次后 _is_logged_in 命中 → 返回 True"""
        page = _make_page(logged_in=False)
        handler = _make_handler(
            page, mode="manual",
            manual_wait_minutes=1, poll_interval_seconds=0.01,  # 极小,快速跑完
        )

        # asyncio.sleep 替换成立即返回(不真等),加速测试
        async def _no_sleep(_):
            return None
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)

        # ensure_logged_in 先在"已登录"预检循环调 _is_logged_in 3 次(都应 False),
        # 然后进 _do_login_manual。设阈值 >=5:预检 3 次 + manual 内首次检查(第4次)
        # 都 False,第 5 次(manual 轮询)起返回 True → 证明确实进了轮询循环。
        original_is_logged_in = LoginHandler._is_logged_in
        call_count = {"n": 0}

        async def _is_logged_in_after_polling(self):
            call_count["n"] += 1
            if call_count["n"] >= 5:
                page.set_element(USER_AVATAR, FakeElement(visible=True))
            return await original_is_logged_in(self)

        monkeypatch.setattr(LoginHandler, "_is_logged_in", _is_logged_in_after_polling)

        result = await handler.ensure_logged_in()

        assert result is True
        # 第 5 次才命中 → 证明经过了预检(3次)+ manual 内首次检查(1次)+ 至少 1 次轮询
        assert call_count["n"] >= 5


# ═══════════════════════════════════════════════════════
#  manual 模式:超时
# ═══════════════════════════════════════════════════════

class TestManualModeTimeout:
    @pytest.mark.asyncio
    async def test_manual_mode_timeout_returns_false(self, monkeypatch):
        """manual + 永远未登录 + 超时 → 返回 False(不抛异常)"""
        page = _make_page(logged_in=False)
        handler = _make_handler(
            page, mode="manual",
            manual_wait_minutes=1,             # int(schema 要求);配合下面的极小间隔
            poll_interval_seconds=0.01,        # 每次轮询间隔 0.01s
        )

        async def _no_sleep(_):
            return None
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)

        result = await handler.ensure_logged_in()

        assert result is False  # 超时,不抛异常

    @pytest.mark.asyncio
    async def test_manual_mode_timeout_does_not_raise_login_error(self, monkeypatch):
        """manual 超时 → 返回 False,不是 LoginError(Orchestrator 走 error_report,不误吞)"""
        page = _make_page(logged_in=False)
        handler = _make_handler(
            page, mode="manual",
            manual_wait_minutes=1, poll_interval_seconds=0.01,
        )

        async def _no_sleep(_):
            return None
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)

        # 不应抛任何异常,返回 False
        result = await handler.ensure_logged_in()
        assert result is False


# ═══════════════════════════════════════════════════════
#  manual 模式:cookie 备份
# ═══════════════════════════════════════════════════════

class TestManualModeCookieBackup:
    @pytest.mark.asyncio
    async def test_manual_mode_backs_up_jobsdb_cookies(self, monkeypatch, tmp_path):
        """_backup_session_cookies 只存 jobsdb/seek 域 cookie 到 cookies_<alias>.json

        直接测 _backup_session_cookies(纯单元):ensure_logged_in 的"已登录短路"
        路径不调备份(由 BrowserEngine.stop 统一保存),只有 _do_login_manual 登录
        成功才调。这里隔离验证域过滤逻辑。
        """
        page = _make_page(logged_in=True)
        page.set_cookies([
            {"name": "AccessToken", "value": "tok", "domain": ".jobsdb.com"},
            {"name": "JSESSIONID", "value": "js", "domain": ".seek.com"},
            {"name": "irrelevant", "value": "x", "domain": ".google.com"},
        ])
        acct = Account(alias="testacct", email="t@e.com", password="x")
        handler = _make_handler(page, mode="manual", account=acct)

        # 备份到 tmp_path(不污染 data/);替换 CookieStore 为写指定路径的替身
        import json
        cookie_file = tmp_path / "cookies_testacct.json"
        monkeypatch.setattr(
            "src.jobsdb.login.CookieStore",
            lambda path: _StubCookieStore(cookie_file),
        )

        n = await handler._backup_session_cookies()

        assert n == 2  # 只存 jobsdb + seek 两个
        assert cookie_file.exists()
        saved = json.loads(cookie_file.read_text())
        domains = {c["domain"] for c in saved}
        assert ".jobsdb.com" in domains
        assert ".seek.com" in domains
        assert ".google.com" not in domains  # 非 jobsdb/seek 域被过滤

    @pytest.mark.asyncio
    async def test_manual_login_path_calls_backup_on_success(self, monkeypatch, tmp_path):
        """_do_login_manual 登录成功(轮询命中)后调用 _backup_session_cookies

        端到端验证 manual 登录路径触发备份(与上面的纯单元互补)。
        """
        page = _make_page(logged_in=False)
        handler = _make_handler(
            page, mode="manual",
            manual_wait_minutes=1, poll_interval_seconds=0.01,
        )

        async def _no_sleep(_):
            return None
        monkeypatch.setattr(asyncio, "sleep", _no_sleep)

        # ensure_logged_in 先在"已登录"预检循环里调 _is_logged_in 3 次(都应返回 False),
        # 然后才进 _do_login_manual。设阈值 >=4:预检 3 次都 False,第 4 次
        # (manual 路径内的检查)起返回 True → 触发备份。
        original = LoginHandler._is_logged_in
        call_count = {"n": 0}

        async def _is_logged_in_then_yes(self):
            call_count["n"] += 1
            if call_count["n"] >= 4:
                page.set_element(USER_AVATAR, FakeElement(visible=True))
            return await original(self)

        monkeypatch.setattr(LoginHandler, "_is_logged_in", _is_logged_in_then_yes)

        # 探针:记录 _backup_session_cookies 是否被调用
        backup_called = {"v": False}
        original_backup = LoginHandler._backup_session_cookies

        async def _spy_backup(self):
            backup_called["v"] = True
            return await original_backup(self)

        monkeypatch.setattr(LoginHandler, "_backup_session_cookies", _spy_backup)

        result = await handler.ensure_logged_in()
        assert result is True
        assert backup_called["v"] is True


class _StubCookieStore:
    """替身 CookieStore:写到指定路径,供断言。实现 LoginHandler 用到的 save 方法。"""

    def __init__(self, path):
        self.path = path

    def save(self, cookies):
        import json
        self.path.write_text(json.dumps(cookies))


# ═══════════════════════════════════════════════════════
#  auto 模式:回归保护(TC-15 不破)
# ═══════════════════════════════════════════════════════
#  登录态检测:JobsDB 真实 cookie 信号(2026-07 e2e 暴露)
# ═══════════════════════════════════════════════════════

class TestIsLoggedInAuth0Detection:
    """_is_logged_in 必须识别 JobsDB 真实登录态 cookie。

    e2e 暴露:JobsDB 用 Auth0,登录态 cookie 是 auth0.<tenant>.is.authenticated=true,
    而非旧白名单的 AccessToken/RefreshToken/JSESSIONID。旧白名单 + 过时 DOM 选择器
    导致已登录的 profile 被判为未登录,manual 模式无限等待。
    """

    @pytest.mark.asyncio
    async def test_auth0_authenticated_cookie_means_logged_in(self):
        """有 auth0.*.is.authenticated=true cookie → 已登录(无需 DOM 元素)"""
        page = _make_page(logged_in=False)  # 无 avatar 元素
        page.set_cookies([
            {"name": "auth0.abc123.is.authenticated", "value": "true",
             "domain": ".jobsdb.com"},
            {"name": "JobseekerSessionId", "value": "xyz", "domain": ".jobsdb.com"},
        ])
        handler = _make_handler(page, mode="manual", account=None)

        assert await handler._is_logged_in() is True

    @pytest.mark.asyncio
    async def test_auth0_cookie_false_means_not_logged_in(self):
        """auth0.*.is.authenticated=false → 未登录"""
        page = _make_page(logged_in=False)
        page.set_cookies([
            {"name": "auth0.abc123.is.authenticated", "value": "false",
             "domain": ".jobsdb.com"},
        ])
        handler = _make_handler(page, mode="manual", account=None)

        assert await handler._is_logged_in() is False

    @pytest.mark.asyncio
    async def test_no_auth0_cookie_no_avatar_means_not_logged_in(self):
        """无 auth0 cookie + 无 avatar → 未登录"""
        page = _make_page(logged_in=False)
        page.set_cookies([
            {"name": "_ga", "value": "x", "domain": ".jobsdb.com"},  # 非 auth cookie
        ])
        handler = _make_handler(page, mode="manual", account=None)

        assert await handler._is_logged_in() is False

    @pytest.mark.asyncio
    async def test_avatar_still_means_logged_in(self):
        """avatar 元素存在 → 已登录(DOM 路径保留,多信号)"""
        page = _make_page(logged_in=True)  # 预设 USER_AVATAR
        page.set_cookies([])  # 无 cookie
        handler = _make_handler(page, mode="manual", account=None)

        assert await handler._is_logged_in() is True


# ═══════════════════════════════════════════════════════

class TestAutoModeRegression:
    @pytest.mark.asyncio
    async def test_auto_mode_still_requires_credentials(self):
        """auto + 无凭证 → 抛 LoginError(TC-15 回归保护)"""
        page = _make_page(logged_in=False)
        handler = _make_handler(page, mode="auto", account=None)

        with pytest.raises(LoginError):
            await handler.ensure_logged_in()
