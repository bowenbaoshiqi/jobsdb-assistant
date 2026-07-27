"""
探测 cover letter 步骤的真实 DOM。

流程:打开一个 quick-apply 职位 → 点 Quick apply → 等表单 → dump 当前页所有
交互元素(按钮/radio/label/textarea),重点找 "Don't include a cover letter"。

用法: uv run python tests/manual/jobsdb_live/probe_cover_letter.py [job_id]
默认 job_id = 93420064 (Digital Transformation, 已验证有 Quick apply)
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import BrowserConfig, AppConfig  # noqa: E402
from src.browser.engine import BrowserEngine  # noqa: E402
from src.jobsdb.selectors import JOB_DETAIL_APPLY_LINK  # noqa: E402

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "93420064"

DUMP_JS = """
() => {
    const out = [];
    const sel = 'button, a, [role="button"], input, label, textarea, select, [role="radio"], [role="checkbox"]';
    document.querySelectorAll(sel).forEach(el => {
        const text = (el.textContent || '').trim();
        const aria = (el.getAttribute('aria-label') || '').trim();
        const combined = (text + ' ' + aria).toLowerCase();
        if (combined.length === 0 || combined.length > 300) return;
        // 命中关键词才记录(cover/letter/don't/include/skip/continue/submit/next/resume/question/review)
        const kw = ['cover', 'letter', "don't", 'dont', 'include', 'skip', 'continue',
                    'submit', 'next', 'resume', 'question', 'review', 'apply', 'radio',
                    'none', 'optional', 'required'];
        const hit = kw.some(k => combined.includes(k));
        if (!hit) return;
        const rect = el.getBoundingClientRect();
        out.push({
            tag: el.tagName.toLowerCase(),
            type: el.getAttribute('type') || '',
            name: el.getAttribute('name') || '',
            value: el.getAttribute('value') || '',
            checked: el.checked === true,
            text: text.substring(0, 80),
            aria: aria.substring(0, 60),
            da: el.getAttribute('data-automation') || '',
            forAttr: el.getAttribute('for') || '',
            cls: (el.className || '').toString().substring(0, 70),
            visible: rect.width > 0 && rect.height > 0,
            x: Math.round(rect.x), y: Math.round(rect.y),
        });
    });
    return out;
}
"""


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

        # 找 Quick apply 按钮并点击
        link = await page.query_selector(JOB_DETAIL_APPLY_LINK)
        if not link:
            print("❌ 没找到 job-detail-apply 按钮")
            return
        text = (await link.text_content() or "").strip()
        print(f"apply 按钮文案: '{text}'")
        await link.click()
        print("✅ 已点击,等待表单加载...")
        await asyncio.sleep(6)

        print(f"\n=== 点击后 URL: {page.url} ===")

        # dump 表单元素
        elements = await page.evaluate(DUMP_JS)
        print(f"\n找到 {len(elements)} 个相关交互元素:")
        for e in elements:
            print(f"  - tag={e['tag']} type={e['type']} checked={e['checked']} "
                  f"da='{e['da']}' name='{e['name']}' value='{e['value']}' "
                  f"for='{e['forAttr']}' visible={e['visible']}")
            print(f"      text='{e['text']}'  aria='{e['aria']}'  cls='{e['cls']}'")

        # 截图留存
        await page.screenshot(path=str(PROJECT_ROOT / "data" / "probe_cover_letter.png"),
                              full_page=True)
        # 存 HTML
        html = await page.content()
        with open(PROJECT_ROOT / "data" / "probe_cover_letter.html", "w",
                  encoding="utf-8") as f:
            f.write(html)
        print("\n截图: data/probe_cover_letter.png")
        print("HTML: data/probe_cover_letter.html")

    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
