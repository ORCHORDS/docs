# Feature Flag Driven Deployment with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You ship code continuously but want to decouple deployment from feature activation. A new feature is deployed dark (disabled) and activated for a percentage of users via a flag in KV — without a re-deploy. Users in an allowlist can access the feature before the percentage rollout begins. After full rollout the flag is cleaned up and the code path becomes unconditional. Every flag change is audited in D1.

## Context

Feature flags decouple when code ships from when users experience it. In a Cloudflare Workers deployment, the natural place for flag evaluation is a middleware Worker that reads flag state from KV, evaluates it against the incoming request, and injects the result as a request header before forwarding to the origin. KV provides ~1 ms reads at the edge without cold-start penalty. D1 stores an immutable audit log of every flag mutation so compliance and incident investigations have a clear record.

## Solution

### Flag definition schema in KV

Key pattern: `flag:<flag-name>`

```typescript
// types/flag.ts
export interface FeatureFlag {
  name: string;
  /** Short description for audit log readability */
  description: string;
  /** 'active' | 'disabled' | 'archived' */
  status: 'active' | 'disabled' | 'archived';
  /** Percentage of traffic to receive the flag [0–100] */
  rolloutPercent: number;
  /** User IDs always granted access regardless of rollout */
  allowlist: string[];
  /** ISO-8601 creation timestamp */
  createdAt: string;
  /** ISO-8601 last-updated timestamp */
  updatedAt: string;
}
```

Example:

```json
{
  "name": "new-checkout-flow",
  "description": "Redesigned checkout UI with one-page layout",
  "status": "active",
  "rolloutPercent": 25,
  "allowlist": ["user_alpha_001", "user_alpha_002"],
  "createdAt": "2026-08-01T00:00:00Z",
  "updatedAt": "2026-08-24T10:30:00Z"
}
```

### Flag evaluation middleware

```typescript
// src/flags.ts
import type { FeatureFlag } from '../types/flag';

/** Stable bucket [0, 99] via FNV-1a */
function bucket(userId: string, flagName: string): number {
  const input = `${flagName}:${userId}`;
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h = Math.imul(h ^ input.charCodeAt(i), 16777619) >>> 0;
  }
  return h % 100;
}

export function evaluateFlag(
  flag: FeatureFlag | null,
  userId: string
): boolean {
  if (!flag || flag.status !== 'active') return false;
  if (flag.allowlist.includes(userId)) return true;
  if (flag.rolloutPercent >= 100) return true;
  if (flag.rolloutPercent <= 0) return false;
  return bucket(userId, flag.name) < flag.rolloutPercent;
}
```

```typescript
// src/index.ts
import { evaluateFlag } from './flags';
import type { FeatureFlag } from '../types/flag';

export interface Env {
  FLAGS: KVNamespace;
  DB: D1Database;
  ORIGIN: Fetcher;
  ADMIN_SECRET: string;
}

// In-process cache to reduce KV reads
const flagCache = new Map<string, { flag: FeatureFlag | null; expiry: number }>();
const CACHE_TTL_MS = 15_000;

async function getFlag(
  kv: KVNamespace,
  name: string
): Promise<FeatureFlag | null> {
  const cached = flagCache.get(name);
  if (cached && Date.now() < cached.expiry) return cached.flag;
  const flag = await kv.get<FeatureFlag>(`flag:${name}`, 'json');
  flagCache.set(name, { flag, expiry: Date.now() + CACHE_TTL_MS });
  return flag;
}

function getUserId(request: Request): string {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/(?:^|;\s*)user_id=([^;]+)/);
  return match ? match[1] : 'anonymous';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Admin: write / update a flag
    if (
      request.method === 'PUT' &&
      url.pathname.startsWith('/__flags/') &&
      request.headers.get('X-Admin-Secret') === env.ADMIN_SECRET
    ) {
      const flagName = url.pathname.replace('/__flags/', '');
      const body = await request.json<Partial<FeatureFlag>>();
      const existing = await env.FLAGS.get<FeatureFlag>(`flag:${flagName}`, 'json');
      const now = new Date().toISOString();
      const updated: FeatureFlag = {
        name: flagName,
        description: body.description ?? existing?.description ?? '',
        status: body.status ?? existing?.status ?? 'disabled',
        rolloutPercent: body.rolloutPercent ?? existing?.rolloutPercent ?? 0,
        allowlist: body.allowlist ?? existing?.allowlist ?? [],
        createdAt: existing?.createdAt ?? now,
        updatedAt: now,
      };

      await env.FLAGS.put(`flag:${flagName}`, JSON.stringify(updated));
      flagCache.delete(flagName);

      // Audit log
      await env.DB.prepare(
        `INSERT INTO flag_audit_log (flag_name, action, payload, changed_at)
         VALUES (?, ?, ?, datetime('now'))`
      )
        .bind(
          flagName,
          existing ? 'update' : 'create',
          JSON.stringify({ before: existing ?? null, after: updated })
        )
        .run();

      return Response.json(updated, { status: existing ? 200 : 201 });
    }

    // Admin: delete (archive) a flag after full rollout cleanup
    if (
      request.method === 'DELETE' &&
      url.pathname.startsWith('/__flags/') &&
      request.headers.get('X-Admin-Secret') === env.ADMIN_SECRET
    ) {
      const flagName = url.pathname.replace('/__flags/', '');
      const existing = await env.FLAGS.get<FeatureFlag>(`flag:${flagName}`, 'json');
      if (!existing) return new Response('Not found', { status: 404 });

      await env.FLAGS.delete(`flag:${flagName}`);
      flagCache.delete(flagName);

      await env.DB.prepare(
        `INSERT INTO flag_audit_log (flag_name, action, payload, changed_at)
         VALUES (?, 'delete', ?, datetime('now'))`
      )
        .bind(flagName, JSON.stringify({ before: existing }))
        .run();

      return new Response(null, { status: 204 });
    }

    // Normal request: evaluate all relevant flags and inject headers
    const userId = getUserId(request);
    const FLAG_NAMES = ['new-checkout-flow', 'dark-mode-beta', 'ai-search'];

    const flagResults: Record<string, boolean> = {};
    await Promise.all(
      FLAG_NAMES.map(async (name) => {
        const flag = await getFlag(env.FLAGS, name);
        flagResults[name] = evaluateFlag(flag, userId);
      })
    );

    const upstreamHeaders = new Headers(request.headers);
    upstreamHeaders.set('X-Feature-Flags', JSON.stringify(flagResults));
    upstreamHeaders.set('X-User-Id', userId);

    return env.ORIGIN.fetch(new Request(request, { headers: upstreamHeaders }));
  },
};
```

### D1 audit log schema

```sql
-- migrations/0001_flag_audit_log.sql
CREATE TABLE IF NOT EXISTS flag_audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  flag_name  TEXT NOT NULL,
  action     TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
  payload    TEXT NOT NULL,
  changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_audit_flag_name ON flag_audit_log (flag_name);
CREATE INDEX idx_audit_changed_at ON flag_audit_log (changed_at);
```

### Percentage rollout lifecycle

```bash
# 1. Create flag at 0% (dark deploy)
curl -X PUT https://flags.orchords.workers.dev/__flags/new-checkout-flow \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"description":"New checkout UI","status":"active","rolloutPercent":0,"allowlist":["user_alpha_001"]}'

# 2. Ramp to 10%
curl -X PUT https://flags.orchords.workers.dev/__flags/new-checkout-flow \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"rolloutPercent":10}'

# 3. Full rollout
curl -X PUT https://flags.orchords.workers.dev/__flags/new-checkout-flow \
  -H "X-Admin-Secret: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"rolloutPercent":100}'

# 4. Remove flag code path, then delete the flag from KV
curl -X DELETE https://flags.orchords.workers.dev/__flags/new-checkout-flow \
  -H "X-Admin-Secret: $ADMIN_SECRET"
```

### Querying the audit log

```bash
# All changes to a specific flag
npx wrangler d1 execute FLAGS_DB \
  --command "SELECT flag_name, action, changed_at FROM flag_audit_log WHERE flag_name='new-checkout-flow' ORDER BY changed_at" \
  --env production

# All flag deletes in the last 7 days
npx wrangler d1 execute FLAGS_DB \
  --command "SELECT * FROM flag_audit_log WHERE action='delete' AND changed_at >= datetime('now','-7 days')" \
  --env production
```

## Implementation Details

- `Promise.all` evaluates all flags in parallel for a single KV lookup round-trip, keeping middleware overhead below 2 ms per request for up to 10 flags.
- The in-process `flagCache` map keyed by flag name prevents redundant KV reads within a single isolate's 15 s window. Cache invalidation on write (`flagCache.delete`) ensures the admin PUT is immediately visible to subsequent reads on the same isolate.
- The `evaluateFlag` function is pure and synchronous — it takes the resolved `FeatureFlag` object and the user ID, making it trivially unit-testable without mocking KV.
- The audit `payload` JSON stores both `before` and `after` states, enabling point-in-time reconstruction of any flag's history from the audit table alone.

## Anti-patterns

- **Reading KV on every request without caching.** At high traffic, uncached KV reads for 5–10 flags per request will saturate your KV read quota and add measurable p99 latency.
- **Using `rolloutPercent: 100` without cleaning up.** A flag at 100% is evaluated every request forever. Once the code path is unconditional, delete the flag and remove the evaluation.
- **Allowing the allowlist to grow indefinitely.** KV values have a 25 MB limit but a large allowlist in every flag read adds JSON parse time. For large allowlists (> 1 000 users) move to a D1 table keyed by `(flag_name, user_id)`.
- **Storing secrets in the flag `meta` field.** Flag values are readable by anyone with KV namespace access. Never put credentials or PII in a flag config.

## Gotchas

- KV writes are eventually consistent: after a `PUT` updates the rollout percent, some Workers instances may see the old value for up to ~60 s (plus the 15 s cache TTL). Plan rollout ramps with this lag in mind — a 10% → 25% ramp may temporarily show between 10% and 25% actual traffic receiving the feature.
- The `flagCache` is per-isolate. Multiple isolates on the same PoP are independent; each has its own cache, so a flag change may propagate faster on PoPs with higher traffic (more isolates invalidated by admin writes hitting them).
- `JSON.stringify(flagResults)` in the `X-Feature-Flags` header can grow large if you evaluate many flags. Use a binary encoding or limit to 20 flags per request.
- D1 writes in the audit log are on the hot path only for admin flag changes (rare). Normal traffic evaluation never writes to D1, so there is no D1 write-rate concern for high-traffic workloads.

## Verification

1. Create a flag at 0% and confirm `evaluateFlag` returns `false` for a non-allowlisted user.
2. Add a user to the allowlist and confirm `evaluateFlag` returns `true` for that user at 0%.
3. Set rollout to 50% and send 1 000 requests with distinct user IDs — confirm approximately 500 receive `X-Feature-Flags: {"new-checkout-flow":true}`.
4. Query the audit log in D1 and confirm all three operations (create, update ×2) are recorded with accurate timestamps.
5. Delete the flag and confirm subsequent requests return `X-Feature-Flags: {"new-checkout-flow":false}`.

## Related

- `workers-a-b-test-deployment-kv.md`
- `canary-deployment-kv-flag.md`
- `workers-scheduled-maintenance-window.md`
- `workers-deployment-changelog-d1.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://martinfowler.com/articles/feature-toggles.html
