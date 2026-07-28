"""Serial, resumable foreground dispatch for material and application work."""

from __future__ import annotations

import asyncio
from typing import Protocol


class TaskRunner(Protocol):
    async def run_next(self) -> bool:
        """Process one runnable item and report whether work was done."""


class ForegroundWorker:
    def __init__(
        self,
        *,
        material_runner: TaskRunner,
        application_runner: TaskRunner,
        idle_poll_seconds: float = 1.0,
    ) -> None:
        if idle_poll_seconds <= 0:
            raise ValueError("idle poll interval must be positive")
        self.material_runner = material_runner
        self.application_runner = application_runner
        self.idle_poll_seconds = idle_poll_seconds

    async def run_until_idle(self) -> int:
        processed = 0
        while True:
            if await self.material_runner.run_next():
                processed += 1
                continue
            if await self.application_runner.run_next():
                processed += 1
                continue
            return processed

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.run_until_idle()
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.idle_poll_seconds,
                )
            except TimeoutError:
                continue
