# GitHub Actions Turborepo Remote Cache with Cloudflare R2
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

In a monorepo using Turborepo, CI builds each PR from scratch because the built-in Vercel Remote
Cache is either unavailable (no Vercel deployment) or undesirable (vendor lock-in, cost). You want
build artifact caching — compiled Workers bundles, transpiled packages, test results — shared
across all GitHub Actions runs and persisted between PRs, using infrastructure you already operate:
a Cloudflare R2 bucket.

## Context

Turborepo supports pluggable remote caches via its open Remote Cache API (compatible with the
`@vercel/remote-cache` protocol). Any HTTP server implementing the `/v8/artifacts` endpoints
can act as a cache backend. Cloudflare Workers + R2 is an ideal host: it is globally distributed,
has low-latency reads near GitHub's runner regions, and integrates with your existing Cloudflare
account.

Two implementation options:
1. **`ducktape` / `turborepo-remote-cache` open-source Worker** — community project; most popular
   drop-in.
2. **Custom Worker** — minimal implementation giving full control over auth and eviction.

This article covers Option 2 (custom Worker) to stay within the example.com stack, plus the
GitHub Actions integration.

## Cloudflare Worker: remote cache server

### R2 bucket

```bash
# Create the bucket (via Wrangler or Cloudflare dashboard)
wrangler r2 bucket create turbo-cache
```

### Worker code (`workers/turbo-cache/src/index.ts`)

```typescript
import { Hono } from 'hono';
import { bearerAuth } from 'hono/bearer-auth';

type Env = {
  TURBO_CACHE: R2Bucket;
  TURBO_TOKEN: string;          // secret via wrangler.toml [vars] or secret
};

const app = new Hono<{ Bindings: Env }>();

// Authenticate all requests with a shared bearer token
app.use('*', async (c, next) => {
  const auth = bearerAuth({ token: c.env.TURBO_TOKEN });
  return auth(c, next);
});

// GET /v8/artifacts/:hash — fetch a cached artifact
app.get('/v8/artifacts/:hash', async (c) => {
  const hash = c.req.param('hash');
  const object = await c.env.TURBO_CACHE.get(hash);
  if (!object) {
    return c.json({ error: 'not found' }, 404);
  }
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  return new Response(object.body, { headers });
});

// PUT /v8/artifacts/:hash — store an artifact
app.put('/v8/artifacts/:hash', async (c) => {
  const hash = c.req.param('hash');
  const body = c.req.raw.body;
  if (!body) return c.json({ error: 'no body' }, 400);

  const contentType = c.req.header('Content-Type') ?? 'application/octet-stream';
  await c.env.TURBO_CACHE.put(hash, body, {
    httpMetadata: { contentType },
    customMetadata: {
      team: c.req.query('teamId') ?? 'default',
      uploadedAt: new Date().toISOString(),
    },
  });
  return c.json({ ok: true }, 200);
});

// HEAD /v8/artifacts/:hash — check existence without downloading
app.on('HEAD', '/v8/artifacts/:hash', async (c) => {
  const hash = c.req.param('hash');
  const object = await c.env.TURBO_CACHE.head(hash);
  if (!object) return new Response(null, { status: 404 });
  return new Response(null, { status: 200 });
});

// POST /v8/artifacts/events — accept Turborepo telemetry events (no-op)
app.post('/v8/artifacts/events', (c) => c.json({ ok: true }));

export default app;
```

### `wrangler.toml`

```toml
name = "turbo-cache"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

[[r2_buckets]]
binding = "TURBO_CACHE"
bucket_name = "turbo-cache"

[vars]
# TURBO_TOKEN is set as a secret: wrangler secret put TURBO_TOKEN
```

### Deploy the Worker

```bash
wrangler secret put TURBO_TOKEN   # enter a random 32-char token
wrangler deploy --env production
```

## Repository turbo.json

```json
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true,
    "preflight": false
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**", ".wrangler/tmp/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "lint": {
      "outputs": []
    }
  }
}
```

## GitHub Actions workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  # Point Turbo at the self-hosted R2-backed cache
  TURBO_API: https://turbo-cache.orchords.workers.dev
  TURBO_TOKEN: ${{ secrets.TURBO_CACHE_TOKEN }}
  TURBO_TEAM: orchords

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2    # needed for turbo --filter=[HEAD^1] comparison

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build affected packages
        run: |
          npx turbo run build \
            --filter='...[HEAD^1]' \
            --remote-only \
            --summarize

      - name: Test affected packages
        run: |
          npx turbo run test \
            --filter='...[HEAD^1]' \
            --remote-only

      - name: Lint affected packages
        run: |
          npx turbo run lint \
            --filter='...[HEAD^1]' \
            --remote-only
```

## Cache hit verification

Add a summary step to surface cache efficiency:

```yaml
      - name: Print Turbo cache summary
        if: always()
        run: |
          SUMMARY_DIR=".turbo/runs"
          if [ -d "$SUMMARY_DIR" ]; then
            LATEST=$(ls -t "$SUMMARY_DIR"/*.json 2>/dev/null | head -1)
            if [ -n "$LATEST" ]; then
              jq -r '
                .tasks |
                group_by(.cache.source) |
                map({
                  source: (.[0].cache.source // "MISS"),
                  count: length
                }) |
                .[] |
                "\(.count) \(.source)"
              ' "$LATEST"
            fi
          fi
```

## R2 lifecycle rule for cache eviction

Artifacts older than 30 days should be evicted to control storage costs. Configure via
Cloudflare dashboard or Wrangler:

```bash
# Not yet available via wrangler CLI for R2 lifecycle; use Cloudflare API
curl -X PUT "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/turbo-cache/lifecycle" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{
      "id": "evict-old-cache",
      "enabled": true,
      "conditions": {
        "maxAgeSeconds": 2592000
      },
      "action": {
        "type": "DeleteObject"
      }
    }]
  }'
```

## Secrets required

| Secret name | Usage |
|---|---|
| `TURBO_CACHE_TOKEN` | Bearer token for the Worker; must match `TURBO_TOKEN` wrangler secret |

The same token value must be set both in the Worker (via `wrangler secret put TURBO_TOKEN`) and
in the GitHub repository secret `TURBO_CACHE_TOKEN`. Rotate them together.

## Multi-team / branch isolation

To prevent cross-contamination between branches:

```yaml
env:
  TURBO_TEAM: ${{ github.ref == 'refs/heads/main' && 'main' || github.head_ref }}
```

Turbo namespaces cache entries by `teamId` query parameter, so different teams get separate
keyspaces in R2.

## Anti-patterns

- **Storing artifacts in GitHub Actions cache (`actions/cache`) instead of remote cache**: the
  Actions cache is local to a single runner OS and has a 10 GB cap per repository. R2 has no
  practical size limit and is accessible from any runner region.
- **Skipping `--remote-only`**: without this flag, Turbo also checks the local filesystem cache,
  which is empty on a fresh runner and wastes time.
- **Using a public Worker endpoint without auth**: any GitHub Actions user in a fork could read
  cached build outputs. Always require `TURBO_TOKEN` bearer auth.
- **Reusing the same team name across production and PR builds**: a broken PR build could poison
  the cache for main. Use branch-scoped team names in PR workflows.
- **Not setting `fetch-depth: 2`**: `--filter='...[HEAD^1]'` needs the previous commit to
  determine which packages changed. With `fetch-depth: 1` (the default), all packages rebuild.

## Gotchas

- R2 object reads are eventually consistent after PUTs in some edge cases; cache misses
  immediately after a PUT are rare but possible. Turbo handles this gracefully (falls back to
  local build).
- The Worker must be in the same Cloudflare account as the R2 bucket; cross-account bindings
  are not supported.
- `TURBO_API` must not have a trailing slash. Turbo constructs paths as `${TURBO_API}/v8/artifacts/...`.
- `wrangler secret put TURBO_TOKEN` encrypts the value at rest; it is not retrievable afterward.
  Keep a copy in your password manager.

## Verification

1. Run a full CI pipeline and confirm cache `MISS` in the first run.
2. Re-run the workflow without changing any code and confirm cache `HIT` for all tasks.
3. Check the R2 bucket in the Cloudflare dashboard for uploaded objects.
4. Modify one package and confirm only affected packages rebuild while unaffected ones hit cache.

## Related

- `github-actions-monorepo-caching.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-matrix-strategy-workers.md`
- `github-actions-cache-pnpm-turbo.md`

## Sources

- https://turbo.build/repo/docs/ci/github-actions
- https://turbo.build/repo/docs/core-concepts/remote-caching
- https://developers.cloudflare.com/r2/
- https://github.com/ducktors/turborepo-remote-cache
