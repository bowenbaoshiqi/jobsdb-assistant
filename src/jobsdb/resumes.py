"""Replace all remote JobsDB resumes with one approved tailored PDF."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.browser.ports.page_controller import PageController
from src.jobsdb.selectors import (
    PROFILE_ADD_RESUME,
    PROFILE_RESUME_DELETE_CONFIRM,
    PROFILE_RESUME_DONE,
    PROFILE_RESUME_FILE_INPUT,
    PROFILE_RESUME_SECTION,
)

PROFILE_URL = "https://hk.jobsdb.com/profile"
MAX_PDF_BYTES = 5 * 1024 * 1024
_REMOTE_NAME = re.compile(
    r"^JBA_[A-Za-z0-9_-]+_v[1-9][0-9]*_[a-f0-9]{8}\.pdf$"
)

_LIST_RESUMES_JS = r"""() => {
  /* JBA_LIST_RESUMES */
  const items = Array.from(document.querySelectorAll(
    '[data-automation="resume-item"], [data-automation="uploaded-resume"]'
  ));
  return items.map(item => {
    const named = item.querySelector(
      '[data-automation="resume-name"], a[href*="resume"], [title]'
    );
    return (named?.textContent || named?.getAttribute('title')
      || item.textContent || '').trim();
  }).filter(Boolean);
}"""

_DELETE_FIRST_RESUME_JS = r"""() => {
  /* JBA_DELETE_FIRST_RESUME */
  const item = document.querySelector(
    '[data-automation="resume-item"], [data-automation="uploaded-resume"]'
  );
  if (!item) return false;
  const button = item.querySelector(
    'button[data-automation="delete-resume"], '
    + 'button[data-automation="remove-resume"], '
    + 'button[aria-label*="Delete"], button[aria-label*="Remove"]'
  );
  if (!button) return false;
  button.click();
  return true;
}"""


class ResumeListNotEmptyError(RuntimeError):
    """Remote resumes could not be cleared safely."""


class ResumeUploadMismatchError(RuntimeError):
    """The uploaded remote filename could not be verified exactly."""


class HumanInterventionRequiredError(RuntimeError):
    """JobsDB requires a login, CAPTCHA, or changed-page intervention."""


@dataclass(frozen=True)
class RemoteResumeReceipt:
    filename: str
    uploaded_at: datetime


class RemoteResumeManager:
    def __init__(self, page: PageController) -> None:
        self.page = page

    async def replace_all_with(
        self,
        pdf_path: Path,
        remote_name: str,
    ) -> RemoteResumeReceipt:
        pdf = pdf_path.resolve()
        self._validate(pdf, remote_name)
        await self.page.goto(PROFILE_URL)
        try:
            await self.page.wait_for_selector(
                PROFILE_RESUME_SECTION,
                timeout=20.0,
            )
        except Exception as exc:
            raise HumanInterventionRequiredError(
                "JobsDB resume section is unavailable"
            ) from exc

        await self._delete_all()
        if await self._list_names():
            raise ResumeListNotEmptyError("remote resume list is not empty")

        await self.page.click(PROFILE_ADD_RESUME)
        await self.page.wait_for_selector(
            PROFILE_RESUME_FILE_INPUT,
            timeout=10.0,
        )
        with tempfile.TemporaryDirectory(prefix="jobsdb-resume-") as directory:
            upload = Path(directory) / remote_name
            shutil.copyfile(pdf, upload)
            await self.page.set_input_files(
                PROFILE_RESUME_FILE_INPUT,
                str(upload),
            )
            if await self.page.is_visible(PROFILE_RESUME_DONE):
                await self.page.click(PROFILE_RESUME_DONE)
            await self.page.wait_for_timeout(500)

        names = await self._list_names()
        if names != [remote_name]:
            raise ResumeUploadMismatchError(
                f"expected sole remote resume {remote_name!r}, got {names!r}"
            )
        return RemoteResumeReceipt(
            filename=remote_name,
            uploaded_at=datetime.now(UTC),
        )

    async def _delete_all(self) -> None:
        for _ in range(20):
            names = await self._list_names()
            if not names:
                return
            clicked = await self.page.evaluate(_DELETE_FIRST_RESUME_JS)
            if not clicked:
                raise ResumeListNotEmptyError(
                    f"could not delete remote resume {names[0]!r}"
                )
            await self.page.wait_for_timeout(200)
            if await self.page.is_visible(PROFILE_RESUME_DELETE_CONFIRM):
                await self.page.click(PROFILE_RESUME_DELETE_CONFIRM)
            await self.page.wait_for_timeout(300)
        raise ResumeListNotEmptyError(
            "remote resume deletion exceeded limit"
        )

    async def _list_names(self) -> list[str]:
        value = await self.page.evaluate(_LIST_RESUMES_JS)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise HumanInterventionRequiredError(
                "JobsDB resume list could not be read"
            )
        return [item.strip() for item in value if item.strip()]

    @staticmethod
    def _validate(pdf: Path, remote_name: str) -> None:
        if not _REMOTE_NAME.fullmatch(remote_name):
            raise ValueError("invalid remote resume filename")
        if (
            not pdf.is_file()
            or pdf.suffix.lower() != ".pdf"
            or not pdf.read_bytes()[:5] == b"%PDF-"
        ):
            raise ValueError("approved resume must be a PDF")
        if pdf.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("approved resume PDF exceeds 5 MB")
