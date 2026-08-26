# backend-for-frontend-pattern

**Issue:** Providing client-specific API aggregation without coupling all clients to a single generic API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A generic API serves mobile, web, and third-party clients with different data needs; every client gets too much or too little data.

## Pattern / Solution
Separate BFF per client type: each BFF aggregates and shapes data for its client.

```
Mobile App → [Mobile BFF] → [User Svc, Product Svc, Order Svc]
Web App    → [Web BFF]    → [User Svc, Product Svc, Analytics Svc]
Partner    → [Public API] → [Product Svc, Inventory Svc]
```

Mobile BFF: fewer fields, image URLs resized, offline sync endpoints.
Web BFF: full data, pagination, filtering for rich UI.
Public API: stable versioned interface, rate limited.

## Gotchas
- BFF duplication: similar aggregation logic in each BFF; extract to shared libraries carefully
- BFF owned by the frontend team, not backend team — aligns incentives
- Do not let BFF accumulate business logic; keep it a thin aggregation layer

## Related
- `api-gateway-pattern.md`
- `graphql-schema-design.md`
- `api-versioning-strategy.md`
