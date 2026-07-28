# Headless Background Discovery Design

## Goal

Run Dashboard-triggered JobsDB public job discovery in a headless browser
without changing scoring, material generation, application, or submission
behavior.

## Design

The Dashboard worker currently shares the production browser configuration
between public discovery and approved application execution. The shared
configuration defaults to a visible browser, so an asynchronous discovery job
still opens in the foreground.

At the discovery boundary, create an independent deep copy of the production
configuration and set only `browser.headless = True`. Construct the discovery
`Orchestrator` with this copy.

Keep the original production configuration unchanged. Approved Quick Apply
preparation and submission continue using a visible browser so manual login,
CAPTCHA handling, review, and intervention remain possible.

## Constraints

- Do not modify discovery, pagination, exclusion, batch-size, scoring, or
  persistence logic.
- Do not change Quick Apply or Apply behavior.
- Do not mutate the shared configuration object.
- Add a regression test proving discovery receives headless configuration
  while application execution retains visible configuration.

