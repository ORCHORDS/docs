# Feature Flag Deployment Gates with Cloudflare KV

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

You want to decouple the *deployment* of new code from its *activation* — releasing a feature to 0% of traffic at deploy time and then gradually opening it to users via a flag, without redeploying. You also want deployment itself to be gated on flag configuration being present and valid before any traffic is served by the new Worker version. Cloudflare KV is the natural backing store for this in the Workers ecosystem: globally consistent reads in <5 ms at the edge, writable via the REST API or Wrangler CLI during the deploy pipeline.

The specific patterns here address:
- Blocking Worker activation until a required flag key exists in KV
- Using KV as a live dial for percentage-based rollout during canary phases
- Automated flag cleanup as part of the deployment lifecycle
- Flag schema versioning to prevent stale readers from misinterpreting a changed flag structure

---

## Context

Existing articles in this knowledge base cover feature flag *decoupling* (code ships dark, flag enables it) and flag *lifecycle* (creation, rollout, removal). This article focuses on the KV-specific mechanics of using flags as **deployment gates** — checks wired into the deploy pipeline and into request routing, not just business logic.

KV characteristics relevant to this use-case:

- **Eventual consistency**: KV writes replicate to all edges within ~60 seconds in typical conditions (the SLA guarantees propagation within 60 seconds for paid plans). A flag written at deploy time may not be readable at all edges for up to 60 seconds. Design gates to account for this lag.
- **Read performance**: KV reads from a Worker binding are served from local edge cache with no external network hop after the first read; typical p50 read latency is 0–1 ms. Appropriate for per-request flag checks on the critical path.
- **Write rate limit**: KV has a write rate limit of 1 write/second per key. Flag updates that need higher write frequency should batch updates or use a Durable Object for coordination.
- **Value size limit**: 25 MiB per value. Flag configuration objects are typically <1 KB; this limit is not a practical constraint.

---

## Flag Schema

A consistent, versioned flag schema prevents silent mismatches when the flag structure evolves between Worker versions.

```typescript
// shared/flag-schema.ts
export interface FeatureFlag {
  /** Schema version — increment when the shape changes */
  v: number;
  /** Global kill switch — false means the flag is off for everyone */
  enabled: boolean;
  /** Percentage of requests to include, 0–100 */
  rollout_pct: number;
  /** Allowlist of user IDs or account IDs always in the flag */
  allowlist: string[];
  /** Blocklist of user IDs always excluded */
  blocklist: string[];
  /** ISO timestamp — for audit and automated expiry */
  updated_at: string;
  /** Human-readable description of the flag's purpose */
  description: string;
}

export const FLAG_SCHEMA_VERSION = 2;

export function parseFlag(raw: string | null): FeatureFlag | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as FeatureFlag;
    if (parsed.v !== FLAG_SCHEMA_VERSION) {
      console.warn(`Flag schema version mismatch: expected ${FLAG_SCHEMA_VERSION}, got ${parsed.v}`);
      return null;  // treat unknown schema as flag-off
    }
    return parsed;
  } catch {
    return null;
  }
}
```

---

## Deployment Gate — Pre-Deploy KV Validation

Before activating a new Worker version in CI, validate that all required flags exist in KV with the expected schema version. This prevents a Worker that reads a new flag from activating when the flag key hasn't been created yet.

```bash
#!/usr/bin/env bash
# scripts/validate-flags-kv.sh
# Usage: ./scripts/validate-flags-kv.sh <kv-namespace-id> <env>

set -euo pipefail

KV_NS_ID="${1:?KV namespace ID required}"
ENV="${2:-production}"
REQUIRED_FLAGS_FILE="config/required-flags.json"
SCHEMA_VERSION=2

echo "Validating required feature flags in KV (env: $ENV)..."

REQUIRED_FLAGS=$(jq -r '.[]' "$REQUIRED_FLAGS_FILE")
FAILED=0

while IFS= read -r FLAG_KEY; do
  RAW=$(wrangler kv key get "$FLAG_KEY" \
    --namespace-id "$KV_NS_ID" \
    --env "$ENV" 2>/dev/null || echo "")

  if [ -z "$RAW" ]; then
    echo "  MISSING: $FLAG_KEY — flag key does not exist in KV"
    FAILED=$((FAILED + 1))
    continue
  fi

  # Validate schema version
  GOT_VERSION=$(echo "$RAW" | jq -r '.v // 0')
  if [ "$GOT_VERSION" != "$SCHEMA_VERSION" ]; then
    echo "  SCHEMA MISMATCH: $FLAG_KEY — expected v$SCHEMA_VERSION, got v$GOT_VERSION"
    FAILED=$((FAILED + 1))
    continue
  fi

  ENABLED=$(echo "$RAW" | jq -r '.enabled')
  ROLLOUT=$(echo "$RAW" | jq -r '.rollout_pct')
  echo "  OK: $FLAG_KEY (enabled=$ENABLED, rollout=${ROLLOUT}%)"
done <<< "$REQUIRED_FLAGS"

if [ "$FAILED" -gt 0 ]; then
  echo ""
  echo "GATE BLOCKED: $FAILED flag(s) missing or invalid. Create them before deploying:"
  echo "  wrangler kv key put \"<flag-key>\" '{\"v\":2,\"enabled\":false,\"rollout_pct\":0,...}' \\"
  echo "    --namespace-id $KV_NS_ID --env $ENV"
  exit 1
fi

echo "All required flags validated. Proceeding with deployment."
```

```json
// config/required-flags.json
[
  "feature/checkout-v2",
  "feature/ai-recommendations",
  "ops/maintenance-mode"
]
```

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Validate feature flags in KV
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  run: ./scripts/validate-flags-kv.sh ${{ vars.KV_FLAGS_NAMESPACE_ID }} production
```

---

## Runtime Flag Evaluation in the Worker

The Worker reads the flag from KV on each request. Keep the read on the critical path but outside the business logic — use a lightweight helper that fails safe to `enabled: false`.

```typescript
// src/flags.ts
import { parseFlag, type FeatureFlag } from "../shared/flag-schema";

export interface FlagEnv {
  FLAGS: KVNamespace;
}

/** Read a flag from KV. Returns null (= disabled) if missing or schema mismatch. */
export async function getFlag(
  env: FlagEnv,
  flagKey: string,
): Promise<FeatureFlag | null> {
  const raw = await env.FLAGS.get(flagKey);
  return parseFlag(raw);
}

/**
 * Evaluate whether the flag is active for a given request context.
 * Uses a stable hash of the user ID for consistent bucketing.
 */
export function isFlagActive(
  flag: FeatureFlag | null,
  userId: string,
): boolean {
  if (!flag || !flag.enabled) return false;
  if (flag.blocklist.includes(userId)) return false;
  if (flag.allowlist.includes(userId)) return true;
  if (flag.rollout_pct >= 100) return true;
  if (flag.rollout_pct <= 0) return false;

  // Deterministic bucketing: user always gets the same result for a given flag
  const bucket = stableHash(`${flagKey}:${userId}`) % 100;
  return bucket < flag.rollout_pct;
}

function stableHash(input: string): number {
  // FNV-1a 32-bit
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0;
  }
  return hash;
}
```

```typescript
// src/index.ts — using the flag in request handling
import { getFlag, isFlagActive } from "./flags";

export default {
  async fetch(request: Request, env: Env & FlagEnv): Promise<Response> {
    const userId = request.headers.get("X-User-ID") ?? "anonymous";

    const checkoutFlag = await getFlag(env, "feature/checkout-v2");
    if (isFlagActive(checkoutFlag, userId)) {
      return handleCheckoutV2(request, env);
    }
    return handleCheckoutV1(request, env);
  },
};
```

---

## KV as a Deployment Gate: Maintenance Mode Flag

Use a KV flag as a live circuit-breaker that puts the Worker into maintenance mode without redeployment.

```typescript
// src/maintenance-gate.ts
export async function checkMaintenanceMode(env: FlagEnv): Promise<boolean> {
  const raw = await env.FLAGS.get("ops/maintenance-mode");
  if (!raw) return false;
  try {
    const flag = JSON.parse(raw) as { enabled: boolean; message?: string };
    return flag.enabled === true;
  } catch {
    return false;
  }
}

// In the main fetch handler:
export default {
  async fetch(request: Request, env: Env & FlagEnv): Promise<Response> {
    if (await checkMaintenanceMode(env)) {
      return new Response(
        JSON.stringify({ error: "Service temporarily unavailable", maintenance: true }),
        { status: 503, headers: { "Content-Type": "application/json", "Retry-After": "300" } },
      );
    }
    return handleRequest(request, env);
  },
};
```

Enable maintenance mode without deploying:

```bash
# Enable maintenance mode instantly (propagates to all edges within ~60s)
wrangler kv key put "ops/maintenance-mode" \
  '{"v":2,"enabled":true,"message":"Scheduled maintenance in progress"}' \
  --namespace-id "$KV_FLAGS_NS_ID" --env production

# Disable after maintenance
wrangler kv key put "ops/maintenance-mode" \
  '{"v":2,"enabled":false,"message":""}' \
  --namespace-id "$KV_FLAGS_NS_ID" --env production
```

---

## Flag Lifecycle Automation: Post-Deploy Cleanup Gate

After a feature reaches 100% rollout and the old code path is removed, delete the flag from KV. Automate this as a CI step triggered by a commit that removes the flag reference from code.

```bash
#!/usr/bin/env bash
# scripts/cleanup-stale-flags.sh
# Removes KV flag keys that are no longer referenced in the codebase

set -euo pipefail

KV_NS_ID="${1:?}"
ENV="${2:-production}"

# Find all flag keys referenced in source code
REFERENCED=$(grep -roh '"feature/[a-z0-9-]\+"' src/ \
  | tr -d '"' | sort -u)

# List all flag keys in KV
ALL_KEYS=$(wrangler kv key list --namespace-id "$KV_NS_ID" --env "$ENV" \
  | jq -r '.[] | select(.name | startswith("feature/")) | .name')

# Delete keys not referenced in code
while IFS= read -r KEY; do
  if ! echo "$REFERENCED" | grep -qx "$KEY"; then
    echo "Deleting stale flag: $KEY"
    wrangler kv key delete "$KEY" --namespace-id "$KV_NS_ID" --env "$ENV"
  fi
done <<< "$ALL_KEYS"

echo "Flag cleanup complete."
```

---

## Anti-patterns

- **Reading KV on every request for high-frequency flags without local caching**: KV reads from Workers are fast but still incur a network call to the local Cloudflare data store. For flags that change rarely, cache in a `Map` per Worker instance or use the Cache API with a short TTL to reduce KV read volume.
- **Writing new flag values during a deploy and immediately evaluating them**: KV eventual consistency means a Worker instance may still see the old flag value for up to 60 seconds after a write. Do not assume flag values are instantaneous; design rollout increments that tolerate a 60-second propagation window.
- **Storing flag state in the Worker's global scope**: `const flags = {}` in module scope persists across requests in the same Worker instance but is invisible to other instances and is reset on Worker restarts. Use KV for durable flag state.
- **Encoding sensitive business logic in the flag key name**: KV key names are visible in Wrangler output and CI logs. Use opaque keys or prefixes for sensitive rollouts (e.g. `feature/proj-42` rather than `feature/gdpr-bypass`).
- **Permitting flag writes from the Worker itself on user requests**: flag writes must flow through trusted paths (CI pipeline, internal admin Worker with auth). A user-visible endpoint that writes to the FLAGS KV namespace is a privilege escalation vector.

---

## Gotchas

- KV `list()` returns a maximum of 1000 keys per call. If you have more than 1000 flags, paginate using the `cursor` returned in `list()` results.
- Flag keys deleted from KV are not recoverable. Soft-delete pattern: set `"enabled": false` rather than deleting the key until confirmed the code path is gone from all active Worker versions.
- The `waitUntil(env.FLAGS.get(...))` pattern does not work for gating the *current* response — `waitUntil` is for fire-and-forget after the response is sent. Always `await` flag reads that affect the response.
- Wrangler KV commands in CI require `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` environment variables, not a `wrangler.toml` auth block (which is per-developer). Use repository secrets for CI.
- KV namespace IDs differ between environments (`preview` vs `production` in `wrangler.toml`). Validate flags in the same namespace that the deployed Worker will actually read from.

---

## Verification

```bash
# Read a flag and confirm schema version
wrangler kv key get "feature/checkout-v2" \
  --namespace-id "$KV_FLAGS_NS_ID" --env production | jq '{v,enabled,rollout_pct}'

# Force-read from KV in a live Worker (bypasses any instance-level cache)
curl -H "X-Debug-Flag-Bypass-Cache: 1" \
  "https://api.example.workers.dev/debug/flag/feature/checkout-v2"

# Confirm the pre-deploy validation script catches a missing flag
echo '["feature/checkout-v2","feature/does-not-exist"]' > /tmp/test-flags.json
./scripts/validate-flags-kv.sh "$KV_FLAGS_NS_ID" staging
# Expected: GATE BLOCKED: 1 flag(s) missing or invalid
```

---

## Related

- `feature-flag-deploy-coupling.md`
- `feature-flag-deployment-decoupling.md`
- `feature-flag-lifecycle-management.md`
- `feature-rollout-strategies.md`
- `env-binding-precedence.md`
- `canary-workers-gradual-traffic-split.md`

---

## Sources

- Cloudflare KV documentation — consistency model, limits, Workers binding (developers.cloudflare.com/kv)
- Cloudflare Workers — KV API reference (developers.cloudflare.com/workers/runtime-apis/kv)
- "Effective Feature Flags" — Martin Fowler (martinfowler.com/articles/feature-toggles.html)
- Cloudflare blog — "Using Cloudflare Workers KV for feature flags" (blog.cloudflare.com)
- Google SRE Workbook — Chapter on Feature Flags and Experiment Infrastructure
