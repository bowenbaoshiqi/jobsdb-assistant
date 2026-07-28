from pathlib import Path

import pytest

from src.jobsdb.resumes import (
    RemoteResumeManager,
    ResumeListNotEmptyError,
    ResumeUploadMismatchError,
)
from src.jobsdb.selectors import (
    PROFILE_ADD_RESUME,
    PROFILE_FIRST_RESUME_OPTIONS,
    PROFILE_RESUME_DELETE,
)


class ResumePage:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.url = ""
        self.uploaded_path: Path | None = None
        self.refuse_delete = False
        self.management_open = False

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        self.url = url

    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 30.0,
    ) -> None:
        return None

    async def evaluate(self, expression: str):
        if not self.management_open:
            raise AssertionError("resume management must be opened first")
        if "JBA_LIST_RESUMES" in expression:
            return list(self.names)
        raise AssertionError(expression)

    async def is_visible(self, selector: str) -> bool:
        return False

    async def click(self, selector: str, timeout: float = 30.0) -> None:
        if selector == PROFILE_ADD_RESUME:
            self.management_open = True
        elif selector == PROFILE_FIRST_RESUME_OPTIONS:
            if self.refuse_delete or not self.names:
                raise RuntimeError("no resume options")
        elif selector == PROFILE_RESUME_DELETE and self.names:
            self.names.pop(0)

    async def set_input_files(self, selector: str, path: str) -> None:
        self.uploaded_path = Path(path)
        self.names.append(self.uploaded_path.name)

    async def wait_for_timeout(self, ms: int) -> None:
        return None


def _pdf(tmp_path: Path) -> Path:
    path = tmp_path / "cv.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"x" * 40 + b"\n%%EOF\n")
    return path


async def test_replace_deletes_every_resume_then_uploads_exact_file(
    tmp_path: Path,
) -> None:
    page = ResumePage(["default.pdf", "old.pdf"])
    manager = RemoteResumeManager(page)

    receipt = await manager.replace_all_with(
        _pdf(tmp_path),
        "JBA_42_v1_abcd1234.pdf",
    )

    assert page.names == ["JBA_42_v1_abcd1234.pdf"]
    assert receipt.filename == "JBA_42_v1_abcd1234.pdf"
    assert page.management_open is True
    assert page.uploaded_path is not None
    assert not page.uploaded_path.exists()


async def test_replace_stops_when_delete_cannot_be_confirmed(
    tmp_path: Path,
) -> None:
    page = ResumePage(["old.pdf"])
    page.refuse_delete = True

    with pytest.raises(ResumeListNotEmptyError):
        await RemoteResumeManager(page).replace_all_with(
            _pdf(tmp_path),
            "JBA_42_v1_abcd1234.pdf",
        )

    assert page.uploaded_path is None


async def test_replace_rejects_unsafe_remote_filename(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="remote resume filename"):
        await RemoteResumeManager(ResumePage([])).replace_all_with(
            _pdf(tmp_path),
            "../../wrong.pdf",
        )


async def test_replace_rejects_non_pdf(tmp_path: Path) -> None:
    text = tmp_path / "cv.txt"
    text.write_text("resume", encoding="utf-8")

    with pytest.raises(ValueError, match="PDF"):
        await RemoteResumeManager(ResumePage([])).replace_all_with(
            text,
            "JBA_42_v1_abcd1234.pdf",
        )


async def test_replace_requires_exact_sole_remote_name(
    tmp_path: Path,
) -> None:
    class WrongNamePage(ResumePage):
        async def set_input_files(self, selector: str, path: str) -> None:
            self.uploaded_path = Path(path)
            self.names.append("server-renamed.pdf")

    with pytest.raises(ResumeUploadMismatchError):
        await RemoteResumeManager(WrongNamePage([])).replace_all_with(
            _pdf(tmp_path),
            "JBA_42_v1_abcd1234.pdf",
        )
