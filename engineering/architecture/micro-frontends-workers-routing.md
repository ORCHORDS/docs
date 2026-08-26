# Micro-Frontend Routing with a Cloudflare Workers Shell

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Multiple product teams deploy independent Cloudflare Pages applications but users must see a unified experience at a single domain. Without a routing layer, teams coordinate deployments, share build pipelines, and duplicate authentication logic — exactly the coupling micro-frontends are meant to eliminate.

---

## Context

A Workers shell sits in front of all micro-frontend deployments and acts as the API gateway and HTML compositor. URL patterns determine which Pages deployment (team-a.internal, team-b.internal, team-c.internal) receives the proxied request, so teams ship independently without touching the shell. The shell merges response headers, strips internal routing headers that must not leak to the browser, injects a shared navigation fragment into every HTML response using HTMLRewriter, and propagates authentication cookies across all micro-frontends so users do not log in repeatedly. Because the shell is a Worker, it runs at the edge with zero round-trips to an origin; backend-for-frontend consolidation happens inside the same Cloudflare network without traversing the public internet.

---

## Config — wrangler.toml

```toml
name = "mfe-shell"
main = "src/shell.ts"
compatibility_date = "2025-09-01"

# Service bindings to each team's Pages deployment worker
[[services]]
binding = "TEAM_A"
service = "team-a-pages"

[[services]]
binding = "TEAM_B"
service = "team-b-pages"

[[services]]
binding = "TEAM_C"
service = "team-c-pages"

[[kv_namespaces]]
binding = "SESSION_KV"
id = "<kv-namespace-id>"

[vars]
NAV_FRAGMENT_URL = "https://nav.internal.example.com/fragment"
AUTH_COOKIE_NAME = "__mfe_session"
```

---

## Implementation — shell Worker

```typescript
// src/shell.ts

export interface Env {
  TEAM_A: Fetcher; // Pages deployment: /app/dashboard/*, /app/reports/*
  TEAM_B: Fetcher; // Pages deployment: /app/catalog/*, /app/search/*
  TEAM_C: Fetcher; // Pages deployment: /app/checkout/*, /app/orders/*
  SESSION_KV: KVNamespace;
  AUTH_COOKIE_NAME: string;
  NAV_FRAGMENT_URL: string;
}

interface Route {
  pattern: URLPattern;
  upstream: (env: Env) => Fetcher;
  teamId: string;
}

const ROUTES: Route[] = [
  {
    pattern: new URLPattern({ pathname: "/app/dashboard{/*}?" }),
    upstream: (env) => env.TEAM_A,
    teamId: "team-a",
  },
  {
    pattern: new URLPattern({ pathname: "/app/reports{/*}?" }),
    upstream: (env) => env.TEAM_A,
    teamId: "team-a",
  },
  {
    pattern: new URLPattern({ pathname: "/app/catalog{/*}?" }),
    upstream: (env) => env.TEAM_B,
    teamId: "team-b",
  },
  {
    pattern: new URLPattern({ pathname: "/app/search{/*}?" }),
    upstream: (env) => env.TEAM_B,
    teamId: "team-b",
  },
  {
    pattern: new URLPattern({ pathname: "/app/checkout{/*}?" }),
    upstream: (env) => env.TEAM_C,
    teamId: "team-c",
  },
  {
    pattern: new URLPattern({ pathname: "/app/orders{/*}?" }),
    upstream: (env) => env.TEAM_C,
    teamId: "team-c",
  },
];

/** Resolve session from cookie, return userId or null. */
async function resolveSession(
  request: Request,
  env: Env
): Promise<{ userId: string; role: string } | null> {
  const cookieHeader = request.headers.get("Cookie") ?? "";
  const match = cookieHeader
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${env.AUTH_COOKIE_NAME}=`));

  if (!match) return null;
  const token = match.slice(env.AUTH_COOKIE_NAME.length + 1);
  return env.SESSION_KV.get<{ userId: string; role: string }>(token, "json");
}

/** Strip headers that must not reach the browser. */
const INTERNAL_HEADERS = new Set([
  "x-internal-team",
  "x-internal-trace",
  "cf-connecting-ip",
  "x-forwarded-for",
]);

function mergeHeaders(
  upstream: Headers,
  additions: Record<string, string>
): Headers {
  const out = new Headers(upstream);
  for (const [k] of [...out.entries()]) {
    if (INTERNAL_HEADERS.has(k.toLowerCase())) out.delete(k);
  }
  for (const [k, v] of Object.entries(additions)) out.set(k, v);
  return out;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Auth guard ──────────────────────────────────────────────────
    const session = await resolveSession(request, env);
    if (!session) {
      return Response.redirect(`${url.origin}/login?next=${encodeURIComponent(url.pathname)}`, 302);
    }

    // ── Route matching ──────────────────────────────────────────────
    const route = ROUTES.find((r) => r.pattern.test(url));
    if (!route) {
      return new Response("Not found", { status: 404 });
    }

    // ── Forward to upstream with internal context headers ───────────
    const upstreamRequest = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        "X-User-Id": session.userId,
        "X-User-Role": session.role,
        "X-Internal-Team": route.teamId,
      }),
    });

    const upstreamResponse = await route.upstream(env).fetch(upstreamRequest);

    // ── Non-HTML responses pass through with header cleanup ─────────
    const contentType = upstreamResponse.headers.get("Content-Type") ?? "";
    if (!contentType.includes("text/html")) {
      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        headers: mergeHeaders(upstreamResponse.headers, {
          "X-Mfe-Team": route.teamId,
        }),
      });
    }

    // ── HTML: inject shared nav fragment via HTMLRewriter ───────────
    const navHtml = NAV_FRAGMENT;

    const transformed = new HTMLRewriter()
      .on("body", {
        element(el) {
          el.prepend(navHtml, { html: true });
        },
      })
      .on("head", {
        element(el) {
          // Inject team identifier for client-side telemetry
          el.append(
            `<meta name="mfe-team" content="${route.teamId}">`,
            { html: true }
          );
        },
      })
      .transform(
        new Response(upstreamResponse.body, {
          status: upstreamResponse.status,
          headers: mergeHeaders(upstreamResponse.headers, {
            "X-Mfe-Team": route.teamId,
            "Cache-Control": "private, no-store",
          }),
        })
      );

    return transformed;
  },
};

// ---------------------------------------------------------------------------
// Shared nav fragment — in production, fetch this from a KV key or
// a stable asset URL and cache it at module init time (it never changes
// per isolate lifetime, so this is safe).
// ---------------------------------------------------------------------------
const NAV_FRAGMENT = `
<nav id="mfe-shell-nav" style="font-family:sans-serif;padding:8px 16px;background:#1a1a2e;color:#fff;display:flex;gap:16px">
  <a  style="color:#e0e0e0;text-decoration:none">Dashboard</a>
  <a    style="color:#e0e0e0;text-decoration:none">Catalog</a>
  <a   style="color:#e0e0e0;text-decoration:none">Checkout</a>
  <a     style="color:#e0e0e0;text-decoration:none">Orders</a>
</nav>
`.trim();
```

---

## Auth cookie propagation across micro-frontends

```typescript
// src/session.ts — utilities used by individual team Workers
// Each team Worker reads the forwarded X-User-Id / X-User-Role headers
// set by the shell rather than decoding the cookie themselves.

export interface ShellSession {
  userId: string;
  role: string;
}

/**
 * Extract the session injected by the shell Worker.
 * Team Workers trust these headers because they are only reachable
 * via the shell's service binding — they are not exposed publicly.
 */
export function getShellSession(request: Request): ShellSession | null {
  const userId = request.headers.get("X-User-Id");
  const role = request.headers.get("X-User-Role");
  if (!userId || !role) return null;
  return { userId, role };
}

// Example usage in a team Worker:
//
// import { getShellSession } from "../shared/session";
//
// export default {
//   async fetch(request: Request, env: TeamEnv): Promise<Response> {
//     const session = getShellSession(request);
//     if (!session) return new Response("Forbidden", { status: 403 });
//     // session.userId and session.role are available here
//     ...
//   }
// };
```

---

## Anti-patterns

- **Letting team Workers read the auth cookie directly** — team Workers behind a service binding should trust the shell-injected headers, not re-decode the cookie; two sources of truth diverge during auth migrations.
- **Using a wildcard `*` route before specific routes** — `URLPattern` tests routes in array order; put the most specific patterns first or a wildcard will shadow them.
- **Injecting the nav fragment on every response including API calls** — gate HTMLRewriter on `Content-Type: text/html` only; transforming binary or JSON responses corrupts them.
- **Propagating `CF-Connecting-IP` or `X-Forwarded-For` to team Workers** — these contain real client IPs; strip them before forwarding to team Workers and inject a sanitised `X-Client-Country` derived from `request.cf.country` instead.

---

## Gotchas

- `HTMLRewriter` streams the response body; do not buffer the full body before transforming — pass the upstream response body directly to avoid doubling memory usage.
- `URLPattern` in Workers uses the WHATWG URL Pattern spec; the `{/*}?` suffix matches an optional trailing path segment; test edge cases with the Workers playground before deploying.
- Service bindings (`Fetcher`) do not add HTTP overhead — they are direct in-process function calls within the same Cloudflare PoP; latency is sub-millisecond.
- Pages deployments used as service binding targets must be **named services** — enable "Service binding" in the Pages project settings and give the Pages project a stable service name.

---

## Verification

```bash
# Deploy shell Worker
wrangler deploy --name mfe-shell

# Verify routing: dashboard request reaches Team A
curl -si https://mfe-shell.example.workers.dev/app/dashboard \
  -H 'Cookie: __mfe_session=<valid-token>' \
  | grep -E 'HTTP|X-Mfe-Team|mfe-shell-nav'

# Verify nav injection in HTML response
curl -s https://mfe-shell.example.workers.dev/app/catalog \
  -H 'Cookie: __mfe_session=<valid-token>' \
  | grep 'mfe-shell-nav'

# Verify unauthenticated requests redirect to /login
curl -si https://mfe-shell.example.workers.dev/app/orders \
  | grep -E 'HTTP|Location'
# Expected: HTTP/2 302 ... Location: .../login?next=%2Fapp%2Forders
```

---

## Related

- `sidecar-pattern-workers-service-binding.md`
- `shared-nothing-workers-stateless-design.md`

---

## Sources

- Cloudflare Workers HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Workers Service Bindings — https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Micro Frontends (Martin Fowler) — https://martinfowler.com/articles/micro-frontends.html
