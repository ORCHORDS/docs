# Workers compatibility-date upgrade governance

**Issue:** A Worker uses an old compatibility date indefinitely or advances it as an unrelated change, making runtime behavior changes hard to attribute and rollback.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Root cause

A Workers compatibility date pins the cumulative set of backward-incompatible runtime changes and compatibility flags through that date. Old dates remain supported, but documentation generally describes current behavior. A deliberate upgrade process is required to benefit from fixes while preserving controlled behavior change.

**Source:** [Cloudflare Workers compatibility dates](https://developers.cloudflare.com/workers/configuration/compatibility-dates/).

## Fix

- record the compatibility date and enabled flags with each deployment;
- set new Workers to the current date, then advance established Workers on a scheduled review cadence;
- review the changes/flags introduced between the current and target dates;
- run focused tests and a canary against the target date before broad rollout;
- give the upgrade an owner, rollback plan, and monitoring window;
- keep a compatibility-date change isolated from unrelated feature work where possible.

## Verification

- A deployment record identifies its compatibility date and flags.
- A target-date canary passes behavior, error-rate, and latency checks.
- A known compatibility-sensitive test runs before promotion.
- Rollback restores the previous date/flags and verifies the expected behavior.
- No Worker is left without an intentional, reviewable date.

## Gotchas

- A compatibility date is not a dependency version pin; upstream services and packages still need their own upgrade controls.
- Avoid relying on undocumented legacy behavior merely because an old date still runs.
- Test both Worker runtime behavior and build/deployment tooling when advancing dates.

## Related

- `cloudflare/workers-deployments.md`
- `deploy/canary-deployments.md`
- `testing/production-smoke-tests.md`
