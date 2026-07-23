"""
首页职位抓取 — 针对 JobsDB HK 真实页面结构

HTML 结构：
  <div aria-label="职位名称">
    <a href="/job/ID?..." data-automation="recommendedJobLink_ID">
      ... (职位详情，但这些在子元素里)

抓取策略：
  1. 找到所有 data-automation="recommendedJobLink_*" 的链接
  2. 向父元素查找带 aria-label 的 div → 获取职位标题
  3. 从 href 提取职位 ID
  4. 组装完整 URL
"""

import asyncio
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.simulation.behavior import HumanSimulator
from src.storage.models import JobListing

EXTRACTION_SCRIPT = """
            () => {
                const jobs = [];
                const seen = new Set();

                // 策略1：推荐职位链接
                const sel1 = 'a[data-automation^="recommendedJobLink_"]';
                const links = document.querySelectorAll(sel1);
                links.forEach(link => {
                    const href = link.getAttribute('href') || '';
                    const idMatch = href.match(/\\/job\\/(\\d+)/);
                    const id = idMatch ? idMatch[1] : '';
                    if (!id || seen.has(id)) return;
                    seen.add(id);

                    let parent = link.parentElement;
                    let title = '';
                    let company = '';
                    let location = '';

                    for (let i = 0; i < 8; i++) {
                        if (!parent) break;
                        if (!title && parent.getAttribute('aria-label')) {
                            title = parent.getAttribute('aria-label');
                        }
                        // 尝试从父元素文本中提取公司/地点
                        const text = parent.textContent || '';
                        if (!company && text.includes(' at ')) {
                            const parts = text.split(' at ');
                            if (parts.length > 1) {
                                company = parts[1].split(/[\\n·•]/)[0].trim();
                            }
                        }
                        parent = parent.parentElement;
                    }

                    if (!title) {
                        const titleEl = link.querySelector('span, div, h3, h2');
                        if (titleEl) title = titleEl.textContent.trim();
                    }
                    if (!title) {
                        title = (link.textContent || '').trim().substring(0, 100);
                    }

                    const base = 'https://hk.jobsdb.com';
                    const path = href.split('?')[0];
                    const url = href.startsWith('http') ? href : base + path;

                    jobs.push({
                        id: id,
                        title: title || 'Unknown Job',
                        company: company || 'Unknown Company',
                        location: location || null,
                        url: url,
                    });
                });

                // 策略2：如果策略1没找到，尝试通用职位卡片
                if (jobs.length === 0) {
                    const sel2 = (
                        'article, [data-automation*="job-card"], '
                        + '[data-automation*="job-list"]'
                    );
                    const cards = document.querySelectorAll(sel2);
                    cards.forEach(card => {
                        const link = card.querySelector('a[href*="/job/"]');
                        if (!link) return;
                        const href = link.getAttribute('href') || '';
                        const idMatch = href.match(/\\/job\\/(\\d+)/);
                        const id = idMatch ? idMatch[1] : '';
                        if (!id || seen.has(id)) return;
                        seen.add(id);

                        const label = card.getAttribute('aria-label');
                        const title = label || link.textContent.trim() || 'Unknown Job';
                        const base = 'https://hk.jobsdb.com';
                        const path = href.split('?')[0];
                        const url = href.startsWith('http') ? href : base + path;

                        jobs.push({
                            id: id,
                            title: title,
                            company: 'Unknown Company',
                            location: null,
                            url: url,
                        });
                    });
                }

                return jobs;
            }
        """


class HomepageScraper:
    """首页职位抓取器"""

    def __init__(self, page: PageController, human: Optional[HumanSimulator] = None):
        self.page = page
        self.human = human

    async def get_recommended_jobs(self, max_jobs: int = 20) -> list[JobListing]:
        """
        抓取首页职位列表
        """
        logger.info("Scraping jobs from homepage...")
        jobs = []

        # 等页面动态内容加载
        await asyncio.sleep(2)

        # 快速滚动触发懒加载（不模拟完整人类浏览，先保证抓到数据）
        for _ in range(2):
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        # 使用 JavaScript 直接提取页面上的职位数据
        job_data = await self.page.evaluate(EXTRACTION_SCRIPT)

        logger.info(f"JS extraction returned {len(job_data)} raw jobs")
        if len(job_data) == 0:
            # 保存调试信息
            try:
                await self.page.screenshot(path="./data/debug_no_jobs.png", full_page=True)
                html = await self.page.content()
                with open("./data/debug_no_jobs.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.warning("No jobs found, saved debug_no_jobs.png/html")
            except Exception as e:
                logger.warning(f"Failed to save debug files: {e}")

        # 去重（按 ID）
        seen_ids = set()
        for data in job_data[:max_jobs]:
            if data['id'] not in seen_ids:
                seen_ids.add(data['id'])
                jobs.append(JobListing(
                    id=data['id'],
                    title=data['title'],
                    company=data['company'],
                    location=data['location'],
                    url=data['url'],
                ))

        logger.info(f"Found {len(jobs)} unique jobs")
        return jobs

    async def _auto_scroll_loading(self) -> None:
        """自动滚动加载更多职位"""
        for _ in range(3):
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)
