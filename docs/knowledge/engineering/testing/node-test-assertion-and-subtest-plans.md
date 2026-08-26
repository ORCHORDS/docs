# Node.js assertion and subtest plans

**Issue:** Conditional asynchronous paths can silently skip assertions or leave subtests pending while the enclosing test appears successful.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use the Node test context's plan support to declare the expected combined count of tracked assertions and subtests. Use `t.assert` so assertions participate in tracking, and choose `wait` deliberately: false checks when the test function completes, true waits indefinitely, and a numeric value sets a bounded wait. Prefer a finite wait for event-driven tests so missing callbacks fail without hanging the suite.

Plans complement semantic assertions; do not inflate a count with meaningless checks. Keep parallel subtests explicitly awaited or included in the plan.

## Verification

Test exact, too few, and too many assertions; a late callback; a never-fired callback; rejected subtests; and timeout boundaries. Confirm ordinary assert calls are not mistakenly assumed to be tracked and verify cancellation cleanup.

## Gotchas

- Indefinite waiting can hang CI.
- A correct count does not prove correct values.
- Pin Node because the test API evolves.

## Official source

- [Node.js test plans](https://nodejs.org/api/test.html#contextplan-count-options)
