import asyncio

from src.application.foreground_worker import ForegroundWorker


class MaterialRunner:
    def __init__(self, results: list[bool] | None = None) -> None:
        self.results = list(results or [])
        self.calls = 0

    async def run_next(self) -> bool:
        self.calls += 1
        return self.results.pop(0) if self.results else False


class ApplicationRunner:
    def __init__(self, results: list[bool] | None = None) -> None:
        self.results = list(results or [])
        self.calls = 0
        self.active = 0
        self.max_concurrency = 0

    async def run_next(self) -> bool:
        self.calls += 1
        self.active += 1
        self.max_concurrency = max(self.max_concurrency, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        return self.results.pop(0) if self.results else False


async def test_worker_drains_material_before_application_tasks() -> None:
    events: list[str] = []

    class OrderedMaterial(MaterialRunner):
        async def run_next(self) -> bool:
            result = await super().run_next()
            events.append("material")
            return result

    class OrderedApplication(ApplicationRunner):
        async def run_next(self) -> bool:
            result = await super().run_next()
            events.append("application")
            return result

    worker = ForegroundWorker(
        material_runner=OrderedMaterial([True, False]),
        application_runner=OrderedApplication([True, False]),
    )

    processed = await worker.run_until_idle()

    assert processed == 2
    assert events == [
        "material",
        "material",
        "application",
        "material",
        "application",
    ]


async def test_worker_never_runs_two_application_tasks_concurrently() -> None:
    application = ApplicationRunner([True, True, False])
    worker = ForegroundWorker(
        material_runner=MaterialRunner(),
        application_runner=application,
    )

    assert await worker.run_until_idle() == 2
    assert application.max_concurrency == 1


async def test_run_forever_stops_via_event_without_long_sleep() -> None:
    stop = asyncio.Event()
    worker = ForegroundWorker(
        material_runner=MaterialRunner(),
        application_runner=ApplicationRunner(),
        idle_poll_seconds=0.01,
    )

    task = asyncio.create_task(worker.run_forever(stop))
    await asyncio.sleep(0.02)
    stop.set()

    await asyncio.wait_for(task, timeout=0.2)


async def test_worker_rejects_invalid_poll_interval() -> None:
    try:
        ForegroundWorker(
            material_runner=MaterialRunner(),
            application_runner=ApplicationRunner(),
            idle_poll_seconds=0,
        )
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected positive poll interval validation")
