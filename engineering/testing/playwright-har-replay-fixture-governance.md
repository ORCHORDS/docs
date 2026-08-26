# Playwright HAR replay fixture governance

**Issue:** Browser tests replay recorded HTTP traffic, but fixtures silently collect sensitive data, drift from intended behavior, or change without review.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Symptom

A test suite becomes fast and deterministic with HAR replay, but failures later reflect stale recordings, accidental live updates, missing response variants, or secrets and personal data committed inside fixtures.

## Root cause

Playwright can record and replay HAR traffic. Replay matches URL and method, and also matches POST bodies strictly. Updating a HAR makes the fixture a new test dependency, so it requires the same review and data-handling discipline as code or test data.

**Source:** [Playwright network mocking and HAR replay](https://playwright.dev/docs/mock).

## Fix

- record HARs only against dedicated non-production accounts and seeded, disposable data;
- redact tokens, cookies, authorization headers, personal data, and internal host details before committing;
- make replay the default in CI; permit live recording/update only through an explicit reviewed workflow;
- name fixtures by scenario and version them with the contract they model;
- test key request variants intentionally, especially POST bodies, pagination, error responses, and authentication failures;
- fail clearly when a required request has no matching fixture instead of silently falling back to live traffic;
- periodically re-record through a controlled review when the external contract intentionally changes.

## Verification

- **Offline:** the test passes with network access to the external dependency blocked.
- **Privacy:** fixture scanning finds no credential, session, or real-user data.
- **Determinism:** the same test selection produces the same replayed responses.
- **Drift:** an intentional contract change produces a reviewed fixture diff and matching assertion change.
- **Failure:** an unmatched URL, method, or POST body fails with an actionable fixture error.

## Gotchas

- HAR replay is not a substitute for a small set of real provider integration tests.
- Recording from production can capture secrets and customer data even when the response body looks harmless.
- A broad fixture can hide request-shape regressions; prefer scenario-specific recordings.

## Related

- `testing/contract-testing.md`
- `testing/playwright-e2e.md`
- `security/test-data-management.md`
