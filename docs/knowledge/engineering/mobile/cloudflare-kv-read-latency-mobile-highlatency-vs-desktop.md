# Cloudflare KV Read Latency Disparity: Mobile High-Latency Networks vs Desktop Broadband

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project session tokens, rate-limit counters, and feature flags are stored in Cloudflare KV.
On desktop broadband, KV reads inside a Worker complete in 5–15 ms and add negligible latency
to API responses. On mobile networks — particularly users on 3G, satellite, or high-latency
LTE — the total API response time is 800 ms–2 s even though the Worker CPU time is under 5 ms.
The KV reads themselves are not slow, but the mobile TCP round-trip cost to the Cloudflare
edge compounds with KV's eventual-consistency propagation window to produce stale reads that
look correct but contain outdated data (e.g., a revoked session token that still validates for
up to 60 seconds after revocation).

## Context

Cloudflare KV is a globally replicated, eventually consistent key-value store. Writes propagate
from the origin data center to all edge PoPs within **60 seconds** (published SLA; in practice
often 10–30 s, but worst-case is 60 s). Reads from a Worker are served from the *local* edge
PoP's in-memory cache — they are fast. But:

1. **The mobile client's TCP connection lands on the nearest Cloudflare PoP** (determined by
   anycast routing). For a user in a city well-served by Cloudflare, this is 5–20 ms. For a
   user on a rural LTE tower routed through a thin PoP, the anycast may route to a PoP 200 ms
   away — effectively doubling the KV TTL window by the time the stale value reaches them.

2. **KV cache TTL per PoP is independent of the HTTP response cache.** The edge PoP caches
   KV values locally for up to 60 s. A write to the KV namespace (e.g., token revocation) does
   not invalidate the PoP cache — it simply propagates a new value which the PoP adopts after
   its local TTL expires. Mobile users hitting a PoP that last synced 55 s ago may receive a
   60-second window of stale reads *on top of* their existing network latency.

3. **Mobile networks add latency non-uniformly.** Desktop broadband RTT to a major Cloudflare
   PoP is typically 5–30 ms. Mobile networks add:
   - LTE: 30–80 ms baseline + 50–200 ms variation during handoffs
   - 3G: 100–300 ms baseline
   - Network switching (Wi-Fi → cellular): 500 ms–2 s stall while the OS re-establishes TCP

4. **React Native's networking module does not reuse TCP connections** across component
   unmount/remount cycles unless the `keepalive` option is set. Each feed refresh may open a
   new TCP connection, adding a full TLS handshake (200–400 ms on mobile) to every KV-backed
   API call.

## Section 1 — KV Access Patterns and Latency Contribution

```typescript
// workers/middleware/auth.ts — naïve pattern (high latency on mobile)
export async function validateSession(
  request: Request,
  env: Env
): Promise<{ userId: string } | null> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) return null;

  // KV read: ~5 ms at edge, but stale for up to 60 s after revocation
  const session = await env.SESSIONS.get(token, { type: 'json' });
  return session as { userId: string } | null;
}
```

```typescript
// workers/middleware/auth.ts — mobile-aware pattern
export async function validateSession(
  request: Request,
  env: Env
): Promise<{ userId: string } | null> {
  const token = request.headers.get('Authorization')?.replace('Bearer ', '');
  if (!token) return null;

  // Use cacheTtl to control PoP-level caching explicitly
  // For session validation, 30 s max stale window is acceptable for non-critical actions
  // For sensitive actions (delete, post), use cacheTtl: 0 to force a fresh read from central KV
  const isSensitiveAction = isSensitive(request);
  const session = await env.SESSIONS.get(token, {
    type: 'json',
    cacheTtl: isSensitiveAction ? 0 : 30, // 0 = bypass PoP cache, go to central KV
  });

  return session as { userId: string } | null;
}

function isSensitive(request: Request): boolean {
  const { pathname, method } = new URL(request.url);
  return method !== 'GET' || pathname.startsWith('/api/admin');
}
```

**Note**: `cacheTtl: 0` forces a read from the central KV store, adding ~20–50 ms of latency
from the edge PoP. For mobile this is worth it on sensitive operations. For reads of stable
data (feature flags, config), use `cacheTtl: 300` to keep the PoP cache warm.

## Section 2 — Feature Flags and Stale Reads on Mobile

```typescript
// workers/feature-flags.ts
const FLAG_CACHE_TTL_SECONDS = {
  desktop: 60,   // Desktop can tolerate 60 s stale flags
  mobile: 300,   // Mobile: keep flags in PoP cache longer to save round trips
  // Rationale: feature flags change rarely; the cost of a stale flag read is low.
  // The cost of an extra KV round-trip on 3G is a 300 ms user-visible stall.
};

export async function getFeatureFlag(
  env: Env,
  flagName: string,
  request: Request
): Promise<boolean> {
  const deviceType = request.headers.get('cf-device-type') ?? 'desktop';
  const ttl = FLAG_CACHE_TTL_SECONDS[deviceType as keyof typeof FLAG_CACHE_TTL_SECONDS]
    ?? FLAG_CACHE_TTL_SECONDS.desktop;

  const value = await env.FEATURE_FLAGS.get(flagName, { cacheTtl: ttl });
  return value === 'true';
}
```

## Section 3 — Rate Limiting KV on Mobile: Precision vs Latency

KV-based rate limiting works by incrementing a counter per user per time window. On mobile,
the combination of KV propagation lag and mobile network latency creates a window where bursts
are under-counted:

```
Timeline for a mobile user on 3G:
T=0ms    Request 1 arrives at PoP-A. KV counter = 0. Write counter = 1.
T=150ms  Request 1 response sent.
T=300ms  Request 2 arrives (same user, different TCP, re-routed to PoP-B).
         PoP-B has not yet received the KV write from PoP-A (propagation < 10 s).
         KV counter at PoP-B = 0. Write counter = 1 again.
         User has now made 2 requests but counter shows 1 at both PoPs.
```

For example project's 21+ anonymous platform, the rate limit on post creation (5 posts/hour) can be
bypassed 2–3× by a mobile user with poor connectivity if relying purely on KV counters.

**Mitigation**: Use Durable Objects for precise rate limiting when accuracy matters, with KV
as a cheap fast-path pre-check:

```typescript
// workers/rate-limit.ts
export async function checkRateLimit(
  request: Request,
  env: Env,
  userId: string
): Promise<{ allowed: boolean; remaining: number }> {
  // Fast path: KV pre-check (may be stale by up to 60 s)
  const kvCount = await env.RATE_LIMITS.get(`rl:${userId}:posts`, { cacheTtl: 10 });
  const estimatedCount = kvCount ? parseInt(kvCount, 10) : 0;

  if (estimatedCount >= 10) {
    // Clearly over limit even with stale data — fast reject, save a DO round-trip
    return { allowed: false, remaining: 0 };
  }

  // Accurate path: Durable Object for precise counting
  const doId = env.RATE_LIMITER.idFromName(`user:${userId}`);
  const stub = env.RATE_LIMITER.get(doId);
  const result = await stub.fetch(new Request('https://fake/check', { method: 'POST' }));
  return result.json();
}
```

## Section 4 — React Native: Connection Reuse and Keep-Alive

Every unnecessary TLS handshake on mobile is 200–400 ms of user-visible latency. Configure
the React Native fetch layer to maintain persistent connections:

```typescript
// src/api/client.ts — React Native HTTP client with connection pooling
import { Platform } from 'react-native';

// On Android, OkHttp maintains a connection pool automatically when using RN's fetch.
// On iOS, NSURLSession reuses connections within the same session object.
// The key is to NOT create new fetch clients per component — use a shared singleton.

class ApiClient {
  private baseUrl = 'https://api.example.com';
  private defaultHeaders: HeadersInit;

  constructor() {
    this.defaultHeaders = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-Client-Platform': Platform.OS,
      'X-Client-Version': '1.0.0',
    };
  }

  async get<T>(path: string, token?: string): Promise<T> {
    const headers: HeadersInit = { ...this.defaultHeaders };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`${this.baseUrl}${path}`, {
      method: 'GET',
      headers,
      // keepalive: true — maintain the TCP connection after this request
      // This prevents a new TLS handshake on the next request from the same client
      keepalive: true,
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json() as Promise<T>;
  }
}

// Singleton — shared across all components so the connection pool is reused
export const apiClient = new ApiClient();
```

```typescript
// Android-specific: configure OkHttp keep-alive via Expo config plugin (app.config.js)
// This ensures the connection pool is configured at the native layer
export default {
  plugins: [
    [
      'expo-build-properties',
      {
        android: {
          // OkHttp default keep-alive is 5 connections / 5 minutes — adequate for example project
          // No custom config needed; just avoid creating multiple fetch client instances
        },
      },
    ],
  ],
};
```

## Anti-patterns

- **Using `cacheTtl: 0` for all KV reads**: This bypasses the PoP cache on every read, adding
  20–50 ms of intra-Cloudflare latency per KV call. On mobile, this is perceptible. Use
  `cacheTtl: 0` only for security-critical reads (token revocation, bans).
- **Reading KV inside a per-request middleware without batching**: If a single Worker handler
  makes 5 sequential KV reads, and each adds 5–20 ms, the total is 25–100 ms of pure KV
  overhead — fine on desktop (adds to a 50 ms response) but doubles the perceived response
  time on mobile (adds to a 300 ms response).
- **Assuming KV write propagation is instantaneous**: After `env.KV.put(key, value)`, other
  Workers in other PoPs see the old value for up to 60 s. Do not use KV for coordination
  where consistency within 1 s matters (use Durable Objects or D1 instead).
- **Creating a new React Native fetch instance per component**: This defeats connection pooling
  at the OkHttp / NSURLSession layer and adds a TLS handshake to every request.
- **Storing large values in KV for mobile clients**: KV has a 25 MB value limit. Reading a
  500 KB value from KV and serialising it through the Worker into a mobile response is far
  slower than reading from R2 (which supports streaming). Use KV for metadata, not bulk data.

## Gotchas

- **`cacheTtl` minimum is 60 seconds for most KV namespaces.** A `cacheTtl: 30` call is
  silently rounded up to 60 s. Only namespaces created with `--expire-ttl` or accessed via
  the `cacheTtl` parameter on accounts with Workers Paid plan honour sub-60 s TTLs. Verify
  your effective TTL in the Workers Analytics dashboard under KV Reads.
- **KV latency from `wrangler dev` is not representative of production.** Local dev uses a
  real KV namespace over the internet — reads are 50–200 ms, far higher than edge reads.
  Always measure production KV latency using Workers Analytics, not local dev timings.
- **Mobile users roaming internationally may hit distant PoPs.** A US-based example project user
  on an international carrier may anycast-route to a European PoP with a 120 ms base RTT.
  KV values written from the primary US region may not have propagated to that PoP yet.
- **KV write-after-read within the same Worker invocation is NOT consistent.** Writing a KV
  key and then reading it in the same handler may still return the old value if the Worker is
  in a PoP that has a cached copy.

## Verification

```bash
# Measure KV read contribution to response time via CF-Ray trace
curl -sI https://api.example.com/feed \
  -H 'Authorization: Bearer test-token' | grep -i 'cf-ray\|server-timing'

# Use Workers Analytics to view KV read latency percentiles
# Dashboard: Workers & Pages → your-worker → Analytics → KV Operations
# Check p99 read latency — should be < 20 ms at well-served PoPs

# Test from a high-latency context using a slow-network proxy
# (Use wrangler dev with --remote to hit real KV from a throttled connection)
wrangler dev --remote --port 8787 &
curl --limit-rate 50k http://localhost:8787/feed  # Simulate 400 kbps mobile
```

## Related

- `cloudflare-workers-response-streaming-mobile-buffer-limits.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `mobile-network-switching-mid-request.md`
- `carrier-cgnat-shared-ip-rate-limiting.md`
- `offline-first-worker-api-resilience.md`

## Sources

- Cloudflare KV docs: "How KV Works" — consistency guarantees and propagation windows
- Cloudflare Workers docs: KV `get` options, `cacheTtl` behaviour
- Cloudflare Community: "KV eventual consistency: what's the actual propagation time?"
- Cloudflare Blog: "Durable Objects: Now Generally Available" (rate limiting use case)
- React Native docs: Networking — `fetch` and connection behaviour
- OkHttp docs: Connection pooling and keep-alive configuration
