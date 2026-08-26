# Playwright trace retention and sensitive evidence

**Issue:** Always-on browser tracing slows CI and stores potentially sensitive DOM, source, and network evidence, while absent traces make intermittent failures hard to diagnose.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Choose a Playwright trace mode from failure evidence needs and retry policy. `on-first-retry` reduces routine overhead; retain-on-failure modes preserve initial-failure evidence when retries might pass. A retry must not convert a flaky required check into success without a separate flake policy.

## Controls and verification

- Set short artifact retention and access controls.
- Avoid real secrets and personal data in test environments.
- Redact or prevent sensitive headers and payloads.
- Pin Playwright and browser versions.
- Measure trace overhead and artifact volume.
- Confirm a failed run produces an accessible, complete trace.

## Sources

- [Playwright: Trace Viewer](https://playwright.dev/docs/trace-viewer)
- [Playwright: testOptions.trace](https://playwright.dev/docs/api/class-testoptions#test-options-trace)
