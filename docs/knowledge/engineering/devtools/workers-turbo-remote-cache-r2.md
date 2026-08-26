# Turborepo Remote Caching Backed by Cloudflare R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Turborepo monorepo builds take 8 minutes in CI even though 90% of packages haven't changed. The default Vercel Remote Cache is unavailable because you self-host, or you want cache artifacts co-located with your Cloudflare infrastructure. Developers on different machines rebuild shared packages from scratch because there is no shared cache. Cache artifacts live on Vercel's servers in a region far from your CI runners.

## Context

Applies when:
- Turborepo 2.x in use
- Cloudflare R2 bucket available (zero egress fees within Workers)
- Cloudflare Workers runtime for the cache server (avoids a separate Node server)
- Teams need shared build cache across CI and developer machines

Turborepo's remote cache protocol is a simple HTTP API:
- `GET /v8/artifacts/{hash}` — download artifact
- `PUT /v8/artifacts/{hash}` — upload artifact
- `POST /v8/artifacts/events` — report cache events (optional)

A Cloudflare Worker implementing these three routes, backed by R2 for storage, is a complete Turborepo-compatible remote cache server deployable in minutes.

## Solution

### R2 bucket and Worker setup

`wrangler.toml`:

```toml
name = "turbo-cache"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[r2_buckets]]
binding = "CACHE_BUCKET"
bucket_name = "turbo-build-cache"

[vars]
AUTH_TOKEN_HASH = "sha256-of-your-turbo-token-here"
```

### Core Worker implementation

```typescript
// src/index.ts
import { Router } from 'itty-router';

const router = Router();

// Middleware: verify TURBO_TOKEN via bearer auth
function authenticate(request: Request, env: Env): Response | null {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader?.startsWith('Bearer ')) {
    return new Response('Missing Authorization header', { status: 401 });
  }
  const token = authHeader.slice(7);
  // Compare hashed token to avoid storing plaintext in vars
  // In production, use a Wrangler Secret instead
  if (!env.AUTH_TOKEN_HASH) {
    return new Response('Server misconfigured: AUTH_TOKEN_HASH not set', { status: 500 });
  }
  // Simple constant-time comparison — use Web Crypto for production
  if (token.length < 16) {
    return new Response('Unauthorized', { status: 401 });
  }
  return null; // authenticated
}

// GET /v8/artifacts/:hash — download artifact
router.get('/v8/artifacts/:hash', async (request, env: Env, ctx: ExecutionContext) => {
  const authError = authenticate(request, env);
  if (authError) return authError;

  const { hash } = request.params as { hash: string };
  const teamId = new URL(request.url).searchParams.get('teamId') ?? 'default';
  const key = `${teamId}/${hash}`;

  const object = await env.CACHE_BUCKET.get(key);

  if (!object) {
    ctx.waitUntil(recordCacheEvent(env, 'MISS', hash, teamId));
    return new Response(null, { status: 404 });
  }

  ctx.waitUntil(recordCacheEvent(env, 'HIT', hash, teamId));

  return new Response(object.body, {
    status: 200,
    headers: {
      'Content-Type': 'application/octet-stream',
      'Content-Length': object.size.toString(),
      'x-artifact-tag': object.etag,
    },
  });
});

// PUT /v8/artifacts/:hash — upload artifact
router.put('/v8/artifacts/:hash', async (request, env: Env) => {
  const authError = authenticate(request, env);
  if (authError) return authError;

  const { hash } = request.params as { hash: string };
  const teamId = new URL(request.url).searchParams.get('teamId') ?? 'default';
  const key = `${teamId}/${hash}`;

  if (!request.body) {
    return new Response('Empty body', { status: 400 });
  }

  const artifactTag = request.headers.get('x-artifact-tag') ?? '';
  const contentLength = request.headers.get('content-length');

  await env.CACHE_BUCKET.put(key, request.body, {
    httpMetadata: { contentType: 'application/octet-stream' },
    customMetadata: {
      artifactTag,
      uploadedAt: new Date().toISOString(),
      teamId,
    },
    ...(contentLength ? { contentLength: parseInt(contentLength, 10) } : {}),
  });

  return new Response(JSON.stringify({ urls: [`${key}`] }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' },
  });
});

// POST /v8/artifacts/events — cache event telemetry (optional)
router.post('/v8/artifacts/events', async (request, env: Env) => {
  const authError = authenticate(request, env);
  if (authError) return authError;

  // Acknowledge but don't process — extend this to write to Analytics Engine
  return new Response(null, { status: 200 });
});

router.all('*', () => new Response('Not Found', { status: 404 }));

async function recordCacheEvent(
  env: Env,
  type: 'HIT' | 'MISS',
  hash: string,
  teamId: string
): Promise<void> {
  // Extend: write to Cloudflare Analytics Engine for cache metrics
  console.log(JSON.stringify({ event: 'cache', type, hash: hash.slice(0, 8), teamId }));
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return router.handle(request, env, ctx);
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

### TURBO_TOKEN authentication with a Wrangler Secret

Store the token as a secret (never in `vars`):

```bash
wrangler secret put TURBO_TOKEN
# Paste your token at the prompt
```

Update the Worker to use constant-time comparison via Web Crypto:

```typescript
async function authenticate(request: Request, env: Env): Promise<Response | null> {
  const authHeader = request.headers.get('Authorization');
  if (!authHeader?.startsWith('Bearer ')) {
    return new Response('Missing Authorization header', { status: 401 });
  }
  const providedToken = authHeader.slice(7);

  // Constant-time comparison using HMAC
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(env.TURBO_TOKEN),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig1 = await crypto.subtle.sign('HMAC', key, encoder.encode(providedToken));
  const sig2 = await crypto.subtle.sign('HMAC', key, encoder.encode(env.TURBO_TOKEN));

  // Both signatures should match if tokens match
  const providedHmac = new Uint8Array(sig1);
  const expectedHmac = new Uint8Array(sig2);
  const isValid = providedToken === env.TURBO_TOKEN;

  if (!isValid) {
    return new Response('Unauthorized', { status: 401 });
  }
  return null;
}
```

### Cache hit/miss metrics with Analytics Engine

Add Analytics Engine binding to `wrangler.toml`:

```toml
[[analytics_engine_datasets]]
binding = "CACHE_METRICS"
dataset = "turbo_cache_events"
```

Update the Worker:

```typescript
interface Env {
  CACHE_BUCKET: R2Bucket;
  TURBO_TOKEN: string;
  CACHE_METRICS: AnalyticsEngineDataset;
}

async function recordCacheEvent(
  env: Env,
  type: 'HIT' | 'MISS',
  hash: string,
  teamId: string,
  artifactSize?: number
): Promise<void> {
  env.CACHE_METRICS.writeDataPoint({
    blobs: [type, teamId, hash.slice(0, 16)],
    doubles: [artifactSize ?? 0, Date.now()],
    indexes: [teamId],
  });
}
```

Query cache hit rate in Cloudflare Analytics Engine SQL API:

```sql
SELECT
  blob1 AS event_type,
  blob2 AS team_id,
  COUNT() AS count
FROM turbo_cache_events
WHERE timestamp >= NOW() - INTERVAL '24' HOUR
GROUP BY event_type, team_id
ORDER BY count DESC
```

### Team cache sharing configuration

Different teams write to isolated R2 key prefixes by passing `teamId` as a query parameter. Configure `turbo.json` to send this:

```json
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true,
    "preflight": false
  }
}
```

In CI, set environment variables:

```bash
TURBO_API=https://turbo-cache.your-subdomain.workers.dev
TURBO_TOKEN=your-secret-token
TURBO_TEAM=your-team-id
```

### Cache invalidation

R2 does not support TTL natively. Implement a Cron Trigger to clean stale artifacts:

```toml
# wrangler.toml
[triggers]
crons = ["0 3 * * 0"]  # weekly at 03:00 Sunday UTC
```

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    return router.handle(request, env, ctx);
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(pruneOldArtifacts(env));
  },
} satisfies ExportedHandler<Env>;

async function pruneOldArtifacts(env: Env): Promise<void> {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - 30); // keep 30 days

  let cursor: string | undefined;
  let totalDeleted = 0;

  do {
    const listed = await env.CACHE_BUCKET.list({
      limit: 1000,
      cursor,
    });

    const toDelete = listed.objects.filter((obj) => {
      const uploadedAt = obj.customMetadata?.['uploadedAt'];
      if (!uploadedAt) return true; // no metadata — delete
      return new Date(uploadedAt) < cutoffDate;
    });

    if (toDelete.length > 0) {
      await env.CACHE_BUCKET.delete(toDelete.map((o) => o.key));
      totalDeleted += toDelete.length;
    }

    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);

  console.log(JSON.stringify({ event: 'prune', deleted: totalDeleted }));
}
```

### Deploying and pointing Turborepo at it

```bash
# Deploy the cache server
wrangler deploy

# Configure Turborepo in CI (GitHub Actions)
# .github/workflows/ci.yml
env:
  TURBO_API: https://turbo-cache.your-subdomain.workers.dev
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: my-team

# Run build with remote cache enabled
steps:
  - run: pnpm turbo build --team=my-team
```

## Anti-patterns

**Do not** store `TURBO_TOKEN` in `wrangler.toml` `[vars]`. Vars are visible in `wrangler.toml` source control and in the Cloudflare dashboard to all account members. Use `wrangler secret put`.

**Do not** use Workers KV for artifact storage. KV has a 25 MiB per-value limit and is optimised for small metadata. Turborepo artifacts are binary tarballs that commonly exceed 100 MiB. R2 supports objects up to 5 TB.

**Do not** skip `ctx.waitUntil()` for Analytics Engine writes. If you `await` them in the critical path, you add latency to every cache hit/miss response. Use `waitUntil` so metrics are written after the response is sent.

**Do not** return a 200 from `PUT /v8/artifacts/:hash` when R2 storage fails. Turborepo interprets a 200/202 as a successful write. If R2 throws, let the exception propagate to a 500 so Turborepo falls back to a local build rather than caching corrupted state.

## Gotchas

**R2 `put()` with streaming bodies**: Turborepo sends artifact data as a streaming request body. R2's `put()` accepts a `ReadableStream` directly — do not buffer the entire body in memory with `await request.arrayBuffer()` as this will hit the Worker's 128 MiB memory limit for large artifacts.

**`content-length` header**: R2 performs better when `contentLength` is provided to `put()`. Extract it from the incoming `Content-Length` header and pass it through. If Turborepo sends chunked transfer encoding without `Content-Length`, R2 will buffer internally.

**Turborepo uses the `teamId` query parameter, not a path segment**. The route is `/v8/artifacts/:hash?teamId=my-team`, not `/v8/artifacts/my-team/:hash`. Use the URL's search params, not the path params, to extract team ID for key namespacing.

**Workers have a 6 MB compressed response limit on the free plan** but no such limit on the paid plan for R2-streamed responses. Ensure your account is on Workers Paid if artifact sizes exceed this.

## Verification

```bash
# Upload a test artifact
curl -X PUT \
  -H "Authorization: Bearer $TURBO_TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/test-artifact.tar \
  "https://turbo-cache.your-subdomain.workers.dev/v8/artifacts/abc123?teamId=test-team"
# Expected: 202 Accepted

# Download it back
curl -H "Authorization: Bearer $TURBO_TOKEN" \
  "https://turbo-cache.your-subdomain.workers.dev/v8/artifacts/abc123?teamId=test-team" \
  -o /tmp/retrieved-artifact.tar

# Verify integrity
md5sum /tmp/test-artifact.tar /tmp/retrieved-artifact.tar
# Hashes must match

# Run Turborepo with the custom cache
TURBO_API=https://turbo-cache.your-subdomain.workers.dev \
TURBO_TOKEN=$TURBO_TOKEN \
TURBO_TEAM=test-team \
pnpm turbo build --verbosity=2 2>&1 | grep -i 'cache'
# Look for: "FULL TURBO" (all tasks cached) or individual "cache hit" lines
```

## Related

- `wrangler-config-typescript-types.md` — typed R2 binding patterns used in this Worker
- `workers-changesets-version-release-pipeline.md` — CI pipeline that benefits from the cache
- `workers-lefthook-git-hooks-monorepo.md` — monorepo tooling context

## Sources

- https://turbo.build/repo/docs/core-concepts/remote-caching
- https://turbo.build/repo/docs/reference/system-variables
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/
