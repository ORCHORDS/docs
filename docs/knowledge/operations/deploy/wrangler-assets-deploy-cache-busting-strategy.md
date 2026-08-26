# Wrangler Assets Deploy Cache-Busting Strategy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

After deploying a new version of a Workers static-assets bundle the browser or Cloudflare's
edge cache continues serving stale JS/CSS files. Users see a mix of old HTML referencing new
asset hashes and new HTML referencing old hashes. You need a deterministic cache-busting
strategy that works with `wrangler deploy --assets` (and the equivalent `wrangler pages deploy`)
so every release delivers a consistent asset set to every visitor instantly.

---

## Context

Cloudflare Workers with `[assets]` (introduced with workers-assets) serves static files from an
R2-backed edge cache. Files are keyed by both path and content hash when the `--assets` flag or
`[assets]` config block is used. However, long-lived `Cache-Control` headers set in
`wrangler.toml` or via `_headers` mean the edge can serve a stale response for a URL that was
mapped to a different content hash in the previous deploy.

Cache busting in this context has two layers:
1. **Build-time**: inject a content-addressable hash into filenames (`main.[contenthash].js`).
   Vite, webpack, and esbuild all support this. Filenames that embed their own hash never
   collide across deploys — the old file and new file coexist at different URLs.
2. **Deploy-time**: purge or bypass the edge cache for the HTML entry points (index.html,
   `_routes.json`) which do NOT carry a content hash and must be re-fetched by every browser
   on every deploy.

---

## 1. Build-time content-hash filenames (Vite example)

```typescript
// vite.config.ts
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    rollupOptions: {
      output: {
        // Deterministic: same source → same hash across machines/CI runs.
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    // Ensure hashes are stable — no random salts.
    sourcemap: false,
  },
});
```

With content-addressable filenames, long `max-age` is safe for everything under `/assets/`:

```toml
# wrangler.toml
[assets]
directory = "dist"

[[rules]]
type = "ESModule"
globs = ["**/*.js"]
fallthrough = true
```

```
# dist/_headers
/assets/*
  Cache-Control: public, max-age=31536000, immutable

/index.html
  Cache-Control: no-cache, must-revalidate

/*.json
  Cache-Control: no-cache, must-revalidate
```

---

## 2. Deploy pipeline with post-deploy cache purge

```typescript
// scripts/deploy-with-purge.ts
import { execSync } from "node:child_process";

const CF_ZONE_ID = process.env.CF_ZONE_ID!;
const CF_API_TOKEN = process.env.CF_API_TOKEN!;
const DEPLOY_URL = process.env.DEPLOY_URL ?? "https://example.com";

/** URLs that must be cache-purged after every deploy. */
const ALWAYS_PURGE = [
  `${DEPLOY_URL}/`,
  `${DEPLOY_URL}/index.html`,
  `${DEPLOY_URL}/_routes.json`,
];

async function purgeFiles(urls: string[]): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/purge_cache`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ files: urls }),
    }
  );

  const body = (await res.json()) as { success: boolean; errors: unknown[] };
  if (!body.success) {
    throw new Error(`Cache purge failed: ${JSON.stringify(body.errors)}`);
  }

  console.log(`Purged ${urls.length} URLs from edge cache.`);
}

async function main(): Promise<void> {
  console.log("Building…");
  execSync("pnpm build", { stdio: "inherit" });

  console.log("Deploying assets…");
  execSync("pnpm wrangler deploy", { stdio: "inherit" });

  console.log("Purging entry-point cache…");
  await purgeFiles(ALWAYS_PURGE);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

---

## 3. Derive purge list from build manifest

Instead of hard-coding paths, read Vite's asset manifest to purge exactly the files that changed:

```typescript
// scripts/purge-from-manifest.ts
import { readFileSync } from "node:fs";

interface ViteManifestEntry {
  file: string;
  src?: string;
  isEntry?: boolean;
}
type ViteManifest = Record<string, ViteManifestEntry>;

function entryUrls(manifestPath: string, baseUrl: string): string[] {
  const manifest: ViteManifest = JSON.parse(
    readFileSync(manifestPath, "utf-8")
  );

  return Object.values(manifest)
    .filter((entry) => entry.isEntry)
    .map((entry) => `${baseUrl}/${entry.file}`);
}

const BASE = process.env.DEPLOY_URL ?? "https://example.com";
const urls = [
  `${BASE}/`,
  `${BASE}/index.html`,
  ...entryUrls("dist/.vite/manifest.json", BASE),
];

console.log("URLs to purge:", urls);
// Pass `urls` to purgeFiles() from the previous section.
```

---

## 4. Smoke-test that the new assets are live

After purge, verify that the deployed `index.html` references the new asset hashes:

```typescript
// scripts/verify-asset-freshness.ts
async function verifyFreshness(indexUrl: string, expectedHash: string): Promise<void> {
  // Add cache-bypass header to confirm origin is fresh.
  const res = await fetch(indexUrl, {
    headers: { "Cache-Control": "no-cache" },
  });

  if (!res.ok) {
    throw new Error(`index.html returned HTTP ${res.status}`);
  }

  const html = await res.text();
  if (!html.includes(expectedHash)) {
    throw new Error(
      `index.html does not reference expected asset hash "${expectedHash}". ` +
        `Stale content may still be serving.`
    );
  }

  console.log(`index.html correctly references hash ${expectedHash} ✓`);
}

// expectedHash is read from the build manifest; example:
import { readFileSync } from "node:fs";
const manifest = JSON.parse(readFileSync("dist/.vite/manifest.json", "utf-8"));
const mainEntry = Object.values(manifest).find(
  (e: any) => e.isEntry && e.src === "src/main.ts"
) as any;
const hash = mainEntry.file.match(/-([a-f0-9]{8})\./)?.[1] ?? "";

await verifyFreshness("https://example.com/", hash);
```

---

## 5. Wiring into GitHub Actions

```yaml
- name: Build
  run: pnpm build

- name: Deploy
  run: pnpm wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

- name: Purge cache
  run: pnpm tsx scripts/deploy-with-purge.ts
  env:
    CF_ZONE_ID: ${{ secrets.CF_ZONE_ID }}
    CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    DEPLOY_URL: https://example.com

- name: Verify freshness
  run: pnpm tsx scripts/verify-asset-freshness.ts
  env:
    DEPLOY_URL: https://example.com
```

---

## Anti-patterns

- **Purging `/assets/*` wildcard on every deploy**: this evicts immutable, content-addressed
  files that edge nodes need not re-fetch, causing an unnecessary origin-hit spike. Purge only
  non-hashed entry points.
- **No `immutable` on content-hashed files**: browsers will still revalidate on navigation
  without it. Set `Cache-Control: public, max-age=31536000, immutable` for `/assets/*`.
- **Purging before deploy**: the purge races the wrangler upload. Always purge *after* the
  deploy completes and the new bundle is fully propagated.
- **Skipping the smoke-test**: the purge API returns `success: true` even when it could not
  reach some edge nodes. The freshness check confirms what users actually receive.

---

## Gotchas

- Cloudflare's cache purge by URL only purges that exact URL including query string. If your
  CDN layer rewrites URLs (e.g., Rocket Loader appending `?cf-v=…`), those URLs differ and
  require a tag-based or path-prefix purge (Enterprise plan only).
- Vite's manifest lives at `dist/.vite/manifest.json` only when `build.manifest: true` is set
  in `vite.config.ts`. Add it explicitly; it is off by default.
- The Workers `[assets]` binding and `wrangler pages deploy` have separate propagation paths.
  After `wrangler deploy` returns, edge nodes may take 30–60 s to reflect the new bundle.
  Build a retry loop into `verifyFreshness` rather than a fixed sleep.

---

## Verification

```bash
# Confirm _headers are uploaded correctly
curl -sI https://example.com/assets/main-abc123.js | grep cache-control
# => cache-control: public, max-age=31536000, immutable

curl -sI https://example.com/ | grep cache-control
# => cache-control: no-cache, must-revalidate

# Confirm manifest is generated
cat dist/.vite/manifest.json | jq 'to_entries[] | select(.value.isEntry)'
```

---

## Related

- `workers-assets-binding-deploy-patterns.md`
- `cloudflare-pages-build-cache-optimization.md`
- `cdn-deploy-cache-purge-orchestration.md`
- `deploy-verification-smoke-tests.md`

---

## Sources

- Cloudflare Cache Purge API: https://developers.cloudflare.com/cache/how-to/purge-cache/
- Workers Static Assets: https://developers.cloudflare.com/workers/static-assets/
- Vite build.manifest option: https://vitejs.dev/config/build-options.html#build-manifest
- MDN Cache-Control immutable: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control#immutable
