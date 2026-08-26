# blue-green-architecture

**Issue:** Deployments require downtime or risky in-place upgrades
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An in-place deploy fails midway, leaving the application in a broken state that requires a manual rollback.

## Pattern / Solution
Maintain two identical production environments (blue and green). Deploy to the inactive environment. Run smoke tests. Switch traffic at the load balancer. Keep the old environment warm for fast rollback.

## Gotchas
Database migrations must be backward compatible because both environments share the database during cutover. Costs roughly double during the transition window.

## Related
canary-deployment-architecture, feature-flag-architecture, disaster-recovery-architecture
