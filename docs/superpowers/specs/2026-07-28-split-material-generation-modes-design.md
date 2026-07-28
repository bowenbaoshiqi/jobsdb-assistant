# Split Material Generation Modes Design

## Goal

Let a user choose, for one or more selected jobs, between:

1. generating only a tailored English cover letter and applying with the
   existing JobsDB default resume; or
2. generating a tailored English resume PDF and cover letter, preserving the
   current behavior.

Both choices must use the existing generation, preview, fact-checking, manual
review, versioning, and application lifecycle.

## Scope

This is a minimal extension of the current v0.6 workflow. It does not introduce
a second material service, a new worker, or a separate review model.

The Dashboard adds two actions:

- `仅定制求职信`
- `定制简历 + 求职信`

The existing material task and package contracts gain a material mode:

- `cover_letter_only`
- `tailored_resume_and_cover_letter`

The selected mode is persisted from the Dashboard command through task
generation, material review, approval, regeneration, and application handoff.

## Generation Behavior

### Cover letter only

- Generate and save one English cover letter per job.
- Run the existing Reviewer, ATS, and fact-consistency checks.
- Do not render, validate, copy, or save a tailored resume PDF.
- Record that the application must use the JobsDB default resume.

### Tailored resume and cover letter

- Preserve the current behavior.
- Rewrite only Professional Summary, Career Highlights, and Core Competencies.
- Render and validate the tailored PDF.
- Generate and save the English cover letter.

For both modes, each selected job creates an independent material version.

## Preview and Review

Both modes use the existing material preview and review page.

For `cover_letter_only`, the resume panel states that the JobsDB default resume
will be used and does not expose a PDF iframe or download link. The cover
letter, Reviewer findings, ATS findings, fact findings, version history, and
approve/reject/regenerate controls remain available.

For `tailored_resume_and_cover_letter`, the current PDF preview and download
remain unchanged.

Regeneration preserves the material mode of the version being regenerated.
Approval never changes the selected mode.

## Application Handoff

The approved-material handoff carries the persisted material mode.

- `cover_letter_only`: keep the JobsDB default resume selected and submit the
  approved cover letter. Do not delete, upload, or select remote resumes.
- `tailored_resume_and_cover_letter`: use the existing remote resume cleanup,
  upload, selection, and cover-letter flow.

The application flow must reject inconsistent data, such as a full-material
mode without an approved resume artifact.

## Compatibility

Existing material records and callers without an explicit mode are interpreted
as `tailored_resume_and_cover_letter`. This preserves current behavior and
avoids migration work for private local data.

The existing direct quick-apply path using the JobsDB default resume without a
cover letter remains unchanged.

## Error Handling

- A cover-letter-only package must not require a resume file.
- A full package must still fail safely when its resume is missing, unsafe, or
  invalid.
- Material mode must be immutable for a created version.
- Repeated Dashboard commands retain existing idempotency rules.
- Review and application errors remain visible through the current status and
  error-reporting surfaces.

## Testing

TDD coverage will verify:

- both Dashboard buttons submit the correct mode for selected jobs;
- task and package persistence preserves the mode;
- cover-letter-only generation does not render or install a resume;
- full generation remains unchanged;
- preview hides PDF controls and explains default-resume use in cover-only mode;
- approve, reject, and regenerate preserve the mode;
- application handoff skips remote resume management in cover-only mode;
- full mode still uploads and selects the approved tailored resume;
- legacy records default to full mode;
- invalid mode/artifact combinations fail safely.

