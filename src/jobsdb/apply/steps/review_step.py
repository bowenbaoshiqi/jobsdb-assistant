"""
review_step — 审核与提交步骤

v1.0 _handle_review_step 的逻辑:找提交按钮,点击,等待,确认成功。
这是最关键的动作(真正提交申请)。
"""

import asyncio
import json

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.apply.detectors import check_success
from src.jobsdb.selectors import (
    CONFIRM_SUBMIT_BUTTON,
    SUBMIT_APPLICATION_BUTTON,
    SUBMIT_APPLICATION_FINAL,
)


def _verify_review_js(context: ApplicationMaterialContext) -> str:
    job_id = json.dumps(context.job_id)
    filename = json.dumps(context.resume_filename)
    require_resume = json.dumps(context.resume_filename is not None)
    cover_excerpt = json.dumps(
        " ".join(context.cover_letter_text.split())[:80]
    )
    return f"""() => {{
      const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
      const body = normalize(document.body?.innerText);
      const values = Array.from(document.querySelectorAll('textarea'))
        .map(item => normalize(item.value)).join(' ');
      const job = {job_id};
      const resume = {filename};
      const requireResume = {require_resume};
      const cover = {cover_excerpt};
      return {{
        job: location.href.includes(job) || body.includes(job),
        resume: !requireResume || body.includes(resume),
        cover_letter: body.includes(cover) || values.includes(cover)
      }};
    }}"""


class ReviewStep:
    """REVIEW 步骤处理器(点击提交)"""

    def __init__(
        self,
        context: ApplicationMaterialContext | None = None,
        *,
        allow_submit: bool = True,
    ) -> None:
        self.context = context
        self.allow_submit = allow_submit

    async def detect(self, page: PageController) -> bool:
        # 由 detectors 判定(Submit 按钮可见 → REVIEW);最终提交按钮优先
        for selector in (SUBMIT_APPLICATION_FINAL, SUBMIT_APPLICATION_BUTTON):
            submit_btn = await page.query_selector(selector)
            if submit_btn:
                return await submit_btn.is_visible()
        return False

    async def handle(self, page: PageController, human=None) -> bool:
        """处理审核与提交(v1.0 _handle_review_step)

        e2e(2026-07-22):review 页真实提交按钮文案是 "Submit application",
        优先用 SUBMIT_APPLICATION_FINAL 精确定位,避免误点向导顶部
        "Review and submit" 步骤指示按钮(也是 type=submit)。
        """
        try:
            if self.context is not None:
                verified = await page.evaluate(
                    _verify_review_js(self.context)
                )
                if not isinstance(verified, dict) or not all(
                    verified.get(key) is True
                    for key in ("job", "resume", "cover_letter")
                ):
                    logger.error(
                        f"Approved material review mismatch: {verified!r}"
                    )
                    return False
                if not self.allow_submit:
                    return True

            # 找提交按钮(最终提交按钮优先)
            submit_btn = await page.query_selector(SUBMIT_APPLICATION_FINAL)
            if not submit_btn:
                submit_btn = await page.query_selector(SUBMIT_APPLICATION_BUTTON)
            if not submit_btn:
                submit_btn = await page.query_selector(CONFIRM_SUBMIT_BUTTON)

            if not submit_btn:
                logger.error("Submit button not found")
                return False

            # 检查是否可点击
            is_visible = await submit_btn.is_visible()
            if not is_visible:
                logger.error("Submit button not visible")
                return False

            # 点击提交(最关键动作,加较长等待)
            logger.info("Clicking submit button")
            url_before = page.url

            if human:
                await human.click_apply_button(submit_btn)
            else:
                await submit_btn.click()

            # 等待提交响应
            await asyncio.sleep(3)

            # 检查成功状态(文案指标)
            if await check_success(page):
                return True

            # e2e(2026-07-22):提交成功但成功页文案不在指标里(用户实见成功页,
            # 但 check_success 判 False)。补充:URL 已离开 /apply/review → 判成功。
            if page.url != url_before and "/apply/review" not in page.url:
                logger.info(f"URL changed after submit ({page.url}), treating as submitted")
                return True

            # 诊断:把提交后的页面文本打进日志,便于补充成功文案指标
            try:
                text = await page.text_content("body")
                logger.warning(
                    f"Submit clicked but success not detected. "
                    f"URL={page.url} | page text[:300]={text[:300]!r}"
                )
            except Exception:
                pass
            return False

        except Exception as e:
            logger.warning(f"Review step error: {e}")
            return False
