# feature-flag-cloudflare-workers-kv

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A team deploys new features to production but needs to roll out to
a controlled percentage of users before full release. Third-party
flag services (LaunchDarkly, etc.) add 50–200 ms of latency per
request via a network call. Mobile apps on slow connections timeout
on feature flag fetches. Flag values must be evaluated at the edge
without an origin round-trip. Flags accumulate over time and dead
flags remain in code for months.

## Context

Workers KV is a globally replicated key-value store with read latency
under 1 ms when a value is cached at the colocated data center. It is
the correct primitive for a self-hosted feature flag system on
Cloudflare: flags are written infrequently (deployments, rollouts),
read on every request, and must be consistent within 60 s of a write.
Analytics Engine provides microsecond-latency event emission from
Workers for A/B tracking without an external analytics service.

## 1. Flag Schema Design

Store all flags as a single JSON blob in one KV key to minimize
reads (one read per request regardless of flag count). The value must
be parseable in under 1 ms.

```typescript
// KV key: "flags:v1"
// KV value (JSON):
interface FlagConfig {
  version: number;               // increment on every write
  flags: Record<string, Flag>;
}

interface Flag {
  enabled: boolean;              // master kill-switch
  rollout: number;               // 0.0–1.0 fraction of users
  variants?: Record<string, number>; // A/B variant weights
  platforms?: ("web" | "ios" | "android")[];  // mobile variants
  expiresAt?: string;            // ISO-8601; trigger cleanup CI
}

// Example flag config:
const exampleConfig: FlagConfig = {
  version: 42,
  flags: {
    "new-checkout": {
      enabled: true,
      rollout: 0.25,              // 25% of users
      platforms: ["web", "ios"],  // not yet on Android
      expiresAt: "2026-10-01T00:00:00Z",
    },
    "dark-mode-v2": {
      enabled: true,
      rollout: 1.0,               // fully rolled out
      variants: { control: 0.5, treatment: 0.5 },
      expiresAt: "2026-09-15T00:00:00Z",
    },
  },
};
```

## 2. Percentage Rollout by User Hash

Assign users deterministically to the rollout bucket using a fast
hash of the user ID. The same user always gets the same bucket;
no session state needed.

```typescript
// Deterministic hash: userId → float in [0, 1)
async function userBucket(userId: string, salt: string): Promise<number> {
  const input = new TextEncoder().encode(`${salt}:${userId}`);
  const hashBuf = await crypto.subtle.digest("SHA-256", input);
  // Use first 4 bytes as uint32, normalize to [0, 1)
  const view = new DataView(hashBuf);
  return view.getUint32(0) / 0xffffffff;
}

// Evaluate a single flag for a user
async function isFlagEnabled(
  flagName: string,
  userId: string,
  platform: "web" | "ios" | "android",
  flags: FlagConfig
): Promise<boolean> {
  const flag = flags.flags[flagName];
  if (!flag || !flag.enabled) return false;
  if (flag.platforms && !flag.platforms.includes(platform)) return false;

  const bucket = await userBucket(userId, flagName);
  return bucket < flag.rollout;
}
```

Using a per-flag salt means a user in the 25% bucket of flag A is
not deterministically in the bucket of flag B—independent rollouts.

## 3. A/B Variant Assignment with Analytics Engine

Assign a variant and record the exposure event in Cloudflare
Analytics Engine (zero-latency, non-blocking):

```typescript
async function getVariant(
  flagName: string,
  userId: string,
  flags: FlagConfig,
  env: Env
): Promise<string | null> {
  const flag = flags.flags[flagName];
  if (!flag?.enabled || !flag.variants) return null;

  const bucket = await userBucket(userId, `${flagName}:variant`);

  // Walk cumulative weights to pick variant
  let cumulative = 0;
  for (const [variant, weight] of Object.entries(flag.variants)) {
    cumulative += weight;
    if (bucket < cumulative) {
      // Emit exposure event — no await; fire-and-forget
      env.ANALYTICS.writeDataPoint({
        blobs: [flagName, variant, userId],
        indexes: [flagName],
        doubles: [1],
      });
      return variant;
    }
  }
  return null;
}
```

Analytics Engine schema (query via SQL API):

```sql
SELECT
  blob1   AS flag_name,
  blob2   AS variant,
  COUNT() AS exposures,
  SUM(double1) AS events
FROM analytics_events
WHERE timestamp > NOW() - INTERVAL '7' DAY
  AND blob1 = 'dark-mode-v2'
GROUP BY blob1, blob2
ORDER BY exposures DESC;
```

## 4. KV Read Pattern with Caching

Reads from the same data center are served from the KV cache layer
and take under 1 ms. Stale-while-revalidate with a short TTL ensures
freshness during rollouts without adding latency spikes.

```typescript
// Singleton cache within a Worker isolate (~30-second lifespan)
let cachedFlags: FlagConfig | null = null;
let cachedAt = 0;
const CACHE_MS = 10_000; // 10 s in-memory; KV propagation is ~60 s

async function getFlags(env: Env): Promise<FlagConfig> {
  const now = Date.now();
  if (cachedFlags && now - cachedAt < CACHE_MS) {
    return cachedFlags; // hot path: zero KV reads
  }
  const raw = await env.FLAGS_KV.get("flags:v1", { type: "json" });
  if (!raw) throw new Error("flags:v1 not found in KV");
  cachedFlags = raw as FlagConfig;
  cachedAt = now;
  return cachedFlags;
}
```

KV write (from a CI/CD pipeline or admin Worker):

```typescript
await env.FLAGS_KV.put(
  "flags:v1",
  JSON.stringify(nextConfig),
  { expirationTtl: 0 }  // never expire; managed by write operations
);
```

## 5. Mobile-Specific Flag Variants

Mobile apps have additional constraints: OS version, app version,
and network type. Extend the flag schema to support these:

```typescript
interface MobileFlag extends Flag {
  minAppVersion?: string;   // semver; "1.4.0"
  minOsVersion?: {
    ios?: string;           // "16.0"
    android?: string;       // "12"
  };
}
```

Evaluate mobile constraints in the Worker using request headers
set by the native SDK:

```typescript
// Native app sets: X-App-Version: 1.5.2, X-OS-Version: 17.0
function checkMobileEligibility(
  flag: MobileFlag,
  req: Request,
  platform: "ios" | "android"
): boolean {
  const appVer = req.headers.get("X-App-Version");
  const osVer = req.headers.get("X-OS-Version");

  if (flag.minAppVersion && appVer) {
    if (!semverGte(appVer, flag.minAppVersion)) return false;
  }
  if (flag.minOsVersion?.[platform] && osVer) {
    if (!semverGte(osVer, flag.minOsVersion[platform]!)) return false;
  }
  return true;
}
```

Send evaluated flag state to the client in a single response header
to avoid additional round-trips from the mobile app:

```
X-Feature-Flags: new-checkout=true,dark-mode-v2=treatment
```

## 6. Flag Cleanup Discipline

Stale flags accumulate technical debt and create confusion. Enforce
removal with a CI check on the `expiresAt` field:

```typescript
// scripts/check-expired-flags.ts (run in CI)
const config: FlagConfig = JSON.parse(
  fs.readFileSync("flags.json", "utf8")
);
const now = new Date();
const expired = Object.entries(config.flags).filter(
  ([, f]) => f.expiresAt && new Date(f.expiresAt) < now
);
if (expired.length > 0) {
  console.error("Expired flags must be removed before merging:");
  expired.forEach(([name]) => console.error(`  - ${name}`));
  process.exit(1);
}
```

Cleanup checklist per flag:

```
[ ] Flag removed from flags.json
[ ] Flag guard removed from all code paths
[ ] Analytics queries archived
[ ] Winning variant promoted to default behavior
[ ] PR description references original rollout issue
```

## Anti-Patterns

- **One KV key per flag** — multiplies KV reads per request; use a
  single JSON blob.
- **Awaiting Analytics Engine writes** — adds latency to every
  flagged request; always fire-and-forget.
- **Non-deterministic rollout** (Math.random()) — same user gets
  different experience on different requests; always hash-based.
- **Using CF Workers cache API for flags** — cache API is
  response-level, not key-level; KV in-memory caching is simpler.
- **Flags without expiresAt** — they never get cleaned up; mandate
  the field in code review.

## Gotchas

- KV propagation to all Cloudflare data centers takes up to 60 s.
  During an emergency rollback, users in remote regions may see the
  old flag state for up to a minute.
- `analytics.writeDataPoint` is rate-limited to 25 writes/sec per
  Worker invocation in the free tier; batch exposures if needed.
- `semver` parsing in a Worker requires a bundled library (no npm
  at runtime); keep it lightweight or use string comparison for
  simple `major.minor.patch` comparisons.
- The isolate-local cache (`cachedFlags`) is reset when Cloudflare
  recycles the isolate (typically every 30 s to a few minutes).
  This means reads are not perfectly batched; size KV quotas
  accordingly.
- Variant weights in the flag config must sum to 1.0 exactly;
  floating-point drift can cause edge cases where no variant is
  returned.

## Verification

```bash
# Write a flag to KV (dev namespace)
wrangler kv key put --namespace-id $DEV_NS_ID \
  "flags:v1" "$(cat flags.json)"

# Read it back
wrangler kv key get --namespace-id $DEV_NS_ID "flags:v1"

# Check rollout distribution (sample 1000 user IDs)
node scripts/simulate-rollout.ts --flag new-checkout --users 1000
# Expected output: ~250 ± 15 users get flag=true (25% rollout)

# Confirm Analytics Engine receives events
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/\
analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "SELECT blob1, blob2, COUNT() FROM analytics_events \
      WHERE blob1 = 'new-checkout' GROUP BY blob1, blob2"
```

## Related

- `documentation/categories/architecture/feature-flag-architecture.md`
- `documentation/categories/architecture/a-b-testing-architecture.md`
- `documentation/categories/architecture/rate-limiting-architecture-workers.md`
- `documentation/categories/architecture/canary-deployment-architecture.md`
- `documentation/categories/architecture/configuration-management.md`

## Source URLs

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
