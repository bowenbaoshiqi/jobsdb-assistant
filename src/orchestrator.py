"""
Orchestrator — Director layer, main loop

Coordinate all modules to complete the end-to-end job submission process.
"""

import asyncio
from typing import Optional

from loguru import logger
from playwright.async_api import Page

from config.settings import AppConfig, get_config
from src.accounts.registry import Account
from src.browser.ports.browser_port import BrowserPort
from src.browser.ports.page_controller import PageController
from src.factory import ComponentFactory, DefaultFactory
from src.jobsdb.apply.flow import ApplyFlow
from src.jobsdb.exceptions import (
    CaptchaDetectedError,
    JobsDBError,
    RateLimitError,
    SessionExpiredError,
)
from src.jobsdb.homepage import HomepageScraper
from src.jobsdb.job_detail import JobDetailPage
from src.jobsdb.login import LoginHandler
from src.jobsdb.search import build_search_url, normalize_keyword
from src.simulation.behavior import HumanSimulator
from src.storage.models import ApplyResult, ApplyStatus, JobListing, SessionStatus
from src.utils.screenshot import capture_screenshot, generate_session_id


class Orchestrator:
    """
    Director

    Main responsibilities:
    1. Initialize and coordinate all modules
    2. Execute the main loop: login → grab positions → submit
    3. Handle exceptions and alerts
    4. Generate session reports
    """

    def __init__(self, config: Optional[AppConfig] = None,
                 account: Optional[Account] = None,
                 max_jobs: Optional[int] = None,
                 factory: Optional[ComponentFactory] = None):
        self.config = config or get_config()
        self.account = account or Account(alias="default", email="", password="")
        self.max_jobs = max_jobs or self.config.scheduler.max_applies_per_session
        # 工厂注入:默认真实(DefaultFactory),测试可传 FakeFactory
        self.factory: ComponentFactory = factory or DefaultFactory(self.config)

        # Core modules(浏览器延迟创建,沿用 v1.0 时机)
        self.browser: Optional[BrowserPort] = None
        self.page: Optional[Page] = None
        self.page_controller: Optional[PageController] = None
        self.human: Optional[HumanSimulator] = None

        # Data storage (带账户隔离)— 走工厂
        self.db = self.factory.create_database(
            self.config.storage.database_path, self.account.alias
        )

        # JobsDB interaction(延迟创建,需要 page)
        self.login_handler: Optional[LoginHandler] = None
        self.scraper: Optional[HomepageScraper] = None

        # Scheduler — 走工厂
        self.queue_manager = self.factory.create_queue_manager(self.db, self.config.scheduler)
        self.rate_limiter = self.factory.create_rate_limiter(self.config.scheduler, self.db)
        self.timing_optimizer = self.factory.create_timing_optimizer(self.config.scheduler)

        # Monitor — 走工厂
        self.tracker = self.factory.create_tracker(self.db)
        self.alert = self.factory.create_alert_manager(self.config.monitoring.alert_on_captcha)
        self.stats = self.factory.create_stats(self.db)

        # State
        self.session_id: Optional[str] = None
        self.jobs_processed = 0
        self.jobs_succeeded = 0
        self.consecutive_failures = 0
        self.detection_suspected = False

    async def discover(
        self,
        keyword: str,
        limit: int = 50,
        excluded_job_ids: set[str] | None = None,
    ) -> dict:
        """Discover and persist JobsDB jobs without applying to them."""
        normalized_keyword = normalize_keyword(keyword)
        try:
            await self._init_browser()
            return await self._discover_loaded(
                normalized_keyword,
                limit,
                excluded_job_ids=excluded_job_ids,
            )
        except Exception:
            logger.exception("JobsDB discovery failed")
            return {
                "keyword": normalized_keyword,
                "error": "discovery_failed",
            }
        finally:
            await self._cleanup()

    async def _discover_loaded(
        self,
        keyword: str,
        limit: int,
        *,
        excluded_job_ids: set[str] | None = None,
    ) -> dict:
        """Run discovery after browser and login initialization."""
        await self.page_controller.goto(build_search_url(keyword))
        jobs = await self.scraper.get_search_jobs(
            max_jobs=limit,
            excluded_job_ids=excluded_job_ids,
        )
        report = {
            "keyword": keyword,
            "found": len(jobs),
            "captured": 0,
            "new": 0,
            "unchanged": 0,
            "changed": 0,
            "apply_types": {
                "quick_apply": 0,
                "apply": 0,
                "unknown": 0,
            },
            "failures": [],
        }

        for job in jobs:
            canonical_url = job.url or f"https://hk.jobsdb.com/job/{job.id}"
            detail = JobDetailPage(
                self.page_controller,
                canonical_url,
                self.human,
            )
            try:
                await detail.navigate_with_simulation()
                capture = await detail.capture_for_discovery(
                    job_id=job.id,
                    canonical_url=canonical_url,
                )
                state = self.db.save_discovered_job(capture)
            except Exception:
                logger.exception("Failed to capture discovered job {}", job.id)
                report["failures"].append({
                    "job_id": job.id,
                    "reason": "detail_capture_failed",
                })
                continue

            report["captured"] += 1
            report[state.value] += 1
            report["apply_types"][capture.apply_type.value] += 1

        return report

    async def run(self, job_ids: Optional[list[str]] = None) -> dict:
        """
        Main execution method

        Args:
            job_ids: 可选的指定职位 ID 列表。传入时跳过首页抓取,直接投递这些职位。

        Returns:
            Session summary report
        """
        logger.info("=" * 50)
        logger.info("JobsDB Resume Assistant Starting...")
        logger.info(f"Max jobs this session: {self.max_jobs}")
        if job_ids:
            logger.info(f"指定职位 IDs: {job_ids}")
        logger.info("=" * 50)

        try:
            # Phase 1: Initialize the browser
            await self._init_browser()

            # Phase 2: Login
            if not await self._ensure_login():
                return self._create_error_report("Login failed")

            # Phase 3: Grab recommended positions (或直接使用指定 IDs)
            if job_ids:
                jobs = [
                    JobListing(
                        id=jid,
                        title=f"Job {jid}",
                        company="Unknown",
                        url=f"https://hk.jobsdb.com/job/{jid}",
                    )
                    for jid in job_ids
                ]
            else:
                jobs = await self._scrape_jobs()

            if not jobs:
                logger.info("No new jobs to apply")
                return self._create_empty_report()

            # Phase 4: Build the queue
            queue = self.queue_manager.build_queue(jobs)
            if not queue:
                logger.info("No new jobs after filtering")
                return self._create_empty_report()

            # Phase 5: Process the queue
            self.session_id = generate_session_id(self.account.alias)
            self.tracker.start_session(session_id=self.session_id)
            await self._process_queue(queue)

            # Phase 6: Generate the report
            return self._create_session_report()
        except CaptchaDetectedError as e:
            logger.warning(f"CAPTCHA detected, manual resolution needed: {e}")
            return self._create_error_report(f"captcha: {e}")
        except SessionExpiredError as e:
            logger.warning(f"Session expired: {e}")
            return self._create_error_report(f"session_expired: {e}")
        except RateLimitError as e:
            logger.warning(f"Rate limited: {e}")
            return self._create_error_report(f"rate_limited: {e}")
        except JobsDBError as e:
            logger.exception(f"JobsDB error: {e}")
            return self._create_error_report(str(e))
        finally:
            await self._cleanup()

    async def _init_browser(self) -> None:
        """Initialize the browser"""
        logger.info(f"Initializing browser for account [{self.account.alias}]...")
        # 走工厂:DefaultFactory → PlaywrightBrowser,FakeFactory → FakeBrowser
        self.browser = self.factory.create_browser(self.account.alias)
        self.page_controller = await self.browser.start()

        # HumanSimulator 仍需原始 Playwright Page(mouse/viewport,超出 v2.0 解耦范围)
        # PlaywrightPageController(工厂产出)暴露 raw_page;FakeBrowser 的 page 无此属性时降级
        raw_page = getattr(self.page_controller, "raw_page", None)
        self.page = raw_page if raw_page is not None else self.page_controller

        # Initialize the human behavior simulator
        self.human = HumanSimulator(
            self.page,
            bezier_points=self.config.simulation.mouse_bezier_points,
            typo_probability=self.config.simulation.typing_typo_probability,
            base_delay_ms=self.config.simulation.typing_base_delay_ms,
            delay_variance_ms=self.config.simulation.typing_delay_variance_ms,
        )

        # Initialize the JobsDB handler — 走工厂
        # 传 config.login(LoginConfig):激活 manual/auto 模式切换
        self.login_handler = self.factory.create_login_handler(
            self.page_controller, self.config.jobsdb, self.human, self.account,
            login_config=self.config.login,
        )
        self.scraper = self.factory.create_scraper(self.page_controller, self.human)

    async def _ensure_login(self) -> bool:
        """Ensure login status"""
        try:
            return await self.login_handler.ensure_logged_in()
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def _scrape_jobs(self) -> list[JobListing]:
        """Grab positions from the homepage"""
        logger.info("Navigating to homepage to scrape jobs...")

        # Navigate to the homepage(走 PageController 接口)
        await self.page_controller.goto(self.config.jobsdb.homepage_url)
        await asyncio.sleep(3)  # Wait for dynamic content to load

        # Grab positions
        jobs = await self.scraper.get_recommended_jobs(max_jobs=50)

        # Save the position information to the database
        for job in jobs:
            self.db.save_job(job)

        return jobs

    async def _process_queue(self, queue: list[JobListing]) -> None:
        """Process the application queue"""
        logger.info(f"Processing {len(queue)} jobs...")

        for i, job in enumerate(queue, 1):
            # max_jobs 硬上限(覆盖 build_queue 的 max_applies_per_session 上限)
            if i > self.max_jobs:
                logger.info(f"Reached max_jobs limit ({self.max_jobs}), stopping")
                break
            logger.info(f"[{i}/{len(queue)}] Processing: {job.title} @ {job.company}")

            # Frequency limit check
            await self.rate_limiter.wait_if_needed()

            # Check if suspected of being detected
            if self.detection_suspected:  # noqa: SIM102 (nested for comment clarity)
                if self.consecutive_failures >= self.config.monitoring.suspicion_threshold:
                    logger.warning("Detection threshold reached, aborting session")
                    self.tracker.end_session(
                        self.session_id,
                        SessionStatus.ABORTED,
                        "Detection suspected",
                    )
                    return

            # Execute the application
            result = await self._apply_to_job(job)

            # Update statistics
            self.jobs_processed += 1
            if result.status == ApplyStatus.SUBMITTED:
                self.jobs_succeeded += 1
                self.consecutive_failures = 0
            elif result.status == ApplyStatus.FAILED:
                self.consecutive_failures += 1
            elif result.status == ApplyStatus.CAPTCHA:
                # CAPTCHA, wait for manual resolution
                await self.alert.captcha_alert(self.page_controller, self.page.url)
                self.consecutive_failures = 0

            # Record the application result
            self.tracker.record_application(self.session_id, job, result)

            # Detection suspicion check
            if self.consecutive_failures >= self.config.monitoring.suspicion_threshold:
                self.detection_suspected = True
                self.alert.detection_suspected_alert(
                    f"{self.consecutive_failures} consecutive failures"
                )

            # Random distraction behavior (simulate real human "daydreaming")
            if i < len(queue) and not self.detection_suspected:  # noqa: SIM102
                if asyncio.iscoroutinefunction(self.human.random_distractor):
                    await self.human.random_distractor()

        # Normal end of session
        self.tracker.end_session(self.session_id, SessionStatus.COMPLETED)

    async def _apply_to_job(self, job: JobListing) -> ApplyResult:
        """
        Apply to a single position

        Full process:
        1. Navigate to the position details page
        2. Check if already applied
        3. Click the apply button
        4. Process the application form
        5. Confirm the result
        """
        try:
            # Navigate to the position details page
            detail_page = JobDetailPage(self.page_controller, job.url, self.human)
            await detail_page.navigate_with_simulation()

            # Check if already applied
            if await detail_page.is_already_applied():
                logger.info(f"Already applied to {job.title}, skipping")
                return ApplyResult(
                    status=ApplyStatus.SKIPPED,
                    job_id=job.id,
                    reason="already_applied",
                )

            # Get the apply button(只投 Quick Apply;标准 Apply 职位跳过)
            apply_button = await detail_page.get_apply_button()
            if not apply_button:
                # v1.0 策略:无 quick-apply 按钮 = 标准 Apply 职位(跳外部/需手动),不投。
                # 旧版判 FAILED,连续 2 个就误触 detection 阈值中止会话(e2e 2026-07-22 暴露)。
                logger.info(f"No Quick Apply button for {job.title}, skipping (standard Apply)")
                return ApplyResult(
                    status=ApplyStatus.SKIPPED,
                    job_id=job.id,
                    reason="not_quick_apply",
                )

            # Click the apply button
            # e2e(2026-07-22)暴露:详情页 React 重渲染会让拿到的 ElementHandle 在点击前
            # detached → "Element is not attached to the DOM"。标准解法:detached 时
            # 重新拉取按钮再点(最多 3 次);若重拉时页面已跳 /apply,说明上次点击其实已生效。
            clicked = False
            for attempt in range(3):
                try:
                    if attempt > 0:
                        apply_button = await detail_page.get_apply_button()
                        if not apply_button:
                            if "/apply" in self.page_controller.url:
                                clicked = True
                                break
                            return ApplyResult(
                                status=ApplyStatus.SKIPPED,
                                job_id=job.id,
                                reason="not_quick_apply",
                            )
                    if self.human:
                        await self.human.click_apply_button(apply_button)
                    else:
                        await apply_button.click()
                        await asyncio.sleep(2)
                    clicked = True
                    break
                except Exception as e:
                    if "not attached" not in str(e):
                        raise
                    logger.warning(
                        f"Apply button detached (attempt {attempt + 1}/3), refetching: {e}"
                    )
                    await asyncio.sleep(1)
            if not clicked:
                raise JobsDBError(f"Apply button keeps detaching for job {job.id}")

            # Wait for the form/modal to appear
            await asyncio.sleep(2)

            # Handle the application flow
            apply_flow = ApplyFlow(self.page_controller, self.human)
            result = await apply_flow.apply(job.id)

            return result

        except Exception as e:
            logger.exception(f"Error applying to job {job.id}: {e}")
            screenshot = await capture_screenshot(self.page_controller, f"error_{job.id}")
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job.id,
                error_message=str(e),
                screenshot_path=screenshot,
            )

    def _create_session_report(self) -> dict:
        """Create a session report"""
        if not self.session_id:
            return self._create_error_report("No session created")

        summary = self.stats.get_session_summary(self.session_id)

        logger.info("=" * 50)
        logger.info("Session Summary")
        logger.info(f"  Session ID: {self.session_id}")
        logger.info(f"  Jobs processed: {summary['total']}")
        logger.info(f"  Successful: {summary['success']}")
        logger.info(f"  Failed: {summary['failed']}")
        logger.info(f"  Skipped: {summary['skipped']}")
        logger.info(f"  Success rate: {summary['success_rate']}%")
        logger.info("=" * 50)

        return summary

    def _create_error_report(self, error: str) -> dict:
        """Create an error report"""
        return {
            "error": error,
            "session_id": self.session_id,
            "total": self.jobs_processed,
            "success": self.jobs_succeeded,
            "success_rate": 0,
        }

    def _create_empty_report(self) -> dict:
        """Create an empty report (no jobs)"""
        return {
            "message": "No jobs to apply",
            "total": 0,
            "success": 0,
            "success_rate": 0,
        }

    async def _cleanup(self) -> None:
        """Clean up resources"""
        if self.browser:
            await self.browser.stop()
            logger.info("Browser stopped")
