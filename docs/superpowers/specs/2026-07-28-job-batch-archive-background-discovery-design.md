# Job Batch Archive and Background Discovery Design

## Goal

Make the Dashboard operate on one explicit batch of at most 15 current jobs.
The user can immediately archive that batch, enter a keyword, and start a
private background JobsDB discovery for a new batch. Historical batches are
excluded from future discovery and are completely purged after 30 days.

## Dashboard interaction

The Dashboard header contains:

- one required keyword input;
- `归档当前批次并抓取下一批`;
- `刷新批次状态`.

On confirmation:

1. The current batch is immediately marked `archived`.
2. Every job in it is considered processed and disappears from the Dashboard.
3. A new batch is created with the supplied normalized keyword and status
   `discovering`.
4. The HTTP request returns immediately; Python discovery runs in the existing
   local Dashboard process.
5. Manual status refresh reports `discovering`, `waiting_for_scoring`,
   `scoring`, `ready`, or `failed`. The page never performs a whole-page
   automatic refresh.

Only one `discovering` batch may exist. A repeated click while one is active
returns HTTP 409 without archiving another batch.

## Batch persistence

Add SQLite tables:

### `job_batches`

- `id`
- `keyword`
- `status`
- `created_at`
- `archived_at`
- `error_code`
- `error_message`

Statuses are:

- `discovering`
- `waiting_for_scoring`
- `scoring`
- `ready`
- `archived`
- `failed`

### `job_batch_jobs`

- `batch_id`
- `job_id`
- `position`
- `added_at`

`(batch_id, job_id)` and `(batch_id, position)` are unique. A partial unique
index allows at most one non-archived batch; that single batch may be
discovering, waiting for scoring, scoring, ready, or failed.

The Dashboard read model shows jobs belonging to the newest non-archived
batch only. Existing job, snapshot, evaluation, material, and application
models remain the source of detailed data.

## Background discovery

The Dashboard application owns one foreground-lifecycle async worker. A
request queues a batch ID; the worker:

1. opens public JobsDB search without credentials;
2. searches Hong Kong with the batch keyword;
3. paginates search results;
4. excludes every job ID present in any current or archived batch;
5. captures complete JD and Apply/Quick Apply type;
6. adds each successfully captured unique job to the batch in stable order;
7. stops after 15 jobs or after JobsDB has no next page;
8. marks the batch `waiting_for_scoring` when at least one job was captured;
9. marks it `failed` when discovery itself fails or captures zero jobs.

If fewer than 15 eligible jobs exist, the batch keeps however many were
captured. The previous batch remains archived and is never restored.

The worker closes with the Dashboard application and resumes any persisted
`discovering` batch when the Dashboard starts again.

## Scoring handoff

The jobsdb-assistant skill keeps the CC/Codex Agent session active while the
Dashboard runs. It watches the current batch:

- `waiting_for_scoring`: Python creates native Career Ops tasks for exactly
  that batch's unevaluated jobs;
- each task is processed through the existing A–F evaluation workflow;
- the batch moves through `scoring` to `ready`;
- isolated evaluation failures are recorded and reported without modifying
  Career Ops or the candidate profile.

No AI provider is added to the Dashboard process. Closing the Agent session
pauses scoring but not public background discovery. Restarting the skill
resumes pending scoring.

## Historical exclusion

Every job assigned to a batch is excluded from later discovery while that
batch record exists. This applies across different and repeated keywords.
Archiving means the user has processed every job in the batch; there is no
per-job archive decision.

## Thirty-day complete purge

Whenever the Dashboard starts and before archive/discovery operations, Python
purges batches whose `archived_at` is more than 30 days old.

For each expired batch, remove all data associated with its jobs, including:

- batch membership and batch row;
- job and complete JD snapshots;
- evaluations and evaluation cache rows;
- selections;
- material tasks, packages, review history, generated PDFs, and cover letters;
- Dashboard and approved-application execution rows and events;
- application and tracking records;
- AI task/checkpoint files and screenshots that are uniquely attributable to
  those jobs.

No job details, scoring, materials, application audit, or batch summary are
retained. Deletion is ordered transactionally around SQLite references;
filesystem artifacts are removed only from validated paths below the private
workspace/data roots. If one job belongs to a newer batch, it is retained
until every referencing batch has expired.

## Initial migration and test batch

For the current local database only, bootstrap one current `AI Lead` batch
from the first 15 successfully captured jobs of the most recent `AI Lead`
discovery. Preserve their stable discovery order. Existing jobs outside that
batch remain in SQLite but are not shown in the current Dashboard and are not
treated as processed unless they later enter a batch.

Fresh installations create no synthetic batch. Their first keyword request
creates the first real batch.

## Privacy and safety

- Dashboard remains bound to `127.0.0.1`.
- Keywords, jobs, and task state never leave local storage except through
  public JobsDB navigation and the pinned local Agent workflow.
- No credentials are required for discovery.
- Purge accepts only database-resolved batch IDs and validated private artifact
  paths; it never accepts arbitrary filesystem paths from HTTP.

## Testing

- Migration and repository tests cover batch uniqueness, stable ordering,
  immediate archive, and historical exclusion.
- Discovery tests cover pagination, historical filtering, the 15-job limit,
  partial batches, zero-result failure, and restart recovery.
- Purge tests use records in every related table plus private test artifacts
  and prove complete removal after 30 days and retention before the cutoff.
- API tests cover required keyword, HTTP 202, HTTP 409, immediate Dashboard
  disappearance, and manual status refresh.
- Browser tests cover the Simplified Chinese controls without whole-page
  automatic refresh.
- Skill contract tests require exact-batch scoring and resume behavior.

## Out of scope

- Public deployment or LAN binding.
- Multiple simultaneous discovery batches.
- Re-displaying archived batches.
- Retaining any data after the 30-day purge.
- Changing Career Ops scoring or either pinned integration checkout.
