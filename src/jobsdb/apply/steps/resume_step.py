"""
resume_step — 简历选择步骤

v1.0 _handle_resume_step 的逻辑:确认默认简历选中(单选/下拉),点 Next/Submit。
"""

import asyncio
import json

from src.browser.ports.page_controller import PageController
from src.domain.material import MaterialMode
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.apply.steps.navigation import click_next_or_submit
from src.jobsdb.selectors import DEFAULT_RESUME_RADIO, RESUME_DROPDOWN, RESUME_SELECTION


def _select_resume_js(filename: str) -> str:
    encoded = json.dumps(filename)
    return f"""() => {{
      const expected = {encoded};
      const normalize = value => (value || '').trim();
      for (const option of document.querySelectorAll('option')) {{
        if (normalize(option.textContent) === expected) {{
          const select = option.closest('select');
          select.value = option.value;
          select.dispatchEvent(new Event('input', {{ bubbles: true }}));
          select.dispatchEvent(new Event('change', {{ bubbles: true }}));
          return true;
        }}
      }}
      for (const label of document.querySelectorAll('label')) {{
        if (normalize(label.textContent).includes(expected)) {{
          label.click();
          return true;
        }}
      }}
      return false;
    }}"""


class ResumeStep:
    """RESUME_SELECTION 步骤处理器"""

    def __init__(
        self,
        context: ApplicationMaterialContext | None = None,
    ) -> None:
        self.context = context

    async def detect(self, page: PageController) -> bool:
        # 由 detectors.detect_current_step 判定;此处保留接口一致性
        return bool(await page.query_selector(RESUME_SELECTION))

    async def handle(self, page: PageController, human=None) -> bool:
        """处理简历选择(v1.0 _handle_resume_step)"""
        try:
            if (
                self.context is not None
                and self.context.material_mode
                is MaterialMode.TAILORED_RESUME_AND_COVER_LETTER
            ):
                selected = await page.evaluate(
                    _select_resume_js(self.context.resume_filename)
                )
                if selected is not True:
                    return False
                return await click_next_or_submit(page, human)

            # 检查默认简历是否选中
            default_radio = await page.query_selector(DEFAULT_RESUME_RADIO)
            if default_radio:
                is_checked = await default_radio.is_checked()
                if not is_checked:
                    if human:
                        await human.mouse.click_element(default_radio)
                    else:
                        await default_radio.click()
                    await asyncio.sleep(0.5)
            else:
                # 尝试下拉
                dropdown = await page.query_selector(RESUME_DROPDOWN)
                if dropdown:
                    options = await dropdown.query_selector_all("option")
                    if len(options) > 0:
                        await dropdown.select_option(index=0)
                        await asyncio.sleep(0.5)

            # 点击下一步按钮
            return await click_next_or_submit(page, human)

        except Exception as e:
            from loguru import logger
            logger.warning(f"Resume step error: {e}")
            return False
