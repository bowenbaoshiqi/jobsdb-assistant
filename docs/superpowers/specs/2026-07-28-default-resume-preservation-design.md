# Default Resume Preservation Design

## Goal

JobsDB requires one default resume. Approved-material preparation must preserve
that default resume while ensuring the application wizard uses the tailored
PDF for the current job.

## Required Behaviour

1. Open the current JobsDB resume-management drawer.
2. Read every resume as a structured record containing its filename, stable
   item identifier, and whether JobsDB marks it as `Default`.
3. Require exactly one default resume. If the default cannot be identified,
   stop without deleting or uploading anything.
4. Preserve the default resume unchanged.
5. Delete every non-default resume using its exact stable item identifier.
6. Upload the approved tailored PDF for the current job.
7. Do not interact with the `Make this my default resumé` checkbox. JobsDB
   preserves the existing default when a new file is uploaded.
8. Verify the final remote state contains exactly:
   - the original default resume, still marked `Default`; and
   - the current job-specific tailored PDF, not marked `Default`.
9. Continue to Quick Apply only after this verification passes. The resume
   step must select the tailored filename exactly, never rely on the default.

## Failure Handling

- Zero or multiple default resumes: stop before mutation.
- A non-default resume cannot be deleted: stop before upload.
- The default filename or marker changes: stop before entering Quick Apply.
- The tailored filename is missing, duplicated, or marked default: stop.
- No failure path submits an application or silently falls back to the
  default resume.

## Testing

- Unit tests cover default detection, non-default-only deletion, preservation
  of the default marker, and exact final-state verification.
- Existing material-aware apply tests continue to require exact tailored
  filename selection.
- The real JobsDB test starts with the current account's default plus saved
  resumes and finishes with the preserved default plus one tailored PDF.
