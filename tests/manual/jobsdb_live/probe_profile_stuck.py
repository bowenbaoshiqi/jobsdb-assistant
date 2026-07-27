"""
诊断 profile 页 Continue 卡住的原因(e2e 2026-07-22: 93480252/93481180 卡在 /apply/profile)。

打开职位 → Quick apply → 选 Don't include cover letter → Continue →
dump profile 页完整状态(所有 select/必填项/alert/错误元素/Continue 状态) →
再点 Continue → dump 看是否报错、报什么。

用法: uv run python tests/manual/jobsdb_live/probe_profile_stuck.py [job_id]
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

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "93481180"

DUMP_JS = """
() => {
    const out = { url: location.href, selects: [], requiredEmpty: [], alerts: [],
                  errors: [], continueBtn: null, headings: [] };
    document.querySelectorAll('h1,h2,h3').forEach(el => {
        const t = (el.textContent||'').trim();
        if (t && t.length < 80) out.headings.push(t);
    });
    document.querySelectorAll('select').forEach(s => {
        const opt = s.options[s.selectedIndex];
        out.selects.push({
            name: s.name, value: s.value,
            selText: opt ? opt.textContent.trim().substring(0,40) : '',
            visible: s.offsetParent !== null, required: s.required,
            ariaInvalid: s.getAttribute('aria-invalid'),
        });
    });
    // 必填但未填的控件
    document.querySelectorAll('[required], [aria-required="true"]').forEach(el => {
        if (el.offsetParent === null) return;
        const v = (el.value || '').trim();
        if (!v) out.requiredEmpty.push({
            tag: el.tagName, type: el.type || '', name: el.name || '',
            aria: (el.getAttribute('aria-label')||'').substring(0,50),
        });
    });
    // alert / error 类元素(宽匹配)
    document.querySelectorAll('[role="alert"], [class*="error" i], [class*="Error"], [aria-live]').forEach(el => {
        const t = (el.textContent||'').trim();
        if (t && t.length < 300 && el.offsetParent !== null) out.alerts.push(t.substring(0,180));
    });
    // 含 "error"/"required"/"please" 文本的可见元素
    document.querySelectorAll('p, span, div').forEach(el => {
        const t = (el.textContent||'').trim();
        if (t.length > 10 && t.length < 250 && el.children.length === 0 && el.offsetParent !== null
            && /please|required|must|issue|error|缺少|必填|請|请/i.test(t)) {
            out.errors.push(t.substring(0,180));
        }
    });
    // Continue 按钮状态
    document.querySelectorAll('button').forEach(b => {
        const t = (b.textContent||'').trim();
        if (t.replace(/[​-‍﻿⁠]/g,'').startsWith('Continue')) {
            const r = b.getBoundingClientRect();
            out.continueBtn = { disabled: b.disabled, ariaDisabled: b.getAttribute('aria-disabled'),
                                visible: b.offsetParent !== null,
                                y: Math.round(r.y), inViewport: r.top >= 0 && r.bottom <= innerHeight };
        }
    });
    return out;
}
"""


async def dump(page, tag):
    d = await page.evaluate(DUMP_JS)
    print(f"\n{'='*60}\n=== {tag} | {d['url']}\n{'='*60}")
    print(f"headings: {d['headings']}")
    print(f"selects: {d['selects']}")
    print(f"requiredEmpty: {d['requiredEmpty']}")
    print(f"alerts: {d['alerts']}")
    print(f"errorTexts: {d['errors'][:8]}")
    print(f"continueBtn: {d['continueBtn']}")
    return d


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
        print(f"apply 按钮: '{(await link.text_content() or '').strip()}'")
        await link.click()
        await asyncio.sleep(6)
        sel = await page.evaluate(_CLICK_NO_COVER_LETTER_JS)
        print(f"选 Don't include cover letter: {sel}")
        await asyncio.sleep(1)

        await page.locator('button:has-text("Continue")').click(timeout=5000)
        print("已点 Continue → profile 页")
        await asyncio.sleep(4)
        await dump(page, "profile-before-continue")

        # 再点 Continue,看发生什么
        try:
            await page.locator('button:has-text("Continue")').click(timeout=5000)
            print("\n再次点 Continue")
        except Exception as e:
            print(f"\n第二次 Continue 点不到: {e}")
        await asyncio.sleep(3)
        await dump(page, "profile-after-continue")

        await page.screenshot(path=str(PROJECT_ROOT / "data" / "profile_stuck.png"), full_page=True)
        print("\n截图: data/profile_stuck.png")
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
