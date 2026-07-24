from types import SimpleNamespace
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from src.accounts.registry import Account
from src.main import app

runner = CliRunner()


def test_discover_requires_keyword() -> None:
    result = runner.invoke(app, ["discover"])

    assert result.exit_code == 2


def test_discover_rejects_whitespace_keyword() -> None:
    result = runner.invoke(app, ["discover", "--keyword", "   "])

    assert result.exit_code != 0
    assert "keyword must not be empty" in result.output


def test_discover_prints_safe_summary(monkeypatch) -> None:
    discover = AsyncMock(return_value={
        "keyword": "Product Manager",
        "found": 2,
        "captured": 2,
        "new": 1,
        "unchanged": 0,
        "changed": 1,
        "apply_types": {
            "quick_apply": 1,
            "apply": 1,
            "unknown": 0,
        },
        "failures": [],
        "jd_text": "must not render",
    })
    monkeypatch.setattr(
        "src.main.AccountRegistry.resolve_active",
        lambda *_args, **_kwargs: Account(
            alias="synthetic",
            email="person@example.invalid",
            password="",
        ),
    )
    monkeypatch.setattr(
        "src.main.Orchestrator",
        lambda *_args, **_kwargs: SimpleNamespace(discover=discover),
    )

    result = runner.invoke(
        app,
        ["discover", "--keyword", "Product Manager"],
    )

    assert result.exit_code == 0
    assert "Product Manager" in result.output
    assert "Quick Apply" in result.output
    assert "must not render" not in result.output
    discover.assert_awaited_once_with("Product Manager", limit=50)


def test_discover_never_resolves_credentials(monkeypatch) -> None:
    def fail_if_credentials_are_resolved(*_args, **_kwargs):
        raise AssertionError(
            "public discovery must not resolve credentials"
        )

    discover = AsyncMock(return_value={
        "keyword": "AI Architect",
        "found": 0,
        "captured": 0,
        "new": 0,
        "unchanged": 0,
        "changed": 0,
        "apply_types": {
            "quick_apply": 0,
            "apply": 0,
            "unknown": 0,
        },
        "failures": [],
    })
    monkeypatch.setattr(
        "src.main.AccountRegistry.resolve_active",
        fail_if_credentials_are_resolved,
    )
    monkeypatch.setattr(
        "src.main.Orchestrator",
        lambda *_args, **_kwargs: SimpleNamespace(discover=discover),
    )

    result = runner.invoke(
        app,
        ["discover", "--keyword", "AI Architect"],
    )

    assert result.exit_code == 0
    discover.assert_awaited_once_with("AI Architect", limit=50)
