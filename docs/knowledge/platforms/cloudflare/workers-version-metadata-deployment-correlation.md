# Workers Version Metadata Deployment Correlation

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** Documented

## Problem

Wall-clock deployment markers are weak evidence. Concurrent releases, gradual rollouts, cached assets, and delayed telemetry can make an error appear associated with the wrong code. Workers should attach the serving version identity to operational signals.

## Contract

Configure a version metadata binding and read its version ID, optional tag, and creation timestamp at runtime. Treat the version ID as the authoritative deployment dimension. A deployment selects one or more Worker versions; storage state in KV, R2, D1, and Durable Objects is not versioned with Worker code.

Example Wrangler configuration:

```json
{
  "version_metadata": {
    "binding": "CF_VERSION_METADATA"
  }
}
```

## Implementation controls

- Add the version ID to structured logs, traces, error events, and Analytics Engine records.
- Use a low-cardinality version dimension. Do not combine it with user identifiers in an index.
- Give release tags a documented format and never use mutable human labels as the sole join key.
- Record the version ID in smoke-test evidence and rollback decisions.
- During gradual deployments, compare error, latency, and asset-failure rates by version rather than by time window alone.
- Keep data and schema compatibility explicit because Worker version rollback does not restore associated storage.

## Verification

1. Deploy two tagged versions through a gradual deployment.
2. Send controlled requests to each version using an approved override or affinity mechanism.
3. Assert telemetry includes the actual serving version ID.
4. Verify dashboards can compare both versions without an unbounded label explosion.
5. Roll back and prove new requests report the restored version.
6. Exercise mixed code/storage compatibility before increasing traffic.

## Gotchas

- A version captures code, static assets, bindings, and compatibility settings, but not state changes in storage products.
- A creation timestamp is context, not a unique release identity.
- Do not expose internal version diagnostics in ordinary public responses unless the disclosure is intentionally reviewed.
- Version affinity can improve testing consistency, but it must not become an authorization control.

## Official sources

- [Version metadata binding](https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/)
- [Workers versions and deployments](https://developers.cloudflare.com/workers/versions-and-deployments/)
- [Version affinity](https://developers.cloudflare.com/workers/versions-and-deployments/gradual-deployments/version-affinity/)
