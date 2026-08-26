# zero-trust-architecture

**Issue:** Network perimeter security fails to protect against insider threats and lateral movement
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An attacker who gains access to the internal network can reach any service because east-west traffic is not authenticated.

## Pattern / Solution
Authenticate and authorize every request regardless of network origin. Verify device posture and user identity continuously. Use mutual TLS between services. Apply least-privilege access to every service account. Log all access and alert on anomalies.

## Gotchas
Zero trust increases operational complexity. Certificate management at scale requires automation. Legacy services that cannot do mTLS need proxied sidecar solutions.

## Related
api-security-architecture, service-mesh-patterns, secret-management-architecture
