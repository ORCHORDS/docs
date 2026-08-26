# Anti-Corruption Layer Between a Legacy HTTP API and a Cloudflare Workers Service

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your new Cloudflare Workers service must integrate with a legacy HTTP API that uses snake_case field names, opaque numeric error codes, and a schema that changes without notice. Every breaking change in the legacy API ripples directly into your new service, forcing widespread domain model updates. You need a translation boundary that isolates your clean domain model from the legacy system's quirks.

## Context

The Anti-Corruption Layer (ACL) pattern, introduced in Domain-Driven Design, places an explicit translation layer between two bounded contexts so that neither contaminates the other's model. In a Cloudflare Workers context the ACL is its own Worker (or a Durable Object) that intercepts all outbound calls to the legacy API, translates request and response shapes, maps error codes to typed domain exceptions, and caches translated responses in KV. Downstream Workers in the new domain never see legacy field names or error codes. When the legacy API changes its schema, only the ACL Worker needs updating.

## ACL Worker: Request Translation and Error Mapping

```typescript
// acl-worker.ts
import { Env } from './types';

// Legacy response shape (snake_case, numeric error codes)
interface LegacyCustomer {
  customer_id: number;
  first_name: string;
  last_name: string;
  email_address: string;
  account_status: number; // 1=active, 2=suspended, 3=closed
  created_ts: number;
}

// New domain model (camelCase, typed status)
export interface Customer {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  status: 'active' | 'suspended' | 'closed';
  createdAt: Date;
}

// Typed domain exceptions
export class CustomerNotFoundError extends Error {
  constructor(id: string) { super(`Customer ${id} not found`); this.name = 'CustomerNotFoundError'; }
}
export class CustomerSuspendedError extends Error {
  constructor(id: string) { super(`Customer ${id} is suspended`); this.name = 'CustomerSuspendedError'; }
}

const LEGACY_STATUS_MAP: Record<number, Customer['status']> = {
  1: 'active',
  2: 'suspended',
  3: 'closed',
};

function translateCustomer(raw: LegacyCustomer): Customer {
  return {
    id:        String(raw.customer_id),
    firstName: raw.first_name,
    lastName:  raw.last_name,
    email:     raw.email_address,
    status:    LEGACY_STATUS_MAP[raw.account_status] ?? 'closed',
    createdAt: new Date(raw.created_ts * 1000),
  };
}

async function fetchLegacyCustomer(
  env: Env,
  legacyId: string,
  version: string,
): Promise<LegacyCustomer> {
  const res = await fetch(`${env.LEGACY_API_BASE}/customers/${legacyId}`, {
    headers: {
      Authorization: `Bearer ${env.LEGACY_API_TOKEN}`,
      'Accept-Version': version,
      'Content-Type': 'application/json',
    },
  });

  if (res.status === 404) throw new CustomerNotFoundError(legacyId);
  if (!res.ok) {
    const body = await res.json<{ error_code: number }>();
    if (body.error_code === 1042) throw new CustomerSuspendedError(legacyId);
    throw new Error(`Legacy API error ${res.status}: ${body.error_code}`);
  }

  return res.json<LegacyCustomer>();
}
```

## KV Caching of Translated Responses

```typescript
// Cache translated (domain) objects, not raw legacy payloads,
// so a schema change only busts the cache — it does not corrupt it.
const CACHE_TTL_SECONDS = 300; // 5 minutes

export async function getCustomer(
  env: Env,
  customerId: string,
  acceptVersion = 'v2',
): Promise<Customer> {
  const cacheKey = `customer:${customerId}:${acceptVersion}`;

  // 1. KV cache hit
  const cached = await env.ACL_CACHE.get<Customer>(cacheKey, 'json');
  if (cached) return cached;

  // 2. Fetch and translate
  const raw = await fetchLegacyCustomer(env, customerId, acceptVersion);
  const customer = translateCustomer(raw);

  // 3. Store translated form
  await env.ACL_CACHE.put(cacheKey, JSON.stringify(customer), {
    expirationTtl: CACHE_TTL_SECONDS,
  });

  return customer;
}

// Invalidate on mutation so stale data is never served
export async function invalidateCustomerCache(
  env: Env,
  customerId: string,
): Promise<void> {
  await Promise.all([
    env.ACL_CACHE.delete(`customer:${customerId}:v1`),
    env.ACL_CACHE.delete(`customer:${customerId}:v2`),
  ]);
}
```

## Version Negotiation via Accept-Version Header

```typescript
// acl-router.ts  —  the ACL Worker's fetch handler
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const version = req.headers.get('Accept-Version') ?? 'v2';
    const supported = ['v1', 'v2'];

    if (!supported.includes(version)) {
      return new Response(
        JSON.stringify({ error: 'Unsupported version', supported }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const match = url.pathname.match(/^\/customers\/([^/]+)$/);
    if (match) {
      try {
        const customer = await getCustomer(env, match[1], version);
        return Response.json(customer);
      } catch (err) {
        if (err instanceof CustomerNotFoundError)
          return new Response(JSON.stringify({ error: err.message }), { status: 404 });
        if (err instanceof CustomerSuspendedError)
          return new Response(JSON.stringify({ error: err.message }), { status: 403 });
        throw err;
      }
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Isolating the New Service from Legacy Schema Changes

All new Workers import only the domain types (`Customer`, `CustomerNotFoundError`) and call the ACL Worker via service bindings. No new Worker ever imports a `LegacyCustomer` type.

```typescript
// order-worker.ts  —  consumes the ACL via service binding, never calls legacy API directly
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { customerId } = await req.json<{ customerId: string }>();

    // Service binding call — hits the ACL Worker, not the legacy API
    const aclRes = await env.ACL_SERVICE.fetch(
      new Request(`https://acl/customers/${customerId}`, {
        headers: { 'Accept-Version': 'v2' },
      }),
    );

    if (!aclRes.ok) {
      return new Response(aclRes.body, { status: aclRes.status });
    }

    const customer = await aclRes.json<Customer>();
    // ... proceed with clean domain model
    return Response.json({ ok: true, customer });
  },
};
```

## Anti-patterns

- **Calling the legacy API directly from domain Workers** — every legacy schema change then requires updating multiple Workers; the ACL must be the single egress point.
- **Caching raw legacy payloads** — if the translation logic changes, stale cached raw payloads will be mis-translated; always cache the translated domain object.
- **Silently swallowing unknown error codes** — map every known code and throw a labelled error for unknowns so they are visible in logs and never masked as success.
- **Version negotiation in domain logic** — the ACL Worker owns version routing; domain Workers always request the latest stable version they were tested against.

## Gotchas

- KV `get` with `'json'` returns `null` on a miss, not an empty object; always null-check before using cached values.
- Service bindings between Workers in the same `wrangler.toml` `services` array are zero-latency; across separate deploys they traverse the network.
- `Accept-Version` is not a standard header name; add it to the `Access-Control-Allow-Headers` CORS policy if the ACL is called from a browser.
- If the legacy API rate-limits by IP, all Workers share the Cloudflare egress pool; set a KV TTL generous enough to absorb burst traffic.
- D1 is not involved in this pattern; the ACL uses KV for cache because KV's global replication suits read-heavy translation workloads.

## Verification

```bash
# Deploy the ACL Worker
wrangler deploy --config wrangler.acl.toml --env production

# Smoke-test translation
curl -H "Accept-Version: v2" https://acl.example.workers.dev/customers/42

# Confirm KV cache write
wrangler kv key get --binding ACL_CACHE "customer:42:v2" --env production

# Test unsupported version rejection
curl -H "Accept-Version: v99" https://acl.example.workers.dev/customers/42
# Expected: 400 {"error":"Unsupported version","supported":["v1","v2"]}
```

## Related

- `hexagonal-architecture-workers-ports-adapters.md`
- `outbox-pattern-workers-d1-queues-reliable-events.md`

## Sources

- Evans, Eric — Domain-Driven Design (Anti-Corruption Layer chapter) — https://www.domainlanguage.com/ddd/
- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare KV — https://developers.cloudflare.com/kv/api/
