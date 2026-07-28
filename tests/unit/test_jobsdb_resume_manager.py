from pathlib import Path

import pytest

from src.jobsdb.resumes import (
    RemoteResumeManager,
    ResumeListNotEmptyError,
    ResumeUploadMismatchError,
)
from src.jobsdb.selectors import (
    PROFILE_ADD_RESUME,
    PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED,
)


class ResumePage:
    def __init__(
        self,
        names: list[str],
        *,
        default_names: set[str] | None = None,
    ) -> None:
        self.names = names
        self.default_names = (
            {names[0]} if default_names is None and names else default_names or set()
        )
        self.url = ""
        self.uploaded_path: Path | None = None
        self.refuse_delete = False
        self.management_open = False
        self.pending_delete: str | None = None
        self.clicked_selectors: list[str] = []
        self.default_checkbox_checked = True

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
            return [
                {
                    "filename": name,
                    "item_automation": f"resume-item-{index}",
                    "is_default": name in self.default_names,
                }
                for index, name in enumerate(self.names)
            ]
        raise AssertionError(expression)

    async def is_visible(self, selector: str) -> bool:
        return (
            selector == PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED
            and self.default_checkbox_checked
        )

    async def click(self, selector: str, timeout: float = 30.0) -> None:
        self.clicked_selectors.append(selector)
        if selector == PROFILE_ADD_RESUME:
            self.management_open = True
        elif selector == PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED:
            self.default_checkbox_checked = False
        elif "resume-item-" in selector and "Options for" in selector:
            if self.refuse_delete or not self.names:
                raise RuntimeError("no resume options")
            index = int(selector.split('resume-item-')[1].split('"')[0])
            self.pending_delete = self.names[index]
        elif "delete-resume-button-" in selector and self.pending_delete:
            self.names.remove(self.pending_delete)
            self.pending_delete = None

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

    assert page.names == ["default.pdf", "JBA_42_v1_abcd1234.pdf"]
    assert page.default_names == {"default.pdf"}
    assert receipt.filename == "JBA_42_v1_abcd1234.pdf"
    assert page.management_open is True
    assert page.uploaded_path is not None
    assert not page.uploaded_path.exists()
    assert page.default_checkbox_checked is False


async def test_replace_waits_until_async_upload_appears(
    tmp_path: Path,
) -> None:
    class AsyncUploadPage(ResumePage):
        def __init__(self) -> None:
            super().__init__(["default.pdf"])
            self.pending_upload_name: str | None = None
            self.upload_polls = 0

        async def set_input_files(self, selector: str, path: str) -> None:
            self.uploaded_path = Path(path)
            self.pending_upload_name = self.uploaded_path.name

        async def evaluate(self, expression: str):
            if self.pending_upload_name is not None:
                self.upload_polls += 1
                if self.upload_polls >= 3:
                    self.names.append(self.pending_upload_name)
                    self.pending_upload_name = None
            return await super().evaluate(expression)

    page = AsyncUploadPage()

    receipt = await RemoteResumeManager(page).replace_all_with(
        _pdf(tmp_path),
        "JBA_42_v1_abcd1234.pdf",
    )

    assert receipt.filename == "JBA_42_v1_abcd1234.pdf"
    assert page.upload_polls >= 3
    assert page.names == ["default.pdf", "JBA_42_v1_abcd1234.pdf"]


async def test_replace_stops_when_delete_cannot_be_confirmed(
    tmp_path: Path,
) -> None:
    page = ResumePage(
        ["default.pdf", "old.pdf"],
        default_names={"default.pdf"},
    )
    page.refuse_delete = True

    with pytest.raises(ResumeListNotEmptyError):
        await RemoteResumeManager(page).replace_all_with(
            _pdf(tmp_path),
            "JBA_42_v1_abcd1234.pdf",
        )

    assert page.uploaded_path is None


@pytest.mark.parametrize(
    "default_names",
    [set(), {"default.pdf", "old.pdf"}],
)
async def test_replace_requires_exactly_one_default_before_mutation(
    tmp_path: Path,
    default_names: set[str],
) -> None:
    page = ResumePage(
        ["default.pdf", "old.pdf"],
        default_names=default_names,
    )

    with pytest.raises(ResumeListNotEmptyError, match="default"):
        await RemoteResumeManager(page).replace_all_with(
            _pdf(tmp_path),
            "JBA_42_v1_abcd1234.pdf",
        )

    assert page.names == ["default.pdf", "old.pdf"]
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
        await RemoteResumeManager(
            WrongNamePage(["default.pdf"])
        ).replace_all_with(
            _pdf(tmp_path),
            "JBA_42_v1_abcd1234.pdf",
        )
