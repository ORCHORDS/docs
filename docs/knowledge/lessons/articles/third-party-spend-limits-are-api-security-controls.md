# Third-Party Spend Limits Are API Security Controls

**Issue:** An endpoint is technically available under load, but attackers or accidental loops can trigger unbounded paid downstream operations such as messaging, verification, storage, or other per-request services.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API4:2023 explicitly includes third-party service spending among resource-consumption risks. Availability controls that ignore monetary exhaustion leave a real denial-of-service and abuse path open.

## Engineering rule

- Identify downstream calls whose cost scales with request count, size, duration, or generated artifacts.
- Configure provider spending limits where supported and billing alerts where hard limits are unavailable.
- Add application-side per-user, per-tenant, and per-operation quotas for expensive actions.
- Require idempotency or deduplication where retries could duplicate charges.
- Surface budget exhaustion as an explicit operational state rather than silently continuing spend.

## Verification

- Map every paid integration to its unit-cost driver and configured limit.
- Simulate a retry loop and repeated client calls to confirm duplicate or excessive spend is bounded.
- Test alerting before the configured hard budget is exhausted.

## Official source

- OWASP API4:2023 Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
