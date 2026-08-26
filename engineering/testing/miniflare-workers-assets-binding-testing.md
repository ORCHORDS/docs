# Miniflare Workers Assets Binding Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker serves a Single-Page Application (SPA) or static site by combining `ASSETS` binding (Workers Static Assets) with dynamic API routes. You need Vitest + Miniflare tests that exercise the asset fallback chain — confirming that `/api/*` routes are handled by Worker logic, known static paths are served from the simulated asset store, and unknown paths receive the correct 404 or `index.html` SPA fallback.

## Context

Cloudflare Workers Static Assets (`ASSETS` binding) replaced Workers Sites in 2024. The Worker receives a `Fetcher`-like `ASSETS` binding that proxies requests to the uploaded static file store. In Miniflare tests via `@cloudflare/vitest-pool-workers`, the binding can be simulated using `miniflare`'s `assets` configuration option or by providing a mock `Fetcher` that returns synthetic responses. This enables unit and integration tests of the routing layer without deploying to Cloudflare.

---

## 1. wrangler.toml Configuration

```toml
# wrangler.toml
name        = "my-app"
main        = "src/index.ts"
compatibility_date = "2024-09-23"

[assets]
directory   = "./dist"
binding     = "ASSETS"
html_handling = "auto-trailing-slash"
not_found_handling = "single-page-application"
```

---

## 2. Worker Router with ASSETS Fallback

```typescript
// src/index.ts
interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Dynamic API routes handled by Worker
    if (url.pathname.startsWith("/api/")) {
      if (url.pathname === "/api/health") {
        return Response.json({ ok: true, ts: Date.now() });
      }
      if (url.pathname === "/api/posts" && request.method === "GET") {
        const rows = await env.DB.prepare("SELECT id, title FROM posts LIMIT 20").all();
        return Response.json(rows.results);
      }
      return Response.json({ error: "Not Found" }, { status: 404 });
    }

    // Everything else: delegate to ASSETS binding (SPA fallback included)
    return env.ASSETS.fetch(request);
  },
};
```

---

## 3. vitest.config.ts with Assets Simulation

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // In Miniflare, ASSETS can be pointed at a local directory.
        // For unit tests we override with a mock fetcher via SELF.
        miniflare: {
          // assets directory simulates the static file store
          assetsPath: "./dist",
        },
      },
    },
  },
});
```

For environments where `assetsPath` is not available, use a mock `Fetcher` injected through the test environment (see Section 5).

---

## 4. API Route Tests (No ASSETS Involvement)

```typescript
// src/index.test.ts
import { describe, it, expect } from "vitest";
import { env, createExecutionContext, waitOnExecutionContext, SELF } from "cloudflare:test";

describe("API routes", () => {
  it("GET /api/health returns ok:true", async () => {
    const req = new Request("http://localhost/api/health");
    const ctx = createExecutionContext();
    const res = await SELF.fetch(req, ctx);
    await waitOnExecutionContext(ctx);

    expect(res.status).toBe(200);
    const body = await res.json<{ ok: boolean }>();
    expect(body.ok).toBe(true);
  });

  it("GET /api/posts returns array", async () => {
    // Seed D1 for this test
    await env.DB.exec("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, title TEXT)");
    await env.DB.prepare("INSERT OR IGNORE INTO posts VALUES (1, 'Hello D1')").run();

    const res = await SELF.fetch("http://localhost/api/posts");
    expect(res.status).toBe(200);
    const posts = await res.json<{ id: number; title: string }[]>();
    expect(posts.length).toBeGreaterThan(0);
  });

  it("unknown /api/* path returns 404 JSON", async () => {
    const res = await SELF.fetch("http://localhost/api/nonexistent");
    expect(res.status).toBe(404);
    const body = await res.json<{ error: string }>();
    expect(body.error).toBe("Not Found");
  });
});
```

---

## 5. ASSETS Binding Mock for Static Route Tests

When `assetsPath` is not wired up in the test pool, inject a mock `Fetcher` to simulate asset serving behaviour.

```typescript
// src/assets.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "./index";

/**
 * Build a mock ASSETS fetcher.
 * fileMap: path → { status, body, contentType }
 */
function mockAssets(
  fileMap: Record<string, { status: number; body: string; contentType?: string }>
): Fetcher {
  return {
    fetch: async (input: RequestInfo | URL): Promise<Response> => {
      const url = new URL(typeof input === "string" ? input : input.toString());
      const entry = fileMap[url.pathname];
      if (entry) {
        return new Response(entry.body, {
          status: entry.status,
          headers: { "Content-Type": entry.contentType ?? "text/html" },
        });
      }
      // SPA fallback: serve index.html for unknown paths
      const fallback = fileMap["/index.html"];
      if (fallback) {
        return new Response(fallback.body, {
          status: 200,
          headers: { "Content-Type": "text/html" },
        });
      }
      return new Response("Not Found", { status: 404 });
    },
  } as unknown as Fetcher;
}

const STATIC_FILES = {
  "/index.html":      { status: 200, body: "<!doctype html><html>…</html>" },
  "/about.html":      { status: 200, body: "<!doctype html><html>About</html>" },
  "/assets/app.js":  { status: 200, body: "// bundle", contentType: "application/javascript" },
  "/assets/app.css": { status: 200, body: "body{}", contentType: "text/css" },
};

const fakeAssets = mockAssets(STATIC_FILES);

function buildEnv(): { ASSETS: Fetcher; DB: D1Database } {
  return {
    ASSETS: fakeAssets,
    DB: {} as D1Database, // not used in asset tests
  };
}

describe("ASSETS binding fallback", () => {
  it("serves known static file", async () => {
    const req = new Request("http://localhost/about.html");
    const res = await worker.fetch(req, buildEnv(), {} as ExecutionContext);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain("About");
  });

  it("serves SPA index.html for unknown client-side route", async () => {
    const req = new Request("http://localhost/some/deep/spa/route");
    const res = await worker.fetch(req, buildEnv(), {} as ExecutionContext);
    expect(res.status).toBe(200);
    const body = await res.text();
    expect(body).toContain("<!doctype html>");
  });

  it("serves JS bundle with correct content-type", async () => {
    const req = new Request("http://localhost/assets/app.js");
    const res = await worker.fetch(req, buildEnv(), {} as ExecutionContext);
    expect(res.headers.get("Content-Type")).toContain("application/javascript");
  });

  it("API routes are NOT forwarded to ASSETS", async () => {
    // Spy on ASSETS.fetch to confirm it is never called for /api/
    const assetsFetchSpy = vi.spyOn(fakeAssets, "fetch");
    const req = new Request("http://localhost/api/health");
    await worker.fetch(req, buildEnv(), {} as ExecutionContext);
    expect(assetsFetchSpy).not.toHaveBeenCalled();
    assetsFetchSpy.mockRestore();
  });
});
```

---

## 6. Not-Found Handling Mode Tests

Test the difference between `not_found_handling = "404-page"` vs `"single-page-application"`.

```typescript
describe("not_found_handling modes", () => {
  it("SPA mode returns index.html for missing paths", async () => {
    const assets = mockAssets({ "/index.html": { status: 200, body: "<app>" } });
    const env = { ASSETS: assets, DB: {} as D1Database };
    const res = await worker.fetch(
      new Request("http://localhost/missing-page"),
      env,
      {} as ExecutionContext
    );
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("<app>");
  });

  it("404-page mode returns 404 for missing paths (custom mock)", async () => {
    // Simulate strict 404 mode — no index.html fallback
    const strictAssets: Fetcher = {
      fetch: async () => new Response("Not Found", { status: 404 }),
    } as unknown as Fetcher;
    const env = { ASSETS: strictAssets, DB: {} as D1Database };
    const res = await worker.fetch(
      new Request("http://localhost/missing-page"),
      env,
      {} as ExecutionContext
    );
    expect(res.status).toBe(404);
  });
});
```

---

## Anti-patterns

- **Testing ASSETS behaviour without a mock** — if `ASSETS.fetch` is undefined in the test environment, static route tests throw `TypeError: env.ASSETS.fetch is not a function`; always provide a real or mock fetcher.
- **Asserting exact HTML bodies** — static file content changes on every build; assert structural properties (status code, content-type, `<doctype` prefix) rather than exact strings.
- **Routing `/api/` requests through ASSETS** — the Worker must check the path before calling `env.ASSETS.fetch`; the spy test in Section 5 catches this regression.
- **Using `vi.mock("cloudflare:test")` for ASSETS** — the `Fetcher` type is a runtime binding, not an ES module; mock it by constructing an object with a `.fetch` method.

## Gotchas

- `ASSETS` binding is a `Fetcher`, not a `KVNamespace`; it only exposes `.fetch(request)` — there is no `.get()`, `.put()`, or `.list()`.
- In production, `not_found_handling = "single-page-application"` serves `index.html` with a `200` status for all unknown paths; tests must assert `200`, not `404`, for SPA route assertions.
- `html_handling = "auto-trailing-slash"` redirects `/about` → `/about/`; Miniflare's asset directory simulation may not replicate this — test trailing-slash redirects in an integration environment against `wrangler dev`.
- The `assetsPath` option in `@cloudflare/vitest-pool-workers` reads the directory at test start; changes to `./dist` during a `--watch` session require restarting the pool.

## Verification

```bash
# Run asset binding tests
npx vitest run src/assets.test.ts src/index.test.ts

# Confirm the mock ASSETS spy assertion passes
npx vitest run src/assets.test.ts --reporter=verbose

# Integration check: serve locally with real ASSETS
npx wrangler dev --local
curl http://localhost:8787/api/health
curl http://localhost:8787/some/spa/route
```

## Related

- `miniflare-r2-event-notification-testing.md`
- `miniflare-multi-worker-environment-setup.md`
- `vitest-cloudflare-pool-workers.md`
- `playwright-cloudflare-pages-e2e.md`
- `visual-regression-testing-cloudflare-pages.md`

## Sources

- https://developers.cloudflare.com/workers/static-assets/
- https://developers.cloudflare.com/workers/static-assets/binding/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- https://developers.cloudflare.com/workers/static-assets/routing/
