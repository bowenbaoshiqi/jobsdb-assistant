"""
验证 cover letter 修复是否真正有效。

打开已确认的 quick-apply 职位(93420064) → 点 Quick apply → 等 /apply 表单 →
执行 CoverLetterStep 的 JS 点 "Don't include a cover letter" → 点 Continue →
等 5s 后截图/记录 URL。
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppConfig, BrowserConfig  # noqa: E402
from src.browser.engine import BrowserEngine  # noqa: E402
from src.jobsdb.selectors import JOB_DETAIL_APPLY_LINK  # noqa: E402
from src.jobsdb.apply.steps.cover_letter_js import (  # noqa: E402
    _CLICK_NO_COVER_LETTER_JS,
    _HAS_COVER_LETTER_JS,
)

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "93420064"

CONTINUE_JS = r"""() => {
  const norm = s => (s || '').toLowerCase().replace(/[​-‍﻿⁠]/g, '').trim();
  const markers = ['continue', 'next', 'review and submit'];
  const btns = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"]'));
  for (const el of btns) {
    const t = norm(el.textContent || el.getAttribute('aria-label') || '');
    if (markers.some(k => t.includes(k))) {
      el.click();
      return { clicked: true, text: el.textContent.trim().substring(0, 60) };
    }
  }
  return { clicked: false };
}"""

RADIO_CHECK_JS = r"""() => {
  const labels = Array.from(document.querySelectorAll('label'));
  for (const el of labels) {
    const t = ((el.textContent || '') + ' ' + (el.getAttribute('aria-label') || '')).toLowerCase();
    if (t.includes("don't include a cover letter") || t.includes('dont include a cover letter')) {
      const input = document.getElementById(el.getAttribute('for') || '');
      if (input) return { found: true, checked: input.checked, for: el.getAttribute('for') };
      return { found: true, checked: null, for: el.getAttribute('for') };
    }
  }
  return { found: false };
}"""

ALL_RADIO_JS = r"""() => {
  return Array.from(document.querySelectorAll('input[type="radio"]')).map(r => {
    const label = document.querySelector('label[for="' + r.id + '"]');
    return {
      id: r.id,
      checked: r.checked,
      disabled: r.disabled,
      labelText: label ? label.textContent.trim().substring(0, 60) : ''
    };
  });
}"""

BUTTON_STATE_JS = r"""() => {
  return Array.from(document.querySelectorAll('button')).map(b => ({
    text: b.textContent.trim().substring(0, 60),
    disabled: b.disabled,
    type: b.type,
    visible: b.offsetParent !== null
  }));
}"""


async def main():
    config = AppConfig(browser=BrowserConfig(
        headless=False,
        user_data_dir=str(PROJECT_ROOT / "data" / "browser_profile"),
        window_width=1280, window_height=900,
    ))
    engine = BrowserEngine(config.browser)
    page = await engine.start()

    try:
        url = f"https://hk.jobsdb.com/job/{JOB_ID}"
        print(f"\n=== 打开职位 {JOB_ID}: {url} ===")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(4)

        link = await page.query_selector(JOB_DETAIL_APPLY_LINK)
        if not link:
            print("❌ 没找到 job-detail-apply 按钮")
            return
        text = (await link.text_content() or "").strip()
        print(f"apply 按钮文案: '{text}'")
        await link.click()
        print("✅ 已点击 Quick apply, 等待表单...")
        await asyncio.sleep(6)
        print(f"当前 URL: {page.url}")

        has = await page.evaluate(_HAS_COVER_LETTER_JS)
        print(f"HAS_COVER_LETTER_JS 返回: {has}")

        before = await page.evaluate(RADIO_CHECK_JS)
        print(f"点击前 radio 状态: {before}")
        print(f"所有 radio 状态: {await page.evaluate(ALL_RADIO_JS)}")
        print(f"所有按钮状态: {await page.evaluate(BUTTON_STATE_JS)}")

        clicked = await page.evaluate(_CLICK_NO_COVER_LETTER_JS)
        print(f"_CLICK_NO_COVER_LETTER_JS 返回: {clicked}")

        await asyncio.sleep(1)
        after = await page.evaluate(RADIO_CHECK_JS)
        print(f"点击后 radio 状态: {after}")
        print(f"所有 radio 状态: {await page.evaluate(ALL_RADIO_JS)}")

        cont = await page.evaluate(CONTINUE_JS)
        print(f"JS Continue 点击结果: {cont}")

        print("等待 3s 看是否进入下一页...")
        await asyncio.sleep(3)
        print(f"JS 点击 3s 后 URL: {page.url}")

        # 如果 JS 点击没跳转,尝试 Playwright 原生 locator.click()
        if '/apply' in page.url:
            try:
                print("尝试 Playwright locator 点 Continue...")
                await page.locator('button:has-text("Continue")').click(timeout=5000)
                await asyncio.sleep(3)
                print(f"Playwright 点击 3s 后 URL: {page.url}")
            except Exception as e:
                print(f"Playwright 点击失败: {e}")

        print("等待 5s 看最终 URL...")
        await asyncio.sleep(5)
        print(f"最终 URL: {page.url}")

        await page.screenshot(path=str(PROJECT_ROOT / "data" / "test_cover_click.png"), full_page=True)
        print("截图已保存: data/test_cover_click.png")

    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
