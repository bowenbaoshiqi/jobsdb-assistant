from pathlib import Path

import pytest

from src.integrations.manager import IntegrationManager
from src.integrations.manifest import load_manifest

LOCKED_SHA = "aa7c7073990492c9111fbdda48f6adde24a1d91b"
APPROVED_URL = "https://github.com/bowenbaoshiqi/ai-job-search.git"


class FakeGitRunner:
    def __init__(
        self,
        *,
        head: str = LOCKED_SHA,
        required_paths: tuple[str, ...] = (),
    ) -> None:
        self.head = head
        self.required_paths = required_paths
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: tuple[str, ...]) -> str:
        self.commands.append(command)
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True)
            return ""
        if "checkout" in command:
            root = Path(command[2])
            for required in self.required_paths:
                path = root / required
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.head = command[-1]
            return ""
        if "rev-parse" in command:
            return f"{self.head}\n"
        raise AssertionError(f"unexpected command: {command}")


def make_manager(
    tmp_path: Path,
    *,
    checkout_exists: bool = False,
    head: str = LOCKED_SHA,
    include_required_paths: bool = True,
) -> tuple[IntegrationManager, FakeGitRunner]:
    manifest = load_manifest(Path("integrations/manifest.json"))
    spec = manifest.integrations["candidate-profile"]
    required_paths = (
        tuple(spec.required_paths) if include_required_paths else ()
    )
    runner = FakeGitRunner(head=head, required_paths=required_paths)
    manager = IntegrationManager(
        root=tmp_path / "integrations",
        manifest=manifest,
        runner=runner,
    )
    if checkout_exists:
        checkout = manager.root / "candidate-profile"
        checkout.mkdir(parents=True)
        for required in required_paths:
            path = checkout / required
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    return manager, runner


def test_missing_install_clones_then_detaches_exact_sha(
    tmp_path: Path,
) -> None:
    manager, runner = make_manager(tmp_path)

    state = manager.install_missing("candidate-profile")

    assert state.status == "ready"
    assert runner.commands == [
        (
            "git",
            "clone",
            "--no-checkout",
            APPROVED_URL,
            str(state.path),
        ),
        (
            "git",
            "-C",
            str(state.path),
            "checkout",
            "--detach",
            LOCKED_SHA,
        ),
        ("git", "-C", str(state.path), "rev-parse", "HEAD"),
    ]


def test_ready_check_never_fetches_pulls_or_installs(tmp_path: Path) -> None:
    manager, runner = make_manager(tmp_path, checkout_exists=True)

    state = manager.check("candidate-profile")

    assert state.status == "ready"
    assert runner.commands == [
        ("git", "-C", str(state.path), "rev-parse", "HEAD")
    ]
    assert all(
        forbidden not in command
        for command in runner.commands
        for forbidden in ("pull", "fetch", "clone", "checkout")
    )


def test_mismatch_requires_explicit_repair(tmp_path: Path) -> None:
    manager, runner = make_manager(
        tmp_path,
        checkout_exists=True,
        head="b" * 40,
    )

    state = manager.check("candidate-profile")

    assert state.status == "mismatch"
    assert state.commit == "b" * 40
    assert len(runner.commands) == 1


def test_missing_required_capability_is_damaged(tmp_path: Path) -> None:
    manager, _runner = make_manager(
        tmp_path,
        checkout_exists=True,
        include_required_paths=False,
    )

    state = manager.check("candidate-profile")

    assert state.status == "damaged"


def test_install_missing_does_not_change_existing_mismatch(
    tmp_path: Path,
) -> None:
    manager, runner = make_manager(
        tmp_path,
        checkout_exists=True,
        head="b" * 40,
    )

    state = manager.install_missing("candidate-profile")

    assert state.status == "mismatch"
    assert len(runner.commands) == 1


def test_unknown_integration_id_is_rejected(tmp_path: Path) -> None:
    manager, _runner = make_manager(tmp_path)

    with pytest.raises(KeyError):
        manager.check("unapproved")
