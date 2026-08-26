# Feature Flag Deployment Decoupling

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A feature ships directly to 100% of users when its PR
merges. A regression forces a full rollback that reverts
unrelated changes already in the same deploy, causing
collateral downtime and re-deployment churn.

## Context

Deploying code and releasing a feature are two separate
events. A feature flag keeps new code paths dark at deploy
time and lets the team light them up deliberately — for a
subset of users, a percentage of traffic, or a specific
environment. When something goes wrong, the flag is
toggled off in seconds without touching the deployed
Worker code. Cloudflare KV is the natural flag store in
Workers because it is globally consistent, low-latency
on read, and writable without a code deploy.

## Separating Deploy from Release

The four-step lifecycle every flag must follow:

```
Create (off by default)
  → Enable for internal / QA
     → Percentage rollout
        → 100 % → cleanup
```

In code, every flag evaluation must default to the known-
good (old) path when the flag is absent or the store is
unreachable:

```typescript
// workers/src/flags.ts
export async function isEnabled(
  flagKey: string,
  userId: string,
  env: Env,
): Promise<boolean> {
  try {
    const raw = await env.FLAGS.get(flagKey, "json");
    if (!raw) return false;           // default: off
    const flag = raw as FlagConfig;
    if (!flag.enabled) return false;
    return isInCohort(userId, flag.percentage ?? 100);
  } catch {
    return false;                     // fail safe
  }
}
```

## Percentage Rollout and A/B Testing

Store rollout config as a JSON value in KV:

```json
{
  "enabled": true,
  "percentage": 20,
  "variant": "B",
  "allowlist": ["user-id-123", "user-id-456"]
}
```

Bucket deterministically so the same user always gets the
same variant; never use `Math.random()` per request:

```typescript
// Deterministic bucket: hash(userId + flagKey) mod 100
function isInCohort(userId: string, pct: number): boolean {
  const hash = cyrb53(userId + ":new_checkout");
  return (hash % 100) < pct;
}
```

Write analytics events tagged with the variant name so
the experiment stays joinable in your metrics store.

## Cloudflare KV as a Flag Store

KV gives eventually-consistent global reads with ~1 ms
p99 latency after the first cache warm. Use it for flag
values that change infrequently (rollout percentage, on/
off state). Do not use KV for per-request user state.

Write a flag via the REST API (suitable for a CI job or
admin UI):

```bash
# Enable new-checkout for 20 % of users
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/<id>/\
storage/kv/namespaces/<ns-id>/values/new_checkout" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true,"percentage":20}'
```

Bind the namespace in `wrangler.toml`:

```toml
[[kv_namespaces]]
binding  = "FLAGS"
id       = "prod-flags-namespace-id"

[env.preview]
[[env.preview.kv_namespaces]]
binding  = "FLAGS"
id       = "preview-flags-namespace-id"
```

Cache the resolved value in a request-scoped `Map` to
avoid multiple KV round-trips for the same flag key.

## Flag Lifecycle and Preventing Flag Debt

| Phase       | Action                                    |
|-------------|-------------------------------------------|
| Create      | Add key to KV with `{"enabled":false}`    |
| Internal QA | Set allowlist to internal user IDs        |
| Rollout     | Increment percentage: 5 → 20 → 50 → 100  |
| Stable      | Open a cleanup ticket, set deadline       |
| Cleanup     | Remove flag code path; delete KV key      |

Rules to prevent accumulation of stale flags:
- Every flag PR must include the target cleanup sprint
  in the PR description.
- Flags older than 30 days at 100 % trigger an automated
  lint warning in CI.
- No more than 2 flag levels of nesting; nested flags
  create untestable combinatorial states.
- Ops/kill-switch flags (e.g. `payments_enabled`) are
  explicitly marked as permanent in their KV metadata
  and are exempt from the cleanup policy.

## Anti-patterns

- Defaulting a new flag to `true` — a missing key or KV
  failure then silently enables untested code.
- Evaluating flags at Worker startup and caching for the
  lifetime of the isolate — misses rollout changes for
  minutes or hours.
- Gating a database migration behind a flag — migrations
  are schema-level; flags are request-level. They operate
  at different layers and must not be coupled.
- Using `Math.random()` for bucketing — the same user
  bounces between variants on every request.

## Gotchas

- KV consistency is eventual. A flag set to 0 % may still
  return `true` on edges that have not yet received the
  invalidation. Build in a 60-second drain assumption.
- KV `get` counts toward billing. Cache aggressively at
  the request level; do not call KV per sub-operation.
- Deleting a KV key does not propagate instantly; code
  that treats a missing key as `true` will misbehave.
- Flag names in KV are case-sensitive. Standardise on
  snake_case and enforce it in the flag SDK layer.

## Verification

```bash
# Read current flag state from KV
wrangler kv key get new_checkout \
  --namespace-id prod-flags-namespace-id
# Expected: {"enabled":true,"percentage":20}

# Confirm the Worker reads the flag correctly
curl -s "https://myapp.workers.dev/api/debug/flags" \
  -H "x-internal-token: $INTERNAL_TOKEN"
# Expected: {"new_checkout":true,"variant":"B"}
```

## Related

- `deploy/feature-flag-lifecycle-management.md`
- `deploy/rollback-strategies-workers-pages.md`
- `deploy/cloudflare-pages-preview-deployments.md`
- `cloudflare/kv-patterns.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/kv/get-started/
- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/environment-variables/
