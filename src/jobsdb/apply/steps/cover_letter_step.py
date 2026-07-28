"""
cover_letter_step — 求职信步骤

e2e(2026-07-22)修复:JobsDB 一键申请的求职信步骤是一页式单选表单
(https://hk.jobsdb.com/job/{id}/apply),三个 label 文本单选:
    "Upload a cover letter" / "Write a cover letter" / "Don't include a cover letter"
label[for] 指向的 radio id 动态生成(如 id-_r_2d_),无固定选择器。

策略(用户 2026-07-22 明确指示):始终选 "Don't include a cover letter",
再点底部 "Continue" 前进。旧版只填 textarea + 点 Next 的逻辑对不上真实 DOM,
导致流程卡死在求职信页。

实现细节:
1. "Don't include a cover letter" 选项用 cover_letter_js 的 JS 按 label 文本点击
   (label 关联 radio,el.click() 即可正确切换选中状态)。
2. Continue 按钮在真实 DOM 中由 React 渲染,必须用 Playwright 原生
   ElementHandle.click() 才能触发跳转,所以这里用选择器找 Continue 按钮再点。
   选择器用 `button:has-text("Continue")`:Playwright 的 :has-text 会归一化零宽
   字符(U+2060),实测能命中真实按钮。
"""

import asyncio
import json

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.apply.steps.cover_letter_js import (
    _CLICK_NO_COVER_LETTER_JS,
    _HAS_COVER_LETTER_JS,
)
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import CONTINUE_BUTTON, COVER_LETTER_SECTION

# v1.0 _handle_cover_letter_step 的通用求职信内容(保留:某些职位强制要求写求职信,
# 此时 "Don't include" 不可选,需 fallback 写一段进 textarea。当前主路径用不到。)
_COVER_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for this position. "
    "With my relevant experience and skills, I believe I would be a great fit. "
    "I look forward to the opportunity to discuss how I can contribute to your team.\n\n"
    "Best regards"
)

# 底部 Continue 按钮。用 :has-text("Continue") 而非固定 id/class;
# Playwright 的 :has-text 会归一化零宽字符(U+2060),实测能命中真实按钮。
def _fill_cover_letter_js(text: str) -> str:
    encoded = json.dumps(text)
    return f"""() => {{
      const approved = {encoded};
      const labels = Array.from(document.querySelectorAll('label'));
      const include = labels.find(label =>
        /write a cover letter|include a cover letter/i.test(label.textContent || '')
        && !/don't|do not/i.test(label.textContent || '')
      );
      if (include) include.click();
      const textarea = document.querySelector(
        'textarea[data-automation="cover-letter-text"], '
        + 'textarea[placeholder*="cover letter" i], textarea'
      );
      if (!textarea) return {{ selected: Boolean(include), filled: false }};
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype, 'value'
      ).set;
      setter.call(textarea, approved);
      textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
      textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return {{
        selected: Boolean(include),
        filled: textarea.value === approved
      }};
    }}"""


class CoverLetterStep:
    """COVER_LETTER 步骤处理器"""

    def __init__(
        self,
        context: ApplicationMaterialContext | None = None,
    ) -> None:
        self.context = context

    async def detect(self, page: PageController) -> bool:
        """当前页是否为求职信步骤。

        主判定:按 label 文本含 "cover letter"(真实一页式表单)。
        兜底:旧版 COVER_LETTER_SECTION 选择器(防御其他 DOM 变体)。
        """
        if await page.query_selector(COVER_LETTER_SECTION):
            return True
        try:
            return bool(await page.evaluate(_HAS_COVER_LETTER_JS))
        except Exception:
            return False

    async def handle(self, page: PageController, human=None) -> bool:
        """处理求职信:选 "Don't include a cover letter" → 点 Continue。"""
        try:
            if self.context is not None:
                filled = await page.evaluate(
                    _fill_cover_letter_js(self.context.cover_letter_text)
                )
                if (
                    not isinstance(filled, dict)
                    or filled.get("selected") is not True
                    or filled.get("filled") is not True
                ):
                    return False
                continue_btn = await page.query_selector(CONTINUE_BUTTON)
                if not continue_btn or not await continue_btn.is_visible():
                    return False
                if human:
                    await human.mouse.click_element(continue_btn)
                else:
                    await continue_btn.click()
                return True

            selected = False
            try:
                result = await page.evaluate(_CLICK_NO_COVER_LETTER_JS)
                if isinstance(result, dict):
                    selected = bool(result.get("selected"))
                elif result is True:
                    selected = True
            except Exception as e:
                from loguru import logger
                logger.debug(f"click-no-cover-letter JS failed: {e}")

            if selected:
                from loguru import logger
                logger.info("Selected 'Don't include a cover letter'")
                await asyncio.sleep(0.5)

            if selected:
                # 真实 Continue 按钮必须用 Playwright 原生 click() 才能触发
                # React 跳转。
                continue_btn = await page.query_selector(CONTINUE_BUTTON)
                if continue_btn and await continue_btn.is_visible():
                    if human:
                        await human.mouse.click_element(continue_btn)
                    else:
                        await continue_btn.click()
                    await asyncio.sleep(2)
                    return True

            # 兜底:填 textarea 或点 Next/Submit
            from src.jobsdb.selectors import COVER_LETTER_TEXTAREA
            textarea = await page.query_selector(COVER_LETTER_TEXTAREA)
            if textarea:
                if human:
                    await human.fill_form_field(textarea, _COVER_LETTER)
                else:
                    await textarea.fill(_COVER_LETTER)
                await asyncio.sleep(0.5)

            return await click_next_or_submit(page, human)

        except Exception as e:
            from loguru import logger
            logger.warning(f"Cover letter step error: {e}")
            return False
