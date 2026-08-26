# Workers Assets Migration from KV to R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The example project platform's legacy static-asset serving Worker stores files — HTML
templates, JS bundles, CSS, and binary blobs — as values in a KV namespace.
Key patterns are `asset::<sha256>` and `asset::meta::<path>`, written by a custom
build script. Issues that motivate migration to R2:

- KV value size limit is 25 MB; several compiled WASM modules exceed this
- KV `list()` API is eventually consistent and returns stale keys during
  high-write deploy windows, causing 404s for recently deployed assets
- KV operations are billed per-read, making CDN-cache-miss traffic expensive
  compared to R2's per-GB storage pricing model
- The new Workers Assets binding (`assets`) provides first-class routing, ETags,
  content-type inference, and cache-control headers without custom Worker code —
  but it requires assets to be uploaded via `wrangler deploy` (which writes to R2
  internally), not manually via KV

## Context

Cloudflare Workers Assets (GA as of late 2025) is backed by R2 and served via
Cloudflare's CDN with automatic cache headers. The `wrangler deploy` command
uploads files from a local `./public` (or configured `assets.directory`) to an
internal R2 bucket managed by Cloudflare, then makes them available via the
`ASSETS` binding and as routed static responses.

This document covers:
1. Exporting existing assets from KV to local disk
2. Restructuring for the `wrangler.toml` `[assets]` configuration
3. Dual-serving during cutover (KV and R2 in parallel)
4. Validating asset parity and flipping production traffic

---

## Section 1 — Enumerate and Export KV Assets

```typescript
// scripts/export-kv-assets.ts
// Run with: CF_ACCOUNT_ID=xxx CF_API_TOKEN=xxx ts-node export-kv-assets.ts

import fs from 'fs/promises';
import path from 'path';

const BASE = 'https://api.cloudflare.com/client/v4';
const ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const TOKEN = process.env.CF_API_TOKEN!;
const KV_NAMESPACE_ID = process.env.KV_NAMESPACE_ID!;
const OUT_DIR = process.env.OUT_DIR ?? './public-migrated';

interface KVKey { name: string }

async function listAllKeys(cursor?: string): Promise<{ keys: KVKey[]; cursor?: string; complete: boolean }> {
  const url = new URL(`${BASE}/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/keys`);
  url.searchParams.set('limit', '1000');
  if (cursor) url.searchParams.set('cursor', cursor);

  const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${TOKEN}` } });
  const json = (await res.json()) as {
    result: KVKey[];
    result_info: { cursor?: string; count: number };
  };
  return {
    keys: json.result ?? [],
    cursor: json.result_info?.cursor,
    complete: !json.result_info?.cursor,
  };
}

async function getKVValue(key: string): Promise<ArrayBuffer> {
  const url = `${BASE}/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NAMESPACE_ID}/values/${encodeURIComponent(key)}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${TOKEN}` } });
  if (!res.ok) throw new Error(`GET ${key} failed: ${res.status}`);
  return res.arrayBuffer();
}

async function main(): Promise<void> {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const allKeys: KVKey[] = [];
  let cursor: string | undefined;

  do {
    const { keys, cursor: next, complete } = await listAllKeys(cursor);
    allKeys.push(...keys);
    cursor = complete ? undefined : next;
  } while (cursor);

  const assetKeys = allKeys.filter((k) => k.name.startsWith('asset::') && !k.name.includes('meta::'));
  console.log(`Found ${assetKeys.length} asset keys`);

  for (const k of assetKeys) {
    // Key format: asset::<sha256>::<relative-path>
    const parts = k.name.split('::');
    const relativePath = parts.slice(2).join('::') || parts[1];
    const outPath = path.join(OUT_DIR, relativePath);

    await fs.mkdir(path.dirname(outPath), { recursive: true });
    const data = await getKVValue(k.name);
    await fs.writeFile(outPath, Buffer.from(data));
    console.log(`  Wrote ${relativePath} (${data.byteLength} bytes)`);

    await new Promise((r) => setTimeout(r, 50)); // 20 req/s
  }

  console.log(`Export complete → ${OUT_DIR}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
```

## Section 2 — Wrangler Configuration for Workers Assets

```toml
# wrangler.toml — after migration
name = "example project-frontend"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

[assets]
directory = "./public-migrated"
binding = "ASSETS"
# Serve assets directly without hitting the Worker script for known paths:
run_worker_first = false

[env.production]
name = "example project-frontend"
[env.production.assets]
directory = "./public-migrated"

[env.staging]
name = "example project-frontend-staging"
[env.staging.assets]
directory = "./public-migrated"
```

## Section 3 — Dual-Serving Worker During Cutover

During the cutover window, the Worker serves assets from R2 (via the `ASSETS`
binding) while retaining a fallback to KV for any path not yet migrated.

```typescript
// src/worker.ts — dual-serve cutover mode
import type { Env } from './types';

export interface Env {
  ASSETS: Fetcher;          // Workers Assets binding (R2-backed)
  LEGACY_KV: KVNamespace;   // old KV namespace — remove after cutover
  FEATURE_FLAGS: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    const useR2 = (await env.FEATURE_FLAGS.get('assets-r2-enabled')) === 'true';

    if (useR2) {
      // Try R2-backed Workers Assets first
      const r2Response = await env.ASSETS.fetch(req);
      if (r2Response.status !== 404) return r2Response;
      // Fall through to KV if asset not found in R2
    }

    // Legacy KV path
    const assetKey = `asset::${url.pathname.replace(/^\//, '')}`;
    const { value, metadata } = await env.LEGACY_KV.getWithMetadata<{ contentType: string }>(
      assetKey,
      'arrayBuffer',
    );

    if (value === null) {
      return new Response('Not Found', { status: 404 });
    }

    return new Response(value, {
      headers: {
        'Content-Type': metadata?.contentType ?? 'application/octet-stream',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  },
};
```

## Section 4 — Asset Parity Verification Script

Before flipping the feature flag to R2, verify that every asset reachable via the
old KV path is also served correctly from the Workers Assets binding.

```typescript
// scripts/verify-asset-parity.ts
import crypto from 'crypto';
import fs from 'fs/promises';
import path from 'path';

const STAGING_URL = process.env.STAGING_URL ?? 'https://example project-frontend-staging.workers.dev';
const PUBLIC_DIR = process.env.PUBLIC_DIR ?? './public-migrated';

interface Result { path: string; status: 'ok' | 'mismatch' | 'missing'; detail?: string }

async function verifyFile(relativePath: string): Promise<Result> {
  const url = `${STAGING_URL}/${relativePath}`;
  const res = await fetch(url);

  if (!res.ok) {
    return { path: relativePath, status: 'missing', detail: String(res.status) };
  }

  const remoteBuffer = Buffer.from(await res.arrayBuffer());
  const localBuffer = await fs.readFile(path.join(PUBLIC_DIR, relativePath));
  const localHash = crypto.createHash('sha256').update(localBuffer).digest('hex');
  const remoteHash = crypto.createHash('sha256').update(remoteBuffer).digest('hex');

  if (localHash !== remoteHash) {
    return { path: relativePath, status: 'mismatch', detail: `local=${localHash.slice(0,8)} remote=${remoteHash.slice(0,8)}` };
  }

  return { path: relativePath, status: 'ok' };
}

async function main(): Promise<void> {
  const files = await walkDir(PUBLIC_DIR);
  console.log(`Verifying ${files.length} assets against ${STAGING_URL}`);

  const results: Result[] = [];
  for (const f of files) {
    const rel = path.relative(PUBLIC_DIR, f).replace(/\\/g, '/');
    const result = await verifyFile(rel);
    if (result.status !== 'ok') {
      console.error(`  ${result.status.toUpperCase()} ${rel} ${result.detail ?? ''}`);
    }
    results.push(result);
    await new Promise((r) => setTimeout(r, 20));
  }

  const ok = results.filter((r) => r.status === 'ok').length;
  const bad = results.length - ok;
  console.log(`\nParity check: ${ok} ok, ${bad} failed`);
  if (bad > 0) process.exit(1);
}

async function walkDir(dir: string): Promise<string[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) files.push(...(await walkDir(full)));
    else files.push(full);
  }
  return files;
}

main().catch((e) => { console.error(e); process.exit(1); });
```

## Section 5 — Rollout and KV Namespace Decommission

```bash
#!/usr/bin/env bash
# scripts/migrate-assets-cutover.sh
set -euo pipefail

ENV="${1:-staging}"

echo "==> [1/4] Deploying with dual-serve mode enabled"
npx wrangler deploy --env "$ENV"

echo "==> [2/4] Verifying asset parity on staging"
STAGING_URL="https://example project-frontend-staging.workers.dev" \
  PUBLIC_DIR="./public-migrated" \
  npx ts-node scripts/verify-asset-parity.ts

echo "==> [3/4] Flipping feature flag to R2"
npx wrangler kv key put assets-r2-enabled true \
  --binding FEATURE_FLAGS --env "$ENV" --remote

echo "==> [4/4] Monitoring error rate for 5 minutes"
sleep 300

# Check for 4xx spike in Analytics Engine
ERRORS=$(npx wrangler d1 execute example project_DB --env "$ENV" --remote \
  --command "SELECT COUNT(*) FROM http_logs WHERE status >= 400 AND path LIKE '/assets/%' AND created_at > strftime('%s','now','-5 minutes')" \
  --json | jq '.[0].results[0]["COUNT(*)"]')

if [ "$ERRORS" -gt 10 ]; then
  echo "ERROR: Asset 4xx spike detected (${ERRORS} errors). Rolling back flag."
  npx wrangler kv key put assets-r2-enabled false \
    --binding FEATURE_FLAGS --env "$ENV" --remote
  exit 1
fi

echo "Migration complete. KV namespace can be decommissioned after 7 days."
```

## Anti-patterns

- **Copying KV values to R2 manually** (via `wrangler r2 object put`) then wiring
  a custom R2 Worker — this bypasses Workers Assets routing, caching, and ETag
  handling. Use `wrangler deploy` with `[assets]` config to let Cloudflare manage
  the R2 bucket.
- **Switching cold** (disabling KV read immediately) — any asset not yet in R2 due
  to an upload race will 404 in production. The dual-serve pattern with a feature
  flag is mandatory.
- **Keeping the `LEGACY_KV` binding in production forever** — after confirming
  parity, remove the binding within 7 days to eliminate billing for reads that will
  never be hit.
- **Hashing on the client side only** — ETag values generated by Workers Assets
  are based on Cloudflare's internal content hash, not a SHA-256 of the raw bytes.
  The parity check above compares byte content, which is the correct approach.

## Gotchas

- Workers Assets ignores files whose path starts with `_` by default. If your KV
  namespace stores internal metadata under `_meta/` paths, those will not be served
  via the Assets binding and must be served through the Worker `fetch` handler.
- The `[assets]` directory is uploaded at deploy time. If the directory is empty
  (e.g., the build step has not run), `wrangler deploy` will warn but succeed,
  overwriting previously deployed assets with nothing.
- `run_worker_first = false` means the Worker script is bypassed entirely for
  matched asset paths. If the Worker was previously performing auth checks on asset
  routes, those checks are silently skipped. Add an auth middleware via `[assets]`
  headers configuration or switch to `run_worker_first = true`.
- KV namespace IDs are not transferable between accounts. If the migration involves
  moving to a new Cloudflare account, the KV export script must be run against the
  source account credentials.

## Verification

```bash
# Confirm Workers Assets is serving a known file
curl -I "https://example project-frontend.workers.dev/index.html" \
  | grep -E "cf-cache-status|etag|content-type|cache-control"

# List top-level items in the managed R2 bucket (indirect — via wrangler pages)
npx wrangler pages deployment list --project-name example project-frontend

# Confirm the LEGACY_KV binding has zero reads after cutover (check AE metrics)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query": "SELECT COUNT(*) FROM kv_reads WHERE namespace = '\''LEGACY_KV'\'' AND timestamp > now() - INTERVAL '\''1'\'' HOUR"}' \
  | jq '.data'
```

## Related

- `workers-assets-binding-deploy-patterns.md`
- `workers-kv-namespace-migration-deploy.md`
- `zero-downtime-r2-bucket-migration.md`
- `kv-namespace-seed-automation-wrangler.md`
- `feature-flag-deployment-gates-cloudflare-kv.md`

## Sources

- Cloudflare Workers Assets: https://developers.cloudflare.com/workers/static-assets/
- Workers Assets `[assets]` configuration: https://developers.cloudflare.com/workers/static-assets/configuration/
- Cloudflare KV REST API: https://developers.cloudflare.com/api/resources/kv/
- R2 object storage: https://developers.cloudflare.com/r2/
