# Cross-Origin Isolation — COEP & COOP on Cloudflare Pages

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example.com needs `SharedArrayBuffer` for high-performance audio processing in the browser (e.g. Wasm-based media encoding) and for `Atomics.wait` in worker threads. Browsers require the page to be cross-origin isolated before granting access to these APIs, which means the entire page — including all subresources — must opt in via two HTTP response headers. Without these headers, `typeof SharedArrayBuffer === 'undefined'` in the browser.

## Context

Cloudflare Pages serves static assets and Pages Functions from the same Cloudflare edge network. Setting `Cross-Origin-Embedder-Policy` (COEP) and `Cross-Origin-Opener-Policy` (COOP) in `public/_headers` is the primary mechanism. However, COEP requires all third-party subresources (images, scripts, iframes) to explicitly opt in too, which creates friction for a social platform that embeds external media. COEP credentialless mode (`credentialless`) is the pragmatic middle ground.

## COEP and COOP Header Semantics

`Cross-Origin-Opener-Policy: same-origin` ensures the page gets its own browsing context group — it cannot share memory with cross-origin popups, and `window.opener` is `null` for cross-origin navigations.

`Cross-Origin-Embedder-Policy: require-corp` requires every subresource to either be same-origin or send `Cross-Origin-Resource-Policy: cross-origin` (or `same-site`). This is strict — it blocks images from CDNs that don't set CORP.

`Cross-Origin-Embedder-Policy: credentialless` loads cross-origin no-CORS requests without credentials instead of blocking them — a weaker but more compatible option for media-heavy pages.

```typescript
// Verify isolation in the browser
function checkCrossOriginIsolation(): void {
  const isolated = self.crossOriginIsolated;
  console.log('Cross-origin isolated:', isolated);

  if (isolated) {
    // These APIs are now available
    const sab = new SharedArrayBuffer(1024);
    console.log('SharedArrayBuffer available, byte length:', sab.byteLength);
  }
}
```

## Cloudflare Pages _headers Configuration

Set both headers at the top-level route. Sub-paths inherit them unless overridden.

```
# public/_headers

/*
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: credentialless
  Cross-Origin-Resource-Policy: cross-origin

# For API routes that serve CORS data, allow it explicitly
/api/*
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: credentialless
  Access-Control-Allow-Origin: https://example.com
  Access-Control-Allow-Credentials: true
```

For R2-hosted assets (user uploads at `assets.example.com`), each R2 public bucket response must include:
```
Cross-Origin-Resource-Policy: cross-origin
```
Configure this via a Cloudflare Worker in front of the R2 bucket.

## Pages Functions Middleware for Dynamic COEP

When isolation is only needed on specific routes (e.g. the `/studio` editor), use Pages Functions middleware to conditionally apply headers rather than polluting the global `_headers` file, which could break embeds.

```typescript
// functions/studio/_middleware.ts

import type { PagesFunction } from '@cloudflare/workers-types';

export const onRequest: PagesFunction = async (ctx) => {
  const response = await ctx.next();
  const headers = new Headers(response.headers);

  // Apply cross-origin isolation only for the studio route
  headers.set('Cross-Origin-Opener-Policy', 'same-origin');
  headers.set('Cross-Origin-Embedder-Policy', 'require-corp');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};
```

For the main feed where external images are embedded, use `credentialless` instead:

```typescript
// functions/_middleware.ts (root — applies everywhere)

import type { PagesFunction } from '@cloudflare/workers-types';

const ISOLATION_REQUIRED_PATHS = ['/studio', '/editor'];

export const onRequest: PagesFunction = async (ctx) => {
  const url = new URL(ctx.request.url);
  const response = await ctx.next();
  const headers = new Headers(response.headers);

  headers.set('Cross-Origin-Opener-Policy', 'same-origin');

  const needsStrict = ISOLATION_REQUIRED_PATHS.some((p) =>
    url.pathname.startsWith(p)
  );

  headers.set(
    'Cross-Origin-Embedder-Policy',
    needsStrict ? 'require-corp' : 'credentialless'
  );

  return new Response(response.body, { status: response.status, headers });
};
```

## Using SharedArrayBuffer with Wasm Workers

Once isolated, `SharedArrayBuffer` is available in both the main thread and dedicated/shared workers. Pass it to a worker via `postMessage` — the underlying memory is shared, not copied.

```typescript
// src/lib/wasm-audio-processor.ts

async function initAudioProcessor(): Promise<void> {
  if (!self.crossOriginIsolated) {
    throw new Error('Page is not cross-origin isolated. SharedArrayBuffer unavailable.');
  }

  // 4 MB shared buffer for audio samples
  const sharedBuffer = new SharedArrayBuffer(4 * 1024 * 1024);
  const view = new Int32Array(sharedBuffer);

  const worker = new Worker('/workers/audio-encode.js', { type: 'module' });

  // Transfer the SAB reference — the worker gets a view into the same memory
  worker.postMessage({ type: 'INIT', sharedBuffer });

  worker.onmessage = (event: MessageEvent) => {
    if (event.data.type === 'ENCODED') {
      uploadToR2(event.data.blob);
    }
  };

  // Signal readiness via Atomics
  Atomics.store(view, 0, 1);
  Atomics.notify(view, 0, 1);
}
```

Inside the worker:

```typescript
// src/workers/audio-encode.ts

let sharedView: Int32Array | null = null;

self.addEventListener('message', async (event: MessageEvent) => {
  if (event.data.type === 'INIT') {
    sharedView = new Int32Array(event.data.sharedBuffer);
    // Wait for the main thread to signal readiness (non-blocking with wait-async)
    const result = Atomics.waitAsync(sharedView, 0, 0);
    if (result.async) {
      await result.value;
    }
    processAudio(sharedView);
  }
});

function processAudio(view: Int32Array): void {
  // Process audio data from shared memory
  self.postMessage({ type: 'ENCODED', blob: new Blob() });
}
```

## Feature Detection and Graceful Degradation

```typescript
// src/lib/isolation-check.ts

export interface IsolationCapabilities {
  crossOriginIsolated: boolean;
  sharedArrayBuffer: boolean;
  atomicsWaitAsync: boolean;
  wasmThreads: boolean;
}

export function detectIsolationCapabilities(): IsolationCapabilities {
  const crossOriginIsolated = self.crossOriginIsolated ?? false;

  return {
    crossOriginIsolated,
    sharedArrayBuffer: crossOriginIsolated && typeof SharedArrayBuffer !== 'undefined',
    atomicsWaitAsync: crossOriginIsolated && typeof Atomics.waitAsync === 'function',
    wasmThreads: crossOriginIsolated && typeof WebAssembly.Memory !== 'undefined',
  };
}

// Usage in the app bootstrap
const caps = detectIsolationCapabilities();
if (!caps.sharedArrayBuffer) {
  console.warn('Falling back to non-threaded Wasm — no SharedArrayBuffer');
  loadSingleThreadedWasm();
} else {
  loadMultiThreadedWasm();
}
```

## Anti-patterns

- Setting `COEP: require-corp` on pages that embed images from third-party CDNs (e.g. user avatar URLs from external services) — these will be blocked with a network error unless the CDN adds `CORP: cross-origin`.
- Setting `COOP: same-origin` on pages that open OAuth popups — the popup and opener can no longer communicate via `window.opener`; use `postMessage` instead.
- Applying isolation headers to API routes that serve JSON to cross-origin callers — COOP does not affect data fetches, but mixing concerns in `_headers` is confusing.
- Using `Atomics.wait()` on the main thread — it blocks the thread and throws in browsers. Always use `Atomics.waitAsync()` or move to a Worker.
- Not testing the isolation headers in staging — COEP `credentialless` drops credentials on cross-origin no-CORS requests, which can silently break authenticated image loads.

## Gotchas

- `self.crossOriginIsolated` is `false` in non-isolated workers even if the parent page is isolated — workers inherit isolation only when spawned from an isolated context.
- `COEP: credentialless` is not supported in Safari < 17.4; use feature detection and fall back to `require-corp` + same-origin images for Safari.
- `COOP: same-origin-allow-popups` allows the page to open cross-origin popups and retain `window.opener`, but the page is NOT considered isolated — `SharedArrayBuffer` remains unavailable.
- Cloudflare Pages `_headers` is not a Worker script — it cannot read request headers or cookies. For conditional header logic, use Pages Functions middleware.
- The `report-to` header combined with `COEP: report-only` lets you audit COEP violations before enforcing them in production.

## Verification

1. Deploy to Cloudflare Pages with the `_headers` changes applied.
2. Open DevTools → Console and run `self.crossOriginIsolated` — should be `true`.
3. Run `new SharedArrayBuffer(256)` — should return an object, not throw.
4. Open the Network tab and check that `Cross-Origin-Embedder-Policy` and `Cross-Origin-Opener-Policy` appear on the HTML response.
5. Check that no COEP errors appear in the Console for image/script loads (if using `credentialless`).
6. Open the page in Safari 17 and confirm `crossOriginIsolated` is `true`.

## Related

- `cloudflare-pages-headers-csp-mobile.md`
- `trusted-types-xss-prevention-workers.md`
- `wasm-cloudflare-workers-image-transform.md`
- `browser-web-workers.md`
- `cloudflare-pages-middleware-auth-gating.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Embedder-Policy
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Opener-Policy
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer
- https://developers.cloudflare.com/pages/configuration/headers/
- https://web.dev/articles/coop-coep
- https://developer.chrome.com/blog/coep-credentialless-origin-trial/
