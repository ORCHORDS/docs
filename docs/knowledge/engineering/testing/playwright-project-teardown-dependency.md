# Playwright project teardown dependency contract

**Problem**

Project teardown can be skipped or misordered if setup/dependency relationships are modeled only with shell cleanup.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for authenticated state, services, or fixtures shared by a Playwright project graph.

## Controls

- Declare setup dependencies and teardown projects in configuration.
- Make teardown idempotent and safe after partial setup.
- Keep required results failing even if cleanup also fails.

## Implementation

- Store temporary state under unique run IDs.
- Run teardown with least privilege and bounded time.
- Upload diagnostics before destructive cleanup.

## Tests

- Exercise success, setup failure, test failure, cancellation, retries, and sharding.
- Verify no state crosses runs.

## Gotchas

- Teardown ordering follows project dependencies.
- Process kill can still bypass in-process cleanup.
- Cleanup success must not mask test failure.

## Official sources

- [Official documentation](https://playwright.dev/docs/test-global-setup-teardown)
