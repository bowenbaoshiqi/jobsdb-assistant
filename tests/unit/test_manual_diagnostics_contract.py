from pathlib import Path

EXPECTED = {
    "probe_apply_buttons.py",
    "probe_apply_wizard.py",
    "probe_cover_letter.py",
    "probe_profile_stuck.py",
    "probe_cover_click.py",
}


def test_live_diagnostics_are_discoverable_but_not_collected() -> None:
    root = Path("tests/manual/jobsdb_live")
    scripts = {path.name for path in root.glob("*.py")}

    assert scripts == EXPECTED
    assert not any(name.startswith("test_") for name in scripts)
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "真实登录状态" in readme
    assert "不会点击最终 Submit" in readme
    assert "常规 `pytest` 或 CI" in readme
    assert "data/" in readme
    assert "不得提交到 public 仓库" in readme


def test_live_diagnostics_resolve_root_and_keep_outputs_private() -> None:
    root = Path("tests/manual/jobsdb_live")
    combined = ""
    for name in EXPECTED:
        text = (root / name).read_text(encoding="utf-8")
        combined += text
        assert "Path(__file__).resolve().parents[3]" in text
        assert "password =" not in text.casefold()
        assert "authorization:" not in text.casefold()
        assert "cookie:" not in text.casefold()

    assert 'PROJECT_ROOT / "data"' in combined
    assert "最终 Submit" in (
        root / "probe_apply_wizard.py"
    ).read_text(encoding="utf-8")
