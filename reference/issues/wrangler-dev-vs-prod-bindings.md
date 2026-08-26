# wrangler-dev-vs-prod-bindings

**Issue:** `wrangler dev` uses local simulation for KV, D1, R2, and Durable Objects; behavior and data differ from production
**Date:** 2026-08-11
**Status:** documented

## Symptom
Code works in `wrangler dev` but fails in production (or vice versa). Data written during local development is not visible in the Cloudflare dashboard. A Durable Object's behavior differs between local and remote.

## Root cause
By default, `wrangler dev` uses a local miniflare simulation backed by SQLite files in `.wrangler/state/`. This local data is separate from the production namespace. Some features (e.g., D1 migrations, Durable Object alarms) behave slightly differently in simulation.

## Fix
Use `wrangler dev --remote` to connect to real production bindings during development (caution: writes affect prod data). For staging, create a separate set of bindings in `wrangler.toml` under an `[env.staging]` block:
```toml
[env.staging]
kv_namespaces = [{ binding = "KV", id = "staging-namespace-id" }]
```
Run with `wrangler dev --env staging`.

## Detection
Compare `wrangler.toml` binding IDs with the IDs shown in the Cloudflare dashboard. If local state exists at `.wrangler/state/`, development is running against simulation.

## Related
- `pages-build-env-vars-vs-runtime.md`
- `d1-env-type-incompatibility.md`
