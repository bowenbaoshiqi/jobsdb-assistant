# Evaluation Backfill Controls Design

## Goal

Add two minimal Dashboard controls that let the user append jobs accidentally
missed by the normal post-scrape Agent scoring flow. These controls are a
backfill mechanism only; they do not replace or independently execute AI
scoring.

## User-visible behavior

The current evaluation progress panel gains two Simplified Chinese buttons:

- `补充全部未评分职位`
- `补充已选未评分职位`

Both actions consider only active jobs that have no persisted evaluation.
Already evaluated jobs and jobs already present in the current evaluation batch
are skipped.

The selected-only action additionally requires an active user selection. Its
button is disabled when no jobs are selected.

After a successful request, the page reports how many jobs were appended. If
there are no eligible jobs, it reports that there are no missing evaluations
and does not create an empty batch.

## Architecture

The Dashboard adds one backfill endpoint accepting a scope of `all` or
`selected`. The server resolves eligible job IDs from SQLite and passes them to
`EvaluationProgressStore`.

`EvaluationProgressStore` gains an append operation:

- If no batch exists, create a batch containing the eligible IDs.
- If a batch exists, preserve its ID, start time, and every existing task
  status, then append only missing IDs as `queued`.
- If no new IDs remain, leave the persisted batch unchanged.

The endpoint never calls Career Ops, an AI provider, or a browser. The active
CC/Codex Agent session remains responsible for consuming queued IDs through the
existing scoring workflow.

## Normal flow

The normal product flow remains unchanged: after a new JobsDB scrape, the
running Agent proceeds directly into scoring. Dashboard backfill controls exist
only for jobs omitted from that normal flow.

## Error handling

- Unsupported scope returns HTTP 422 through request validation.
- A selected-only request with no eligible selected jobs returns a successful
  zero-appended response.
- Missing dependencies return HTTP 503.
- Repeated sequential requests are idempotent because existing task IDs are
  excluded before persistence.

## Testing

- Unit tests cover appending to idle, active, and completed batches; duplicate
  suppression; and empty input.
- Integration tests cover both endpoint scopes and confirm evaluated or already
  queued jobs are skipped.
- Browser-level tests verify the two Chinese controls, selected-button disabled
  state, request payload, and user-visible result.
- Existing non-E2E tests and lint must remain green.

## Out of scope

- Re-scoring evaluated jobs.
- Starting a second AI service or provider.
- Automatic polling or page refresh.
- Changing the existing post-scrape Agent scoring behavior.
