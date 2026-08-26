# Playwright expect.poll and toPass timeout boundaries

**Issue:** Retrying arbitrary assertions without an explicit timeout or side-effect policy can turn a fast failure into an unbounded test, repeat destructive actions, or conceal a system that never becomes stable.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Prefer locator auto-retrying assertions for UI state. Use `expect.poll` when repeatedly obtaining one value and `expect(...).toPass` when the whole assertion block must be retried.
- Set explicit `timeout` and reviewed `intervals` at the call site. `toPass` defaults to timeout `0` and does not inherit the configured expect timeout.
- Keep retried callbacks observational or idempotent. Move writes outside the retry loop, or protect them with an operation key.
- Keep the retry budget below the enclosing test and job deadlines, and include the last observed value or assertion in failure evidence.
- Distinguish eventual consistency from flakiness; do not expand timeouts without measuring the expected convergence distribution.

## Verification

Test immediate success, success on a later probe, permanent failure, callback exception, a slow probe, enclosing test timeout, custom intervals, and a callback that would duplicate a write. Assert elapsed time and attempt count stay within policy.

## Gotchas

- Polling can increase load on an already degraded dependency.
- A zero timeout has different consequences across assertion forms; configure it rather than relying on defaults.
- Retrying a non-idempotent action changes the system being observed.

## Official source

- [Playwright assertions: expect.poll and expect.toPass](https://playwright.dev/docs/test-assertions#expectpoll)
