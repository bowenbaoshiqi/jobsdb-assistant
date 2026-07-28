"""Lazy, persistent browser runtime for approved application execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.jobsdb.material_wizard import JobsDBMaterialWizard
from src.jobsdb.resumes import RemoteResumeManager


class BrowserOrchestrator(Protocol):
    page_controller: object
    human: object

    async def _init_browser(self) -> None: ...

    async def _ensure_login(self) -> bool: ...

    async def _cleanup(self) -> None: ...


@dataclass(frozen=True)
class ApprovedRuntimeComponents:
    resume_manager: RemoteResumeManager
    wizard: JobsDBMaterialWizard


class ApprovedApplicationRuntime:
    """Own one browser from first queued task until Dashboard shutdown."""

    def __init__(
        self,
        *,
        orchestrator: BrowserOrchestrator,
        job_url: Callable[[str], str],
    ) -> None:
        self.orchestrator = orchestrator
        self.job_url = job_url
        self._components: ApprovedRuntimeComponents | None = None
        self._lock = asyncio.Lock()

    async def components(self) -> ApprovedRuntimeComponents:
        async with self._lock:
            if self._components is not None:
                return self._components
            await self.orchestrator._init_browser()
            if not await self.orchestrator._ensure_login():
                await self.orchestrator._cleanup()
                raise RuntimeError("JobsDB login failed")
            page = self.orchestrator.page_controller
            self._components = ApprovedRuntimeComponents(
                resume_manager=RemoteResumeManager(page),
                wizard=JobsDBMaterialWizard(
                    page=page,
                    human=self.orchestrator.human,
                    job_url=self.job_url,
                ),
            )
            return self._components

    async def close(self) -> None:
        async with self._lock:
            if self._components is None:
                return
            await self.orchestrator._cleanup()
            self._components = None


class LazyResumeManager:
    def __init__(self, runtime: ApprovedApplicationRuntime) -> None:
        self.runtime = runtime

    async def replace_all_with(self, pdf_path, remote_name):
        components = await self.runtime.components()
        return await components.resume_manager.replace_all_with(
            pdf_path,
            remote_name,
        )


class LazyMaterialWizard:
    def __init__(self, runtime: ApprovedApplicationRuntime) -> None:
        self.runtime = runtime

    async def prepare(self, context):
        components = await self.runtime.components()
        return await components.wizard.prepare(context)

    async def submit(self, context):
        components = await self.runtime.components()
        return await components.wizard.submit(context)
