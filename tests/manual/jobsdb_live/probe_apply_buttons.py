"""
探测真实职位详情页的 apply 按钮DOM。

用已登录的持久化 profile(headed)打开 5 个职位页,dump 所有"看起来像申请按钮"的元素:
tag / text / aria-label / data-automation / class / href / visible / boundingBox。
并对比当前 QUICK_APPLY_BUTTON / EASY_APPLY_BUTTON 选择器能否命中,以及"等更久"是否影响可见性。

用法: uv run python tests/manual/jobsdb_live/probe_apply_buttons.py
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BrowserConfig, AppConfig  # noqa: E402
from src.browser.engine import BrowserEngine  # noqa: E402
from src.jobsdb.selectors import (  # noqa: E402
    APPLY_BUTTON,
    APPLY_NOW_BUTTON,
    EASY_APPLY_BUTTON,
    JOB_DETAIL_APPLY_LINK,
    QUICK_APPLY_BUTTON,
)

JOBS = [
    ("93164966", "Associate Director"),
    ("92924389", "Senior Manager"),
    ("93420064", "Digital Transformation"),  # 用户称有 quick apply
    ("93469825", "AI Agentic Consultant"),   # 用户称有 quick apply
    ("93253153", "Senior Solution Architect"),  # 用户称有 quick apply
]

DUMP_JS = """
() => {
    const out = [];
    // 宽泛抓取: 所有 button/a/[role=button],文本或aria含 apply/申请/quick/easy
    const sel = 'button, a, [role="button"], input[type="submit"]';
    document.querySelectorAll(sel).forEach(el => {
        const text = (el.textContent || '').trim();
        const aria = (el.getAttribute('aria-label') || '').trim();
        const combined = (text + ' ' + aria).toLowerCase();
        if (combined.length === 0 || combined.length > 200) return;
        const hit = ['apply', 'quick', 'easy', '申请', '申請', '立即', '一键', '快速', '简单', '簡單']
            .some(k => combined.includes(k));
        if (!hit) return;
        const rect = el.getBoundingClientRect();
        const da = el.getAttribute('data-automation') || '';
        out.push({
            tag: el.tagName.toLowerCase(),
            text: text.substring(0, 60),
            aria: aria.substring(0, 60),
            dataAutomation: da,
            cls: (el.className || '').toString().substring(0, 80),
            href: el.getAttribute('href') || '',
            type: el.getAttribute('type') || '',
            visible: rect.width > 0 && rect.height > 0,
            x: Math.round(rect.x), y: Math.round(rect.y),
            w: Math.round(rect.width), h: Math.round(rect.height),
        });
    });
    return out;
}
"""


async def probe_one(engine, page, job_id, title):
    url = f"https://hk.jobsdb.com/job/{job_id}"
    print(f"\n{'='*70}")
    print(f"职位 {job_id}: {title}")
    print(f"URL: {url}")
    print('='*70)

    await page.goto(url, wait_until="domcontentloaded")
    # 模拟真实流程的 2s 等待
    await asyncio.sleep(2)
    buttons_2s = await page.evaluate(DUMP_JS)
    print(f"\n[domcontentloaded + 2s] 找到 {len(buttons_2s)} 个候选按钮:")
    for b in buttons_2s:
        print(f"  - tag={b['tag']} visible={b['visible']} da='{b['dataAutomation']}' "
              f"text='{b['text']}' aria='{b['aria']}' href='{b['href'][:40]}' "
              f"cls='{b['cls'][:40]}' pos=({b['x']},{b['y']}) {b['w']}x{b['h']}")

    # 用当前选择器逐一测试(@2s)
    print("\n[选择器命中 @2s]:")
    for name, sel in [
        ("QUICK_APPLY_BUTTON", QUICK_APPLY_BUTTON),
        ("EASY_APPLY_BUTTON", EASY_APPLY_BUTTON),
        ("APPLY_BUTTON", APPLY_BUTTON),
        ("APPLY_NOW_BUTTON", APPLY_NOW_BUTTON),
        ("JOB_DETAIL_APPLY_LINK", JOB_DETAIL_APPLY_LINK),
    ]:
        try:
            count = await page.locator(sel).count()
            vis = 0
            if count:
                for i in range(min(count, 5)):
                    if await page.locator(sel).nth(i).is_visible():
                        vis += 1
            print(f"  {name}: count={count} visible={vis}  sel={sel[:70]}")
        except Exception as e:
            print(f"  {name}: ERROR {e}")

    # 再等 6s(总共 8s),看按钮是否异步出现
    await asyncio.sleep(6)
    buttons_8s = await page.evaluate(DUMP_JS)
    print(f"\n[+6s 共 8s] 候选按钮数: {len(buttons_8s)} (2s时 {len(buttons_2s)})")
    new_btns = [b for b in buttons_8s if b not in buttons_2s]
    for b in new_btns:
        print(f"  [新增] tag={b['tag']} visible={b['visible']} da='{b['dataAutomation']}' "
              f"text='{b['text']}'")

    # 选择器再测一次 @8s
    print("\n[选择器命中 @8s]:")
    for name, sel in [
        ("QUICK_APPLY_BUTTON", QUICK_APPLY_BUTTON),
        ("EASY_APPLY_BUTTON", EASY_APPLY_BUTTON),
        ("APPLY_BUTTON", APPLY_BUTTON),
    ]:
        try:
            count = await page.locator(sel).count()
            vis = 0
            if count:
                for i in range(min(count, 5)):
                    if await page.locator(sel).nth(i).is_visible():
                        vis += 1
            print(f"  {name}: count={count} visible={vis}")
        except Exception as e:
            print(f"  {name}: ERROR {e}")


async def main():
    config = AppConfig(browser=BrowserConfig(
        headless=False,
        user_data_dir=str(PROJECT_ROOT / "data" / "browser_profile"),
        window_width=1280, window_height=900,
    ))
    engine = BrowserEngine(config.browser)
    page = await engine.start()
    try:
        for job_id, title in JOBS:
            await probe_one(engine, page, job_id, title)
            await asyncio.sleep(1)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
