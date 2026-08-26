# Screenshot Service Using Cloudflare Browser Rendering API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate PNG screenshots of arbitrary URLs on demand — for social preview cards, visual regression testing, or PDF report thumbnails. Running a headless Chromium server is expensive to operate and scale. Cloudflare's Browser Rendering API provides on-demand Puppeteer access from inside a Worker, with R2 for storing the results and KV for rate limiting.

## Context

Cloudflare Browser Rendering spins up a headless Chromium browser instance accessible from your Worker via `@cloudflare/puppeteer` (a fork of `puppeteer-core` that connects to Cloudflare's managed browser fleet). You pay per session, and concurrent sessions are limited by plan. Key constraints:

- Max browser session duration: 60 seconds (hard limit).
- Concurrent sessions: depends on plan (Paid plans: up to 2 concurrent by default).
- Output size: No artificial limit, but R2 object max is 5 TB.
- Navigation timeout: Default 30 seconds; configurable.

The typical flow: Worker receives a screenshot request, checks rate limit in KV, launches browser, navigates, screenshots, uploads PNG to R2, returns a signed R2 URL.

## Solution

```typescript
// src/screenshot-worker.ts

import puppeteer from '@cloudflare/puppeteer';

export interface Env {
  BROWSER: Fetcher;
  SCREENSHOTS: R2Bucket;
  RATE_LIMIT_KV: KVNamespace;
  SIGNING_SECRET: string;
  MAX_REQUESTS_PER_MINUTE: string;
}

const NAVIGATION_TIMEOUT_MS = 25_000;
const VIEWPORT = { width: 1280, height: 720, deviceScaleFactor: 2 };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'GET') {
      return new Response('Method not allowed', { status: 405 });
    }

    const url = new URL(request.url);
    const targetUrl = url.searchParams.get('url');
    const fullPage = url.searchParams.get('full') === '1';

    if (!targetUrl) {
      return Response.json(
        { error: 'missing_param', message: 'url query parameter is required' },
        { status: 400 },
      );
    }

    // Validate target URL — only allow http/https
    let parsedTarget: URL;
    try {
      parsedTarget = new URL(targetUrl);
      if (!['http:', 'https:'].includes(parsedTarget.protocol)) {
        throw new Error('Invalid protocol');
      }
    } catch {
      return Response.json(
        { error: 'invalid_url', message: 'Target URL must be a valid http/https URL' },
        { status: 400 },
      );
    }

    // Rate limiting — N requests per minute per IP
    const clientIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    const rateLimitKey = `rl:${clientIp}`;
    const maxRpm = parseInt(env.MAX_REQUESTS_PER_MINUTE, 10) || 5;

    const isLimited = await checkRateLimit(env.RATE_LIMIT_KV, rateLimitKey, maxRpm);
    if (isLimited) {
      return Response.json(
        { error: 'rate_limited', message: `Maximum ${maxRpm} screenshots per minute per IP` },
        { status: 429, headers: { 'Retry-After': '60' } },
      );
    }

    // Generate a deterministic R2 key from the URL + options
    const screenshotKey = await buildR2Key(targetUrl, fullPage);

    // Check if a recent screenshot exists in R2 (cache for 5 minutes)
    const cached = await env.SCREENSHOTS.head(screenshotKey);
    if (cached && cached.uploaded > new Date(Date.now() - 5 * 60 * 1000)) {
      const signedUrl = await buildSignedUrl(screenshotKey, env.SIGNING_SECRET);
      return Response.json({ url: signedUrl, cached: true });
    }

    let browser: Awaited<ReturnType<typeof puppeteer.launch>> | null = null;

    try {
      browser = await puppeteer.launch(env.BROWSER);
      const page = await browser.newPage();

      await page.setViewport(VIEWPORT);

      // Block resource-intensive assets to speed up rendering
      await page.setRequestInterception(true);
      page.on('request', (req) => {
        const resourceType = req.resourceType();
        if (['font', 'media'].includes(resourceType)) {
          req.abort();
        } else {
          req.continue();
        }
      });

      // Navigate to the target URL
      try {
        await page.goto(parsedTarget.href, {
          waitUntil: 'networkidle0',
          timeout: NAVIGATION_TIMEOUT_MS,
        });
      } catch (navErr) {
        const message = navErr instanceof Error ? navErr.message : String(navErr);

        if (message.includes('timeout')) {
          // Retry with a looser wait condition on timeout
          await page.goto(parsedTarget.href, {
            waitUntil: 'domcontentloaded',
            timeout: NAVIGATION_TIMEOUT_MS,
          });
        } else {
          throw navErr;
        }
      }

      // Wait for fonts and a brief settle period for lazy-loaded images
      await page.evaluate(() =>
        document.fonts.ready.then(() => new Promise((r) => setTimeout(r, 500))),
      );

      const screenshotBuffer = await page.screenshot({
        type: 'png',
        fullPage,
        clip: fullPage
          ? undefined
          : { x: 0, y: 0, width: VIEWPORT.width, height: VIEWPORT.height },
      });

      await env.SCREENSHOTS.put(screenshotKey, screenshotBuffer, {
        httpMetadata: { contentType: 'image/png' },
        customMetadata: {
          targetUrl,
          capturedAt: new Date().toISOString(),
          fullPage: String(fullPage),
        },
      });

      const signedUrl = await buildSignedUrl(screenshotKey, env.SIGNING_SECRET);

      return Response.json({
        url: signedUrl,
        cached: false,
        key: screenshotKey,
      });
    } catch (err) {
      console.error('Screenshot error:', err);
      const message = err instanceof Error ? err.message : 'Unknown error';
      return Response.json(
        { error: 'screenshot_failed', message },
        { status: 500 },
      );
    } finally {
      // Always close the browser — leaked sessions count against your concurrency limit
      await browser?.close();
    }
  },
};

async function checkRateLimit(
  kv: KVNamespace,
  key: string,
  maxRpm: number,
): Promise<boolean> {
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= maxRpm) return true;

  await kv.put(key, String(count + 1), { expirationTtl: 60 });

  return false;
}

async function buildR2Key(targetUrl: string, fullPage: boolean): Promise<string> {
  const hash = await sha256(targetUrl + String(fullPage));
  return `screenshots/${hash.slice(0, 16)}.png`;
}

async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

async function buildSignedUrl(key: string, secret: string): Promise<string> {
  const expiry = Math.floor(Date.now() / 1000) + 3600; // 1 hour
  const message = `${key}|${expiry}`;

  const cryptoKey = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const signatureBuffer = await crypto.subtle.sign(
    'HMAC',
    cryptoKey,
    new TextEncoder().encode(message),
  );

  const signature = btoa(String.fromCharCode(...new Uint8Array(signatureBuffer)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');

  return `https://screenshots.example.com/${key}?expiry=${expiry}&sig=${signature}`;
}
```

**Signed URL validator Worker (serves screenshots from R2):**

```typescript
// src/serve-screenshot.ts — deployed as a separate Worker on screenshots.example.com

export interface ServeEnv {
  SCREENSHOTS: R2Bucket;
  SIGNING_SECRET: string;
}

export default {
  async fetch(request: Request, env: ServeEnv): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1);
    const expiry = url.searchParams.get('expiry');
    const sig = url.searchParams.get('sig');

    if (!expiry || !sig) {
      return new Response('Missing signature parameters', { status: 400 });
    }

    if (parseInt(expiry, 10) < Math.floor(Date.now() / 1000)) {
      return new Response('Signed URL expired', { status: 410 });
    }

    const message = `${key}|${expiry}`;
    const cryptoKey = await crypto.subtle.importKey(
      'raw',
      new TextEncoder().encode(env.SIGNING_SECRET),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify'],
    );

    const sigBytes = Uint8Array.from(
      atob(sig.replace(/-/g, '+').replace(/_/g, '/')),
      (c) => c.charCodeAt(0),
    );

    const valid = await crypto.subtle.verify(
      'HMAC',
      cryptoKey,
      sigBytes,
      new TextEncoder().encode(message),
    );

    if (!valid) {
      return new Response('Invalid signature', { status: 403 });
    }

    const object = await env.SCREENSHOTS.get(key);
    if (!object) {
      return new Response('Screenshot not found', { status: 404 });
    }

    return new Response(object.body, {
      headers: {
        'Content-Type': 'image/png',
        'Cache-Control': 'public, max-age=3600',
      },
    });
  },
};
```

**wrangler.toml:**

```toml
name = "screenshot-service"
main = "src/screenshot-worker.ts"
compatibility_date = "2025-08-01"

[browser]
binding = "BROWSER"

[[r2_buckets]]
binding = "SCREENSHOTS"
bucket_name = "orchords-screenshots"

[[kv_namespaces]]
binding = "RATE_LIMIT_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[vars]
MAX_REQUESTS_PER_MINUTE = "5"
```

## Implementation Details

**Puppeteer session lifecycle:**

Each `puppeteer.launch()` call acquires a browser session. Always close it in a `finally` block. Leaked sessions count against your concurrency limit and are billed until they time out (60s hard limit).

**`waitUntil` strategy:**

- `networkidle0` — waits until no network activity for 500ms. Best for SPAs. Can timeout on pages with long-polling or WebSockets.
- `networkidle2` — allows up to 2 in-flight connections. Faster, less strict.
- `domcontentloaded` — fastest; does not wait for images or scripts. Use as a fallback.

**Full-page screenshots:**

Full-page screenshots capture the entire scrollable document height. This can be very tall for content-heavy pages. Cloudflare's Puppeteer has a max screenshot dimension limit; test pages above 8000px height.

**Blocking fonts and media:**

Bypassing font and media requests speeds up page rendering significantly (often 30-50%). Screenshots will use system fallback fonts; this is acceptable for thumbnail use cases.

## Anti-patterns

- **Not closing the browser in a `finally` block.** An exception before `browser.close()` leaks the session and consumes your concurrency quota.
- **Not validating the target URL.** Without validation, attackers can use your screenshot service to probe internal network URLs (`file://`, `http://169.254.169.254/`, etc.). Restrict to `http:` and `https:` and consider a domain allowlist.
- **Skipping rate limiting.** Browser sessions are expensive. Without rate limiting, a single client can exhaust your concurrency quota.
- **Caching screenshots indefinitely.** Screenshots become stale. Use a short TTL (5-15 minutes for live pages) and include the TTL in your freshness check.
- **Using R2 pre-signed URLs (not yet available in Workers).** As of 2026, R2 does not natively support pre-signed URLs from Workers. Use the validator Worker pattern shown above.

## Gotchas

- **Browser Rendering is not available in `wrangler dev` local mode.** Use `wrangler dev --remote` to test against Cloudflare's actual browser fleet.
- **`networkidle0` timeouts on pages with infinite scroll or real-time feeds.** Use `domcontentloaded` + `page.waitForTimeout(1000)` for these.
- **CORS on R2 public buckets.** If you serve PNGs directly from an R2 public bucket URL, configure CORS in the R2 bucket settings or the screenshots will not render in cross-origin `<img>` tags.
- **Viewport scaling.** `deviceScaleFactor: 2` produces a 2560x1440 PNG from a 1280x720 viewport. Reduce to `1` if storage cost is a concern.
- **`page.setRequestInterception(true)` must be called before `page.goto()`**, otherwise request interception has no effect on the initial page load.
- **Chromium memory.** Each browser session uses roughly 150-200 MB of RAM in Cloudflare's fleet. High concurrency with full-page screenshots of complex pages can trigger OOM, causing `puppeteer.launch()` to throw.

## Verification

```bash
# Deploy to Cloudflare
npx wrangler deploy

# Test basic screenshot (use --remote for local dev)
curl "https://screenshot-service.example.workers.dev/?url=https://example.com"
# Expect: {"url": "https://screenshots.example.com/screenshots/xxxx.png?...", "cached": false}

# Test the returned signed URL
curl -L "<signed-url-from-above>" --output test-screenshot.png

# Test rate limiting (run 6 times in quick succession)
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    "https://screenshot-service.example.workers.dev/?url=https://example.com"
done
# Expect: first 5 return 200, 6th returns 429

# Test invalid URL
curl "https://screenshot-service.example.workers.dev/?url=file:///etc/passwd"
# Expect: 400 {"error": "invalid_url"}
```

## Related

- `workers-r2-storage-patterns.md` — R2 bucket setup, CORS, and lifecycle rules
- `workers-kv-rate-limiting.md` — sliding window vs fixed window rate limiting in KV
- `workers-smart-placement-optimization.md` — keep the screenshot Worker near R2 for faster uploads

## Sources

- https://developers.cloudflare.com/browser-rendering/
- https://developers.cloudflare.com/browser-rendering/get-started/screenshots/
- https://developers.cloudflare.com/r2/
- https://pptr.dev/
