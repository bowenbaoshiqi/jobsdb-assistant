"""
探测 quick-apply 多步向导的完整链路(不点最终 Submit,避免真实提交)。

链路: job页 → Quick apply → /apply(Choose documents, 选 Don't include cover letter)
→ Continue → /apply/profile(Update Jobsdb Profile) → Continue → Review(只 dump,不提交)

用法: uv run python tests/manual/jobsdb_live/probe_apply_wizard.py [job_id]
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import AppConfig, BrowserConfig  # noqa: E402
from src.browser.engine import BrowserEngine  # noqa: E402
from src.jobsdb.selectors import JOB_DETAIL_APPLY_LINK  # noqa: E402
from src.jobsdb.apply.steps.cover_letter_js import _CLICK_NO_COVER_LETTER_JS  # noqa: E402

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "93420064"

DUMP_JS = """
() => {
    const out = { headings: [], buttons: [], inputs: [], bodySnippet: '' };
    document.querySelectorAll('h1, h2, h3, [role="heading"]').forEach(el => {
        const t = (el.textContent || '').trim();
        if (t && t.length < 100) out.headings.push(t);
    });
    document.querySelectorAll('button, a[role="button"], input[type="submit"]').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        out.buttons.push({
            text: (el.textContent || '').trim().substring(0, 50),
            type: el.type || '', disabled: el.disabled,
            da: el.getAttribute('data-automation') || '',
        });
    });
    document.querySelectorAll('input:not([type="hidden"]), select, textarea').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        out.inputs.push({
            tag: el.tagName.toLowerCase(), type: el.type || '',
            name: el.name || '', value: (el.value || '').substring(0, 40),
            da: el.getAttribute('data-automation') || '',
            required: el.required,
        });
    });
    out.bodySnippet = (document.body.textContent || '').replace(/\\s+/g, ' ').substring(0, 300);
    return out;
}
"""


async def dump(page, stage):
    print(f"\n{'='*60}\n=== STAGE: {stage} | URL: {page.url}\n{'='*60}")
    d = await page.evaluate(DUMP_JS)
    print(f"headings: {d['headings']}")
    print("buttons:")
    for b in d["buttons"]:
        print(f"  - text='{b['text']}' type={b['type']} disabled={b['disabled']} da='{b['da']}'")
    print("inputs:")
    for i in d["inputs"]:
        print(f"  - {i['tag']} type={i['type']} name='{i['name']}' value='{i['value']}' "
              f"da='{i['da']}' required={i['required']}")
    print(f"body: {d['bodySnippet'][:200]}")


async def main():
    config = AppConfig(browser=BrowserConfig(
        headless=False,
        user_data_dir=str(PROJECT_ROOT / "data" / "browser_profile"),
        window_width=1280, window_height=900,
    ))
    engine = BrowserEngine(config.browser)
    page = await engine.start()

    try:
        await page.goto(f"https://hk.jobsdb.com/job/{JOB_ID}", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        link = await page.query_selector(JOB_DETAIL_APPLY_LINK)
        print(f"apply 按钮文案: '{(await link.text_content() or '').strip()}'")
        await link.click()
        await asyncio.sleep(6)

        await dump(page, "1-choose-documents")

        sel = await page.evaluate(_CLICK_NO_COVER_LETTER_JS)
        print(f"\n选 Don't include cover letter: {sel}")
        await asyncio.sleep(1)

        # Continue → profile
        await page.locator('button:has-text("Continue")').click(timeout=5000)
        print("已点 Continue (1)")
        await asyncio.sleep(4)
        await dump(page, "2-profile")

        # Continue → review
        try:
            await page.locator('button:has-text("Continue")').click(timeout=5000)
            print("已点 Continue (2)")
            await asyncio.sleep(4)
            await dump(page, "3-review")
        except Exception as e:
            print(f"第二个 Continue 不存在或不可点: {e}")

        await page.screenshot(path=str(PROJECT_ROOT / "data" / "probe_wizard.png"), full_page=True)
        print("\n截图: data/probe_wizard.png (未点 Submit,未真实提交)")

    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
