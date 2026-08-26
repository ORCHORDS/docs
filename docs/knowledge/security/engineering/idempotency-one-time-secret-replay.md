# idempotency-one-time-secret-replay

**Issue:** A retry of a successful endpoint cannot safely replay a response that originally contained a one-time secret.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

An API creates a credential, recovery code, payment token, download URL, or other value intentionally shown once. The endpoint is made idempotent by caching a successful response, but the secret is not retained. A retry then receives a successful status with an empty or altered body and the client cannot tell whether the operation succeeded.

## Root cause

Idempotency replay assumes the original response is safe and meaningful to reproduce. One-time secrets violate that assumption: storing them expands the secret-retention surface, while omitting them makes a cached 2xx response ambiguous.

Idempotency protocol behavior must define a server-managed lifecycle and request outcome; it does not make sensitive response material safe to retain or replay.

**Source:** [IETF draft — Idempotency-Key HTTP Header Field](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-07).

## Fix

Classify endpoints before enabling response replay:

- exclude endpoints that mint one-time secret material from generic completed-response caching;
- retain a non-sensitive operation record: caller, request fingerprint, resource identifier, creation time, and terminal state;
- on a duplicate request, return a documented response that tells the client the original secret cannot be recovered and gives the correct recovery action;
- provide a separate, authenticated secret-rotation, regeneration, or recovery workflow when the product permits it;
- redact secret-bearing fields from logs, metrics, error reports, traces, and idempotency storage;
- test the endpoint contract with a real retry, not just a repeated unit-level handler call.

## Verification

- **First call:** the secret is delivered once over the intended authenticated channel and is absent from logs and persistence.
- **Replay:** a duplicate request never returns a blank successful response that clients can misinterpret.
- **Recovery:** the documented rotation or replacement path works without disclosing the original secret.
- **Access control:** no caller can use an idempotency key to learn whether another caller created a secret.

## Gotchas

- Hashing a secret may prove equality but does not make the original value replayable.
- Encrypting cached secrets is still a retention decision; it needs a threat model, key lifecycle, access controls, and deletion policy.
- A signed URL is often a one-time or time-bounded credential; apply the same analysis.

## Related

- `patterns/idempotency-reservation-lease-recovery.md`
- `security/secrets-rotation-runbook-2026.md` or the rotation section in this file
- `patterns/idempotency-keys.md`
