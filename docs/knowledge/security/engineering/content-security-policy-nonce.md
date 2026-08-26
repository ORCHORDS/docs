# content-security-policy-nonce

**Issue:** CSP nonce generation in Cloudflare Workers via HTMLRewriter, nonces vs hashes, Strict CSP, reporting endpoint
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your `script-src 'unsafe-inline'` is flagged in a security audit.
You try hashes but they break every time a dev changes an inline
script. You set up nonces but they don't rotate between requests.
Your CSP report-uri returns 404.

## Root cause
**`'unsafe-inline'` negates the XSS protection CSP provides.**
Nonces solve dynamic inline scripts because they are unique per
request and cannot be guessed by an attacker. Hashes are fragile for
dynamic content because the hash must be recomputed on every change.
The CSP is generated in the Worker before the response is streamed
to the client.

**Source:** https://developers.cloudflare.com/workers/examples/alter-headers/
https://content-security-policy.com/nonce/

## Nonce vs hash — when to use each

| | Nonce | Hash |
|---|---|---|
| Dynamic inline scripts | Yes | No (hash changes) |
| Static inline scripts | Either | Yes (no per-request cost) |
| External scripts | Use `'strict-dynamic'` | Same |
| Tooling compatibility | Requires server cooperation | Works with static sites |
| Attack resistance | High (rotate per request) | High (content-locked) |

**Use nonces** for example.com Workers — every response is dynamic.

## Generating a nonce in a Worker

```typescript
function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
```

The nonce must be:
- At least 128 bits of entropy (16 bytes = 128 bits)
- Base64-encoded
- Unique per response (never cached with the nonce in the response)
- **Never** logged or stored

## Injecting nonces via HTMLRewriter

`HTMLRewriter` streams the HTML response and injects the nonce
attribute into `<script>` tags without buffering the whole document.

```typescript
class NonceInjector implements HTMLRewriterElementContentHandlers {
  constructor(private nonce: string) {}

  element(element: Element): void {
    // Only inject into same-origin inline scripts (no src attribute)
    // and trusted external scripts
    element.setAttribute("nonce", this.nonce);
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const nonce = generateNonce();

    // Fetch the origin response (e.g., from Pages or R2)
    const originResponse = await env.ASSETS.fetch(request);

    // Build the CSP header with the nonce
    const csp = buildCSP(nonce);

    // Stream the response through HTMLRewriter
    const transformed = new HTMLRewriter()
      .on("script", new NonceInjector(nonce))
      .on("style", new NonceInjector(nonce))
      .transform(originResponse);

    // Replace or add the CSP header
    const headers = new Headers(transformed.headers);
    headers.set("Content-Security-Policy", csp);
    // Remove any CSP set by the origin (avoid double-CSP)
    headers.delete("X-Content-Security-Policy");

    return new Response(transformed.body, {
      status: transformed.status,
      headers,
    });
  },
};
```

## Building a Strict CSP with nonces

```typescript
function buildCSP(nonce: string): string {
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [
      `'nonce-${nonce}'`,
      "'strict-dynamic'",   // allows scripts loaded by nonce-bearing scripts
      "'unsafe-eval'",      // remove if not needed (avoid if possible)
      "https:",             // fallback for browsers not supporting strict-dynamic
      "http:",              // fallback for local dev
    ],
    "style-src": [
      `'nonce-${nonce}'`,
      "'self'",
    ],
    "img-src": ["'self'", "data:", "https://cdn.example.com"],
    "font-src": ["'self'", "https://cdn.example.com"],
    "connect-src": [
      "'self'",
      "https://api.example.com",
      "wss://rtc.live.cloudflare.com",
    ],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
    "report-uri": ["/api/csp-report"],
    "report-to": ["csp-endpoint"],
  };

  return Object.entries(directives)
    .map(([key, values]) => `${key} ${values.join(" ")}`)
    .join("; ");
}
```

`'strict-dynamic'` allows scripts dynamically loaded by a
nonce-bearing script (e.g., webpack chunks) without listing their
hashes. This is the key to making modern SPAs work with Strict CSP.

## No-cache for nonce-bearing responses

**Never** serve a nonce-bearing HTML response from Cloudflare's CDN
cache. A cached response serves the same nonce to multiple users,
allowing a nonce leak to be exploited.

```typescript
headers.set("Cache-Control", "private, no-store");
// Or at minimum:
headers.set("Vary", "Cookie"); // different nonce per session
```

Alternatively, strip the nonce from cached static pages and only
inject it for authenticated responses.

## CSP reporting endpoint

Set up a Worker endpoint to collect CSP violations for monitoring.

```typescript
// POST /api/csp-report
async function handleCspReport(request: Request, env: Env): Promise<Response> {
  if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

  const contentType = request.headers.get("Content-Type") ?? "";
  let report: unknown;

  if (contentType.includes("application/csp-report")) {
    // Old CSP report format
    report = await request.json();
  } else if (contentType.includes("application/reports+json")) {
    // Reporting API v1 format (array)
    report = await request.json();
  } else {
    return new Response("Unsupported Media Type", { status: 415 });
  }

  // Log to Analytics Engine for aggregation
  env.ANALYTICS.writeDataPoint({
    blobs: [JSON.stringify(report)],
    doubles: [1],
    indexes: ["csp_violation"],
  });

  // Return 204 — no body needed
  return new Response(null, { status: 204 });
}
```

Reporting API header (modern browsers):
```typescript
headers.set(
  "Reporting-Endpoints",
  `csp-endpoint="/api/csp-report"`,
);
```

## Handling nonces in React / Next.js on Workers

```tsx
// React: pass nonce from server context into <script> tags
// Server component (Workers + React SSR):
export function ServerApp({ nonce }: { nonce: string }) {
  return (
    <html>
      <head>
        <script nonce={nonce}  />
      </head>
      <body>...</body>
    </html>
  );
}

// The nonce is set in the Worker before rendering:
const nonce = generateNonce();
const html = renderToString(<ServerApp nonce={nonce} />);
```

## Testing your CSP

```bash
# Check your live CSP:
curl -I https://example.com | grep -i content-security-policy

# Validate with Google CSP Evaluator:
# https://csp-evaluator.withgoogle.com/

# Check browser console for CSP violations (F12 → Console)
```

Browser extensions: "CSP Tester" (Chrome) shows effective policy.

## Verification
- Open DevTools → Network → HTML response → Headers → `Content-Security-Policy`
  confirms nonce is present and changes on each reload
- DevTools → Console → no `Refused to execute inline script` errors
- POST a fake violation to `/api/csp-report`; verify it appears in Analytics Engine
- Load-test: confirm nonce is different across concurrent requests
  (`curl -s https://example.com | grep nonce` repeated 5×)

## Gotchas
- **The "caching" gotcha.** A Cloudflare cache hit serves a stale
  nonce. The attacker who observed the cached nonce can inject a script
  with that nonce. Always `Cache-Control: private, no-store` for
  nonce-bearing HTML.
- **The "React hydration" gotcha.** React expects the server-rendered
  nonce to match the client-side nonce. Pass it via a meta tag or
  a non-cached server variable; do not regenerate on the client.
- **The "report-uri deprecated" gotcha.** `report-uri` is deprecated
  in favour of `report-to` + Reporting API. Include both for backward
  compatibility.
- **The "strict-dynamic overrides allowlist" gotcha.** When
  `'strict-dynamic'` is present, `'self'` and host allowlists are
  ignored for `script-src` in modern browsers. Keep them only as
  fallbacks for older browsers.
- **The "style nonce" gotcha.** Injecting nonces into `<style>` tags
  requires `style-src 'nonce-...'`. If you use a CSS-in-JS library
  that injects styles dynamically, you may need `'unsafe-inline'` for
  styles — isolate script and style policies.

## Related
- `cloudflare/csp-headers-and-cf-waf.md`
- `security/csp-deep-2026.md`
- `security/xss-deep-2026.md`
- `security/security-headers-comprehensive.md`
- CF HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- MDN CSP: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- CSP nonce guide: https://content-security-policy.com/nonce/
- Google Strict CSP: https://web.dev/strict-csp/
