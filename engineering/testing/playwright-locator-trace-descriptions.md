# Playwright locator descriptions for trace diagnostics

**Issue:** Repeated generic locators make CI traces difficult to interpret and slow root-cause analysis without improving test correctness.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use `locator.describe()` to attach stable, non-sensitive intent labels to important locators shown in traces and reports. Describe the user-visible role of the element rather than DOM structure or dynamic account data. Retain accessible role, label, or test-id locator contracts; descriptions improve evidence but do not change matching or strictness.

Establish a short naming convention for shared page objects and prohibit secrets, personal data, tokens, or raw customer identifiers because descriptions may enter retained CI artifacts.

## Verification

Record a failing trace and confirm descriptions identify intended controls across retries and page-object reuse. Verify the locator still fails on zero or multiple matches, review artifact redaction, and test report compatibility on the pinned Playwright version.

## Gotchas

- Descriptions do not make weak selectors stable.
- Trace retention is a data-governance decision.
- The API requires a sufficiently recent Playwright release.

## Official source

- [Playwright Locator.describe](https://playwright.dev/docs/api/class-locator#locator-describe)
