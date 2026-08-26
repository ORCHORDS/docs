# Workers binding rotation and global-scope safety

**Issue:** A Worker caches a client or derived value created from a binding in global scope. A later deployment changes the binding or rotates a secret, but a reused isolate continues using the stale derivative.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Symptom

A credential rotation or binding-only deployment succeeds, yet a fraction of requests continue to authenticate with an older value, target an older resource, or behave differently until isolates happen to be replaced.

## Root cause

Workers may reuse running isolates across deployments that change only bindings. A global object derived from `env` is therefore not a safe cache boundary for binding-dependent credentials, clients, destinations, or policy. Importable environment access does not make top-level I/O safe.

**Sources:**

- [Cloudflare Workers bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/)
- [Cloudflare importable environment bindings](https://developers.cloudflare.com/changelog/post/2025-03-17-importable-env/)

## Fix

- construct binding-dependent clients, credentials, and derived policy inside the request path;
- keep global scope limited to immutable code, parsers, static configuration, and factories that do not capture a deployment binding;
- pass the current binding explicitly into helpers rather than closing over a global client;
- make rotation and binding-only changes first-class deployment scenarios with an owner, rollback, and observability window;
- where a request-scoped context is needed through asynchronous work, use the platform-supported request context rather than an ambient mutable global;
- fail closed when a required binding is absent, malformed, or does not match the expected resource identity.

## Verification

- **Rotation:** after a secret or binding change, requests accepted by a new deployment use only the current credential/resource.
- **Isolate reuse:** an integration test simulates or observes repeated requests across a binding-only change and detects stale derived state.
- **Scope:** no global variable stores a binding-derived client, token, endpoint, or mutable authorization decision.
- **Failure:** an unavailable or invalid binding produces a bounded error without falling back to an old credential.
- **Rollback:** restoring the previous binding produces the intended behavior without relying on process restart timing.

## Gotchas

- Global code caching is still useful for binding-independent work; do not eliminate it indiscriminately.
- Rotating a secret in an external provider and updating a Worker binding are separate operations; monitor both sides.
- Request-scoped construction does not remove the need for connection pooling or provider-side rate limits.
- Never log binding values, tokens, or connection strings while diagnosing a rotation.

## Related

- `cloudflare/secrets-store-binding-selection-and-blast-radius-control.md`
- `security/secrets-rotation-runbook-2026.md`
- `deploy/rollback-strategy.md`
- `patterns/configuration-management.md`
