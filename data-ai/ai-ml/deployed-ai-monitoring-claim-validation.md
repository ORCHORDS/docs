# Deployed AI monitoring for claim validation

**Issue:** Pre-deployment evaluation claims remain unchanged while real users, inputs, integrations, and model behavior diverge.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Map each release claim to observable production indicators, affected populations, thresholds, review owner, and response. Monitor model/service version, input drift, output quality, refusals, tool calls, human overrides, incidents, latency/cost, and downstream outcomes with privacy minimization. Compare with pre-deployment distributions and retain rollback identity.

## Verification

Replay monitored failures in a safe evaluation set; inject telemetry gaps; test threshold alerts, human review, rollback, and model-provider silent-change detection.

## Gotchas

Monitoring methods are still nascent; NIST's March 2026 paper describes challenges rather than a universal standard. Proxy metrics can hide harm. Logging prompts may create privacy/security risk.

## Sources

- [NIST: Challenges to monitoring deployed AI systems](https://www.nist.gov/publications/challenges-monitoring-deployed-ai-systems-center-ai-standards-and-innovation)
- [NIST AI Resource Center](https://airc.nist.gov/)
