# D1 Service Binding Access Isolation in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A monolithic Worker handles dozens of routes, all sharing direct access to the same D1
binding. Over time, one route's schema changes break another; a bug in a low-priority
background task corrupts data in a production-critical table; there is no way to enforce
which routes are allowed to write to which tables.

You want to isolate D1 access behind a dedicated "database gateway" Worker that:
- Enforces access control (which callers can run which queries)
- Validates inputs before they reach D1
- Is the single source of truth for schema knowledge
- Can be independently deployed, versioned, and rate-limited

## Context

Cloudflare Workers supports **Service Bindings** — a way for one Worker to call another
Worker directly, with no HTTP round-trip through the public internet and sub-millisecond
latency. The callee Worker runs in the same Cloudflare PoP as the caller.

By placing the D1 binding *only* on a gateway Worker and exposing it via a service binding,
you achieve:
- **Least privilege**: caller Workers never hold a D1 credential directly.
- **Centralised validation**: input sanitisation, row-level access control, and query
  whitelisting live in one place.
- **Independent deployability**: the gateway can be updated (new indexes, schema changes,
  query optimisations) without touching caller Workers.
- **Observability**: all D1 traffic passes through one Worker, simplifying logging and tracing.

## Architecture Overview

```
┌────────────────────────┐
│   Public Internet      │
└──────────┬─────────────┘
           │ HTTPS
┌──────────▼─────────────┐   Service Binding    ┌───────────────────────┐
│   API Gateway Worker   │ ─────────────────►   │  DB Gateway Worker    │
│  (no D1 binding)       │                      │  (holds D1 binding)   │
└────────────────────────┘                      └──────────┬────────────┘
                                                           │ D1 API
                                                ┌──────────▼────────────┐
                                                │   D1 Database          │
                                                └───────────────────────┘
```

## DB Gateway Worker Implementation

```typescript
// workers/db-gateway/src/index.ts
import type { Env } from "./env";
import { handleArticles } from "./handlers/articles";
import { handleUsers } from "./handlers/users";
import { authenticate } from "./auth";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Gateway is only reachable via service binding — never from the internet.
    // Enforce this by checking a shared secret set in the binding caller.
    const callerSecret = request.headers.get("X-Internal-Secret");
    if (callerSecret !== env.INTERNAL_SECRET) {
      return Response.json({ error: "forbidden" }, { status: 403 });
    }

    const url = new URL(request.url);

    // Route to domain-specific handlers — each handler owns one set of tables
    if (url.pathname.startsWith("/articles")) {
      return handleArticles(request, env);
    }
    if (url.pathname.startsWith("/users")) {
      return handleUsers(request, env);
    }

    return Response.json({ error: "not found" }, { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

```typescript
// workers/db-gateway/src/env.ts
export interface Env {
  DB: D1Database;
  INTERNAL_SECRET: string;  // Wrangler secret: wrangler secret put INTERNAL_SECRET
}
```

```typescript
// workers/db-gateway/src/handlers/articles.ts
import type { Env } from "../env";

interface ArticleInput {
  title: string;
  body: string;
  authorId: string;
}

function validateArticleInput(data: unknown): ArticleInput {
  if (typeof data !== "object" || data === null) throw new Error("invalid input");
  const d = data as Record<string, unknown>;
  if (typeof d.title !== "string" || d.title.length < 1 || d.title.length > 255) {
    throw new Error("title must be 1-255 characters");
  }
  if (typeof d.body !== "string" || d.body.length < 1) {
    throw new Error("body is required");
  }
  if (typeof d.authorId !== "string" || !/^[0-9a-f-]{36}$/.test(d.authorId)) {
    throw new Error("authorId must be a UUID");
  }
  return { title: d.title, body: d.body, authorId: d.authorId };
}

export async function handleArticles(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const segments = url.pathname.split("/").filter(Boolean);
  // segments: ["articles"] or ["articles", "<publicId>"]

  // POST /articles — create
  if (request.method === "POST" && segments.length === 1) {
    let input: ArticleInput;
    try {
      input = validateArticleInput(await request.json());
    } catch (err) {
      return Response.json({ error: String(err) }, { status: 400 });
    }

    const publicId = crypto.randomUUID();
    const result = await env.DB
      .prepare(
        `INSERT INTO articles (public_id, title, body, author_id, created_at)
         VALUES (?, ?, ?, (SELECT id FROM users WHERE public_id = ?), unixepoch())
         RETURNING public_id, created_at`
      )
      .bind(publicId, input.title, input.body, input.authorId)
      .first<{ public_id: string; created_at: number }>();

    if (!result) {
      return Response.json({ error: "authorId not found" }, { status: 422 });
    }

    return Response.json({ id: result.public_id, createdAt: result.created_at }, { status: 201 });
  }

  // GET /articles/<publicId> — fetch one
  if (request.method === "GET" && segments.length === 2) {
    const publicId = segments[1];
    if (!/^[0-9a-f-]{36}$/.test(publicId)) {
      return Response.json({ error: "invalid id" }, { status: 400 });
    }

    const row = await env.DB
      .prepare(
        `SELECT a.public_id, a.title, a.body, a.created_at, u.public_id AS author_public_id
         FROM articles a
         JOIN users u ON u.id = a.author_id
         WHERE a.public_id = ?`
      )
      .bind(publicId)
      .first<{
        public_id: string; title: string; body: string;
        created_at: number; author_public_id: string;
      }>();

    if (!row) return Response.json({ error: "not found" }, { status: 404 });

    return Response.json({
      id: row.public_id,
      title: row.title,
      body: row.body,
      createdAt: row.created_at,
      authorId: row.author_public_id,
    });
  }

  return Response.json({ error: "method not allowed" }, { status: 405 });
}
```

## Caller Worker Implementation

The caller Worker has **no D1 binding** — it only has the service binding to the gateway.

```typescript
// workers/api-gateway/src/index.ts
import type { Env } from "./env";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Forward article requests to the DB gateway
    if (url.pathname.startsWith("/v1/articles")) {
      return forwardToDbGateway(request, env, url.pathname.replace("/v1", ""));
    }

    return Response.json({ error: "not found" }, { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function forwardToDbGateway(
  originalRequest: Request,
  env: Env,
  path: string
): Promise<Response> {
  // Build the internal request — strip public-facing headers, add internal auth
  const gatewayRequest = new Request(`http://db-gateway${path}`, {
    method: originalRequest.method,
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": env.INTERNAL_SECRET,
      // Forward the authenticated user context if needed
      "X-User-Id": originalRequest.headers.get("X-User-Id") ?? "",
    },
    body: originalRequest.method !== "GET" ? originalRequest.body : undefined,
  });

  return env.DB_GATEWAY.fetch(gatewayRequest);
}
```

```typescript
// workers/api-gateway/src/env.ts
export interface Env {
  DB_GATEWAY: Fetcher;     // Service binding to the DB gateway Worker
  INTERNAL_SECRET: string;
}
```

## Wrangler Configuration

```toml
# workers/db-gateway/wrangler.toml
name = "db-gateway"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding      = "DB"
database_name = "myapp-production"
database_id  = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
# INTERNAL_SECRET is set via: wrangler secret put INTERNAL_SECRET
```

```toml
# workers/api-gateway/wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-01-01"

# No [[d1_databases]] binding here — intentional

[[services]]
binding = "DB_GATEWAY"
service = "db-gateway"
# environment = "production"  # optional: pin to a specific gateway environment

[vars]
# INTERNAL_SECRET must match db-gateway's secret
```

## Typed Client Library Pattern

Generate a typed client for the gateway so callers don't hand-roll request construction:

```typescript
// packages/db-gateway-client/src/index.ts

export class DbGatewayClient {
  constructor(
    private readonly gateway: Fetcher,
    private readonly internalSecret: string,
  ) {}

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const response = await this.gateway.fetch(
      new Request(`http://db-gateway${path}`, {
        method,
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Secret": this.internalSecret,
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      })
    );

    if (!response.ok) {
      const error = await response.json<{ error: string }>();
      throw Object.assign(new Error(error.error), { status: response.status });
    }

    return response.json<T>();
  }

  // Articles
  async createArticle(input: {
    title: string;
    body: string;
    authorId: string;
  }): Promise<{ id: string; createdAt: number }> {
    return this.request("POST", "/articles", input);
  }

  async getArticle(id: string): Promise<{
    id: string;
    title: string;
    body: string;
    createdAt: number;
    authorId: string;
  } | null> {
    try {
      return await this.request("GET", `/articles/${id}`);
    } catch (err) {
      if ((err as { status?: number }).status === 404) return null;
      throw err;
    }
  }

  // Users (add more methods per domain)
  async getUserByPublicId(publicId: string): Promise<{ id: string; name: string } | null> {
    try {
      return await this.request("GET", `/users/${publicId}`);
    } catch (err) {
      if ((err as { status?: number }).status === 404) return null;
      throw err;
    }
  }
}
```

## Access Control per Caller Identity

For multi-service architectures where different caller Workers need different permissions:

```typescript
// workers/db-gateway/src/access-control.ts

type Permission = "articles:read" | "articles:write" | "users:read" | "users:write";

const CALLER_PERMISSIONS: Record<string, Permission[]> = {
  "api-gateway":        ["articles:read", "articles:write", "users:read"],
  "background-worker":  ["articles:read"],
  "admin-worker":       ["articles:read", "articles:write", "users:read", "users:write"],
};

export function checkPermission(
  callerName: string | null,
  required: Permission
): boolean {
  if (!callerName) return false;
  const perms = CALLER_PERMISSIONS[callerName] ?? [];
  return perms.includes(required);
}
```

```typescript
// In db-gateway/src/index.ts — add to the fetch handler:
const callerName = request.headers.get("X-Caller-Name");
// Callers set this header; it's trusted because only internal service bindings
// can reach this Worker (validated via X-Internal-Secret above).

// Example: block writes from background workers
if (request.method !== "GET" && !checkPermission(callerName, "articles:write")) {
  return Response.json({ error: "insufficient permissions" }, { status: 403 });
}
```

## Anti-patterns

**Putting the D1 binding on all Workers "for convenience."** This defeats the isolation
goal. If any caller Worker is compromised, it has direct unmediated D1 access.

**Using a public HTTP URL as the gateway endpoint.** Service bindings are private and have
zero network egress cost. A public URL means latency, TLS overhead, public exposure, and
the need for authentication tokens instead of a simple shared secret.

**Skipping input validation in the gateway because "callers are trusted."** The gateway
is the last defence before data enters D1. Validate all inputs regardless of caller identity.
A bug in a trusted caller can still corrupt data.

**One giant gateway handler file.** Split by domain (articles, users, orders) so each
domain can be reasoned about and tested independently.

**Re-implementing HTTP routing in every caller.** Extract a typed client package shared
across caller Workers. This eliminates path-construction bugs and gives you IDE autocompletion.

## Gotchas

- **Service binding calls count against the caller Worker's CPU time.** The callee runs in
  its own isolate, but the awaited response time affects the caller's wall-clock duration.

- **Wrangler local dev requires `wrangler dev --service` to wire up service bindings.**
  Without it, `env.DB_GATEWAY.fetch(...)` will throw "Service not found" locally. Run both
  Workers in a local dev session or use `wrangler dev --config api-gateway/wrangler.toml`
  with the gateway already running.

- **The gateway Worker's D1 binding is in its own `wrangler.toml` — not the caller's.**
  Deploying the caller does not redeploy the gateway. They are independently deployed via
  their own `wrangler.toml` configurations.

- **Secret synchronisation.** `INTERNAL_SECRET` must be set identically on both Workers.
  Use the same `wrangler secret put` value and rotate them together.

- **Service bindings have no built-in retry.** If the gateway Worker throws, the caller
  receives a 500 response — implement retry logic in the typed client where appropriate.

## Verification

```typescript
// Integration test: confirm caller cannot reach D1 directly
async function testIsolation(env: Env): Promise<void> {
  // Attempt to access DB directly — should be undefined on the caller Worker
  const hasDirectDb = "DB" in env;
  console.assert(!hasDirectDb, "Caller Worker must NOT have a direct D1 binding");

  // Gateway round-trip
  const article = await new DbGatewayClient(env.DB_GATEWAY, env.INTERNAL_SECRET)
    .getArticle("00000000-0000-0000-0000-000000000000");

  console.assert(article === null, "Non-existent article should return null, not throw");
  console.log("service binding isolation: OK");
}
```

## Related

- `d1-row-level-security-tenant-id.md` — per-row access control inside the gateway
- `d1-rate-limiting-sliding-window-workers.md` — rate-limit inside the gateway
- `database-roles-least-privilege.md` — least-privilege principle
- `d1-advisory-lock-pattern-workers.md` — concurrency control in the gateway
- `d1-audit-event-log.md` — audit logging all gateway mutations

## Sources

- Cloudflare Workers Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Cloudflare D1 Worker bindings: https://developers.cloudflare.com/d1/worker-api/
- Wrangler service bindings configuration: https://developers.cloudflare.com/workers/wrangler/configuration/#services
- Cloudflare Workers security model: https://developers.cloudflare.com/workers/reference/security-model/
