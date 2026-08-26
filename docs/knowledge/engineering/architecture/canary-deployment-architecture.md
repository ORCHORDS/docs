# canary-deployment-architecture

**Issue:** Full deployments expose all users to regressions simultaneously
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A bad deploy takes down the entire user base before the on-call engineer can respond.

## Pattern / Solution
Route a small percentage of traffic (1-5%) to the new version. Monitor error rates and latency against the stable version. Automatically roll back if metrics breach thresholds. Gradually increase traffic as confidence grows.

## Gotchas
Canary and stable versions must be compatible with the same database schema. Sticky sessions ensure the same user is not bounced between versions mid-session.

## Related
blue-green-architecture, feature-flag-architecture, observability-architecture
