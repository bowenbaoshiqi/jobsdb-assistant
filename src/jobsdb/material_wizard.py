"""Material-aware JobsDB Quick Apply wizard using one persistent page."""

from __future__ import annotations

from collections.abc import Callable

from src.browser.ports.page_controller import PageController
from src.jobsdb.apply.context import ApplicationMaterialContext
from src.jobsdb.apply.flow import ApplyFlow
from src.jobsdb.job_detail import JobDetailPage
from src.simulation.behavior import HumanSimulator
from src.storage.models import ApplyResult, ApplyStatus


class JobsDBMaterialWizard:
    def __init__(
        self,
        *,
        page: PageController,
        human: HumanSimulator | None,
        job_url: Callable[[str], str],
    ) -> None:
        self.page = page
        self.human = human
        self.job_url = job_url

    async def prepare(
        self,
        context: ApplicationMaterialContext,
    ) -> ApplyResult:
        detail = JobDetailPage(
            self.page,
            self.job_url(context.job_id),
            self.human,
        )
        await detail.navigate_with_simulation()
        if await detail.is_already_applied():
            return ApplyResult(
                status=ApplyStatus.SKIPPED,
                job_id=context.job_id,
                reason="already_applied",
            )
        button = await detail.get_apply_button()
        if button is None:
            return ApplyResult(
                status=ApplyStatus.SKIPPED,
                job_id=context.job_id,
                reason="not_quick_apply",
            )
        if self.human is None:
            await button.click()
        else:
            await self.human.click_apply_button(button)
        await self.page.wait_for_timeout(1000)
        return await ApplyFlow(
            self.page,
            self.human,
            material_context=context,
            submit_confirmed=False,
        ).apply(context.job_id)

    async def submit(
        self,
        context: ApplicationMaterialContext,
    ) -> ApplyResult:
        return await ApplyFlow(
            self.page,
            self.human,
            material_context=context,
            submit_confirmed=True,
        ).apply(context.job_id)
