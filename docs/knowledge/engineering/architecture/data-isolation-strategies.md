# data-isolation-strategies

**Issue:** Tenants can access each other's data due to missing query filters
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A bug in a shared-table design allows one tenant's API token to retrieve another tenant's records.

## Pattern / Solution
Enforce isolation at multiple layers: row-level security in the database, middleware that injects tenant context, and integration tests that assert cross-tenant access returns 403. Prefer database-level enforcement as the final defense.

## Gotchas
Shared tables with composite indexes on tenant_id are necessary for performance. Full-table scans with missing tenant filters are the most common exploit vector.

## Related
multi-tenancy-architecture, tenant-routing-patterns, api-security-architecture
