# cloudflare-logpush-no-backfill-loss-and-health-slo

**Issue:** A Cloudflare Logpush destination fails or is disabled, and the team assumes the missed interval can be replayed later.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Log delivery is an operational data pipeline. A failed or disabled destination can create permanent observability gaps; field selection, compression, destination health, and ownership determine whether security and incident evidence remains usable.

**Source:** [Cloudflare Logpush](https://developers.cloudflare.com/logs/logpush/).

## Fix

- assign owner, destination, retention, field-minimization, and cost budget for each job;
- alert on destination validation, delivery failures, and delivery gaps;
- test the ownership challenge and a controlled destination failure;
- document the evidence gap and incident procedure when logs are lost;
- avoid unnecessary sensitive fields and validate compression/volume assumptions;
- periodically reconcile destination ingestion with expected delivery.

## Verification

- A failed destination generates an actionable alert.
- A delivery gap is visible to the owning team.
- Required incident fields arrive at the destination.
- Destination recovery is tested without assuming backfill.

## Related

- `monitoring/observability-three-pillars.md`
- `cloudflare/workers-analytics-engine.md`
