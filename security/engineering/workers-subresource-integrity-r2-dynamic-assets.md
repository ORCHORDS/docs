# Subresource Integrity for Dynamically Served Assets from R2 via Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You serve JavaScript bundles and CSS files from Cloudflare R2 through a Worker. Without Subresource Integrity (SRI), a compromised R2 object or CDN layer could silently serve tampered scripts to users. You need the browser to reject assets whose bytes do not match a known-good digest.

## Context

SRI lets you add `integrity="sha384-<base64>"` to `<script>` and `<link>` tags. The browser fetches the resource, hashes the response body, and refuses to execute it if the digest does not match. The challenge with dynamically generated HTML is that the Worker must inject the correct digest at response time. This article shows how to: compute the digest at upload time, store it in D1, and inject it server-side via a lightweight string replacement.

---

## Asset Upload Pipeline with Digest Storage

```typescript
// scripts/upload-assets.ts  — run during CI deploy
// Usage: npx tsx scripts/upload-assets.ts

import { createReadStream, readdirSync, statSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';

// In CI, call the Cloudflare API directly or use the Workers SDK.
// Here we produce a manifest JSON consumed by a separate wrangler upload step.

const DIST_DIR = path.resolve('./dist');

interface AssetManifestEntry {
  r2Key: string;
  sha384: string;  // base64url, ready for the integrity attribute
}

async function buildManifest(): Promise<AssetManifestEntry[]> {
  const entries: AssetManifestEntry[] = [];
  const files = readdirSync(DIST_DIR).filter(f => /\.(js|css)$/.test(f));

  for (const file of files) {
    const filePath = path.join(DIST_DIR, file);
    const bytes = await readFile(filePath);
    const hash = createHash('sha384').update(bytes).digest('base64');
    entries.push({ r2Key: `assets/${file}`, sha384: hash });
    console.log(`${file}  sha384-${hash}`);
  }
  return entries;
}

buildManifest().then(manifest => {
  process.stdout.write(JSON.stringify(manifest, null, 2));
});
```

---

## D1 Schema

```sql
-- Run once: wrangler d1 execute example project-db --file schema.sql
CREATE TABLE IF NOT EXISTS asset_sri (
  r2_key   TEXT PRIMARY KEY,
  sha384   TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
```

---

## Worker: Serving HTML with Injected SRI Attributes

```typescript
// worker/index.ts
interface Env {
  ASSETS: R2Bucket;
  DB: D1Database;
}

const FALLBACK_INLINE_BUNDLE = '<script>/* minimal inline fallback */console.warn("SRI fallback active");</script>';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Serve individual assets directly from R2
    if (url.pathname.startsWith('/assets/')) {
      const key = url.pathname.slice(1); // strip leading '/'
      const object = await env.ASSETS.get(key);
      if (!object) return new Response('Not found', { status: 404 });
      const headers = new Headers();
      object.writeHttpMetadata(headers);
      return new Response(object.body, { headers });
    }

    // Serve HTML page with SRI-annotated tags
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return serveIndexWithSri(env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function serveIndexWithSri(env: Env): Promise<Response> {
  // Fetch HTML template from R2
  const templateObj = await env.ASSETS.get('templates/index.html');
  if (!templateObj) return new Response('Template missing', { status: 500 });
  let html = await templateObj.text();

  // Load all SRI digests from D1 in one query
  const { results } = await env.DB
    .prepare('SELECT r2_key, sha384 FROM asset_sri')
    .all<{ r2_key: string; sha384: string }>();

  const sriMap = new Map(results.map(r => [r.r2_key, r.sha384]));

  // Inject integrity attributes into <script > and <link rel="stylesheet" >
  html = html.replace(
    /<script([^>]*)\ssrc="'"'>/g,
    (_match, pre, src, post) => {
      const key = src.slice(1); // '/assets/app.js' -> 'assets/app.js'
      const digest = sriMap.get(key);
      if (!digest) return _match; // unknown asset: leave unchanged
      return `<script${pre}  integrity="sha384-${digest}" crossorigin="anonymous"${post}>`;
    },
  );

  html = html.replace(
    /<link([^>]*)\shref="'"'>/g,
    (_match, pre, href, post) => {
      const key = href.slice(1);
      const digest = sriMap.get(key);
      if (!digest) return _match;
      return `<link${pre}  integrity="sha384-${digest}" crossorigin="anonymous"${post}>`;
    },
  );

  return new Response(html, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}
```

---

## Handling SRI Mismatch — Inline Fallback Bundle

When the browser blocks a script due to SRI mismatch, no `error` event fires on the `<script>` tag. Use an `onerror` fallback combined with an inline noscript shim:

```html
<!-- In your HTML template -->
<script
        integrity="sha384-PLACEHOLDER"
        crossorigin="anonymous"
        onerror="loadFallback()"></script>
<script>
function loadFallback() {
  var s = document.createElement('script');
  // Inline minimal bundle as data URI — no SRI required for inline scripts
  s.textContent = window.__FALLBACK_BUNDLE__ || '';
  document.head.appendChild(s);
  console.error('SRI mismatch: loaded inline fallback');
}
</script>
```

---

## CI Deploy Pipeline Integration

```yaml
# .github/workflows/deploy.yml (relevant steps)
- name: Build assets
  run: npm run build

- name: Compute SRI manifest
  run: npx tsx scripts/upload-assets.ts > dist/sri-manifest.json

- name: Upload assets to R2
  run: wrangler r2 object put assets/ --dir dist/ --recursive

- name: Seed SRI digests into D1
  run: |
    node -e "
      const m = require('./dist/sri-manifest.json');
      const sql = m.map(e =>
        \`INSERT INTO asset_sri(r2_key,sha384,updated_at) VALUES('\${e.r2Key}','\${e.sha384}',\${Date.now()/1000|0}) ON CONFLICT(r2_key) DO UPDATE SET sha384=excluded.sha384,updated_at=excluded.updated_at;\`
      ).join('\n');
      require('fs').writeFileSync('/tmp/sri_seed.sql', sql);
    "
    wrangler d1 execute example project-db --file /tmp/sri_seed.sql

- name: Deploy Worker
  run: wrangler deploy
```

---

## Anti-patterns

- **Generating the digest in the Worker at serve time** — the Worker must fetch the full asset bytes to hash them, defeating the purpose of caching and adding latency.
- **Using `sha256` instead of `sha384`** — browsers support both, but `sha384` is the current recommended minimum per the SRI spec.
- **Omitting `crossorigin="anonymous"`** — without it, the browser sends credentials on the asset request, which can cause CORS issues with R2.
- **Storing digests only in the HTML template** — any template update wipes the digests; D1 is the source of truth.

## Gotchas

- The regex-based injection above breaks if attribute order in your template varies widely. Consider a more robust HTML parser for production.
- R2 `get()` returns `null` for missing objects — always null-check before calling `.text()` or `.body`.
- The CI `upload-assets.ts` script uses Node's `crypto.createHash`; the Workers runtime uses `crypto.subtle.digest` — both produce the same SHA-384 hash.
- D1 queries inside a single Worker request are batched; use `db.batch([...])` to run schema inserts in parallel.

## Verification

```bash
# Check that integrity attribute is present in served HTML
curl https://your-worker.workers.dev/ | grep 'integrity='
# Expected: integrity="sha384-<base64>"

# Manually corrupt the R2 object and confirm browser console shows:
# "Failed to find a valid digest in the 'integrity' attribute"
```

## Related

- `workers-content-security-policy-nonce-injection.md`
- `workers-request-signing-hmac-sha256-verification.md`
- W3C SRI specification

## Sources

- https://www.w3.org/TR/SRI/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
