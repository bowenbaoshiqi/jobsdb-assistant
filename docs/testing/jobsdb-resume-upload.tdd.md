# JobsDB tailored resume upload — TDD evidence

## User journey

An approved Quick Apply job preserves the user's sole default resume, removes
other non-default resumes, uploads the approved job-specific PDF as non-default,
and waits for JobsDB to publish it before continuing.

## Evidence

| Guarantee | Test or validation | Result |
|---|---|---|
| A checked `Make this my default resumé` control is cleared before upload | `tests/unit/test_jobsdb_resume_manager.py::test_replace_deletes_every_resume_then_uploads_exact_file` | PASS |
| The manager waits for an asynchronous upload to appear | `tests/unit/test_jobsdb_resume_manager.py::test_replace_waits_until_async_upload_appears` | PASS |
| Default resume cleanup and application execution remain compatible | `uv run pytest tests/unit/test_jobsdb_resume_manager.py tests/unit/test_playwright_controller.py tests/integration/test_application_execution_workflow.py -q` | 36 passed |
| Changed Python files satisfy lint | `uv run ruff check src/jobsdb/resumes.py src/jobsdb/selectors.py tests/unit/test_jobsdb_resume_manager.py` | PASS |

## RED/GREEN checkpoints

- RED `06f8f44`: the test suite failed because the default-checkbox contract
  and asynchronous upload behavior did not exist.
- GREEN `7207487`: the same focused suite passed after clearing the checkbox
  and polling for the uploaded record.
- Real latency `8502c29`: live JobsDB observation showed the record appearing
  after roughly eight seconds, so the bounded polling window was raised to
  thirty seconds.

## Live verification

On 2026-07-28, the production browser path selected
`JBA_93533309_v1_16a96a14.pdf`, JobsDB displayed `Uploading resumé`, and the
record appeared as non-default. A second run through the Dashboard worker
removed the prior non-default copy and uploaded it again. The final visible
JobsDB list contained:

- `Bowen_Bao_resume_v5.pdf` — Default
- `JBA_93533309_v1_16a96a14.pdf` — non-default

The subsequent Quick Apply wizard stopped at `waiting_for_human` because its
Review page was not reached; that is separate from resume upload verification.
