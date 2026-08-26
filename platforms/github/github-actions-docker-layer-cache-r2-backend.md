# GitHub Actions Docker Layer Cache with Cloudflare R2 Backend

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Docker builds in GitHub Actions re-pull and rebuild every layer on each run because the
default GitHub-hosted runner has no persistent disk. `cache-from: type=gha` is limited
to 10 GB and is scoped to a single repository. Teams with large multi-stage images or
monorepos with many services need a durable, cross-repository cache that survives runner
recycling. Cloudflare R2 is S3-compatible, egress-free, and integrates with BuildKit's
`s3` cache exporter natively.

---

## Context

BuildKit supports a pluggable cache backend via `--cache-to` / `--cache-from` flags.
The `type=s3` backend stores layer blobs in any S3-compatible bucket. R2 exposes an
S3-compatible API at `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. A Cloudflare API
token with `Object Storage: Edit` permission and a dedicated R2 bucket provides a
persistent, globally available cache. Because R2 charges no egress fees, cache hits from
GitHub's US-East runners are effectively free.

Required secrets:

- `R2_ACCOUNT_ID` – Cloudflare account ID
- `R2_ACCESS_KEY_ID` – R2 API token access key
- `R2_SECRET_ACCESS_KEY` – R2 API token secret key
- `R2_BUCKET` – bucket name (e.g. `docker-layer-cache`)

---

## 1. Creating the R2 Bucket via Wrangler

```typescript
// scripts/provision-r2-cache.ts
import { execSync } from "node:child_process";

const BUCKET = process.env.R2_BUCKET ?? "docker-layer-cache";

// wrangler r2 bucket create <name> --jurisdiction=default
execSync(`npx wrangler r2 bucket create ${BUCKET}`, { stdio: "inherit" });

// Lifecycle: delete incomplete multipart uploads older than 7 days
// (set via Cloudflare dashboard or API; not yet in wrangler CLI)
console.log(`Bucket "${BUCKET}" created. Configure lifecycle rules in the dashboard.`);
```

Run once during repo bootstrap; the bucket persists across all workflow runs.

---

## 2. Workflow: Build with R2 Cache Backend

```yaml
# .github/workflows/docker-build.yml
name: Docker Build (R2 cache)

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  id-token: write   # only needed if also pushing to GHCR

env:
  IMAGE: ghcr.io/${{ github.repository }}/app

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver: docker-container   # required for s3 cache type

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: ${{ github.ref == 'refs/heads/main' }}
          tags: ${{ env.IMAGE }}:${{ github.sha }}
          cache-from: |
            type=s3,region=auto,bucket=${{ secrets.R2_BUCKET }},
            endpoint_url=https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com,
            access_key_id=${{ secrets.R2_ACCESS_KEY_ID }},
            secret_access_key=${{ secrets.R2_SECRET_ACCESS_KEY }}
          cache-to: |
            type=s3,region=auto,bucket=${{ secrets.R2_BUCKET }},
            endpoint_url=https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com,
            access_key_id=${{ secrets.R2_ACCESS_KEY_ID }},
            secret_access_key=${{ secrets.R2_SECRET_ACCESS_KEY }},
            mode=max
```

`mode=max` caches every intermediate layer, not just the final image, maximising hit rate.

---

## 3. Cache Key Scoping per Service (Monorepo)

```yaml
# .github/workflows/docker-build-monorepo.yml
jobs:
  build:
    strategy:
      matrix:
        service: [api, worker, migrator]
    steps:
      - uses: docker/build-push-action@v6
        with:
          context: services/${{ matrix.service }}
          cache-from: |
            type=s3,region=auto,bucket=${{ secrets.R2_BUCKET }},
            prefix=${{ matrix.service }}/,
            endpoint_url=https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com,
            access_key_id=${{ secrets.R2_ACCESS_KEY_ID }},
            secret_access_key=${{ secrets.R2_SECRET_ACCESS_KEY }}
          cache-to: |
            type=s3,region=auto,bucket=${{ secrets.R2_BUCKET }},
            prefix=${{ matrix.service }}/,
            endpoint_url=https://${{ secrets.R2_ACCOUNT_ID }}.r2.cloudflarestorage.com,
            access_key_id=${{ secrets.R2_ACCESS_KEY_ID }},
            secret_access_key=${{ secrets.R2_SECRET_ACCESS_KEY }},
            mode=max
```

The `prefix=` parameter namespaces layers by service, preventing cross-contamination.

---

## 4. Workers-Based Cache Metrics Collector

Track R2 cache hit/miss rates by parsing BuildKit output streamed to a Cloudflare Worker.

```typescript
// workers/cache-metrics/src/index.ts
export interface Env {
  DB: D1Database;
}

interface BuildEvent {
  repository: string;
  service: string;
  cacheHit: boolean;
  layerCount: number;
  buildDurationMs: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const event: BuildEvent = await request.json();

    await env.DB.prepare(
      `INSERT INTO docker_cache_events
         (repository, service, cache_hit, layer_count, build_duration_ms, recorded_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    )
      .bind(
        event.repository,
        event.service,
        event.cacheHit ? 1 : 0,
        event.layerCount,
        event.buildDurationMs
      )
      .run();

    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
} satisfies ExportedHandler<Env>;
```

Post build stats from GitHub Actions using `curl` in an `after` step.

---

## 5. R2 Lifecycle Cleanup Worker (Scheduled)

```typescript
// workers/r2-cache-janitor/src/index.ts
export interface Env {
  CACHE_BUCKET: R2Bucket;
  MAX_AGE_DAYS: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const maxAgeMs = parseInt(env.MAX_AGE_DAYS, 10) * 86_400_000;
    const cutoff = new Date(Date.now() - maxAgeMs);

    let cursor: string | undefined;
    let deleted = 0;

    do {
      const list = await env.CACHE_BUCKET.list({ cursor, limit: 1000 });
      const stale = list.objects.filter(
        (o) => o.uploaded < cutoff
      );
      if (stale.length > 0) {
        await env.CACHE_BUCKET.delete(stale.map((o) => o.key));
        deleted += stale.length;
      }
      cursor = list.truncated ? list.cursor : undefined;
    } while (cursor);

    console.log(`Deleted ${deleted} stale cache objects older than ${env.MAX_AGE_DAYS} days`);
  },
} satisfies ExportedHandler<Env>;
```

Schedule weekly via `wrangler.toml` cron trigger: `crons = ["0 2 * * 0"]`.

---

## Anti-patterns

- **Using `mode=min`** – only caches the final stage; misses all intermediate layers and
  provides minimal speedup for multi-stage builds.
- **Sharing one bucket prefix across unrelated services** – layers collide and incorrect
  layers may be restored, causing subtle build failures.
- **Storing R2 credentials as plain environment variables** – always use GitHub Actions
  secrets; never hardcode in workflow YAML.
- **Skipping Buildx driver override** – `type=s3` requires `docker-container` driver;
  the default `docker` driver does not support external cache backends.

---

## Gotchas

- R2 S3-compatible endpoint requires `region=auto`; passing `us-east-1` returns
  `AuthorizationHeaderMalformed` errors from BuildKit.
- BuildKit's `type=s3` backend does not support server-side encryption (SSE-C); use
  bucket-level default encryption in Cloudflare dashboard instead.
- Multipart uploads that are aborted leave orphaned parts in R2 that count toward
  storage but are invisible in normal listings – configure an incomplete-multipart
  lifecycle policy (7-day expiry recommended).
- The `cache-to` and `cache-from` values in `docker/build-push-action` must be on a
  single line or use YAML block scalars; wrapping mid-value breaks the argument parser.
- GitHub's 10 GB GHA cache limit does NOT apply to R2; only R2 storage quotas do.

---

## Verification

```bash
# Confirm layers are landing in R2 after a build
aws s3 ls s3://<R2_BUCKET>/ \
  --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com \
  --recursive | head -20

# Check BuildKit cache-hit output in Actions logs
grep -E "CACHED|cache hit|cache miss" build.log

# Measure speedup: compare first-run vs cached-run duration in job summary
```

---

## Related

- `github-actions-turborepo-remote-cache-cloudflare-r2.md`
- `github-actions-cache-dependencies.md`
- `github-actions-docker-build-push.md`
- `github-actions-wasm-build-caching-workers.md`

---

## Sources

- BuildKit S3 cache backend docs: https://github.com/moby/buildkit/blob/master/docs/reference/buildkitd.md
- Cloudflare R2 S3 compatibility: https://developers.cloudflare.com/r2/api/s3/api/
- `docker/build-push-action` cache docs: https://github.com/docker/build-push-action/blob/main/docs/advanced/cache.md
- Cloudflare R2 lifecycle rules: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
