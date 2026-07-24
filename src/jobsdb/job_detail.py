"""
职位详情页处理
"""

import asyncio
from typing import Optional

from loguru import logger

from src.browser.ports.page_controller import PageController
from src.domain.job import ApplyType, JobDetailCapture
from src.jobsdb.exceptions import JobNotFoundError
from src.jobsdb.selectors import (
    ALREADY_APPLIED_BADGE,
    APPLY_BUTTON,
    EASY_APPLY_BUTTON,
    JOB_DESCRIPTION,
    JOB_DETAIL_APPLY_LINK,
    JOB_DETAIL_COMPANY,
    JOB_DETAIL_LOCATION,
    JOB_DETAIL_SALARY,
    JOB_DETAIL_TITLE,
    QUICK_APPLY_BUTTON,
)
from src.simulation.behavior import HumanSimulator
from src.utils.screenshot import capture_screenshot


def normalize_jd_text(text: str) -> str:
    """Normalize visible JD text without rewriting its content."""
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    normalized: list[str] = []
    for line in lines:
        if line or (normalized and normalized[-1]):
            normalized.append(line)
    return "\n".join(normalized).strip()


class JobDetailPage:
    """职位详情页处理器"""

    def __init__(self, page: PageController, job_url: Optional[str] = None,
                 human: Optional[HumanSimulator] = None):
        self.page = page
        self.job_url = job_url
        self.human = human

    async def navigate_with_simulation(self, job_url: Optional[str] = None) -> None:
        """
        模拟人类行为导航到职位详情页

        Args:
            job_url: 职位详情页 URL（如果构造时已提供则不需要）
        """
        url = job_url or self.job_url
        if not url:
            raise ValueError("Job URL not provided")

        logger.info(f"Navigating to job detail: {url[:60]}...")

        # 导航
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)  # 等页面初始加载

        # 模拟人类浏览行为
        if self.human:
            await self.human.view_job_detail()
        else:
            # 基础等待
            await asyncio.sleep(2)

        # 检查页面是否加载成功
        title = await self._get_job_title()
        if not title:
            logger.warning("Job title not found, page may have failed to load")
            await capture_screenshot(self.page, "job_detail_error")
            raise JobNotFoundError(f"Failed to load job detail page: {url}")

        logger.debug(f"Loaded job: {title}")

    async def is_already_applied(self) -> bool:
        """检查是否已经投递过该职位"""
        try:
            badge = await self.page.query_selector(ALREADY_APPLIED_BADGE)
            if badge:
                return True

            # 备选：检查按钮文本
            apply_btn = await self.page.query_selector(APPLY_BUTTON)
            if apply_btn:
                text = await apply_btn.text_content()
                if text and "applied" in text.lower():
                    return True

            return False
        except Exception:
            return False

    async def get_apply_button(self):
        """获取 Quick Apply 按钮(只投一键申请的职位)

        v1.0 策略:JobsDB 只投 Quick/Easy Apply 职位(站内一键完成);
        标准 "Apply"/"Apply now" 常跳外部站点或需手动填长表,不自动投。

        v2.0 强化:无 quick-apply 按钮 = 标准 Apply 职位,返回 None,
        由 orchestrator 判 SKIPPED(not_quick_apply),不计入连续失败。

        e2e(2026-07-22)回归:旧版用 QUICK_APPLY_BUTTON/EASY_APPLY_BUTTON 选择器,
        但当前 JobsDB DOM 里 quick/standard apply **共用同一个**申请入口:
            <a data-automation="job-detail-apply" href="/job/{id}/apply">Quick apply</a>
            <a data-automation="job-detail-apply" href="/job/{id}/apply">Apply</a>
        区别只在按钮文案("Quick apply" vs "Apply"),没有独立的 quick/easy 按钮 DOM,
        也没有 data-automation="quick-apply" 属性。所以旧选择器永远命中 0 → 全 SKIPPED。

        正确做法:用 JOB_DETAIL_APPLY_LINK 找到统一入口,再读文案——
        含 "quick apply"(或 easy apply / 中文变体)才投,否则返回 None(标准 Apply)。
        旧的独立按钮选择器保留为兜底,防御 JobsDB 其他页面的旧 DOM 变体。
        """
        # 1) 主路径:统一申请入口 job-detail-apply,按文案区分 quick/standard
        link = await self.page.query_selector(JOB_DETAIL_APPLY_LINK)
        if link:
            is_visible = await link.is_visible()
            if is_visible:
                text = (await link.text_content() or "").strip().lower()
                if self._is_quick_apply_text(text):
                    return link
                # 可见但文案不含 quick apply → 标准 Apply,跳过
                logger.info(
                    f"job-detail-apply found but text='{text[:40]}' "
                    f"is not quick-apply, skipping (standard Apply)"
                )
                return None

        # 2) 兜底:旧 DOM 变体(独立 quick/easy 按钮)——当前 JobsDB 主站已无,
        # 但保留以防部分子页面/旧版残存。命中即投(选择器本身已限定 quick/easy)。
        for selector in [QUICK_APPLY_BUTTON, EASY_APPLY_BUTTON]:
            btn = await self.page.query_selector(selector)
            if btn and await btn.is_visible():
                return btn

        return None

    @staticmethod
    def _is_quick_apply_text(text: str) -> bool:
        """判断按钮文案是否表示 quick/easy apply(中英文变体)"""
        quick_markers = [
            "quick apply", "easy apply",
            "快速申请", "快速申請", "简单申请", "簡單申請",
            "一键申请", "一鍵申請",
        ]
        return any(m in text for m in quick_markers)

    async def get_job_info(self) -> dict:
        """获取职位详细信息"""
        info = {
            "title": "",
            "company": "",
            "location": "",
            "salary": "",
            "description": "",
        }

        try:
            # 标题
            title_el = await self.page.query_selector(JOB_DETAIL_TITLE)
            if title_el:
                info["title"] = await title_el.text_content() or ""

            # 公司
            company_el = await self.page.query_selector(JOB_DETAIL_COMPANY)
            if company_el:
                info["company"] = await company_el.text_content() or ""

            # 地点
            location_el = await self.page.query_selector(JOB_DETAIL_LOCATION)
            if location_el:
                info["location"] = await location_el.text_content() or ""

            # 薪资
            salary_el = await self.page.query_selector(JOB_DETAIL_SALARY)
            if salary_el:
                info["salary"] = await salary_el.text_content() or ""

            # 描述（可选）
            desc_el = await self.page.query_selector(JOB_DESCRIPTION)
            if desc_el:
                info["description"] = await desc_el.text_content() or ""

        except Exception as e:
            logger.warning(f"Error getting job info: {e}")

        return info

    async def capture_for_discovery(
        self,
        job_id: str,
        canonical_url: str,
    ) -> JobDetailCapture:
        """Capture complete normalized fields without clicking an apply control."""
        title = normalize_jd_text(await self.page.get_text(JOB_DETAIL_TITLE) or "")
        company = normalize_jd_text(
            await self.page.get_text(JOB_DETAIL_COMPANY) or ""
        )
        location = normalize_jd_text(
            await self.page.get_text(JOB_DETAIL_LOCATION) or ""
        )
        jd_text = normalize_jd_text(
            await self.page.get_text(JOB_DESCRIPTION) or ""
        )

        if not title:
            raise JobNotFoundError("job title is missing")
        if not company:
            raise JobNotFoundError("job company is missing")
        if not jd_text:
            raise JobNotFoundError("job description is missing")

        apply_type = ApplyType.UNKNOWN
        apply_link = await self.page.query_selector(JOB_DETAIL_APPLY_LINK)
        if apply_link and await apply_link.is_visible():
            button_text = (await apply_link.text_content() or "").strip().lower()
            apply_type = (
                ApplyType.QUICK_APPLY
                if self._is_quick_apply_text(button_text)
                else ApplyType.APPLY
            )

        return JobDetailCapture(
            jobsdb_job_id=job_id,
            canonical_url=canonical_url,
            title=title,
            company=company,
            location=location or None,
            jd_text=jd_text,
            apply_type=apply_type,
        )

    async def _get_job_title(self) -> Optional[str]:
        """获取职位标题

        v2.0: `except Exception: pass` → 捕获 + debug 日志
        (三分法 B 类:降级 — 标题取不到返回 None,不阻断)。
        """
        try:
            title_el = await self.page.query_selector(JOB_DETAIL_TITLE)
            if title_el:
                return await title_el.text_content()
        except Exception as e:
            logger.debug(f"Failed to get job title: {e}")
        return None
