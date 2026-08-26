# Turborepo Remote Cache Backed by Cloudflare R2

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

CI builds in a Turborepo monorepo take 4–8 minutes even when only one package changed,
because Turborepo's local cache lives on the runner's ephemeral disk and is discarded
after each run. You want a persistent remote cache that all branches and all CI runners
share, without paying for Vercel's hosted cache or running a separate cache server.

## Context

Turborepo supports a self-hosted remote cache via a simple HTTP API (the "Remote Cache
Protocol"). Any server that implements `PUT /v8/artifacts/:hash` and
`GET /v8/artifacts/:hash` can act as the backend. A Cloudflare Worker backed by an R2
bucket implements this API in ~80 lines of TypeScript and costs effectively nothing at
typical monorepo artifact sizes (artifacts are gzip-compressed build outputs, usually
1–50 MB each; R2 charges $0.015/GB/month with no egress fee inside Cloudflare).

Stack: Turborepo ≥ 2.x, Wrangler 3.x, R2, TypeScript, pnpm workspaces.

## Deploying the Cache Worker

Create a dedicated `apps/turbo-cache` package in your monorepo:

```
apps/
  turbo-cache/
    src/
      index.ts
    wrangler.toml
    package.json
```

`apps/turbo-cache/wrangler.toml`:

```toml
name = "turbo-cache"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[[r2_buckets]]
binding = "CACHE"
bucket_name = "turbo-cache-prod"

[vars]
# Shared secret validated on every request; rotate via `wrangler secret put`
# TURBO_TOKEN is set as a secret, not a plain var
```

`apps/turbo-cache/src/index.ts`:

```typescript
export interface Env {
  CACHE: R2Bucket;
  TURBO_TOKEN: string; // wrangler secret
}

function authorized(request: Request, env: Env): boolean {
  const header = request.headers.get("Authorization") ?? "";
  // Turborepo sends "Bearer <token>"
  return header === `Bearer ${env.TURBO_TOKEN}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!authorized(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    // Path: /v8/artifacts/<hash>
    const match = url.pathname.match(/^\/v8\/artifacts\/([0-9a-f]+)$/i);
    if (!match) {
      return new Response("Not Found", { status: 404 });
    }
    const key = match[1];

    if (request.method === "PUT") {
      const body = request.body;
      if (!body) return new Response("Bad Request", { status: 400 });
      await env.CACHE.put(key, body, {
        httpMetadata: { contentEncoding: "zstd" },
      });
      return new Response(null, { status: 204 });
    }

    if (request.method === "GET" || request.method === "HEAD") {
      const object = await env.CACHE.get(key);
      if (!object) return new Response("Not Found", { status: 404 });
      const headers = new Headers();
      object.writeHttpMetadata(headers);
      headers.set("etag", object.httpEtag);
      if (request.method === "HEAD") {
        return new Response(null, { status: 200, headers });
      }
      return new Response(object.body, { status: 200, headers });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
} satisfies ExportedHandler<Env>;
```

Deploy once:

```bash
# Create the bucket first
wrangler r2 bucket create turbo-cache-prod

# Set the shared secret (use a random 32-char hex string)
wrangler secret put TURBO_TOKEN --name turbo-cache

# Deploy the worker
wrangler deploy --config apps/turbo-cache/wrangler.toml
```

## Configuring Turborepo to Use the Remote Cache

In the repo root `turbo.json`:

```json
{
  "$schema": "https://turborepo.com/schema.json",
  "remoteCache": {
    "enabled": true,
    "apiUrl": "https://turbo-cache.<your-subdomain>.workers.dev"
  }
}
```

Set environment variables in CI (GitHub Actions example):

```yaml
# .github/workflows/ci.yml
env:
  TURBO_TOKEN: ${{ secrets.TURBO_CACHE_TOKEN }}
  TURBO_TEAM: orchords          # arbitrary; Turborepo uses it as a namespace prefix
  TURBO_REMOTE_CACHE_SIGNATURE_KEY: ${{ secrets.TURBO_SIGNATURE_KEY }}
```

For local development, put these in `.env.local` (git-ignored):

```bash
TURBO_TOKEN=<your-token>
TURBO_TEAM=orchords
# optional: sign artifacts so the worker can reject tampered cache entries
TURBO_REMOTE_CACHE_SIGNATURE_KEY=<32-char-hex>
```

## Artifact Signature Verification (Optional but Recommended)

Turborepo can HMAC-sign each artifact before upload and verify on download. Add
verification to the worker:

```typescript
import { createHmac } from "node:crypto";   // available in Workers via compat flag

async function verifySignature(
  body: ArrayBuffer,
  signatureHeader: string | null,
  secret: string
): Promise<boolean> {
  if (!signatureHeader) return false;
  const expected = createHmac("sha256", secret)
    .update(new Uint8Array(body))
    .digest("hex");
  return signatureHeader === expected;
}
```

Enable the compat flag in `wrangler.toml`:

```toml
compatibility_flags = ["nodejs_compat"]
```

## Turborepo Pipeline Integration

Ensure the cache worker is deployed before any pipeline task that reads from cache:

```json
// turbo.json pipeline excerpt
{
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**"],
      "cache": true
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"],
      "cache": true
    }
  }
}
```

Run with remote cache explicitly enabled to confirm hits:

```bash
pnpm turbo build --remote-only
# Output: cache miss on first run, cache hit on subsequent runs
```

## Cache Eviction with R2 Lifecycle Rules

R2 does not yet support automatic object expiration via lifecycle rules (as of 2026-08).
Implement a scheduled Worker to evict stale entries:

```typescript
// Add to the same worker
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000; // 7 days
    let cursor: string | undefined;
    do {
      const listed = await env.CACHE.list({ cursor, limit: 1000 });
      for (const obj of listed.objects) {
        if (obj.uploaded.getTime() < cutoff) {
          await env.CACHE.delete(obj.key);
        }
      }
      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);
  },
} satisfies ExportedHandler<Env>;
```

Add the cron trigger in `wrangler.toml`:

```toml
[triggers]
crons = ["0 3 * * *"]   # daily at 03:00 UTC
```

## Anti-patterns

- **Storing the token in `turbo.json`** — `turbo.json` is committed to the repo. Always
  use environment variables or `wrangler secret` for the bearer token.
- **Skipping `TURBO_TEAM`** — Without it, all branches share a flat key namespace. Set
  `TURBO_TEAM` so Turborepo namespaces keys by team, avoiding cross-repo collisions if
  multiple projects use the same bucket.
- **Deploying the cache worker inside Turborepo's own pipeline** — The cache worker must
  exist before any pipeline run. Deploy it via a separate `wrangler deploy` step outside
  of `pnpm turbo`.
- **Using a public R2 bucket** — The worker enforces auth; the bucket itself should remain
  private (no public access).

## Gotchas

- Turborepo sends `Content-Type: application/octet-stream` and may send chunked
  transfer. Workers handle this natively, but log the `content-length` header — a
  missing header means Turborepo is streaming, and R2's `put()` still works fine.
- The remote cache API path changed between Turborepo v1 (`/v8/artifacts`) and any
  future versions. Pin your Turborepo version in `package.json` and test after upgrades.
- R2 `put()` is atomic; a failed upload leaves no partial object. If the Worker times
  out on a large artifact (> 100 MB), increase `upload_concurrency` in the Turborepo
  config or split large outputs into smaller globs.
- Workers have a 128 MB memory limit; streaming the body directly to R2 (not buffering)
  avoids OOM on large artifacts. The example above streams via `request.body`.

## Verification

```bash
# First run — should show MISS and upload artifacts
pnpm turbo build --summarize 2>&1 | grep -E "MISS|HIT|remote"

# Second run (same inputs) — should show FULL TURBO (all HIT)
pnpm turbo build --summarize 2>&1 | grep "FULL TURBO"

# Confirm objects landed in R2
wrangler r2 object list turbo-cache-prod --limit 5
```

Check the worker's request logs:

```bash
wrangler tail turbo-cache --format pretty
```

## Related

- `turborepo-cloudflare-workers-pipeline.md`
- `turborepo-setup.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `pnpm-workspaces-selective-deploy-changed.md`
- `miniflare-r2-event-notification-testing.md`

## Sources

- Turborepo Remote Cache Protocol: https://turborepo.com/docs/core-concepts/remote-caching
- Cloudflare R2 API: https://developers.cloudflare.com/r2/
- Wrangler R2 commands: https://developers.cloudflare.com/workers/wrangler/commands/#r2
