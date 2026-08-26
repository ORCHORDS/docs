# api-security-architecture

**Issue:** APIs expose sensitive operations without sufficient authentication or authorization controls
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An internal admin API is accessible without authentication from the internal network, relying on network perimeter security alone.

## Pattern / Solution
Authenticate every request with short-lived tokens (JWT, API keys rotated regularly). Authorize at the operation level, not just the resource level. Validate and sanitize all inputs. Rate limit by identity. Log all access for audit. Apply HTTPS everywhere.

## Gotchas
JWTs are not revocable by default. Use short expiry and a revocation list for sensitive operations. CORS misconfiguration allows cross-origin credential theft. Input validation must happen server-side regardless of client-side validation.

## Related
oauth-architecture, zero-trust-architecture, rate-limiting-architecture
