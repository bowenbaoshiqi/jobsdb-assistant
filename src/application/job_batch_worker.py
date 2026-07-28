"""Foreground-lifecycle worker for background public discovery."""

from __future__ import annotations

import asyncio

from src.application.job_batch_discovery import JobBatchDiscoveryService


class JobBatchWorker:
    def __init__(
        self,
        *,
        service: JobBatchDiscoveryService,
        idle_poll_seconds: float = 1.0,
    ) -> None:
        if idle_poll_seconds <= 0:
            raise ValueError("idle poll seconds must be positive")
        self.service = service
        self.idle_poll_seconds = idle_poll_seconds
        self.task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self.task is not None and not self.task.done():
            return
        self._stop.clear()
        self.task = asyncio.create_task(self._run())

    async def close(self) -> None:
        self._stop.set()
        if self.task is not None:
            await self.task
            self.task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            if await self.service.run_next():
                continue
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.idle_poll_seconds,
                )
            except TimeoutError:
                continue
