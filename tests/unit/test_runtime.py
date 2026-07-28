from pathlib import Path
from types import SimpleNamespace

from src.adapters.career_ops_profile import CareerOpsProfileAdapter
from src.application.runtime import (
    build_material_generation_service,
    build_workflow,
)


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


def test_material_runtime_uses_private_fixed_template(
    monkeypatch,
    tmp_path: Path,
) -> None:
    template = tmp_path / "fixed-v5.pdf"
    monkeypatch.setenv("JOBSDB_RESUME_TEMPLATE_PATH", str(template))
    monkeypatch.setattr(
        "src.application.runtime.get_config",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(
                database_path=str(tmp_path / "runtime.db")
            )
        ),
    )

    service = build_material_generation_service(Path.cwd())

    assert service.adapter.resume_template_path == template.resolve()
