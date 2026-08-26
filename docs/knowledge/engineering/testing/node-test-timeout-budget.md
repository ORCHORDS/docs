# Node test timeout budget

**Problem**

Tests without bounded timeouts can occupy a worker until the job timeout, while one global aggressive timeout creates false failures.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when test duration has an explicit service-level budget.

## Controls

- Set suite or test timeouts from measured behavior.
- Keep the job timeout higher for reporting and cleanup.
- Separate network/integration budgets from unit tests.

## Implementation

- Pass timeout through supported test options.
- Make teardown bounded and preserve diagnostics.
- Use AbortSignal-aware helpers.

## Tests

- Test just below/above timeout, hung setup/body/teardown, nested tests, and concurrency.

## Gotchas

- Timeout cancellation may not stop blocking native code.
- Fake timers alter semantics.
- A timeout is not a performance benchmark.

## Official sources

- [Official documentation](https://nodejs.org/api/test.html)
