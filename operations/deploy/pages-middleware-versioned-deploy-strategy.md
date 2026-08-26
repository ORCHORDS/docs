# Pages Functions Middleware Versioned Deploy Strategy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A example project Cloudflare Pages application uses Pages Functions middleware to enforce authentication, inject CORS headers, and log requests. During a deploy, the middleware chain must upgrade atomically with the page assets it protects. If middleware logic and frontend assets deploy out of step — or if a new middleware version is not backward-compatible with in-flight session tokens — users see spurious 401s, broken CORS preflight, or stale security headers. This article covers how to version Pages Functions middleware, validate the chain in CI, and coordinate middleware and asset deploys safely.

## Context

Pages Functions middleware lives in `functions/_middleware.ts` (global) or `functions/api/_middleware.ts` (path-scoped). Unlike Workers, Pages Functions are bundled and deployed as part of `wrangler pages deploy` — there is no separate versioning primitive for middleware alone. This means every frontend asset change triggers a potential middleware re-evaluation, and any middleware regression ships with the asset deploy. Treating the middleware as a versioned, testable contract (rather than incidental glue code) prevents silent regressions.

---

## 1. Middleware Version Header Contract

Stamp every response with a `X-Middleware-Version` header. This lets smoke tests confirm the correct middleware version is live after each deploy.

```typescript
// functions/_middleware.ts
const MIDDLEWARE_VERSION = "2.4.1"; // increment on any middleware change

export const onRequest: PagesFunction[] = [
  authMiddleware,
  corsMiddleware,
  loggingMiddleware,
  versionStampMiddleware,
];

const versionStampMiddleware: PagesFunction = async (ctx) => {
  const response = await ctx.next();
  const mutable = new Response(response.body, response);
  mutable.headers.set("X-Middleware-Version", MIDDLEWARE_VERSION);
  return mutable;
};
```

---

## 2. Ordered Middleware Chain with Typed Context

```typescript
// functions/_middleware.ts (continued)
import type { EventContext } from "@cloudflare/workers-types";

export interface PageData {
  user: { id: string; role: string } | null;
  requestId: string;
}

const loggingMiddleware: PagesFunction<Env, "/", PageData> = async (ctx) => {
  ctx.data.requestId = crypto.randomUUID();
  const start = Date.now();
  const res = await ctx.next();
  console.log(JSON.stringify({
    requestId: ctx.data.requestId,
    method: ctx.request.method,
    url: ctx.request.url,
    status: res.status,
    durationMs: Date.now() - start,
    middlewareVersion: MIDDLEWARE_VERSION,
  }));
  return res;
};

const authMiddleware: PagesFunction<Env, "/", PageData> = async (ctx) => {
  const token = ctx.request.headers.get("Authorization")?.replace("Bearer ", "");
  if (!token) {
    ctx.data.user = null;
    return ctx.next(); // unauthenticated — let route handlers decide
  }
  // Validate JWT; set ctx.data.user for downstream middleware and Functions
  ctx.data.user = await verifyToken(token, ctx.env);
  return ctx.next();
};

const corsMiddleware: PagesFunction<Env, "/", PageData> = async (ctx) => {
  const origin = ctx.request.headers.get("Origin") ?? "";
  const allowed = ctx.env.ALLOWED_ORIGINS?.split(",") ?? [];

  if (ctx.request.method === "OPTIONS") {
    if (allowed.includes(origin)) {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin,
          "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
          "Access-Control-Allow-Headers": "Authorization,Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }
    return new Response("Forbidden", { status: 403 });
  }
  const response = await ctx.next();
  const mutable = new Response(response.body, response);
  if (allowed.includes(origin)) {
    mutable.headers.set("Access-Control-Allow-Origin", origin);
  }
  return mutable;
};

async function verifyToken(token: string, env: Env): Promise<{ id: string; role: string } | null> {
  // JWT verification logic (example: use a JWKS endpoint cached in KV)
  return null; // replace with real implementation
}
```

---

## 3. Path-Scoped Middleware for API vs. Static Assets

Avoid applying auth to static asset routes by scoping middleware per path:

```
functions/
  _middleware.ts        ← global: logging, CORS, version stamp
  api/
    _middleware.ts      ← API-only: auth enforcement
    users.ts
    health.ts
```

```typescript
// functions/api/_middleware.ts — auth required on all /api/* routes
export const onRequest: PagesFunction<Env, "/api/*", PageData> = async (ctx) => {
  if (!ctx.data.user) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  return ctx.next();
};
```

---

## 4. CI Middleware Compatibility Test Before Deploy

Run a lightweight test harness in CI using Miniflare or `wrangler pages dev` to validate the middleware chain against a known request matrix:

```typescript
// tests/middleware.test.ts (Vitest + @cloudflare/vitest-pool-workers)
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("middleware chain", () => {
  it("stamps X-Middleware-Version on every response", async () => {
    const res = await SELF.fetch("http://localhost/");
    expect(res.headers.get("X-Middleware-Version")).toBeTruthy();
  });

  it("returns 401 on /api/* without token", async () => {
    const res = await SELF.fetch("http://localhost/api/users");
    expect(res.status).toBe(401);
  });

  it("handles CORS preflight for allowed origin", async () => {
    const res = await SELF.fetch("http://localhost/api/users", {
      method: "OPTIONS",
      headers: { Origin: "https://example.com" },
    });
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("https://example.com");
  });
});
```

Add to CI pipeline:

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Test middleware chain
  run: npx vitest run tests/middleware.test.ts

- name: Deploy to Pages
  run: wrangler pages deploy dist --project-name example project-frontend --branch main
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 5. Atomic Middleware + Asset Deploy via Direct Upload

Use `wrangler pages deploy` with `--commit-dirty=false` to ensure the asset manifest and middleware bundle come from the same build artifact. Never deploy assets and middleware from separate build steps or pipelines.

```bash
# Single atomic deploy — assets and Functions in one wrangler call
pnpm build          # outputs dist/ including functions/ symlink or copy
wrangler pages deploy dist \
  --project-name example project-frontend \
  --branch main \
  --commit-message "chore: deploy v$(cat package.json | jq -r .version)" \
  --commit-dirty false
```

---

## 6. Post-Deploy Middleware Version Smoke Test

```bash
#!/usr/bin/env bash
set -euo pipefail

EXPECTED_VERSION="2.4.1"
DEPLOYMENT_URL="https://example project-frontend.example.com"

ACTUAL=$(curl -sI "$DEPLOYMENT_URL" | grep -i "x-middleware-version" | awk '{print $2}' | tr -d '\r')

if [ "$ACTUAL" != "$EXPECTED_VERSION" ]; then
  echo "Middleware version mismatch: expected $EXPECTED_VERSION, got '$ACTUAL'"
  exit 1
fi

echo "Middleware version gate passed: $ACTUAL"
```

---

## Anti-patterns

- Mutating `ctx.data` in a downstream middleware after an upstream middleware has already read it — execution order in `PagesFunction[]` arrays is top-to-bottom; ordering bugs cause auth bypasses.
- Throwing an unhandled exception inside middleware — Pages Functions wraps this as a 500 and bypasses `versionStampMiddleware`, making smoke tests fail for the wrong reason.
- Deploying middleware changes without incrementing `MIDDLEWARE_VERSION` — makes it impossible to confirm which version is live after a deploy via the header check.
- Using path-scoped middleware in `functions/api/_middleware.ts` to enforce auth, but also having a global `_middleware.ts` that calls `ctx.next()` unconditionally before auth runs — the order depends on nesting depth, not array position.

## Gotchas

- Pages Functions middleware runs in the same isolate as the Function handlers but is a separate bundle entry point. Changes to shared utilities imported by both middleware and handlers require a full rebuild, not just a middleware redeploy.
- `ctx.data` is typed per-Function invocation. Mutating it in one middleware does not affect a *different* path's middleware chain.
- `wrangler pages deploy` does not support per-Function deployment — the entire `functions/` directory deploys atomically. You cannot deploy a middleware hotfix without also deploying all other Function changes in the working tree.
- The `MIDDLEWARE_VERSION` constant in the source must be updated manually. Forgetting to bump it after logic changes is the most common cause of stale smoke-test results.

## Verification

```bash
# 1. Confirm middleware version header
curl -sI https://example project-frontend.example.com | grep -i x-middleware-version

# 2. Confirm auth gate is active on /api/*
curl -s -o /dev/null -w "%{http_code}" https://example project-frontend.example.com/api/users

# 3. Confirm CORS preflight returns 204 for allowed origin
curl -s -o /dev/null -w "%{http_code}" -X OPTIONS \
  -H "Origin: https://example.com" \
  https://example project-frontend.example.com/api/users
```

## Related

- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-functions-env-var-management.md`
- `cloudflare-pages-preview-deployments.md`
- `deployment-verification-smoke-tests.md`
- `feature-flag-deployment-decoupling.md`

## Sources

- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/pages/functions/bindings/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
