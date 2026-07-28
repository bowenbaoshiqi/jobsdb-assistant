"""
登录流程处理
"""

import asyncio
from typing import Optional

from loguru import logger

from config.settings import JobsDBConfig, LoginConfig
from src.accounts.registry import Account
from src.browser.ports.page_controller import PageController
from src.jobsdb.exceptions import CaptchaDetectedError, LoginError
from src.jobsdb.selectors import (
    LOGIN_EMAIL_INPUT,
    LOGIN_ERROR_MESSAGE,
    LOGIN_PASSWORD_INPUT,
    LOGIN_SUBMIT_BUTTON,
    RECAPTCHA_IFRAME,
    USER_AVATAR,
    USER_NAME,
)
from src.simulation.behavior import HumanSimulator
from src.storage.cookies import CookieStore
from src.utils.screenshot import capture_screenshot


class LoginHandler:
    """JobsDB 登录处理器

    支持两种模式(由 config.login.mode 控制):
    - auto:   自动填邮箱密码登录(需要凭证)
    - manual: 导航到登录页后等用户手动登录,被动轮询 _is_logged_in,
              登录成功后备份 cookies。不要求凭证,适合持久化 profile 一次登录长期复用。
    """

    def __init__(self, page: PageController, config: JobsDBConfig,
                 human: Optional[HumanSimulator] = None,
                 account: Optional[Account] = None,
                 login_config: Optional[LoginConfig] = None):
        self.page = page
        self.config = config
        self.human = human
        self.account = account
        # 默认 auto,保证向后兼容(LoginHandler(page, config) 两参构造仍走 v1.0 路径)
        self.login_config = login_config or LoginConfig()

    def _get_credentials(self) -> tuple[str, str]:
        """获取凭证：优先用 Account，其次用 JobsDBConfig"""
        if self.account:
            return self.account.email, self.account.password
        if self.config.email and self.config.password:
            logger.warning("使用 .env 中的 JOBSDB_EMAIL/PASSWORD（向后兼容）")
            return self.config.email, self.config.password
        raise LoginError("未配置账户凭证")

    async def ensure_logged_in(self) -> bool:
        """
        确保用户已登录

        Returns:
            True 如果登录成功或已经是登录状态
        """
        logger.info("Checking login status...")

        # 先导航到首页，确保不在 about:blank 上
        current_url = self.page.url
        if "about:blank" in current_url or not current_url.startswith("https://hk.jobsdb.com"):
            logger.info("Navigating to JobsDB homepage before login check...")
            await self.page.goto(
                self.config.homepage_url,
                wait_until="domcontentloaded",
            )
            # SPA 需要额外时间渲染用户菜单
            await asyncio.sleep(5)

        # 先检查是否已经在登录状态（带重试，SPA 可能延迟渲染）
        for attempt in range(3):
            if await self._is_logged_in():
                logger.info("Already logged in")
                return True
            if attempt < 2:
                logger.debug(f"Login check attempt {attempt+1} failed, waiting for page to render...")  # noqa: E501
                await asyncio.sleep(3)

        # 需要登录:按 config.login.mode 分支
        if self.login_config.mode == "manual":
            return await self._do_login_manual()

        logger.info("Need to login (auto)")
        return await self._do_login()

    async def _is_logged_in(self) -> bool:
        """检查当前是否已登录"""
        try:
            # 先关闭可能的 cookie banner
            try:
                cookie_accept = await self.page.query_selector('button:has-text("Accept")')
                if cookie_accept:
                    await cookie_accept.click()
                    await asyncio.sleep(1)
            except Exception as e:
                # cookie banner 关闭失败不阻断登录检查(三分法 B 类:降级)
                logger.debug(f"Cookie banner dismiss failed: {e}")

            # 尝试查找用户头像/用户名元素
            avatar = await self.page.query_selector(USER_AVATAR)
            if avatar:
                return True

            # 备选：检查用户名
            user_name = await self.page.query_selector(USER_NAME)
            if user_name:
                return True

            # 检查 cookies 中是否有登录态(cookie 是最权威信号,优先于 DOM 文案判断)
            cookies = await self.page.get_cookies()
            jobsdb_cookies = [c for c in cookies if "jobsdb" in c.get("domain", "")]
            # Auth0 登录态:auth0.<tenant>.is.authenticated=true(JobsDB 真实信号,2026-07 确认)
            # 比旧白名单(AccessToken 等)更稳:JobsDB 已迁到 Auth0,旧 cookie 名不再出现
            for c in jobsdb_cookies:
                name = c.get("name", "")
                value = c.get("value", "")
                if "is.authenticated" in name and value == "true":
                    logger.info("Found auth0 authenticated cookie, assuming logged in")
                    return True
            # 旧白名单(向后兼容,部分场景可能仍用)
            login_cookies = [c for c in jobsdb_cookies if c.get("name", "") in (
                "AccessToken", "RefreshToken", "JSESSIONID", "session_id",
                "auth_st", "user_status", "jsessionid", "access_token",
            )]
            if login_cookies:
                logger.info(f"Found {len(login_cookies)} login cookies, assuming logged in")
                return True

            # 检查页面是否有 "Sign in" 链接（有的话说明没登录）
            # 注意:此判断在 cookie 之后,避免登录态页面的页脚 "Sign in" 文案误判
            signin_link = await self.page.query_selector(
                'a[href*="login"], button:has-text("Sign in"), a:has-text("Sign in")'
            )
            if signin_link:
                return False

            # 检查是否有用户相关的文本
            page_content = await self.page.content()
            user_indicators = ["My jobs", "My profile", "Dashboard", "Account"]
            return any(indicator in page_content for indicator in user_indicators[:2])

        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            return False

    async def _do_login(self) -> bool:
        """
        执行登录流程

        流程:
        1. 导航到登录页
        2. 填写邮箱和密码
        3. 点击登录
        4. 等待跳转
        5. 验证登录成功
        """
        try:
            email, password = self._get_credentials()
        except LoginError:
            raise

        if not email or not password:
            raise LoginError("JobsDB email 和 password 未配置。"
                           "请在 .env 文件中设置 JOBSDB_EMAIL 和 JOBSDB_PASSWORD，"
                           "或用 `python -m src.main account add <alias>` 添加账户")

        try:
            logger.info(f"Navigating to login page: {self.config.login_url}")

            # ... 继续原有的登录流程 ...
            # 导航到首页/登录页
            await self.page.goto(self.config.login_url, wait_until="domcontentloaded")

            # 等待页面加载
            await asyncio.sleep(2)

            # 检查是否需要点击登录链接（从首页进入）
            signin_button = await self.page.query_selector(
                'a[href*="login"], button:has-text("Sign in")'
            )
            if signin_button:
                logger.debug("Clicking sign in link")
                if self.human:
                    await self.human.mouse.click_element(signin_button)
                else:
                    await signin_button.click()
                await asyncio.sleep(2)

            # 检查验证码
            if await self._check_for_captcha():
                raise CaptchaDetectedError("CAPTCHA detected on login page")

            # 找到邮箱输入框
            logger.debug("Filling email")
            email_input = await self.page.wait_for_selector(
                LOGIN_EMAIL_INPUT, timeout=10  # 秒(controller 内部 ×1000);误传 10000 会等 2.7h
            )
            if not email_input:
                raise LoginError("Email input not found")

            if self.human:
                await self.human.fill_form_field(email_input, email)
            else:
                await email_input.fill(email)

            await asyncio.sleep(0.5)

            # 找到密码输入框
            logger.debug("Filling password")
            password_input = await self.page.wait_for_selector(
                LOGIN_PASSWORD_INPUT, timeout=10
            )
            if not password_input:
                raise LoginError("Password input not found")

            if self.human:
                await self.human.fill_form_field(
                    password_input, password, is_password=True
                )
            else:
                await password_input.fill(password)

            await asyncio.sleep(0.5)

            # 点击登录按钮
            logger.debug("Clicking login button")
            submit_button = await self.page.wait_for_selector(
                LOGIN_SUBMIT_BUTTON, timeout=10
            )
            if not submit_button:
                raise LoginError("Login submit button not found")

            if self.human:
                await self.human.mouse.click_element(submit_button)
            else:
                await submit_button.click()

            # 等待导航（首页 or dashboard）
            logger.debug("Waiting for navigation after login...")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                # 超时也没关系,继续检查登录状态(三分法 B 类:降级)
                # 注:v2.0 收紧为只容忍超时类异常;其他异常应上抛
                logger.debug(f"Login load state wait failed (continuing): {e}")

            await asyncio.sleep(3)  # 给页面点时间渲染

            # 验证登录成功
            if await self._is_logged_in():
                logger.info("Login successful")
                return True

            # 检查是否有错误信息
            error_msg = await self._get_login_error()
            if error_msg:
                raise LoginError(f"Login failed: {error_msg}")

            # 仍不确定，尝试再等待一下
            await asyncio.sleep(3)
            if await self._is_logged_in():
                logger.info("Login successful (after extra wait)")
                return True

            # 登录失败
            screenshot = await capture_screenshot(self.page, "login_failed")
            logger.error(f"Login failed. Screenshot: {screenshot}")
            return False

        except CaptchaDetectedError:
            raise
        except LoginError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during login: {e}")
            screenshot = await capture_screenshot(self.page, "login_error")
            raise LoginError(f"Login failed with unexpected error: {e}") from e

    async def _do_login_manual(self) -> bool:
        """手动登录(manual 模式)

        导航到登录页 → logger 通知用户 → 被动轮询 _is_logged_in → 超时返回 False。
        全程不主动 goto(避免打断用户输密码/过验证码),不要求凭证。
        登录成功后 JobsDB 通常自动跳首页,此时 _is_logged_in 命中 → 备份 cookies → 返回 True。
        超时不抛异常,返回 False(让 Orchestrator 走 error_report,不误吞)。
        """
        # 导航到登录页给用户一个起点
        await self.page.goto(self.config.login_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 再查一次:持久化 profile 可能自带有效 session
        if await self._is_logged_in():
            logger.info("Manual login: already logged in, backing up cookies")
            await self._backup_session_cookies()
            return True

        wait_min = self.login_config.manual_wait_minutes
        interval = self.login_config.poll_interval_seconds
        # 轮询次数 = 总等待时长 / 间隔。至少 1 次,避免配置为 0 时跳过轮询
        deadline_iters = max(1, int(wait_min * 60 / interval))

        logger.warning(
            f"请在当前浏览器窗口登录 JobsDB(可处理验证码,程序不会刷新页面)。"
            f"等待手动登录...(最多 {wait_min} 分钟,每 {interval}s 检查一次)"
        )

        for attempt in range(deadline_iters):
            await asyncio.sleep(interval)
            try:
                if await self._is_logged_in():
                    logger.info("检测到已登录,备份 cookies")
                    await self._backup_session_cookies()
                    # 登录后稳定一下,导航到首页开始投递
                    await asyncio.sleep(2)
                    await self.page.goto(self.config.homepage_url, wait_until="domcontentloaded")  # noqa: E501
                    await asyncio.sleep(3)
                    return True
                if attempt % 4 == 0:
                    elapsed = (attempt + 1) * interval / 60
                    logger.info(f"仍在等待登录... ({elapsed:.1f} 分钟) URL: {self.page.url}")
            except Exception as e:
                # 三分法 B 类:降级 — 检查异常不阻断等待,不跳页
                logger.debug(f"登录检查异常(继续等,不跳页): {e}")

        logger.error(f"等待手动登录超时({wait_min} 分钟)")
        return False

    async def _backup_session_cookies(self) -> int:
        """登录成功后备份 jobsdb/seek 域 cookies 到 data/cookies_<alias>.json

        用 PageController.get_cookies()(接口方法,保持 v2.0 解耦一致)。
        只存 jobsdb/seek 域,与 BrowserEngine.cookie_store 的 account 隔离命名对齐。
        备份失败不阻断登录成功(三分法 B 类:降级)。
        """
        try:
            all_cookies = await self.page.get_cookies()
            session_cookies = [
                c for c in all_cookies
                if "jobsdb" in c.get("domain", "") or "seek" in c.get("domain", "")
            ]
            alias = self.account.alias if self.account else "default"
            CookieStore(f"./data/cookies_{alias}.json").save(session_cookies)
            logger.info(f"已备份 {len(session_cookies)} 个 JobsDB cookies")
            return len(session_cookies)
        except Exception as e:
            logger.warning(f"cookies 备份失败(非阻断): {e}")
            return 0

    async def _check_for_captcha(self) -> bool:
        """检查页面是否有验证码"""
        captcha = await self.page.query_selector(RECAPTCHA_IFRAME)
        if captcha:
            logger.warning("CAPTCHA detected on page")
            return True
        return False

    async def _get_login_error(self) -> Optional[str]:
        """获取登录错误信息

        v2.0: `except Exception: pass` → 捕获 + debug 日志
        (三分法 B 类:降级 — 错误信息取不到返回 None,不阻断登录流程)。
        """
        try:
            error_elem = await self.page.query_selector(LOGIN_ERROR_MESSAGE)
            if error_elem:
                return await error_elem.text_content()
        except Exception as e:
            logger.debug(f"Failed to get login error message: {e}")
        return None

    async def handle_session_refresh(self) -> bool:
        """
        处理 Session 过期后的重新登录
        """
        logger.info("Session expired, attempting re-login...")
        # 清除可能的问题状态
        await self.page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(2)
        return await self._do_login()
