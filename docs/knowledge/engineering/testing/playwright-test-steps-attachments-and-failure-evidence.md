# Playwright test steps, attachments, and failure evidence

**Issue:** End-to-end failures have only a long test name or a generic screenshot, making triage slow and encouraging retries instead of diagnosis.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use Playwright test steps to expose meaningful user or system phases and attach narrowly scoped diagnostic evidence on failure. Keep secrets and personal data out of artifacts.

## Practice

1. Name steps by observable intent, such as “customer confirms payment” rather than implementation details.
2. Keep assertions close to the action they validate, so a failed step preserves causal context.
3. Attach traces, screenshots, logs, and selected response details only according to retention and redaction rules.
4. Use the same evidence policy locally and in CI; publish the report only after access controls are verified.
5. Classify a failure from evidence before retrying it; retries are not a substitute for a stable assertion or synchronized test state.

## Guardrails

- Excessive nesting or per-line steps makes reports noisier rather than clearer.
- Do not attach authentication headers, cookies, API keys, full production payloads, or sensitive user data.
- A passing retry does not erase the original failure; retain enough context to detect flakes.
- Confirm that artifacts are reachable only by the intended project members and expire them on schedule.

## Sources

- [Playwright: test steps](https://playwright.dev/docs/test-steps)
- [Playwright: trace viewer](https://playwright.dev/docs/trace-viewer)
