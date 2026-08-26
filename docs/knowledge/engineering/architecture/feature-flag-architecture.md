# feature-flag-architecture

**Issue:** Code is deployed to production but features are not ready to expose to users
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Long-lived feature branches cause merge conflicts. Teams want to ship code continuously but control visibility.

## Pattern / Solution
Separate deployment from release using runtime flags. Store flags in a dedicated service such as LaunchDarkly, Unleash, or GrowthBook. Evaluate flags per-request using user and tenant context. Gate UI and backend code paths behind the same flag key.

## Gotchas
Flag proliferation creates maintenance debt. Establish a TTL policy and remove stale flags within two sprints of full rollout. Never use feature flags for security controls.

## Related
a-b-testing-architecture, canary-deployment-architecture, multi-tenancy-architecture
