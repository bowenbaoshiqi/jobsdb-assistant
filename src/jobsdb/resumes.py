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
    PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED,
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
    '[data-automation^="resume-item-"]'
    + ':not([data-automation="resume-item-list"])'
  ));
  return items.map(item => {
    const options = item.querySelector(
      'button[aria-label^="Options for "]'
    );
    const label = options?.getAttribute('aria-label') || '';
    return {
      filename: label.replace(/^Options for /, '').trim(),
      item_automation: item.getAttribute('data-automation') || '',
      is_default: Boolean(item.querySelector(
        '[data-automation^="resume-is-default-"]'
      )),
    };
  }).filter(item => item.filename && item.item_automation);
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


@dataclass(frozen=True)
class RemoteResumeRecord:
    filename: str
    item_automation: str
    is_default: bool


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

        await self.page.click(PROFILE_ADD_RESUME)
        await self.page.wait_for_selector(
            PROFILE_RESUME_FILE_INPUT,
            timeout=10.0,
        )
        initial = await self._list_records()
        defaults = [item for item in initial if item.is_default]
        if len(defaults) != 1:
            raise ResumeListNotEmptyError(
                "exactly one default remote resume is required"
            )
        default = defaults[0]
        await self._delete_non_default(default)

        with tempfile.TemporaryDirectory(prefix="jobsdb-resume-") as directory:
            upload = Path(directory) / remote_name
            shutil.copyfile(pdf, upload)
            if await self.page.is_visible(
                PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED
            ):
                await self.page.click(
                    PROFILE_RESUME_DEFAULT_CHECKBOX_CHECKED
                )
            await self.page.set_input_files(
                PROFILE_RESUME_FILE_INPUT,
                str(upload),
            )
            records = await self._wait_for_uploaded(
                default=default,
                remote_name=remote_name,
            )
            if await self.page.is_visible(PROFILE_RESUME_DONE):
                await self.page.click(PROFILE_RESUME_DONE)

        default_matches = [
            item
            for item in records
            if item.filename == default.filename and item.is_default
        ]
        tailored_matches = [
            item
            for item in records
            if item.filename == remote_name and not item.is_default
        ]
        if (
            len(records) != 2
            or len(default_matches) != 1
            or len(tailored_matches) != 1
        ):
            raise ResumeUploadMismatchError(
                "expected preserved default plus sole tailored resume"
            )
        return RemoteResumeReceipt(
            filename=remote_name,
            uploaded_at=datetime.now(UTC),
        )

    async def _wait_for_uploaded(
        self,
        *,
        default: RemoteResumeRecord,
        remote_name: str,
    ) -> list[RemoteResumeRecord]:
        for _ in range(20):
            records = await self._list_records()
            if any(item.filename == remote_name for item in records):
                return records
            await self.page.wait_for_timeout(500)
        raise ResumeUploadMismatchError(
            f"JobsDB did not finish uploading {remote_name!r}"
        )

    async def _delete_non_default(
        self,
        default: RemoteResumeRecord,
    ) -> None:
        for _ in range(20):
            records = await self._list_records()
            defaults = [item for item in records if item.is_default]
            if (
                len(defaults) != 1
                or defaults[0].filename != default.filename
            ):
                raise ResumeListNotEmptyError(
                    "default remote resume changed during cleanup"
                )
            removable = [item for item in records if not item.is_default]
            if not removable:
                return
            target = removable[0]
            if not re.fullmatch(
                r"resume-item-[A-Za-z0-9-]+",
                target.item_automation,
            ):
                raise ResumeListNotEmptyError(
                    "invalid remote resume item identifier"
                )
            item_id = target.item_automation.removeprefix("resume-item-")
            options_selector = (
                f'[data-automation="{target.item_automation}"] '
                'button[aria-label^="Options for "]'
            )
            delete_selector = (
                f'button[data-automation="delete-resume-button-{item_id}"]'
            )
            try:
                await self.page.click(options_selector)
            except Exception as exc:
                raise ResumeListNotEmptyError(
                    f"could not open remote resume {target.filename!r}"
                ) from exc
            await self.page.wait_for_timeout(300)
            await self.page.click(delete_selector)
            await self.page.wait_for_timeout(300)
            if await self.page.is_visible(PROFILE_RESUME_DELETE_CONFIRM):
                await self.page.click(PROFILE_RESUME_DELETE_CONFIRM)
            await self.page.wait_for_timeout(300)
        raise ResumeListNotEmptyError(
            "remote resume deletion exceeded limit"
        )

    async def _list_records(self) -> list[RemoteResumeRecord]:
        value = await self.page.evaluate(_LIST_RESUMES_JS)
        if not isinstance(value, list):
            raise HumanInterventionRequiredError(
                "JobsDB resume list could not be read"
            )
        try:
            records = [
                RemoteResumeRecord(
                    filename=item["filename"].strip(),
                    item_automation=item["item_automation"],
                    is_default=item["is_default"],
                )
                for item in value
                if isinstance(item, dict)
            ]
        except (KeyError, AttributeError, TypeError) as exc:
            raise HumanInterventionRequiredError(
                "JobsDB resume list could not be read"
            ) from exc
        if len(records) != len(value):
            raise HumanInterventionRequiredError(
                "JobsDB resume list could not be read"
            )
        return records

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
