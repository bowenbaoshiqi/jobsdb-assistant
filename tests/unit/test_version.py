from importlib.metadata import version

from typer.testing import CliRunner

from src.main import app
from src.version import __version__

runner = CliRunner()


def test_runtime_and_installed_package_versions_match() -> None:
    assert __version__ == "0.2.0"
    assert version("jobsdb-assistant") == __version__


def test_cli_version_prints_only_public_product_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "jobsdb-assistant 0.2.0"
