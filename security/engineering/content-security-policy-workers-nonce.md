# Content Security Policy: Per-Request Nonce in Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Inline scripts blocked by CSP in production even though `'unsafe-inline'` is absent. Mobile WebView
reports `ERR_BLOCKED_BY_CSP` for first-party inline event handlers. next-intl locale switcher
breaks after adding a nonce-based policy. Logpush shows `csp-violation` events with empty `script-sample`.

## Context

example project (example.com) uses Cloudflare Workers as the API and edge rendering layer. CSP headers must be set
per-request, not statically, because each response embeds a unique nonce. Static CSP set in
`_headers` or `wrangler.toml` cannot carry a per-request nonce — it must be injected in the Worker
response handler and propagated through the React/next-intl render tree. Mobile WebView runtimes
(WKWebView on iOS, WebView on Android) enforce CSP more strictly than desktop Chrome for certain
directive combinations, and `report-uri` delivery differs from `report-to`.

---

## Nonce Generation in Workers

Every HTML response gets a fresh nonce. The nonce must be cryptographically random, base64url-encoded,
and at least 128 bits.

```ts
// workers/src/lib/csp.ts
export function generateNonce(): string {
  const bytes = new Uint8Array(16); // 128 bits
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, ''); // base64url
}

export function buildCspHeader(nonce: string, env: Env): string {
  const reportUri = `https://csp.example.com/report?v=1`;
  const directives: string[] = [
    `default-src 'none'`,
    `script-src 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'nonce-${nonce}' https://fonts.googleapis.com`,
    `font-src https://fonts.gstatic.com`,
    `img-src 'self' data: https://cdn.example.com`,
    `connect-src 'self' https://api.example.com wss://rt.example.com`,
    `frame-ancestors 'none'`,
    `base-uri 'none'`,
    `form-action 'self'`,
    `upgrade-insecure-requests`,
    `report-uri ${reportUri}`,
    `report-to csp-endpoint`,
  ];
  return directives.join('; ');
}
```

The `'strict-dynamic'` keyword makes nonce-validated scripts able to load further scripts
dynamically without whitelisting those URLs — critical for Next.js chunk loading.

---

## Nonce Propagation Through next-intl

next-intl's `<NextIntlClientProvider>` serialises locale messages into an inline script. Without
nonce propagation, this script is blocked.

```tsx
// app/layout.tsx  (Next.js App Router on Workers / next-on-pages)
import { headers } from 'next/headers';
import { NextIntlClientProvider } from 'next-intl';

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Workers middleware injects X-Nonce before the Next.js handler runs
  const nonce = (await headers()).get('x-nonce') ?? '';

  return (
    <html lang="en">
      <head>
        {/* CSP nonce on any <script> or <style> emitted by layout */}
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: '' }} />
      </head>
      <body>
        <NextIntlClientProvider nonce={nonce}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
```

```ts
// workers/src/middleware/nonce.ts  — sets X-Nonce before Next.js sees the request
import { generateNonce, buildCspHeader } from '../lib/csp';

export async function nonceMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  next: () => Promise<Response>,
): Promise<Response> {
  const nonce = generateNonce();
  // Clone request with nonce header so Next.js can read it
  const proxied = new Request(request, {
    headers: { ...Object.fromEntries(request.headers), 'x-nonce': nonce },
  });

  const response = await next(); // call Next.js handler
  const mutableResponse = new Response(response.body, response);
  mutableResponse.headers.set('content-security-policy', buildCspHeader(nonce, env));
  mutableResponse.headers.set(
    'reporting-endpoints',
    `csp-endpoint="https://csp.example.com/report"`,
  );
  return mutableResponse;
}
```

---

## Mobile WebView CSP Enforcement Differences

| Behaviour                         | Desktop Chrome 125+ | WKWebView (iOS 17) | Android WebView (API 34) |
|-----------------------------------|---------------------|--------------------|--------------------------|
| `'strict-dynamic'` honoured       | Yes                 | Yes (iOS 16.4+)    | Yes (Chromium 114+)      |
| `report-uri` delivery             | Yes                 | No (silent drop)   | Yes                      |
| `report-to` / Reporting API v1    | Yes                 | No                 | Partial (flag needed)    |
| `frame-ancestors` enforced        | Yes                 | Yes                | Yes                      |
| `upgrade-insecure-requests`       | Yes                 | Yes                | Yes                      |
| `wasm-unsafe-eval` required       | Only for Wasm       | Yes, always        | Only for Wasm            |
| Inline event handler (`onclick=`) | Blocked by nonce    | Blocked            | Blocked                  |

WKWebView silently drops `report-uri` requests. Use in-app JS error listeners as a fallback:

```ts
// Mobile app (React Native WebView) — catch CSP violations locally
webviewRef.current?.injectJavaScript(`
  document.addEventListener('securitypolicyviolation', (e) => {
    window.ReactNativeWebView.postMessage(JSON.stringify({
      type: 'csp-violation',
      blockedURI: e.blockedURI,
      violatedDirective: e.violatedDirective,
      disposition: e.disposition,
    }));
  });
`);
```

---

## report-uri via Cloudflare Logpush

Route CSP violation reports to Cloudflare Logpush for centralised analysis without a separate
reporting server.

```jsonc
// wrangler.toml — Workers Route for the report collector
[[routes]]
pattern = "csp.example.com/report"
zone_name = "example.com"
```

```ts
// workers/src/handlers/cspReport.ts
export async function handleCspReport(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') return new Response(null, { status: 405 });

  const contentType = request.headers.get('content-type') ?? '';
  let payload: unknown;
  if (contentType.includes('application/csp-report')) {
    payload = await request.json(); // legacy format
  } else if (contentType.includes('application/reports+json')) {
    payload = await request.json(); // Reporting API v1
  } else {
    return new Response(null, { status: 415 });
  }

  // Emit to Analytics Engine for Logpush
  env.CSP_AE.writeDataPoint({
    blobs: [JSON.stringify(payload), request.headers.get('user-agent') ?? ''],
    indexes: ['csp-violation'],
  });

  return new Response(null, { status: 204 });
}
```

Enable Logpush dataset `workers_analytics_engine` → S3/R2 bucket with field `blob1` to get
structured CSP reports in your SIEM.

---

## Directive Reference Table

| Directive                  | example project value                                              | Rationale                              |
|----------------------------|---------------------------------------------------------|----------------------------------------|
| `script-src`               | `'nonce-{n}' 'strict-dynamic'`                         | Nonce-only; dynamic children inherit   |
| `style-src`                | `'nonce-{n}' https://fonts.googleapis.com`             | Google Fonts stylesheet allowed        |
| `connect-src`              | `'self' https://api.example.com wss://rt.example.com`    | API + realtime WS                      |
| `img-src`                  | `'self' data: https://cdn.example.com`                  | CDN and inline avatar data URIs        |
| `frame-ancestors`          | `'none'`                                               | Clickjacking prevention                |
| `base-uri`                 | `'none'`                                               | Prevent base-tag injection             |
| `form-action`              | `'self'`                                               | No off-origin form POST                |
| `object-src`               | `'none'`                                               | No plugins                             |
| `upgrade-insecure-requests`| (flag)                                                 | HTTP→HTTPS upgrade                     |

---

## Anti-patterns

- Setting `'unsafe-inline'` alongside a nonce: `'unsafe-inline'` is *ignored* by browsers that
  support nonces, but it signals intent to fall back to inline — drop it entirely.
- Reusing a nonce across requests: nonces must be per-response, never cached or stored in KV.
- Serving the nonce in a meta tag only: mobile WebViews may not honour `<meta http-equiv="Content-Security-Policy">` equivalently to the HTTP header — always set the header.
- Putting `report-uri` without a CORS-capable receiver: the browser POSTs from the page origin; the receiver must accept cross-origin POSTs or use same-origin Workers routing.
- Omitting `wasm-unsafe-eval` for WASM modules on WKWebView: required even with a nonce on iOS.

## Gotchas

- `'strict-dynamic'` ignores URL allowlists in `script-src` when a nonce is present — removing a
  nonce causes previously-trusted CDN URLs to suddenly fail unless added back.
- next-intl v3+ reads `nonce` from `RequestContext` not from props — confirm the version contract
  before using the prop-based approach shown above.
- Cloudflare's HTML minifier (Polish) can strip `nonce` attributes — disable Polish on HTML
  responses or configure it to preserve attributes.
- `report-to` requires the `Reporting-Endpoints` header (not `Report-To`) in Reporting API v1;
  mixing the two causes Firefox to ignore reports.
- Workers `HTMLRewriter` can inject nonce attributes during streaming but only on elements it
  visits; ensure the rewriter selector covers all `<script>` and `<style>` tags including those
  emitted by Next.js server components.

## Verification

```bash
# 1. Confirm nonce is unique per response
for i in {1..5}; do
  curl -si https://example.com/ | grep -i 'content-security-policy' | grep -oP "nonce-[^']*"
done
# Expect 5 different nonce values

# 2. Confirm report-uri endpoint accepts POST
curl -X POST https://csp.example.com/report \
  -H 'Content-Type: application/csp-report' \
  -d '{"csp-report":{"blocked-uri":"https://evil.com","violated-directive":"script-src"}}' \
  -o /dev/null -w '%{http_code}'
# Expect 204

# 3. Validate CSP with Google CSP Evaluator (manual)
# https://csp-evaluator.withgoogle.com/

# 4. Check WKWebView enforcement (iOS simulator)
# Open Safari → Develop → Simulator → Console, load https://example.com/
# Expect zero CSP console errors
```

## Related

- `content-security-policy-workers-pages.md`
- `content-security-policy-nonce.md`
- `x-frame-options-vs-csp.md`
- `security-headers-comprehensive.md`
- `clickjacking-defense.md`

## Sources

- MDN CSP nonce: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/script-src#nonces
- W3C CSP Level 3 `strict-dynamic`: https://www.w3.org/TR/CSP3/#strict-dynamic-usage
- Cloudflare Workers Crypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- next-intl nonce support: https://next-intl.dev/docs/environments/server-client-components#nonce
- Reporting API v1: https://www.w3.org/TR/reporting-1/
- Cloudflare Logpush Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
