# Playwright flaky-test release gate

**Issue**

Retries can turn an initially failing test green while masking instability unless flaky outcomes fail the release policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable `failOnFlakyTests` for protected CI after quarantining known debt.
- Keep retries and flaky classification visible in reports.
- Assign ownership and expiry to quarantine entries.

## Verification

1. Create pass, fail, and fail-then-pass fixtures.
2. Verify flaky status fails protected CI.
3. Test shards and merged reports.

## Gotchas

- Retries are evidence collection, not correctness.
- A flaky gate without triage can block indefinitely.
- Local and CI policies may intentionally differ.

## Official source

- [Official documentation](https://playwright.dev/docs/api/class-testconfig#test-config-fail-on-flaky-tests)
