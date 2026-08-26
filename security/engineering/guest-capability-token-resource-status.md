# guest-capability-token-resource-status

**Issue:** An anonymous status endpoint uses only a predictable resource identifier, enabling status enumeration or access to another user’s pending resource.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

A resource ID identifies an object; it is not necessarily authorization. Guest status access needs an unguessable capability token bound to the specific resource and lifecycle, with revocation/rotation and uniform externally visible failure behavior.

## Fix

- generate high-entropy capability tokens server-side and store only a suitable verifier;
- bind token, resource, purpose, expiry, and lifecycle state;
- require the token for anonymous reads and scoped actions;
- revoke or rotate on completion, cancellation, compromise, or ownership transfer;
- return the same public response for missing and invalid tokens where enumeration risk matters;
- rate-limit and audit denied attempts without logging raw tokens.

## Verification

- A resource ID without its capability token cannot reveal status.
- A token cannot access a different resource.
- Revoked and expired tokens fail.
- Valid tokens retain only the minimal intended permission.

## Related

- `security/oauth-dpop-sender-constrained-token-validation.md`
- `patterns/multi-tenant-data-isolation.md`
