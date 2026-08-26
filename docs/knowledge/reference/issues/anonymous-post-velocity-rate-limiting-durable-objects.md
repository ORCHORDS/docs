# Anonymous Post Velocity Rate Limiting Durable Objects

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

An anonymous session floods the platform with posts — either a human spam campaign or an automated bot. Because example project has no persistent identity, traditional per-user rate limiting is insufficient. Rate limits must be applied per session token, per device fingerprint, and per IP subnet simultaneously, with limits that reset on a sliding window rather than a fixed clock boundary.

## Context

Durable Objects (DOs) are the right tool because they provide single-threaded, strongly consistent state co-located with the rate-limit logic. Each DO instance owns one "bucket" (session, device, or /24 subnet). Workers route incoming post requests to the appropriate DO, which increments a counter and returns allow/deny. Limits are configurable per bucket type and can be tightened globally via a KV config key.

---

## Durable Object — Sliding Window Counter

```typescript
// rate-limiter.do.ts
export class PostRateLimiter implements DurableObject {
  private storage: DurableObjectStorage;
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    const { limit, windowMs } = await request.json<{
      limit: number;
      windowMs: number;
    }>();

    const now = Date.now();
    const windowStart = now - windowMs;

    // Retrieve timestamps of past requests within window
    const raw = await this.storage.get<number[]>('timestamps') ?? [];
    const inWindow = raw.filter(t => t > windowStart);

    if (inWindow.length >= limit) {
      const retryAfter = Math.ceil((inWindow[0] + windowMs - now) / 1000);
      return Response.json(
        { allowed: false, retryAfter },
        { status: 429 },
      );
    }

    inWindow.push(now);
    await this.storage.put('timestamps', inWindow);

    // Alarm to clean up stale state after the window expires
    const alarmTime = await this.storage.getAlarm();
    if (!alarmTime) {
      await this.storage.setAlarm(now + windowMs + 1000);
    }

    return Response.json({ allowed: true, remaining: limit - inWindow.length });
  }

  async alarm(): Promise<void> {
    // Evict timestamps older than the longest possible window (1 h)
    const raw = await this.storage.get<number[]>('timestamps') ?? [];
    const cutoff = Date.now() - 60 * 60 * 1000;
    const pruned = raw.filter(t => t > cutoff);
    if (pruned.length > 0) {
      await this.storage.put('timestamps', pruned);
      await this.storage.setAlarm(Date.now() + 60 * 60 * 1000);
    } else {
      await this.storage.deleteAll(); // evict DO when idle
    }
  }
}
```

## Worker Router — Multi-Bucket Check

A post is checked against three buckets in parallel. Any deny aborts the post.

```typescript
interface RateConfig {
  session: { limit: number; windowMs: number };
  device:  { limit: number; windowMs: number };
  subnet:  { limit: number; windowMs: number };
}

const DEFAULT_CONFIG: RateConfig = {
  session: { limit: 10,  windowMs: 60_000 },      // 10 posts/min per session
  device:  { limit: 20,  windowMs: 60_000 },      // 20 posts/min per device
  subnet:  { limit: 50,  windowMs: 60_000 },      // 50 posts/min per /24
};

function ipToSubnet(ip: string): string {
  const parts = ip.split('.');
  return parts.slice(0, 3).join('.');
}

async function checkRateLimits(
  env: { RATE_LIMITER: DurableObjectNamespace; KV: KVNamespace },
  sessionToken: string,
  deviceFingerprint: string,
  ip: string,
): Promise<{ allowed: boolean; retryAfter?: number }> {
  // Allow KV override of limits for platform-wide tightening
  const configRaw = await env.KV.get('rate_config:post');
  const config: RateConfig = configRaw ? JSON.parse(configRaw) : DEFAULT_CONFIG;

  const subnet = ipToSubnet(ip);
  const buckets = [
    { key: `session:${sessionToken}`, cfg: config.session },
    { key: `device:${deviceFingerprint}`, cfg: config.device },
    { key: `subnet:${subnet}`,          cfg: config.subnet  },
  ];

  const results = await Promise.all(
    buckets.map(({ key, cfg }) => {
      const id = env.RATE_LIMITER.idFromName(key);
      const stub = env.RATE_LIMITER.get(id);
      return stub.fetch('https://do/check', {
        method: 'POST',
        body: JSON.stringify(cfg),
      }).then(r => r.json<{ allowed: boolean; retryAfter?: number }>());
    }),
  );

  const denied = results.find(r => !r.allowed);
  if (denied) return { allowed: false, retryAfter: denied.retryAfter };
  return { allowed: true };
}
```

## Post Handler Integration

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/api/posts') {
      return new Response('Not found', { status: 404 });
    }

    const sessionToken   = request.headers.get('X-Session-Token') ?? 'unknown';
    const deviceFp       = request.headers.get('X-Device-Fingerprint') ?? 'unknown';
    const ip             = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';

    const { allowed, retryAfter } = await checkRateLimits(env, sessionToken, deviceFp, ip);
    if (!allowed) {
      return Response.json(
        { error: 'rate_limited', retryAfter },
        { status: 429, headers: { 'Retry-After': String(retryAfter ?? 60) } },
      );
    }

    const body = await request.json<{ content: string }>();
    const postId = await createPost(env.DB, sessionToken, body.content);
    return Response.json({ postId }, { status: 201 });
  },
};
```

## Adaptive Limit Tightening

When platform-wide abuse is detected, KV config is updated to reduce limits globally. All DO instances read config fresh on each request.

```typescript
async function tightenGlobalPostLimits(
  kv: KVNamespace,
  multiplier: number, // e.g. 0.5 = halve all limits
): Promise<void> {
  const current: RateConfig = DEFAULT_CONFIG;
  const tightened: RateConfig = {
    session: { ...current.session, limit: Math.max(1, Math.floor(current.session.limit * multiplier)) },
    device:  { ...current.device,  limit: Math.max(2, Math.floor(current.device.limit  * multiplier)) },
    subnet:  { ...current.subnet,  limit: Math.max(5, Math.floor(current.subnet.limit  * multiplier)) },
  };
  await kv.put('rate_config:post', JSON.stringify(tightened), {
    expirationTtl: 60 * 60, // auto-restore after 1 hour
  });
}
```

## Abuse Signal Recording

Rate-limited requests are written to Analytics Engine for trend analysis without hitting D1.

```typescript
function recordRateLimitHit(
  ae: AnalyticsEngineDataset,
  bucket: string,
  ip: string,
  cf: IncomingRequestCfProperties,
): void {
  ae.writeDataPoint({
    blobs:   [bucket, ip, cf.country ?? 'XX', cf.asOrganization ?? ''],
    doubles: [1],
    indexes: [bucket],
  });
}
```

---

## Anti-patterns

- Using D1 as the rate-limit counter store — D1 write latency (10–50 ms) plus lock contention makes it unsuitable for hot counters.
- Fixed-window (per-minute-clock) counters — allows a burst of 2× the limit straddling a minute boundary.
- Checking only the session token — anonymous sessions rotate tokens; device fingerprint and subnet are the more persistent signals.
- Not setting a DO alarm — idle DOs with stale timestamp arrays accumulate unbounded storage.

## Gotchas

- DO instances are evicted after ~10 seconds of inactivity. The first request after eviction cold-starts the DO; the `timestamps` array is reloaded from storage.
- `DurableObjectStorage.get()` returns `undefined` (not `null`) for missing keys.
- Durable Objects are billed per request. 10 parallel bucket checks per post = 10 DO requests; budget accordingly.
- `idFromName()` is deterministic — the same key always routes to the same DO instance, which is the desired property.

## Verification

```bash
# Trigger rate limit (send >10 posts in 60 s from same session token)
for i in $(seq 1 12); do
  curl -s -X POST https://example.com/api/posts \
    -H "X-Session-Token: test-session-abc" \
    -H "X-Device-Fingerprint: test-fp-xyz" \
    -H "CF-Connecting-IP: 1.2.3.4" \
    -H "Content-Type: application/json" \
    -d '{"content":"test post '"$i"'"}' | jq '{status: .postId // .error}'
done
# Expect first 10 to succeed, 11th to return rate_limited

# Check Analytics Engine for hits
wrangler analytics-engine query \
  "SELECT blob1 as bucket, SUM(_sample_interval) as hits FROM example project_RATE_LIMITS GROUP BY blob1"
```

---

## Related

- `anonymous-dm-spam-burst-detection-durable-objects.md`
- `content-flooding-rate-shaping-durable-objects.md`
- `viral-content-cascade-rate-limiting-durable-objects.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`

## Sources

- Cloudflare Durable Objects docs — https://developers.cloudflare.com/durable-objects/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare KV — https://developers.cloudflare.com/kv/
