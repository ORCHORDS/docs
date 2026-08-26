# Playwright trace viewer debugging

**Date:** 2026-08-26
**Status:** documented
**Sources:**
- https://playwright.dev/docs/test-cli
- https://playwright.dev/docs/test-assertions

## Context

Playwright can retain traces for failed/retried tests and open them with Trace Viewer. Traces are useful post-mortem evidence for browser state and actions when a CI failure is hard to reproduce locally.

## Pattern

- Configure tracing for failures or retries rather than indiscriminately retaining every run when storage is a concern.
- Preserve the first useful failure evidence before retries mutate server/client state.
- Pair trace inspection with web-first auto-retrying assertions so the test waits on user-visible conditions instead of arbitrary sleeps.
- Treat a retry pass as evidence of flakiness, not proof the original failure was harmless.

## Useful CLI behavior

Playwright supports tracing modes such as `on-first-retry`, `on-all-retries`, `retain-on-failure`, and related failure/retry modes. Trace files can be opened with `npx playwright show-trace`.

## Verification

Intentionally fail a safe test in CI and confirm:

1. a trace is retained under the configured failure mode;
2. the trace opens and contains the expected action timeline;
3. sensitive values are not intentionally embedded in test data, URLs, screenshots, or logs;
4. retries do not erase the evidence needed to understand the first failure.
