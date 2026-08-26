# Platform-Wide Emergency Lockdown & Circuit Breaker (Cloudflare Workers)

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A coordinated CSAM dump, a viral hate-speech campaign, or a zero-day exploit can require freezing example project across all surfaces within seconds — not the minutes it takes to push a Wrangler deployment. A platform-wide lockdown must: halt all new content submissions, restrict feed visibility to logged-in verified users only, disable the invite system, and surface an incident-status banner — all without a code deploy and reversible from a single API call.

---

## Context

A KV key (`platform:lockdown`) acts as the circuit breaker. Every inbound Worker reads this key at request time (cached in-process for ≤ 5 s). When the key is set, Workers enter a degraded mode defined by the lockdown's `level` field. A separate, IP-allowlisted admin Worker writes the key. The system supports three levels: `soft` (read-only public feeds), `hard` (authenticated users only), and `total` (503 for all non-admin traffic). The key TTL prevents a stuck lockdown from outlasting an incident without deliberate renewal.

---

## 1. Types — Lockdown Envelope

```typescript
// src/types/lockdown.ts
export type LockdownLevel = 'soft' | 'hard' | 'total';

export interface LockdownState {
  active: boolean;
  level: LockdownLevel;
  reason: string;
  initiatedBy: string;
  initiatedAt: number;    // Unix epoch
  expiresAt: number;      // Unix epoch — auto-expiry safety valve
  renewalToken: string;   // rotated on each set; required to renew/lift
}

export const LOCKDOWN_TTL_SECONDS: Record<LockdownLevel, number> = {
  soft:  3_600,    // auto-expires in 1 h if not renewed
  hard:  1_800,    // auto-expires in 30 min
  total:   900,    // auto-expires in 15 min
};
```

---

## 2. Lockdown Read Helper — In-process Cached

```typescript
// src/lib/lockdown.ts
import { Env } from '../types';
import { LockdownState } from '../types/lockdown';

let cachedState: LockdownState | null = null;
let cacheExpiry = 0;
const CACHE_TTL_MS = 5_000;   // re-read KV at most once every 5 s per isolate

export async function getLockdownState(env: Env): Promise<LockdownState | null> {
  const now = Date.now();
  if (cachedState !== null && now < cacheExpiry) return cachedState;

  const raw = await env.PLATFORM_KV.get<LockdownState>('platform:lockdown', { type: 'json' });

  if (!raw || !raw.active || raw.expiresAt < Math.floor(now / 1000)) {
    cachedState = null;
    cacheExpiry = now + CACHE_TTL_MS;
    return null;
  }

  cachedState = raw;
  cacheExpiry = now + CACHE_TTL_MS;
  return raw;
}

export function buildLockdownResponse(level: LockdownState['level']): Response {
  const messages: Record<LockdownState['level'], string> = {
    soft:  'The platform is currently in read-only mode. New submissions are paused.',
    hard:  'The platform is temporarily restricted to verified users.',
    total: 'example project is temporarily unavailable due to a platform incident. Please check status.example project.app.',
  };
  return new Response(
    JSON.stringify({ error: 'platform_lockdown', message: messages[level] }),
    {
      status: 503,
      headers: {
        'Content-Type': 'application/json',
        'Retry-After': '300',
        'X-Lockdown-Level': level,
      },
    }
  );
}
```

---

## 3. Gate Middleware — Applied in Every Inbound Worker

```typescript
// src/lib/lockdown-gate.ts
import { Env } from '../types';
import { getLockdownState, buildLockdownResponse } from './lockdown';
import { getSessionTier } from './session';

export type RouteKind = 'submit' | 'read' | 'admin' | 'status';

export async function applyLockdownGate(
  request: Request,
  env: Env,
  routeKind: RouteKind
): Promise<Response | null> {
  // Admin and status routes always pass through
  if (routeKind === 'admin' || routeKind === 'status') return null;

  const lockdown = await getLockdownState(env);
  if (!lockdown) return null;   // no active lockdown

  switch (lockdown.level) {
    case 'total':
      return buildLockdownResponse('total');

    case 'hard': {
      // Allow only authenticated verified users on read routes
      if (routeKind === 'submit') return buildLockdownResponse('hard');
      const tier = await getSessionTier(request, env);
      if (tier !== 'verified') return buildLockdownResponse('hard');
      return null;
    }

    case 'soft':
      // Block all submissions; reads pass through
      if (routeKind === 'submit') return buildLockdownResponse('soft');
      return null;
  }
}
```

---

## 4. Admin Lockdown Writer — Authenticated Control Plane

```typescript
// src/workers/lockdown-control.ts
import { Env } from '../types';
import { LockdownLevel, LockdownState, LOCKDOWN_TTL_SECONDS } from '../types/lockdown';
import { requireAdminAuth } from '../lib/auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!requireAdminAuth(request, env)) return new Response('Unauthorized', { status: 401 });

    const url = new URL(request.url);
    const action = url.pathname.split('/').pop();

    if (action === 'set' && request.method === 'POST') {
      const { level, reason, initiatedBy } = await request.json<{
        level: LockdownLevel; reason: string; initiatedBy: string;
      }>();

      const now = Math.floor(Date.now() / 1000);
      const ttl = LOCKDOWN_TTL_SECONDS[level];
      const renewalToken = crypto.randomUUID();

      const state: LockdownState = {
        active: true,
        level,
        reason,
        initiatedBy,
        initiatedAt: now,
        expiresAt: now + ttl,
        renewalToken,
      };

      await env.PLATFORM_KV.put('platform:lockdown', JSON.stringify(state), {
        expirationTtl: ttl + 60,   // KV TTL slightly longer than logical expiry
      });

      await logLockdownEvent(env, 'set', state, request);

      return new Response(JSON.stringify({ ok: true, renewalToken, expiresAt: state.expiresAt }), {
        status: 200,
      });
    }

    if (action === 'renew' && request.method === 'POST') {
      const { renewalToken } = await request.json<{ renewalToken: string }>();
      const existing = await env.PLATFORM_KV.get<LockdownState>('platform:lockdown', { type: 'json' });

      if (!existing || existing.renewalToken !== renewalToken) {
        return new Response('Invalid renewal token', { status: 403 });
      }

      const now = Math.floor(Date.now() / 1000);
      const ttl = LOCKDOWN_TTL_SECONDS[existing.level];
      const newToken = crypto.randomUUID();
      const renewed: LockdownState = {
        ...existing,
        expiresAt: now + ttl,
        renewalToken: newToken,
      };

      await env.PLATFORM_KV.put('platform:lockdown', JSON.stringify(renewed), {
        expirationTtl: ttl + 60,
      });

      await logLockdownEvent(env, 'renewed', renewed, request);
      return new Response(JSON.stringify({ ok: true, renewalToken: newToken }), { status: 200 });
    }

    if (action === 'lift' && request.method === 'POST') {
      const { renewalToken } = await request.json<{ renewalToken: string }>();
      const existing = await env.PLATFORM_KV.get<LockdownState>('platform:lockdown', { type: 'json' });

      if (!existing || existing.renewalToken !== renewalToken) {
        return new Response('Invalid renewal token', { status: 403 });
      }

      await env.PLATFORM_KV.delete('platform:lockdown');
      await logLockdownEvent(env, 'lifted', existing, request);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function logLockdownEvent(
  env: Env,
  event: string,
  state: LockdownState,
  request: Request
): Promise<void> {
  await env.PLATFORM_KV.put(
    `lockdown:audit:${Date.now()}`,
    JSON.stringify({ event, state, ip: request.headers.get('CF-Connecting-IP') }),
    { expirationTtl: 86_400 * 30 }   // retain for 30 days
  );
}
```

---

## 5. Status Page Endpoint — Public Circuit-Breaker View

```typescript
// src/workers/platform-status.ts
import { Env } from '../types';
import { getLockdownState } from '../lib/lockdown';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const lockdown = await getLockdownState(env);

    const body = {
      operational: lockdown === null,
      lockdownLevel: lockdown?.level ?? null,
      message: lockdown
        ? 'Platform incident in progress. See status.example project.app for updates.'
        : 'All systems operational.',
      checkedAt: new Date().toISOString(),
    };

    return new Response(JSON.stringify(body), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
      },
    });
  },
};
```

---

## Anti-patterns

- **Using a Workers secret flag instead of KV.** Secrets require a deployment to change; KV writes propagate globally within seconds.
- **Hardcoding a single admin token in the Worker.** Store the token in a Workers Secret and rotate it independently of the lockdown mechanism.
- **Setting a very long KV TTL without a renewal mechanism.** An operator going offline mid-incident can leave the platform locked for hours. The auto-expiry + renewal token pattern solves this.
- **Applying the gate only at the API layer but not the feed/CDN layer.** If the CDN serves cached content, cache-bypass headers (`Cache-Control: no-store`) must be set during a `total` lockdown.

---

## Gotchas

- KV `expirationTtl` values below 60 seconds are rejected; the minimum is 60 s. The lockdown TTL for `total` (900 s) is well above this.
- The in-process `cachedState` cache means each Worker isolate can serve up to 5 s of stale data after a lockdown is lifted. Add a `Retry-After` header so clients back off gracefully.
- `crypto.randomUUID()` is synchronous in the Workers runtime — no need to `await` it.
- KV audit keys keyed on `Date.now()` can collide if two admin actions happen within the same millisecond; suffix with a random fragment if collision-free audit is required.

---

## Verification

```bash
# Activate a soft lockdown
curl -X POST https://admin.example project.internal/lockdown/set \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"level":"soft","reason":"coordinated_spam_campaign","initiatedBy":"ops-alice"}' \
  | jq '{renewalToken, expiresAt}'

# Confirm submission is blocked
curl -X POST https://api.example project.internal/post/submit \
  -H "Content-Type: application/json" \
  -d '{"body":"test"}' | jq .error
# Expected: "platform_lockdown"

# Confirm status endpoint is unaffected
curl https://api.example project.internal/status | jq .lockdownLevel
# Expected: "soft"

# Lift lockdown
curl -X POST https://admin.example project.internal/lockdown/lift \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"renewalToken":"<token-from-set-response>"}'
```

---

## Related

- `emergency-content-takedown-circuit-breaker-queues.md`
- `platform-audit-log-immutable-d1-workers.md`
- `platform-trust-score-cloudflare-signals.md`
- `platform-health-score-dashboard-analytics-engine.md`
- `content-appeal-escalation-workflow-durable-objects.md`

---

## Sources

- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- Cloudflare Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- Circuit Breaker Pattern (Martin Fowler): https://martinfowler.com/bliki/CircuitBreaker.html
- NCMEC CyberTipline Emergency Protocol
- DSA Article 36 — Crisis Response Mechanism
