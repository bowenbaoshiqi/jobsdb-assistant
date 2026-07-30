from datetime import UTC, datetime

import pytest

from src.dashboard.evaluation_progress import (
    EvaluationProgressStore,
    EvaluationTaskStatus,
)

NOW = datetime(2026, 7, 27, 14, 0, tzinfo=UTC)


def test_batch_progress_is_durable_and_counted(tmp_path) -> None:
    path = tmp_path / "evaluation-progress.json"
    store = EvaluationProgressStore(path)
    store.start(["task-1", "task-2", "task-3"], now=NOW)
    store.mark("task-1", EvaluationTaskStatus.RUNNING)
    store.mark("task-1", EvaluationTaskStatus.COMPLETED)
    store.mark("task-2", EvaluationTaskStatus.FAILED)

    progress = EvaluationProgressStore(path).get()

    assert progress.status == "active"
    assert progress.total == 3
    assert progress.queued == 1
    assert progress.running == 0
    assert progress.completed == 1
    assert progress.failed == 1


def test_missing_batch_is_idle(tmp_path) -> None:
    progress = EvaluationProgressStore(
        tmp_path / "missing.json"
    ).get()

    assert progress.status == "idle"
    assert progress.total == 0


def test_unknown_task_cannot_be_marked(tmp_path) -> None:
    store = EvaluationProgressStore(tmp_path / "progress.json")
    store.start(["task-1"], now=NOW)

    with pytest.raises(KeyError, match="missing"):
        store.mark("missing", EvaluationTaskStatus.RUNNING)


def test_claim_next_marks_first_queued_task_running(tmp_path) -> None:
    store = EvaluationProgressStore(tmp_path / "progress.json")
    store.start(["task-1", "task-2"], now=NOW)

    assert store.claim_next() == "task-1"
    progress = store.get()
    assert progress.queued == 1
    assert progress.running == 1


def test_claim_next_returns_none_when_queue_is_drained(tmp_path) -> None:
    store = EvaluationProgressStore(tmp_path / "progress.json")
    store.start(["task-1"], now=NOW)
    store.mark("task-1", EvaluationTaskStatus.COMPLETED)

    assert store.claim_next() is None


def test_requeue_if_running_does_not_move_terminal_task_backwards(tmp_path) -> None:
    now = datetime.now(UTC)
    store = EvaluationProgressStore(tmp_path / "progress.json")
    store.start(["task-1"], now=now)
    store.mark("task-1", EvaluationTaskStatus.COMPLETED)

    store.requeue_if_running("task-1")

    assert store.get().completed == 1
    assert store.get().queued == 0
