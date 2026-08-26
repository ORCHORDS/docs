# Storage Access API — Cloudflare Pages Iframe Cookies

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

An embedded iframe on example.com (e.g. an embedded post preview, OAuth popup, or third-party media player) cannot read first-party session cookies because browsers now block cross-site cookie access by default under ITP, Total Cookie Protection, and the Privacy Sandbox. The Storage Access API provides a user-gesture-gated escape hatch so the embedded frame can request access to its own first-party storage inside a cross-origin context.

## Context

Cloudflare Pages serves the top-level shell at `example.com` and the embeddable widget at `embed.example.com`. Both origins share the same Cloudflare zone, but browsers treat them as cross-site. Workers middleware sets `SameSite=None; Secure` cookies for authenticated sessions, yet those cookies are still blocked in iframes by default in Safari and Firefox without explicit Storage Access API consent.

## Storage Access API Overview

`document.hasStorageAccess()` returns a Promise that resolves to `true` if the frame already has access to unpartitioned cookies. `document.requestStorageAccess()` triggers a browser permission prompt (Safari/Firefox) or may auto-grant silently (Chrome with related-website-sets). This must be called inside a user gesture handler.

```typescript
// embed.example.com/embed.ts

async function checkStorageAccess(): Promise<boolean> {
  if (!document.hasStorageAccess) {
    // API not supported — assume access (older browsers)
    return true;
  }
  return document.hasStorageAccess();
}

async function requestStorageAccess(): Promise<boolean> {
  try {
    await document.requestStorageAccess();
    return true;
  } catch {
    // User denied or gesture requirement not met
    return false;
  }
}

async function initEmbedSession(): Promise<void> {
  const hasAccess = await checkStorageAccess();
  if (!hasAccess) {
    // Must wait for user gesture before requesting
    renderAccessPrompt();
    return;
  }
  await loadAuthenticatedContent();
}

initEmbedSession();
```

## Implementing the User Gesture Gate

Browsers require a transient user activation (click, keypress) before `requestStorageAccess()` is called. Showing a "Continue" button is the standard pattern. After the user interacts, the browser may show its own permission dialog (Safari) or silently grant (Chrome within a Related Website Set).

```typescript
// embed.example.com/access-prompt.ts

function renderAccessPrompt(): void {
  const container = document.getElementById('embed-root')!;
  container.innerHTML = `
    <div class="storage-access-prompt" role="dialog" aria-labelledby="prompt-title">
      <p id="prompt-title">Sign in to view this content</p>
      <button id="grant-access" type="button">Continue</button>
    </div>
  `;

  document.getElementById('grant-access')!.addEventListener('click', async () => {
    const granted = await requestStorageAccess();
    if (granted) {
      await loadAuthenticatedContent();
    } else {
      renderDeniedState();
    }
  });
}

function renderDeniedState(): void {
  const container = document.getElementById('embed-root')!;
  container.innerHTML = `
    <p>Cookie access was denied.
       <a href="https://example.com/post/123" target="_blank" rel="noopener">
         Open in full site
       </a>
    </p>
  `;
}

async function loadAuthenticatedContent(): Promise<void> {
  // Now unpartitioned cookies are readable — fetch protected content
  const response = await fetch('https://embed.example.com/api/content', {
    credentials: 'include',
  });
  const data = await response.json();
  renderContent(data);
}
```

## Cloudflare Pages — Related Website Sets Configuration

Chrome 120+ auto-grants `requestStorageAccess()` without a prompt if the top-level site and the embedded site are in the same Related Website Set (RWS). This is declared via a `/.well-known/related-website-set.json` file served from the primary domain, and submitted to the RWS list maintained by Google.

```typescript
// functions/api/related-website-set.ts (Cloudflare Pages Function)
// Serves /.well-known/related-website-set.json

export const onRequestGet: PagesFunction = async () => {
  const set = {
    primary: 'https://example.com',
    associatedSites: ['https://embed.example.com', 'https://assets.example.com'],
    contact: 'admin@example.com',
  };

  return new Response(JSON.stringify(set), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=86400',
    },
  });
};
```

Place the `_routes.json` include for this path and also configure `_headers`:

```
# public/_headers
/.well-known/related-website-set.json
  Access-Control-Allow-Origin: *
  Content-Type: application/json
```

## Cloudflare Pages Headers for the Embedded Frame

The iframe host must allow embedding from the parent and set appropriate cookie attributes. Cloudflare Pages middleware can inject these headers for the embed subdomain.

```typescript
// functions/_middleware.ts on embed.example.com

import type { PagesFunction } from '@cloudflare/workers-types';

export const onRequest: PagesFunction = async (ctx) => {
  const response = await ctx.next();
  const headers = new Headers(response.headers);

  // Allow the iframe to be embedded only from example.com
  headers.set('X-Frame-Options', 'ALLOW-FROM https://example.com');
  // Modern replacement for X-Frame-Options
  headers.set(
    'Content-Security-Policy',
    "frame-ancestors 'self' https://example.com https://*.example.com"
  );
  // Required for SameSite=None cookies
  headers.set('Cross-Origin-Resource-Policy', 'cross-origin');

  return new Response(response.body, { status: response.status, headers });
};
```

Session cookies for the embed origin must be set with:
```
Set-Cookie: session=TOKEN; SameSite=None; Secure; HttpOnly; Path=/
```

## Feature Detection and Progressive Enhancement

```typescript
// Detect Storage Access API support and fall back gracefully

interface StorageAccessStatus {
  supported: boolean;
  hasAccess: boolean;
  autoGrantLikely: boolean; // Chrome RWS scenario
}

async function detectStorageAccess(): Promise<StorageAccessStatus> {
  const supported = 'hasStorageAccess' in document;

  if (!supported) {
    return { supported: false, hasAccess: true, autoGrantLikely: false };
  }

  const hasAccess = await document.hasStorageAccess();

  // Chrome with RWS will grant without prompt — test with a dry-run
  // requestStorageAccess without gesture is rejected with NotAllowedError by Firefox/Safari
  // but resolves immediately in Chrome when RWS matches
  let autoGrantLikely = false;
  if (!hasAccess) {
    try {
      // This throws in Firefox/Safari without a gesture; resolves in Chrome/RWS
      await document.requestStorageAccess();
      autoGrantLikely = true;
    } catch {
      autoGrantLikely = false;
    }
  }

  return { supported, hasAccess: hasAccess || autoGrantLikely, autoGrantLikely };
}
```

## Anti-patterns

- Calling `requestStorageAccess()` outside a user gesture handler — it will always reject in Firefox and Safari.
- Setting `SameSite=Lax` or omitting `SameSite` on cookies intended for cross-site iframe use — they are blocked unconditionally.
- Using `document.cookie` to read cookies before confirming `hasStorageAccess()` returns `true`.
- Embedding the same session token in both first-party and third-party contexts without verifying the frame origin via `window.location.ancestorOrigins`.
- Relying solely on the Related Website Set mechanism without a user-gesture fallback for Safari and Firefox, which do not implement RWS.

## Gotchas

- Safari requires that the user has previously visited the embedded origin as a top-level site; otherwise `requestStorageAccess()` is always denied regardless of gesture.
- Firefox caps `requestStorageAccess()` grants at 30 days and the user must interact with the embed once per top-level site.
- Chrome's Partitioned cookies (`CHIPS`) and RWS are separate mechanisms — CHIPS partitions cookies by top-level site without requiring Storage Access API.
- `document.requestStorageAccess()` only grants access within the current page load; it does not persist across navigations inside the iframe without re-checking `hasStorageAccess()`.
- The `X-Frame-Options: ALLOW-FROM` header is not supported in Chrome — use CSP `frame-ancestors` instead.
- `ancestorOrigins` is not available in Firefox; use `document.referrer` as a fallback to verify the parent frame origin.

## Verification

1. Open `https://example.com` in Safari with ITP in strict mode.
2. Embed an iframe pointing to `https://embed.example.com/widget`.
3. Confirm that `document.hasStorageAccess()` returns `false` on load.
4. Click the "Continue" button — browser permission dialog appears (Safari) or auto-grants (Chrome + RWS).
5. Confirm `document.hasStorageAccess()` returns `true` after the grant.
6. Open DevTools → Application → Cookies for `embed.example.com` — session cookie should be readable.
7. In Chrome, verify the `/.well-known/related-website-set.json` endpoint returns 200 with correct JSON.

## Related

- `cloudflare-pages-headers-csp-mobile.md`
- `web-crypto-api-client-side-encryption-cloudflare-pages.md`
- `cookie-store-async-access-and-change-events.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `trusted-types-xss-prevention-workers.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Storage_Access_API
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/configuration/headers/
- https://privacycg.github.io/storage-access/
- https://developer.chrome.com/docs/privacy-sandbox/related-website-sets/
- https://webkit.org/blog/8124/introducing-storage-access-api/
