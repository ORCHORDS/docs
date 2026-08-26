# Turborepo Remote Cache Cloudflare R2 Backend

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

CI pipelines for the example project monorepo run full `turbo build` and `turbo test` passes on every PR, even when only one package changed. Without a shared remote cache, each GitHub Actions runner re-compiles unchanged packages from scratch, adding 3–8 minutes per run. Moving the Turborepo remote cache to Cloudflare R2 gives zero-egress-cost storage with a Workers-based cache API that lives in the same Cloudflare account as the deployed workers.

## Context

Turborepo's remote cache protocol is an HTTP API that accepts PUT and GET requests keyed by artifact hash. Any HTTP server implementing the Vercel Remote Cache API spec can serve as a backend. A lightweight Cloudflare Worker proxying reads and writes to an R2 bucket satisfies the spec and adds per-team token auth without requiring a third-party service.

## Provisioning the R2 Bucket and Worker

Create the R2 bucket via Wrangler, then deploy the cache Worker. The Worker only needs an R2 binding and a secret token for Bearer authentication.

```bash
# Create R2 bucket
wrangler r2 bucket create example project-turbo-cache

# Generate a long random token and store as a secret
openssl rand -hex 32 | tr -d '\n' > .turbo-token
wrangler secret put TURBO_TOKEN --env production < .turbo-token
```

```toml
# workers/turbo-cache/wrangler.toml
name = "example project-turbo-cache"
main = "src/index.ts"
compatibility_date = "2026-06-01"

[[r2_buckets]]
binding = "CACHE"
bucket_name = "example project-turbo-cache"

[vars]
TURBO_API_URL = "https://turbo-cache.example project.workers.dev"
```

## Implementing the Cache Worker

The Vercel Remote Cache API uses two routes: `GET /v8/artifacts/:hash` and `PUT /v8/artifacts/:hash`. A minimal Workers implementation:

```typescript
// workers/turbo-cache/src/index.ts
export interface Env {
  CACHE: R2Bucket;
  TURBO_TOKEN: string;
}

function authorize(request: Request, env: Env): boolean {
  const auth = request.headers.get("Authorization") ?? "";
  return auth === `Bearer ${env.TURBO_TOKEN}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!authorize(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    // Route: /v8/artifacts/:hash
    const match = url.pathname.match(/^\/v8\/artifacts\/([a-f0-9]+)$/);
    if (!match) return new Response("Not Found", { status: 404 });

    const key = match[1];

    if (request.method === "GET") {
      const obj = await env.CACHE.get(key);
      if (!obj) return new Response("Cache Miss", { status: 404 });
      return new Response(obj.body, {
        headers: {
          "Content-Type": "application/octet-stream",
          "x-artifact-duration": obj.customMetadata?.duration ?? "0",
        },
      });
    }

    if (request.method === "PUT") {
      const duration = request.headers.get("x-artifact-duration") ?? "0";
      await env.CACHE.put(key, request.body!, {
        customMetadata: { duration },
      });
      return new Response(JSON.stringify({ urls: { [key]: `/${key}` } }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
};
```

## Configuring Turborepo to Use the Worker

Set the remote cache endpoint and token in the monorepo root. The token is read from the environment at CI time and from a local `.env` file in development.

```jsonc
// turbo.json (root)
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true,
    "apiUrl": "https://example project-turbo-cache.example project.workers.dev",
    "teamId": "example project"
  },
  "pipeline": {
    "build": { "outputs": [".svelte-kit/**", "dist/**"] },
    "test": { "outputs": [] },
    "typecheck": { "outputs": [] }
  }
}
```

```yaml
# .github/workflows/ci.yml (relevant env section)
env:
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: example project
  TURBO_REMOTE_ONLY: "false"   # fall through to local cache on miss
```

Run CI with `turbo run build test --cache-dir=.turbo` to let Turborepo use both local and remote caches.

## Lifecycle Management and Cache Eviction

R2 has no native TTL on objects. Implement eviction via a scheduled Worker that deletes objects older than N days:

```typescript
// workers/turbo-cache/src/evict.ts
export async function evict(env: Env, maxAgeDays = 14): Promise<void> {
  const cutoff = Date.now() - maxAgeDays * 86_400_000;
  let cursor: string | undefined;

  do {
    const list = await env.CACHE.list({ cursor, limit: 1000 });
    const toDelete = list.objects
      .filter((o) => o.uploaded.getTime() < cutoff)
      .map((o) => o.key);

    if (toDelete.length > 0) {
      await env.CACHE.delete(toDelete);
    }

    cursor = list.truncated ? list.cursor : undefined;
  } while (cursor);
}
```

Attach it to a cron trigger in `wrangler.toml`:

```toml
[triggers]
crons = ["0 3 * * *"]   # 03:00 UTC daily
```

## Anti-patterns

- Storing the TURBO_TOKEN in plaintext in `turbo.json` or committed `.env` files — use `wrangler secret` and GitHub Actions secrets exclusively.
- Using a single R2 bucket across all teams/projects without key namespacing — prefix keys with `{teamId}/{hash}` to isolate projects.
- Skipping the `x-artifact-duration` metadata — Turborepo uses this value for cache performance dashboards; missing it breaks `turbo run --summarize` output.
- Deploying the cache Worker without authentication — an open endpoint lets any actor pollute or exhaust your cache bucket.
- Setting `TURBO_REMOTE_ONLY=true` in CI — if the Worker is temporarily unavailable, all builds fail even when local cache would satisfy them.

## Gotchas

- R2 free tier includes 10 GB storage and 1 million Class A (write) operations per month. A large monorepo with frequent CI runs can exceed Class A limits; monitor via Cloudflare dashboard.
- Turborepo hashes include the Node.js version, OS, and env vars tagged with `env` in `turbo.json`. Mismatched CI images will always miss cache.
- The Worker must be deployed before CI can write to the cache. Add the Workers deploy to infrastructure bootstrapping, not to the app CI pipeline.
- R2 object keys are case-sensitive. Turborepo artifact hashes are lowercase hex, but confirm no tooling transforms them to uppercase.
- `wrangler dev` runs the cache Worker against a local R2 simulator; local dev hits the simulator, not the production bucket, when `TURBO_API_URL` points to localhost.

## Verification

Run `turbo run build --dry=json | jq '.packages[] | {name, cache}'` after a warm CI run. All unchanged packages should show `"cache": {"status": "HIT", "source": "REMOTE"}`. Monitor R2 metrics in the Cloudflare dashboard for PUT/GET counts per pipeline run.

## Related

- monorepo-turborepo-remote-cache-ci.md
- monorepo-pnpm-turborepo-2026.md
- workers-kv-r2-d1-storage-selection.md
- wrangler-secrets-bulk-management-ci.md
- monorepo-ci-parallelization.md

## Sources

- https://turbo.build/repo/docs/core-concepts/remote-caching
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/r2/
- https://github.com/ducktors/turborepo-remote-cache (reference implementation)
