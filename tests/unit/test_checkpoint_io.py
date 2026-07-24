import json
from hashlib import sha256
from pathlib import Path

import pytest

from src.adapters.checkpoint_io import CheckpointStore


def test_checkpoint_store_writes_atomic_private_task(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "workspace" / "ai-tasks")

    ref = store.write_task("profile-run-1", {"task_id": "profile-run-1"})

    assert ref.path.is_relative_to(store.root)
    assert ref.sha256 == sha256(ref.path.read_bytes()).hexdigest()
    assert json.loads(ref.path.read_text())["task_id"] == "profile-run-1"


def test_checkpoint_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "workspace" / "ai-tasks")

    with pytest.raises(ValueError, match="invalid task id"):
        store.write_task("../private", {"task_id": "../private"})


def test_result_must_match_task_and_size_limit(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "workspace" / "ai-tasks")
    store.write_task("profile-run-1", {"task_id": "profile-run-1"})

    with pytest.raises(ValueError, match="task id mismatch"):
        store.submit_result(
            "profile-run-1",
            json.dumps({"task_id": "other"}).encode(),
        )
    with pytest.raises(ValueError, match="result exceeds"):
        store.submit_result("profile-run-1", b"x" * (2 * 1024 * 1024 + 1))
