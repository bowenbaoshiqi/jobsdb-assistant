from pathlib import Path
from types import SimpleNamespace

from src.adapters.career_ops_profile import CareerOpsProfileAdapter
from src.application.runtime import build_workflow


def test_runtime_wires_profile_projector_to_evaluation_service(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "src.application.runtime.get_config",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(
                database_path=str(tmp_path / "runtime.db")
            )
        ),
    )

    workflow = build_workflow(Path.cwd())

    assert isinstance(
        workflow.evaluations.profile_projector,
        CareerOpsProfileAdapter,
    )
