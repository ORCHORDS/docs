# tenant-routing-patterns

**Issue:** Requests must reach the correct tenant shard or region
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A global SaaS product must route EU tenants to EU data centers for compliance while keeping a unified API surface.

## Pattern / Solution
Resolve tenant from subdomain, JWT claim, or API key prefix at the edge. Store a tenant-to-region mapping in a low-latency lookup such as Redis or edge KV. Redirect or proxy the request to the correct backend shard.

## Gotchas
Caching tenant routing decisions reduces lookup latency but must be invalidated on tenant migration. Wildcard TLS certificates are needed for subdomain-based routing.

## Related
multi-tenancy-architecture, data-isolation-strategies, cdn-architecture
