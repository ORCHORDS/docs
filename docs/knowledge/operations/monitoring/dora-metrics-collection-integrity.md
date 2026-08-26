# dora-metrics-collection-integrity

**Issue:** Delivery metrics report zero or undercount deployments because workflow data is paginated, filtered incorrectly, or unavailable.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A DORA dashboard reports a sudden deployment-frequency drop to zero. The underlying API actually returned only its default first page, excluded the production deployment workflow, or failed during collection. The dashboard silently turns the failure into `0`, making an instrumentation outage look like a delivery regression.

## Root cause

A delivery metric is only meaningful when its event definition and collection completeness are explicit. Deployment frequency should count successful deployments to production, not commits, workflow starts, preview deployments, or a partial API page. A missing or failed collection is unknown data, not the numeric value zero.

**Source:** [Google Cloud — DORA metrics](https://docs.cloud.google.com/deploy/docs/metrics).

## Fix

Define and verify the pipeline contract:

- document the canonical production-deployment event, environment, repository scope, success state, and reporting window;
- paginate every source API to exhaustion or a documented, monitored upper bound;
- persist collection metadata: cursor/page count, source timestamp, query parameters, record count, and failure status;
- model the metric as `available`, `partial`, or `unavailable`; never coerce failed collection to zero;
- alert on stale, partial, or failed collection separately from changes in the metric itself;
- test a dataset larger than the provider default page size and a simulated API failure.

## Verification

- **Volume:** more workflow runs than one API page are all enumerated and counted once.
- **Definition:** preview, failed, and non-production workflows do not affect deployment frequency.
- **Failure:** an API timeout produces `unavailable` with diagnostic metadata, not `0`.
- **Regression:** a known production deployment increments the metric exactly once.

## Gotchas

- Different teams may deploy through different workflows; centralize the event definition before comparing teams.
- Retries and reruns can represent one logical deployment. Deduplicate with a documented deployment identity.
- Do not expose provider tokens or raw response bodies in metric diagnostics.

## Related

- `patterns/observability-three-pillars.md`
- `patterns/error-budget-slo.md`
- `monitoring/observability-alert-fatigue.md`
