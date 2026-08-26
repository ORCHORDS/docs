# Cloudflare Browser Rendering: Full-Page Screenshots to R2

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need on-demand full-page screenshots of URLs (for link previews, OG image generation, visual regression tests, or SaaS PDF exports) without managing headless-browser infrastructure. Cloudflare Browser Rendering provides a managed Puppeteer endpoint that runs inside Workers, and R2 gives you cheap durable storage for the resulting PNGs.

## Context

Cloudflare Browser Rendering exposes a headless Chromium instance via the `@cloudflare/puppeteer` package. You bind it in `wrangler.toml` as a `browser` binding and call standard Puppeteer APIs (`page.goto`, `page.screenshot`, etc.) inside a Worker. The PNG is then stored in R2, and the Worker returns a pre-signed URL or streams the image directly.

---

## Section 1 — Setup: wrangler.toml and Dependencies

```toml
# wrangler.toml
name = "screenshot-service"
main = "src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

# Browser Rendering binding
[browser]
binding = "BROWSER"

# R2 bucket for storing screenshots
[[r2_buckets]]
binding     = "SCREENSHOTS"
bucket_name = "screenshots-prod"

[vars]
SERVICE_URL = "https://screenshots.example.com"
```

```bash
npm install @cloudflare/puppeteer
```

No other dependencies are needed. `@cloudflare/puppeteer` re-exports Puppeteer's types and connects to Cloudflare's managed browser via the `BROWSER` binding.

---

## Section 2 — Worker: Take Screenshot and Store in R2

```typescript
// src/index.ts
import puppeteer from '@cloudflare/puppeteer';
import type { BrowserWorker, R2Bucket } from '@cloudflare/workers-types';

interface Env {
  BROWSER: BrowserWorker;
  SCREENSHOTS: R2Bucket;
  SERVICE_URL: string;
}

// Stable key derived from URL so repeated requests are de-duplicated
function screenshotKey(targetUrl: string): string {
  // Use a hash-like slug: just encode the URL, truncated
  const encoded = btoa(targetUrl).replace(/[+/=]/g, '_').slice(0, 96);
  return `screenshots/${encoded}.png`;
}

async function takeScreenshot(
  browser: BrowserWorker,
  targetUrl: string
): Promise<Uint8Array> {
  const b = await puppeteer.launch(browser);
  let screenshot: Uint8Array;
  try {
    const page = await b.newPage();

    // Emulate a 1280×800 viewport
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });

    // Abort images/fonts to speed up the capture (optional)
    await page.setRequestInterception(true);
    page.on('request', (req) => {
      const type = req.resourceType();
      if (type === 'image' || type === 'font') {
        req.abort();
      } else {
        req.continue();
      }
    });

    await page.goto(targetUrl, {
      waitUntil: 'networkidle0',
      timeout: 20_000,
    });

    // Full-page screenshot as PNG
    const buf = await page.screenshot({
      type: 'png',
      fullPage: true,
    });

    screenshot = new Uint8Array(buf as Buffer);
  } finally {
    await b.close();
  }
  return screenshot;
}

async function generateSignedUrl(
  bucket: R2Bucket,
  key: string,
  expiresInSeconds: number
): Promise<string> {
  // R2 does not yet have a native signed URL API via the binding;
  // use the Workers URL + a short-lived HMAC token instead,
  // or serve via a public R2 custom domain.
  // Here we return a path the same Worker can serve with a token.
  // For simplicity, this example serves directly.
  return key;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'GET' && request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);

    // --- Serve stored screenshot ---
    if (url.pathname.startsWith('/serve/')) {
      const key = decodeURIComponent(url.pathname.slice('/serve/'.length));
      const obj = await env.SCREENSHOTS.get(key);
      if (!obj) return new Response('Not found', { status: 404 });
      return new Response(obj.body, {
        headers: {
          'Content-Type': 'image/png',
          'Cache-Control': 'public, max-age=86400',
        },
      });
    }

    // --- Capture endpoint: GET /capture?url=https://... ---
    const targetUrl = url.searchParams.get('url');
    if (!targetUrl) {
      return new Response('Missing ?url param', { status: 400 });
    }

    let parsedTarget: URL;
    try {
      parsedTarget = new URL(targetUrl);
    } catch {
      return new Response('Invalid URL', { status: 400 });
    }

    // Block SSRF: only allow http/https
    if (!['http:', 'https:'].includes(parsedTarget.protocol)) {
      return new Response('Protocol not allowed', { status: 400 });
    }

    const key = screenshotKey(targetUrl);
    const forceRefresh = url.searchParams.get('refresh') === '1';

    // Return cached version if available and not forcing refresh
    if (!forceRefresh) {
      const cached = await env.SCREENSHOTS.head(key);
      if (cached) {
        const serveUrl = `${env.SERVICE_URL}/serve/${encodeURIComponent(key)}`;
        return Response.json({ url: serveUrl, cached: true, key });
      }
    }

    // Take screenshot
    let png: Uint8Array;
    try {
      png = await takeScreenshot(env.BROWSER, targetUrl);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return Response.json({ error: 'Screenshot failed', detail: message }, { status: 500 });
    }

    // Store in R2
    await env.SCREENSHOTS.put(key, png, {
      httpMetadata: { contentType: 'image/png' },
      customMetadata: {
        sourceUrl: targetUrl,
        capturedAt: new Date().toISOString(),
        sizeBytes: String(png.byteLength),
      },
    });

    const serveUrl = `${env.SERVICE_URL}/serve/${encodeURIComponent(key)}`;
    return Response.json({
      url: serveUrl,
      cached: false,
      key,
      sizeBytes: png.byteLength,
    });
  },
};
```

---

## Section 3 — R2 Lifecycle Rule for Screenshot Expiry

Screenshots are ephemeral. Apply a lifecycle rule so they auto-delete after 7 days:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/screenshots-prod/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [{
      "id": "delete-screenshots-after-7-days",
      "enabled": true,
      "prefix": "screenshots/",
      "conditions": { "maxAge": 604800 },
      "deleteObjects": {}
    }]
  }'
```

After applying the rule, combine with a `HEAD` check in the Worker (already done above via `env.SCREENSHOTS.head(key)`) to serve a fresh capture when the cached version has been lifecycle-deleted.

---

## Section 4 — Signed URL Pattern for Private Buckets

For screenshots that must not be publicly accessible, implement HMAC-signed URLs:

```typescript
// src/signed-url.ts
export async function signKey(
  key: string,
  expiresAt: number,
  secret: string
): Promise<string> {
  const payload = `${key}:${expiresAt}`;
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, enc.encode(payload));
  const sigHex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
  return sigHex;
}

export async function verifySignedRequest(
  url: URL,
  secret: string
): Promise<boolean> {
  const key   = url.searchParams.get('key');
  const exp   = url.searchParams.get('exp');
  const token = url.searchParams.get('token');
  if (!key || !exp || !token) return false;
  if (Date.now() > Number(exp)) return false;
  const expected = await signKey(key, Number(exp), secret);
  return expected === token;
}

// Usage in fetch handler:
// GET /signed?key=<redacted-secret>&exp=1740000000000&token=<hmac>
```

---

## Anti-patterns

- **Not closing the browser** — always call `b.close()` in a `finally` block. Leaked browser instances count against your concurrency limit and raise costs.
- **Using `waitUntil: 'load'` for JS-heavy SPAs** — prefer `networkidle0` or `networkidle2` so the page has time to hydrate before screenshot.
- **Blocking the request thread on slow pages** — for background screenshot jobs, enqueue via Queue and return a job ID immediately; serve from R2 when ready.
- **Storing full-resolution screenshots indefinitely** — apply R2 lifecycle rules to cap storage cost.

## Gotchas

- Browser Rendering is available on **Workers Paid** plan. It is not available on the free tier.
- Each `puppeteer.launch()` call consumes a browser session. Cloudflare limits concurrent sessions; queue screenshot requests if your volume is high.
- `page.setRequestInterception(true)` must be called **before** `page.goto()`. Calling it after navigation starts has no effect.
- PNG screenshots of long pages can be several MB. Consider using `clip` option to limit the screenshot to the viewport, or use JPEG (`type: 'jpeg', quality: 80`) to reduce size.
- The `@cloudflare/puppeteer` package is not the same as upstream `puppeteer`. Do not mix APIs — some upstream Puppeteer methods are not available in the Cloudflare variant.

## Verification

```bash
# Local dev (browser binding requires wrangler dev with remote flag)
wrangler dev --remote

# Capture a screenshot
curl 'http://localhost:8787/capture?url=https://example.com' | jq .

# Serve the stored PNG
curl -o test.png 'http://localhost:8787/serve/screenshots%2F<key>.png'
open test.png

# Check R2 object metadata
wrangler r2 object get screenshots-prod screenshots/<key>.png --pipe | file -
```

## Related

- `cloudflare-r2-lifecycle-auto-delete.md` — lifecycle rules for the `screenshots/` prefix
- `workers-durable-objects-sqlite-api.md` — storing screenshot job state and deduplication in a DO

## Sources

- https://developers.cloudflare.com/browser-rendering/
- https://developers.cloudflare.com/browser-rendering/platform/puppeteer/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
