"""
flow — 申请流程状态机骨架

v2.0: 从 v1.0 apply_flow.py(543 行) 拆出的主循环。只含:
- ApplyStep 枚举
- ApplyFlow.apply() 主循环(状态推进 + 超时/计数)
- default_handler_chain()(按优先级的步骤处理器链)

每个 step 的处理逻辑在 steps/* 独立类里,可单独用 FakePageController 测。
行为与 v1.0 完全一致(机械迁移),特征化测试保证。
"""

import asyncio
import random
import time
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.detectors import (
    check_captcha,
    check_success,
    detect_current_step,
    get_error_message,
)
from src.jobsdb.apply.step_base import ApplyStep, StepHandler
from src.jobsdb.apply.steps import (
    CoverLetterStep,
    QuestionsStep,
    ResumeStep,
    ReviewStep,
    SubmitStep,
)
from src.jobsdb.exceptions import CaptchaDetectedError
from src.jobsdb.selectors import APPLY_FORM, APPLY_MODAL, SUBMIT_APPLICATION_BUTTON
from src.simulation.behavior import HumanSimulator
from src.storage.models import ApplyResult, ApplyStatus
from src.utils.screenshot import capture_screenshot

# 校验错误兜底:补填页面中未选择的下拉,选**最后一个**有效选项(用户 2026-07-22 指定:
# 如教育程度,最后一个通常是最高学位)。React 受控组件需 native setter + input/change 事件。
# noqa: E501 — JS 模板行不可拆
_AUTOFILL_SELECTS_JS = r"""() => {
  const sels = Array.from(document.querySelectorAll('select'))
    .filter(s => s.offsetParent !== null && !s.disabled);
  let filled = 0;
  for (const s of sels) {
    const cur = s.options[s.selectedIndex];
    const curEmpty = !s.value || !cur || cur.disabled || cur.textContent.trim() === ''
      || /select|请选择|請選擇/i.test(cur.textContent);
    if (!curEmpty) continue;
    const valid = Array.from(s.options).filter(o => o.value && !o.disabled);
    if (valid.length === 0) continue;
    const target = valid[valid.length - 1];
    try {
      const proto = window.HTMLSelectElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(s, target.value);
    } catch (e) { s.value = target.value; }
    s.dispatchEvent(new Event('input', { bubbles: true }));
    s.dispatchEvent(new Event('change', { bubbles: true }));
    filled++;
  }
  return filled;
}"""

# 步骤 → handler 映射(v1.0 _handle_step 的 handlers dict 等价)
_STEP_HANDLERS = {
    ApplyStep.RESUME_SELECTION: ResumeStep(),
    ApplyStep.QUESTIONS: QuestionsStep(),
    ApplyStep.COVER_LETTER: CoverLetterStep(),
    ApplyStep.REVIEW: ReviewStep(),
}


def default_handler_chain() -> list[StepHandler]:
    """默认步骤处理器链(按优先级)"""
    return [
        SubmitStep(),       # SUBMITTED 检测优先
        ResumeStep(),
        QuestionsStep(),
        CoverLetterStep(),
        ReviewStep(),
    ]


class ApplyFlow:
    """申请流程处理器(v2.0 状态机骨架)"""

    def __init__(self, page: PageController, human: Optional[HumanSimulator] = None,
                 max_steps: int = 10,
                 handlers: Optional[list[StepHandler]] = None):
        self.page = page
        self.human = human
        self.max_steps = max_steps
        self.handlers = handlers or default_handler_chain()
        self.current_step: ApplyStep = ApplyStep.UNKNOWN
        self.step_count = 0
        self.start_time: Optional[float] = None

    async def apply(self, job_id: str) -> ApplyResult:
        """执行完整申请流程(v1.0 apply 主循环,行为一致)"""
        self.start_time = time.time()
        self.step_count = 0
        self._autofill_attempted_for: Optional[str] = None
        self._last_unknown_url: Optional[str] = None
        self._same_url_count = 0

        try:
            logger.info(f"Starting apply flow for job {job_id}")

            # 检测到 CAPTCHA
            if await check_captcha(self.page):
                return ApplyResult(
                    status=ApplyStatus.CAPTCHA,
                    job_id=job_id,
                    error_message="CAPTCHA detected",
                )

            # 处理可能的弹窗
            await self._dismiss_popups()

            # 等待申请表单/弹窗出现
            await self._wait_for_apply_form()

            # 状态机循环
            while self.step_count < self.max_steps:
                self.step_count += 1
                current = await detect_current_step(self.page)
                self.current_step = current
                logger.debug(f"Apply step {self.step_count}: {current.value}")

                if current == ApplyStep.SUBMITTED:
                    # 成功!
                    duration = time.time() - self.start_time
                    return ApplyResult(
                        status=ApplyStatus.SUBMITTED,
                        job_id=job_id,
                        duration_seconds=round(duration, 2),
                    )

                if current == ApplyStep.UNKNOWN:
                    # 无法识别当前阶段,检查是否已在成功状态
                    if await check_success(self.page):
                        duration = time.time() - self.start_time
                        return ApplyResult(
                            status=ApplyStatus.SUBMITTED,
                            job_id=job_id,
                            duration_seconds=round(duration, 2),
                        )

                    error = await get_error_message(self.page)

                    # 卡住检测(e2e 2026-07-22):同一 URL 连续点 Continue 都不前进
                    # (如校验阻断但错误横幅消失),空转到 max_steps 浪费 1 分钟/职位。
                    url = self.page.url or ""
                    if url == self._last_unknown_url:
                        self._same_url_count += 1
                    else:
                        self._same_url_count = 0
                        self._last_unknown_url = url
                    if self._same_url_count >= 4:
                        return ApplyResult(
                            status=ApplyStatus.FAILED,
                            job_id=job_id,
                            error_message=f"Stuck at {url} (Continue not advancing)",
                        )

                    # e2e(2026-07-22):quick-apply 向导中间页(如 /apply/profile)
                    # 无特定步骤特征,策略是只要有 Continue 就点它继续前进。
                    # 注意:profile 页的信息横幅("Your Jobsdb Profile is part of...")
                    # 会误命中 ERROR_MESSAGE 选择器,不能见到 error 就 FAILED;
                    # 真正的校验错误("please address the following issues")
                    # 先自动补填空的下拉,再点 Continue;同一错误补填后仍出现才放弃。
                    if await self._has_visible_continue():
                        if error and self._is_validation_error(error):
                            if self._autofill_attempted_for == error:
                                return ApplyResult(
                                    status=ApplyStatus.FAILED,
                                    job_id=job_id,
                                    error_message=error,
                                )
                            await self._autofill_empty_selects()
                            self._autofill_attempted_for = error
                        await self._click_continue()
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        continue

                    # 无 Continue 且有错误 → 失败
                    if error:
                        return ApplyResult(
                            status=ApplyStatus.FAILED,
                            job_id=job_id,
                            error_message=error,
                        )

                    # 可能还在加载
                    await asyncio.sleep(1)
                    continue

                # 处理当前阶段
                success = await self._handle_step(current)
                if not success:
                    return ApplyResult(
                        status=ApplyStatus.FAILED,
                        job_id=job_id,
                        error_message=f"Failed at step: {current.value}",
                    )

                # 阶段转换等待
                await asyncio.sleep(random.uniform(1.5, 3.0))

            # 超过最大步数
            screenshot = await capture_screenshot(
                self.page,
                f"apply_max_steps_{job_id}",
            )
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job_id,
                error_message="Max steps exceeded",
                screenshot_path=screenshot,
            )

        except CaptchaDetectedError:
            return ApplyResult(
                status=ApplyStatus.CAPTCHA,
                job_id=job_id,
                error_message="CAPTCHA detected",
            )
        except Exception as e:
            logger.exception(f"Apply flow error: {e}")
            screenshot = await capture_screenshot(self.page, f"apply_error_{job_id}")
            return ApplyResult(
                status=ApplyStatus.FAILED,
                job_id=job_id,
                error_message=str(e),
                screenshot_path=screenshot,
            )

    async def _handle_step(self, step: ApplyStep) -> bool:
        """处理指定阶段(v1.0 _handle_step:委托给对应 handler)"""
        handler = _STEP_HANDLERS.get(step)
        if handler:
            return await handler.handle(self.page, self.human)
        return False

    async def _has_visible_continue(self) -> bool:
        from src.jobsdb.selectors import CONTINUE_BUTTON
        btn = await self.page.query_selector(CONTINUE_BUTTON)
        return bool(btn and await btn.is_visible())

    async def _click_continue(self) -> None:
        """UNKNOWN 页兜底:点可见的 Continue 按钮(向导中间页一路前进)"""
        from src.jobsdb.selectors import CONTINUE_BUTTON
        btn = await self.page.query_selector(CONTINUE_BUTTON)
        if btn and await btn.is_visible():
            logger.info("Unknown step, Continue button found, clicking to advance")
            if self.human:
                await self.human.mouse.click_element(btn)
            else:
                await btn.click()

    @staticmethod
    def _is_validation_error(error: str) -> bool:
        """区分真正的表单校验错误与信息横幅(e2e 2026-07-22:

        profile 页 "Your Jobsdb Profile is part of your application..." 横幅
        会误命中 ERROR_MESSAGE 选择器,但它不是错误,点 Continue 即可前进)。
        """
        markers = (
            "please address the following issues",
            "please make a selection",
            "this field is required",
            "is required",
        )
        lower = error.lower()
        return any(m in lower for m in markers)

    async def _autofill_empty_selects(self) -> None:
        """校验错误兜底:自动补填页面中未选择的下拉(选最后一个有效选项,用户 2026-07-22 指定)"""
        try:
            filled = await self.page.evaluate(_AUTOFILL_SELECTS_JS)
            if filled:
                logger.info(f"Auto-filled {filled} empty select(s) after validation error")
        except Exception as e:
            logger.debug(f"autofill selects failed: {e}")

    async def _dismiss_popups(self) -> None:
        """关闭可能的弹窗(v1.0 _dismiss_popups,委托到 steps/popup_dismiss)"""
        from src.jobsdb.apply.steps.popup_dismiss import run as dismiss_popups
        await dismiss_popups(self.page)

    async def _wait_for_apply_form(self) -> None:
        """等待申请表单出现(v1.0 _wait_for_apply_form)"""
        try:
            await self.page.wait_for_selector(
                f"{APPLY_MODAL}, {APPLY_FORM}, {SUBMIT_APPLICATION_BUTTON}",
                # 单位是秒(PageController 内部 ×1000 转 ms);e2e 曾传 10000 → 等 2.7h 卡死
                timeout=10,
            )
        except Exception:
            logger.warning("Apply form not detected, proceeding anyway")
