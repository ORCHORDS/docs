# Service Granularity and Decomposition in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a monolithic Worker that handles authentication, business logic, data access, and
serving static assets from a single `fetch` handler. Or you went the other extreme: every
function is its own Worker, and you spend more time managing bindings than building features.
Neither extreme is right. This article establishes heuristics for right-sizing Workers.

## Context

Service granularity answers the question: "How much should one deployable unit do?" In
Cloudflare Workers the unit of deployment is a Worker Script (plus its Durable Object
classes, Queues, and KV namespaces). Splitting too fine creates operational overhead —
more `wrangler.toml` files, more service bindings to maintain, and network hops even when
bindings are local loopback calls. Splitting too coarsely creates coupling — a schema
migration or rate-limit change in one domain forces redeployment of unrelated logic.

The canonical decomposition axes are:

1. **Business domain** (DDD Bounded Context) — the primary cut
2. **Rate of change** — logic that changes weekly vs. logic that is stable for years
3. **Scaling profile** — CPU-bound AI inference vs. lightweight routing
4. **Team ownership** — Conway's Law alignment
5. **Security boundary** — untrusted user input handled separately from internal services

## Heuristic 1 — Single Reason to Redeploy

A Worker should have exactly one reason to be redeployed. If you find yourself editing
authentication logic and business logic in the same file during a sprint, they belong in
separate Workers.

```typescript
// BAD: one Worker doing auth + business logic + data access
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    // Auth
    const token = req.headers.get("Authorization");
    const user = await verifyJwt(token, env.JWT_SECRET);
    if (!user) return new Response("Unauthorized", { status: 401 });

    // Business logic (separate domain)
    const order = await processOrder(env.DB, user.id);

    // Sending email (yet another domain)
    await env.EMAIL_SERVICE.fetch(/* ... */);

    return Response.json(order);
  },
};
```

```typescript
// GOOD: auth at the edge Worker, business logic behind a service binding
// edge-worker/index.ts  — sole reason to change: auth policy
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const user = await verifyJwt(req.headers.get("Authorization"), env.JWT_SECRET);
    if (!user) return new Response("Unauthorized", { status: 401 });
    const forwarded = new Request(req, {
      headers: { ...Object.fromEntries(req.headers), "x-user-id": user.id },
    });
    return env.ORDERS_SERVICE.fetch(forwarded);
  },
};
```

## Heuristic 2 — Scaling Profile Isolation

Workers that perform heavy AI inference (Workers AI) or large aggregation queries (D1
full-table scans) should be isolated from Workers on the hot path for simple CRUD
operations. A slow AI Worker does not degrade the latency of a fast routing Worker.

```typescript
// ai-enrichment-worker/index.ts — CPU-heavy, low request rate
import { Ai } from "@cloudflare/ai";
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { text } = await req.json<{ text: string }>();
    const ai = new Ai(env.AI);
    const { data } = await ai.run("@cf/baai/bge-small-en-v1.5", {
      text: [text],
    });
    return Response.json({ embedding: data[0] });
  },
};

// crud-worker/index.ts — lightweight, high request rate
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const item = await env.DB.prepare("SELECT * FROM items WHERE id = ?")
      .bind(new URL(req.url).searchParams.get("id"))
      .first();
    return Response.json(item);
  },
};
```

## Heuristic 3 — Data Ownership Boundary

Each Worker owns one logical schema. The ownership rule maps directly to which Worker holds
the D1 binding in `wrangler.toml`. If two Workers need the same table, one of them is
wrong about its boundary.

```typescript
// accounts-worker — owns the `accounts` D1 schema exclusively
export async function getAccount(env: Env, id: string) {
  return env.ACCOUNTS_DB.prepare("SELECT * FROM accounts WHERE id = ?")
    .bind(id).first();
}

// billing-worker — owns the `invoices` schema
// Needs account name? → calls the Accounts service API, does not touch accounts DB
export async function getInvoiceWithAccount(
  env: Env,
  invoiceId: string
): Promise<Response> {
  const invoice = await env.BILLING_DB.prepare(
    "SELECT * FROM invoices WHERE id = ?"
  ).bind(invoiceId).first();
  if (!invoice) return new Response("Not Found", { status: 404 });
  const accountRes = await env.ACCOUNTS_SERVICE.fetch(
    new Request(`https://accounts/v1/account?id=${invoice.account_id}`)
  );
  const account = await accountRes.json();
  return Response.json({ invoice, account });
}
```

## Heuristic 4 — Team Topology Alignment

Map Workers to team boundaries. A shared Worker owned by two teams creates a merge
conflict bottleneck. Use the `wrangler.toml` `name` field as the canonical service name,
and match it to your organisation's team names.

```toml
# team: payments
name = "payments-worker"

# team: identity
name = "identity-worker"
```

A service boundary checklist:

```typescript
// service-checklist.ts — run during architecture review
interface ServiceContract {
  name: string;
  team: string;
  ownedSchemas: string[];      // D1 database IDs
  ownedQueues: string[];       // Queue names
  externalApis: string[];      // Other Worker names called via service bindings
  publicRoutes: string[];      // Routes this service exposes
}

const paymentsService: ServiceContract = {
  name: "payments-worker",
  team: "payments",
  ownedSchemas: ["payments-db"],
  ownedQueues: ["payment-events"],
  externalApis: ["identity-worker", "notifications-worker"],
  publicRoutes: ["/v1/charge", "/v1/refund", "/v1/subscription"],
};
```

## Heuristic 5 — Anti-chunking: When NOT to Split

Do not split a Worker solely because a file is large. Split only when a genuine boundary
exists. Signs that splitting would be premature:

- Both halves would share the same D1 database and KV namespace
- The new service would have only one client (the original Worker)
- The functionality changes at the same frequency in the same sprint
- The team size is < 3 engineers (overhead exceeds benefit)

```typescript
// PREMATURE SPLIT — splitting helpers into a micro-Worker
// These utilities have no independent lifecycle; keep them as a module.
// helper-worker/index.ts (BAD)
export default {
  async fetch(req: Request): Promise<Response> {
    const { value } = await req.json<{ value: number }>();
    return Response.json({ result: value * 2 });
  },
};

// GOOD — shared as an imported TypeScript module
// lib/math.ts
export function double(value: number): number {
  return value * 2;
}
```

## Anti-patterns

- Creating a Worker per HTTP route (nano-services) — service binding overhead and cold-start
  latency accumulate at every hop.
- Grouping Workers by technical layer (all "database Workers", all "cache Workers") instead
  of by business domain — violates cohesion and creates coupling.
- Sharing a Durable Object class across Workers that represent different business domains —
  DO classes should be co-located with the Worker that owns their schema.
- Using KV as an IPC channel between Workers instead of service bindings — KV is eventually
  consistent; use service bindings for synchronous calls and Queues for async.

## Gotchas

- Cloudflare imposes a limit of 6 service binding hops in a single request chain. Deep
  call trees that exceed this will fail with a 503. Flatten the call graph when possible.
- CPU time limits (10 ms on bundled plans, 30 s on paid) apply per Worker invocation in
  the chain. Latency-sensitive paths should not chain more than 2–3 Workers.
- Each Durable Object namespace is scoped to the Worker that declares it. A Durable Object
  in the `orders-worker` cannot be accessed by the `payments-worker` directly; access must
  go through a service binding to the owning Worker.
- Workers deployed to the same `wrangler.toml` (multiple entrypoints) share a CPU limit
  budget; move latency-sensitive and CPU-heavy Workers to separate `wrangler.toml` files.

## Verification

1. List all Workers and their D1 bindings. Confirm no two Workers share the same
   `database_id`. If they do, apply the shared-database remediation.
2. Draw a service dependency graph. If it has more than 4 hops in any chain, refactor.
3. Measure per-Worker CPU time in Analytics Engine. Workers at < 5 ms average are
   candidates for consolidation; Workers at > 20 ms average should be profiled.
4. Run `wrangler deploy --dry-run` for each Worker in CI. If two Workers must always be
   deployed together, they should probably be one Worker.

## Related

- `bounded-context-design.md`
- `shared-database-coupling-anti-pattern.md`
- `worker-to-worker-rpc-service-bindings.md`
- `microservices-vs-monolith.md`
- `modular-monolith-pattern.md`

## Sources

- Sam Newman — Building Microservices (Chapter 3: How to Model Services)
- Team Topologies, Skelton & Pais
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Conway's Law: https://www.melconway.com/Home/Committees_Paper.html
