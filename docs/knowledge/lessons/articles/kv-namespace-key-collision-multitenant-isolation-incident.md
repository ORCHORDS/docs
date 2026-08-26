# KV Namespace Key Collision Multi-Tenant Isolation Incident

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

On 2026-06-02, a subset of example project enterprise customers briefly received cached API responses belonging to a different tenant. The window of data leakage was 4 minutes. 11 organisations were affected; no passwords or payment data were exposed, but workspace names and member counts from unrelated tenants were visible in UI responses. Regulatory notification was required under GDPR Article 33.

## Context

example project uses a single shared KV namespace (`example project_CACHE`) to cache tenant-scoped API responses for performance. Key construction used only the resource path as the key without a tenant prefix. A refactor two sprints prior had stripped the tenant prefix "to reduce key length," assuming URL paths were tenant-unique. They are not — `/api/workspaces/settings` is the same path for every tenant.

---

## Section 1: The Broken Key Construction

```typescript
// BEFORE — path-only key construction leaked cross-tenant data
async function cachedApiResponse(
  path: string,
  fetcher: () => Promise<unknown>,
  env: Env
): Promise<unknown> {
  const cacheKey = path; // e.g. "/api/workspaces/settings"

  const cached = await env.example project_CACHE.get(cacheKey, 'json');
  if (cached !== null) return cached;

  const fresh = await fetcher();
  await env.example project_CACHE.put(cacheKey, JSON.stringify(fresh), {
    expirationTtl: 60,
  });
  return fresh;
}
```

Two tenants with identical resource paths would read each other's cached values.

---

## Section 2: Mandatory Tenant-Scoped Key Prefix

All KV keys must be prefixed with a stable, unguessable tenant identifier. Use the tenant's internal UUID, not their slug (slugs can be renamed).

```typescript
// AFTER — tenant UUID prefix enforced at the cache layer
async function cachedApiResponse(
  tenantId: string, // internal UUID, not slug
  path: string,
  fetcher: () => Promise<unknown>,
  env: Env
): Promise<unknown> {
  if (!tenantId || tenantId.length < 16) {
    throw new Error('cachedApiResponse: tenantId is required and must be a UUID');
  }

  const cacheKey = `tenant:${tenantId}:${path}`;

  const cached = await env.example project_CACHE.get(cacheKey, 'json');
  if (cached !== null) return cached;

  const fresh = await fetcher();
  await env.example project_CACHE.put(cacheKey, JSON.stringify(fresh), {
    expirationTtl: 60,
  });
  return fresh;
}
```

---

## Section 3: Key-Builder Utility With Type Safety

Centralise key construction so no callsite can omit the tenant prefix.

```typescript
// kv-keys.ts — single source of truth for all KV key shapes
const KV_VERSION = 'v2';

export const kvKey = {
  apiCache: (tenantId: string, path: string) =>
    `${KV_VERSION}:tenant:${tenantId}:api:${path}`,

  sessionToken: (tenantId: string, tokenHash: string) =>
    `${KV_VERSION}:tenant:${tenantId}:session:${tokenHash}`,

  featureFlag: (tenantId: string, flag: string) =>
    `${KV_VERSION}:tenant:${tenantId}:ff:${flag}`,

  globalRateLimit: (ip: string) =>
    `${KV_VERSION}:global:ratelimit:${ip}`,
} as const;

// Usage — impossible to call without tenantId
const key = kvKey.apiCache(ctx.tenantId, '/api/workspaces/settings');
const value = await env.example project_CACHE.get(key, 'json');
```

The `KV_VERSION` prefix allows namespace-wide invalidation by bumping the version constant and deploying.

---

## Section 4: Audit Scan for Bare-Path Keys (Migration Script)

Before deploying the fix, enumerate and delete any keys that lack the tenant prefix to prevent serving stale cross-tenant data.

```typescript
// scripts/audit-kv-keys.ts — run via `wrangler dev --remote` one-off
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let cursor: string | undefined;
    const bare: string[] = [];

    do {
      const list = await env.example project_CACHE.list({ cursor, limit: 1000 });
      for (const key of list.keys) {
        if (!key.name.startsWith('v2:tenant:') && !key.name.startsWith('v2:global:')) {
          bare.push(key.name);
        }
      }
      cursor = list.list_complete ? undefined : list.cursor;
    } while (cursor);

    // Delete bare keys in batches
    for (const key of bare) {
      await env.example project_CACHE.delete(key);
    }

    return Response.json({ purged: bare.length, keys: bare.slice(0, 20) });
  },
};
```

---

## Section 5: Integration Test for Tenant Isolation

```typescript
// tests/kv-isolation.test.ts
import { describe, it, expect, beforeEach } from 'vitest';

describe('KV tenant isolation', () => {
  const mockKV = new Map<string, string>();
  const fakeEnv = {
    example project_CACHE: {
      get: async (k: string) => mockKV.get(k) ?? null,
      put: async (k: string, v: string) => { mockKV.set(k, v); },
    },
  } as unknown as Env;

  beforeEach(() => mockKV.clear());

  it('does not serve tenant A cache to tenant B', async () => {
    await cachedApiResponse('tenant-A-uuid', '/api/workspaces/settings',
      async () => ({ name: 'Tenant A Workspace' }), fakeEnv);

    // Tenant B cache miss — fetcher returns different data
    const result = await cachedApiResponse('tenant-B-uuid', '/api/workspaces/settings',
      async () => ({ name: 'Tenant B Workspace' }), fakeEnv);

    expect((result as any).name).toBe('Tenant B Workspace');
  });

  it('key includes tenant UUID', async () => {
    await cachedApiResponse('abc-123', '/api/workspaces/settings',
      async () => ({}), fakeEnv);

    const keys = [...mockKV.keys()];
    expect(keys.every(k => k.includes('abc-123'))).toBe(true);
    expect(keys.every(k => k.startsWith('v2:tenant:'))).toBe(true);
  });
});
```

---

## Anti-patterns

- Using resource paths, slugs, or human-readable names as KV keys in a multi-tenant system — they are not globally unique.
- Constructing KV keys inline at each callsite instead of routing through a centralised key-builder that enforces structure.
- Using a single shared KV namespace for both global and tenant-scoped data without a strict prefix schema.
- Shortening KV keys by removing tenant context "to save bytes" — KV key size is not a significant cost driver.

## Gotchas

- KV `list()` returns keys in lexicographic order; tenant-prefixed keys naturally group by tenant, making isolation audits feasible.
- KV does not support row-level access control — isolation is 100% the application's responsibility.
- Bumping `KV_VERSION` in the key prefix effectively orphans all existing keys; pair with a TTL-based cleanup job rather than a manual purge to avoid rate limits.
- `tenantId` must come from a verified auth context (JWT claim, session store), never from a user-supplied header or query parameter.

## Verification

1. Deploy `audit-kv-keys.ts` to staging with `--remote` and confirm zero bare-path keys remain.
2. Run the isolation test suite; all assertions must pass before next deploy.
3. Add a CI lint rule via a custom ESLint plugin that flags direct `env.example project_CACHE.get/put` calls outside `kv-keys.ts`.
4. Schedule a weekly KV audit script in a Cron Trigger to alert on keys that do not match the `v2:tenant:*` or `v2:global:*` patterns.

## Related

- `kv-namespace-deleted-wrong-environment-postmortem.md`
- `kv-ttl-expiry-race-condition-session-logout-incident.md`
- `workers-kv-namespace-key-limit-production-incident.md`
- `cloudflare-storage-primitive-selection.md`
- `data-minimization-reduces-breach-impact.md`
- `gdpr-by-design-not-retrofit.md`

## Sources

- Cloudflare KV documentation — Limits and Namespaces: https://developers.cloudflare.com/kv/reference/kv-namespaces/
- GDPR Article 33 — Notification of a personal data breach: https://gdpr-info.eu/art-33-gdpr/
- example project incident ticket INC-2026-0602-KV-ISOLATION / GDPR report ref GR-2026-041
