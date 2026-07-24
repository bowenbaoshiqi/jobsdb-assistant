"""Private atomic JSON exchange for controlled AI checkpoints."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MAX_RESULT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CheckpointRef:
    path: Path
    sha256: str


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _task_dir(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("invalid task id")
        return self.root / task_id

    def write_task(
        self,
        task_id: str,
        payload: dict[str, Any],
    ) -> CheckpointRef:
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        if task_dir.is_symlink():
            raise ValueError("task directory must not be a symlink")
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        temporary = task_dir / "task.json.tmp"
        path = task_dir / "task.json"
        temporary.write_bytes(encoded)
        temporary.replace(path)
        return CheckpointRef(path=path, sha256=sha256(encoded).hexdigest())

    def submit_result(self, task_id: str, payload: bytes) -> CheckpointRef:
        if len(payload) > _MAX_RESULT_BYTES:
            raise ValueError("result exceeds 2 MiB limit")
        task_dir = self._task_dir(task_id)
        if not (task_dir / "task.json").is_file():
            raise FileNotFoundError(task_id)
        parsed = json.loads(payload)
        if parsed.get("task_id") != task_id:
            raise ValueError("task id mismatch")
        temporary = task_dir / "result.json.tmp"
        path = task_dir / "result.json"
        temporary.write_bytes(payload)
        temporary.replace(path)
        return CheckpointRef(path=path, sha256=sha256(payload).hexdigest())

    def read_task(self, task_id: str) -> dict[str, Any]:
        path = self._task_dir(task_id) / "task.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def read_result(self, task_id: str) -> dict[str, Any]:
        path = self._task_dir(task_id) / "result.json"
        return json.loads(path.read_text(encoding="utf-8"))
