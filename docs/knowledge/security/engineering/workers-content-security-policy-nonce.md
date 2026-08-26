# Per-Request CSP Nonce Injection with Workers and HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker serves HTML pages (proxied from an origin or generated inline) and you need a strict Content-Security-Policy that allows only explicitly authorised inline scripts while blocking injected XSS payloads. A per-request cryptographic nonce injected into each `<script>` and `<style>` tag via `HTMLRewriter` — combined with a `Content-Security-Policy` header using `'nonce-{value}' 'strict-dynamic'` — achieves this without whitelisting unsafe inline scripts globally.

---

## Context

Static CSP nonces are useless because an attacker who can read a static nonce can reuse it. The nonce must be different on every HTTP response so that it cannot be cached and replayed. Cloudflare Workers run on every request, making them the ideal injection point: `HTMLRewriter` streams the HTML response and appends `nonce="{token}"` attributes to `<script>` and `<style>` elements before they reach the browser. The same nonce value is placed in the `Content-Security-Policy` header. `'strict-dynamic'` propagates trust to scripts loaded by a nonced script, removing the need to whitelist every CDN URL. A reporting endpoint — also deployed as a Worker route — collects CSP violation reports for monitoring.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name            = "csp-nonce-proxy"
main            = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
ORIGIN_URL        = "https://origin.example.com"
CSP_REPORT_URI    = "/csp-report"

# Route that handles the CSP report endpoint
[[routes]]
pattern = "example.com/csp-report"
zone_name = "example.com"
```

---

## Section 2 — Worker Implementation

```typescript
// src/nonce.ts

/**
 * Generate a cryptographically random nonce suitable for CSP.
 * crypto.randomUUID() produces 36 chars of entropy (122 random bits);
 * the hyphens are stripped so the value is URL-safe and slightly shorter.
 */
export function generateNonce(): string {
  return crypto.randomUUID().replace(/-/g, '');
}

export function buildCspHeader(nonce: string, reportUri: string): string {
  return [
    `default-src 'self'`,
    `script-src 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'nonce-${nonce}' 'self'`,
    `img-src 'self' data: https:`,
    `font-src 'self' https://fonts.gstatic.com`,
    `connect-src 'self'`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `frame-ancestors 'none'`,
    `upgrade-insecure-requests`,
    `report-uri ${reportUri}`,
  ].join('; ');
}
```

```typescript
// src/index.ts
import { generateNonce, buildCspHeader } from './nonce';

export interface Env {
  ORIGIN_URL: string;
  CSP_REPORT_URI: string;
}

/** HTMLRewriter handler that appends nonce to script/style elements. */
class NonceInjector implements HTMLRewriterElementContentHandlers {
  constructor(private readonly nonce: string) {}

  element(element: Element): void {
    element.setAttribute('nonce', this.nonce);
  }
}

/** CSP violation report handler */
async function handleCspReport(request: Request): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }
  try {
    const report = await request.json<{ 'csp-report': Record<string, unknown> }>();
    // In production, forward to your logging pipeline (e.g. Logpush, Sentry).
    console.log('CSP violation:', JSON.stringify(report['csp-report']));
  } catch {
    // Ignore malformed reports
  }
  return new Response(null, { status: 204 });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Handle the CSP report endpoint
    if (url.pathname === '/csp-report') {
      return handleCspReport(request);
    }

    // Proxy to origin
    const originUrl = new URL(url.pathname + url.search, env.ORIGIN_URL);
    const originResponse = await fetch(originUrl.toString(), {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });

    const contentType = originResponse.headers.get('Content-Type') ?? '';

    // Only rewrite HTML responses
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    const nonce = generateNonce();
    const csp = buildCspHeader(nonce, env.CSP_REPORT_URI);

    // Build response headers: forward origin headers, add/replace CSP
    const responseHeaders = new Headers(originResponse.headers);
    responseHeaders.set('Content-Security-Policy', csp);
    // Remove legacy X-XSS-Protection — CSP replaces it
    responseHeaders.delete('X-XSS-Protection');
    // Prevent the browser from sniffing MIME types (belt-and-suspenders)
    responseHeaders.set('X-Content-Type-Options', 'nosniff');

    // Stream HTML through HTMLRewriter, injecting the nonce
    const rewriter = new HTMLRewriter()
      .on('script', new NonceInjector(nonce))
      .on('style', new NonceInjector(nonce));

    return rewriter.transform(
      new Response(originResponse.body, {
        status: originResponse.status,
        statusText: originResponse.statusText,
        headers: responseHeaders,
      }),
    );
  },
};
```

---

## Section 3 — Testing / Verification

```typescript
// test/nonce.test.ts
import { describe, it, expect } from 'vitest';
import { generateNonce, buildCspHeader } from '../src/nonce';

describe('generateNonce', () => {
  it('produces a 32-character hex-like string', () => {
    const nonce = generateNonce();
    expect(nonce).toHaveLength(32);
    expect(nonce).toMatch(/^[0-9a-f]+$/);
  });

  it('produces a unique value on each call', () => {
    const set = new Set(Array.from({ length: 1000 }, generateNonce));
    expect(set.size).toBe(1000);
  });
});

describe('buildCspHeader', () => {
  it('contains the nonce in script-src and style-src', () => {
    const nonce = 'abc123';
    const header = buildCspHeader(nonce, '/csp-report');
    expect(header).toContain(`'nonce-${nonce}'`);
    expect(header).toContain("'strict-dynamic'");
    expect(header).toContain("object-src 'none'");
  });
});
```

```bash
# Integration test: verify nonce appears in response HTML
curl -s https://csp-nonce-proxy.<subdomain>.workers.dev/ \
  | grep -oP 'nonce="[^"]+"' | head -5

# Verify CSP header is present and contains nonce
curl -sI https://csp-nonce-proxy.<subdomain>.workers.dev/ \
  | grep -i content-security-policy
```

---

## Anti-patterns

- **Using a static nonce baked into the HTML template** — a nonce that is the same across responses provides no security; it must be unique per response.
- **Adding `'unsafe-inline'` alongside a nonce** — this silently disables nonce enforcement in browsers that support CSP Level 2; omit `'unsafe-inline'` entirely.
- **Caching HTML responses that contain a nonce** — cached pages will serve the same nonce to every visitor; set `Cache-Control: no-store` on HTML responses or vary by nonce.
- **Forgetting inline event handlers** (`onclick="..."`) — `'strict-dynamic'` does not cover inline event handlers; refactor them to `addEventListener`.
- **Rewriting non-HTML responses** — only run HTMLRewriter on `Content-Type: text/html` to avoid corrupting JSON, images, or binary assets.

---

## Gotchas

- `HTMLRewriter` is a streaming transformer; it does not parse the full DOM. Tag matching is case-insensitive but attribute order is preserved.
- If the origin already sets a `Content-Security-Policy` header, you must explicitly overwrite it with `responseHeaders.set(...)`, not `append`.
- `<link rel="stylesheet">` tags are not `<style>` tags; if you use external stylesheets loaded by `<link>`, add `'self'` to `style-src` or whitelist the host explicitly.
- The Workers `HTMLRewriter` `element()` handler runs for every matched element, including dynamically inserted ones during streaming — this is the correct hook for nonce injection.
- `report-uri` is deprecated in CSP Level 3 in favour of `report-to`; include both for maximum compatibility during transition.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Check that each response has a unique CSP nonce
for i in 1 2 3; do
  curl -sI https://csp-nonce-proxy.<subdomain>.workers.dev/ \
    | grep -i content-security-policy \
    | grep -oP "nonce-[a-f0-9]+"
done
# All three values should be different

# Run unit tests
npx vitest run

# Use Google CSP Evaluator to validate the policy:
# https://csp-evaluator.withgoogle.com/
```

---

## Related

- `workers-csrf-double-submit-cookie-pattern.md`
- `workers-ip-rate-limiting-kv-sliding-window.md`

---

## Sources

- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- MDN Content-Security-Policy — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
- CSP Level 3 W3C Specification — https://www.w3.org/TR/CSP3/
- Google CSP Evaluator — https://csp-evaluator.withgoogle.com/
