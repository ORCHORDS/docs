# Workers Gradual Traffic Rollout Using KV Percentage Flags

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to ship a risky feature to production without exposing all users at once. By storing a rollout percentage in Cloudflare KV and hashing each request's user-id into a stable bucket, you can gradually ramp traffic from 5% to 100% while monitoring error rates between steps and rolling back instantly by setting the percentage to 0.

---

## Context
Cloudflare Workers run at the edge with no shared memory between isolates, making traditional in-process feature flags impossible. KV provides a globally-replicated, low-latency store that all Worker instances can read. A consistent hash of the user-id ensures the same user always lands in the same bucket, giving a deterministic and repeatable split. The rollout key stores both `enabled` and `percentage` so the flag can be killed entirely without changing the percentage value.

---

## Section 1 — KV Namespace and Flag Schema

Create the namespace and write the initial flag:

```bash
# Create namespace
wrangler kv:namespace create "FEATURE_FLAGS"
# Note the returned id and preview_id

# Write initial flag (5% rollout, disabled)
wrangler kv:key put --namespace-id=<YOUR_NAMESPACE_ID> \
  'rollout:feature-x' \
  '{"percentage":5,"enabled":false}'

# Enable the flag at 5%
wrangler kv:key put --namespace-id=<YOUR_NAMESPACE_ID> \
  'rollout:feature-x' \
  '{"percentage":5,"enabled":true}'
```

Add the binding in `wrangler.toml`:

```toml
[[kv_namespaces]]
binding = "FEATURE_FLAGS"
id = "<YOUR_NAMESPACE_ID>"
preview_id = "<YOUR_PREVIEW_NAMESPACE_ID>"
```

---

## Section 2 — Implementation

```typescript
// src/rollout.ts
export interface RolloutFlag {
  percentage: number;
  enabled: boolean;
}

/**
 * Compute a stable bucket (0-99) for a given user-id using FNV-1a.
 * The same userId always maps to the same bucket, so the user experience
 * is consistent across requests.
 */
export function userBucket(userId: string): number {
  let hash = 2166136261;
  for (let i = 0; i < userId.length; i++) {
    hash ^= userId.charCodeAt(i);
    hash = (hash * 16777619) >>> 0; // keep 32-bit unsigned
  }
  return hash % 100;
}

export async function isFeatureEnabled(
  kv: KVNamespace,
  flagKey: string,
  userId: string
): Promise<boolean> {
  const raw = await kv.get(flagKey);
  if (!raw) return false;

  const flag: RolloutFlag = JSON.parse(raw);
  if (!flag.enabled) return false;

  const bucket = userBucket(userId);
  return bucket < flag.percentage;
}

// src/index.ts
export interface Env {
  FEATURE_FLAGS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = request.headers.get('x-user-id') ??
                   url.searchParams.get('uid') ??
                   crypto.randomUUID(); // anonymous fallback

    const useNewPath = await isFeatureEnabled(
      env.FEATURE_FLAGS,
      'rollout:feature-x',
      userId
    );

    if (useNewPath) {
      return newCodePath(request, env);
    }
    return legacyCodePath(request, env);
  },
};

async function newCodePath(request: Request, env: Env): Promise<Response> {
  // new implementation
  return new Response(JSON.stringify({ path: 'new', ok: true }), {
    headers: { 'content-type': 'application/json', 'x-rollout': 'new' },
  });
}

async function legacyCodePath(request: Request, env: Env): Promise<Response> {
  return new Response(JSON.stringify({ path: 'legacy', ok: true }), {
    headers: { 'content-type': 'application/json', 'x-rollout': 'legacy' },
  });
}
```

---

## Section 3 — Ramp Script and Monitoring

```bash
#!/usr/bin/env bash
# ramp.sh — progressively ramp feature-x rollout
set -euo pipefail

NAMESPACE_ID="<YOUR_NAMESPACE_ID>"
KEY="rollout:feature-x"
STEPS=(5 25 50 100)
MONITOR_SECONDS=120   # wait 2 min between steps

ramp_to() {
  local pct="$1"
  echo ">>> Ramping to ${pct}%"
  wrangler kv:key put --namespace-id="${NAMESPACE_ID}" \
    "${KEY}" "{\"percentage\":${pct},\"enabled\":true}"
  echo "    Flag updated. Sleeping ${MONITOR_SECONDS}s for monitoring..."
  sleep "${MONITOR_SECONDS}"
}

check_error_rate() {
  # Placeholder — replace with your observability query (Logpush / Analytics Engine)
  local rate
  rate=$(curl -sf 'https://metrics.internal/error-rate?worker=feature-x' | jq '.rate')
  echo "    Current error rate: ${rate}"
  if (( $(echo "${rate} > 0.01" | bc -l) )); then
    echo "ERROR: error rate ${rate} exceeds threshold. Rolling back."
    wrangler kv:key put --namespace-id="${NAMESPACE_ID}" \
      "${KEY}" '{"percentage":0,"enabled":false}'
    exit 1
  fi
}

for step in "${STEPS[@]}"; do
  ramp_to "${step}"
  check_error_rate
done

echo "Rollout complete at 100%."
```

```bash
# Rollback at any time
wrangler kv:key put --namespace-id=<YOUR_NAMESPACE_ID> \
  'rollout:feature-x' '{"percentage":0,"enabled":false}'
```

---

## Anti-patterns
- **Random bucketing per request** — Using `Math.random()` instead of a consistent hash means the same user sees different code paths on successive requests, breaking UX and making debugging impossible.
- **Storing the flag in Worker source code** — Hard-coded percentages require a full redeploy to change; KV lets you update instantly without touching code.
- **No monitoring gate between steps** — Jumping from 5% directly to 100% defeats the purpose of a gradual rollout; always instrument and check between ramp steps.
- **Omitting `enabled` boolean** — Relying solely on `percentage: 0` for rollback is error-prone; a separate `enabled` flag lets you kill the feature without losing the percentage setting.

---

## Gotchas
- KV reads have eventual consistency with ~60 s propagation globally; do not expect an instant 0% rollback across all edge nodes.
- `crypto.randomUUID()` fallback for anonymous users means unauthenticated traffic is randomly distributed and not stable across requests — accept this or require authentication before rollout.
- Namespace IDs differ between `[env.staging]` and `[env.production]` blocks; double-check bindings when promoting flags.
- FNV-1a produces a 32-bit unsigned value; `% 100` gives a slight bias for bucket values 0-95 vs 96-99 on a 2^32 space — negligible in practice but worth noting.

---

## Verification

```bash
# Read current flag state
wrangler kv:key get --namespace-id=<NAMESPACE_ID> 'rollout:feature-x'

# Smoke test: send 20 requests and count new-path responses
for i in $(seq 1 20); do
  curl -s -H 'x-user-id: user-'"$i" https://your-worker.workers.dev/ | jq -r '.path'
done | sort | uniq -c

# Confirm bucket for a known user (expect deterministic output)
node -e "
  const userId = 'user-42';
  let h = 2166136261;
  for (const c of userId) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }
  console.log('bucket:', h % 100);
"
```

---

## Related
- `wrangler-environments-secrets-promotion.md`
- `workers-deploy-on-git-tag-actions.md`

---

## Sources
- Cloudflare KV documentation — https://developers.cloudflare.com/kv/
- Cloudflare Workers runtime API — https://developers.cloudflare.com/workers/runtime-apis/
- FNV hash reference — https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
