from pathlib import Path

from src.doctor import CheckStatus, DoctorPaths, run_checks


def test_doctor_reports_required_and_optional_tools_without_secrets(
    tmp_path: Path,
) -> None:
    paths = DoctorPaths(
        root=tmp_path,
        database=tmp_path / "data/jobsdb.db",
        browser_profile=tmp_path / "data/browser_profile",
    )
    available = {
        "python": "/usr/bin/python",
        "uv": "/usr/local/bin/uv",
        "node": "/usr/local/bin/node",
        "claude": "/usr/local/bin/claude",
    }

    results = run_checks(lambda name: available.get(name), paths)
    by_name = {result.name: result for result in results}

    assert by_name["python"].status is CheckStatus.PASS
    assert by_name["uv"].status is CheckStatus.PASS
    assert by_name["node-or-bun"].status is CheckStatus.PASS
    assert by_name["claude-or-codex"].status is CheckStatus.PASS
    assert by_name["latex"].status is CheckStatus.WARN
    assert all("token" not in result.detail.lower() for result in results)


def test_doctor_fails_when_required_runtime_is_missing(tmp_path: Path) -> None:
    paths = DoctorPaths(
        root=tmp_path,
        database=tmp_path / "data/jobsdb.db",
        browser_profile=tmp_path / "data/browser_profile",
    )

    results = run_checks(lambda _name: None, paths)

    assert next(
        item for item in results if item.name == "python"
    ).status is CheckStatus.FAIL
    assert next(item for item in results if item.name == "uv").status is CheckStatus.FAIL


def test_doctor_only_reports_private_path_existence(tmp_path: Path) -> None:
    profile = tmp_path / "data/browser_profile"
    profile.mkdir(parents=True)
    paths = DoctorPaths(
        root=tmp_path,
        database=tmp_path / "data/jobsdb.db",
        browser_profile=profile,
    )

    results = run_checks(lambda name: f"/bin/{name}", paths)
    profile_result = next(item for item in results if item.name == "browser-profile")

    assert profile_result.detail == "present"
    assert str(profile) not in profile_result.detail
