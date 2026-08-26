# service-discovery-patterns

**Issue:** Service endpoints change dynamically but clients have hardcoded addresses
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A rolling deploy changes the IP addresses of upstream services, causing hardcoded clients to fail until manually updated.

## Pattern / Solution
Use client-side discovery (query a registry then connect directly) or server-side discovery (route through a load balancer that queries the registry). Kubernetes DNS provides built-in service discovery via stable cluster-internal hostnames.

## Gotchas
Service registries must themselves be highly available. Stale registry entries after crashes require TTL-based expiry and health-check eviction. DNS TTLs must be short enough to track changes without overloading resolvers.

## Related
container-orchestration-design, service-mesh-patterns, configuration-management
