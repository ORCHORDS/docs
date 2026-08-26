# multi-tenancy-architecture

**Issue:** Serving multiple customers from shared infrastructure without data leakage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A SaaS product launches with a single-tenant mental model. Adding a second customer requires database duplicates and separate deployments.

## Pattern / Solution
Three main models: silo (separate infrastructure per tenant), pool (shared infrastructure, tenant ID column), and bridge (shared compute, separate databases). Pool is most cost-efficient but requires rigorous row-level isolation. Silo offers the strongest compliance boundary.

## Gotchas
Row-level security must be enforced at the query layer, not the application layer. Tenant ID must be present on every request and validated early in the middleware stack.

## Related
data-isolation-strategies, tenant-routing-patterns, feature-flag-architecture
