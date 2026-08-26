# content-security-policy-workers-pages

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

DevTools shows `Refused to execute inline script because it violates
the following Content Security Policy directive`. A Pages static
export breaks under a strict CSP because bundled inline scripts have
no nonce. The Cloudflare challenge page (Turnstile, IUAM) stops
rendering after a CSP header is deployed. Violation reports sent to
`report-uri` return 404.

## Context

Workers sit in front of all responses and are the correct place to
inject CSP headers. Pages static exports cannot generate per-request
nonces, so they require hash-based `script-src` or rely on external
script files instead. The Cloudflare challenge page injects its own
scripts from `challenges.cloudflare.com` and breaks if that origin is
absent from the policy. Getting all three concerns right is the main
CSP integration challenge for this stack.

## strict-dynamic with nonces for dynamic Workers responses

```typescript
// workers/csp.ts
function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

function buildCSP(nonce: string): string {
  return [
    `default-src 'self'`,
    // https: http: are fallbacks for browsers without strict-dynamic
    `script-src 'nonce-${nonce}' 'strict-dynamic' https: http:`,
    `style-src 'nonce-${nonce}' 'self'`,
    `img-src 'self' data: https://cdn.example.com`,
    `connect-src 'self' https://api.example.com`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `frame-ancestors 'none'`,
    `report-to csp-endpoint`,
    `report-uri /api/csp-report`,
  ].join("; ");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const nonce = generateNonce();
    const origin = await env.ASSETS.fetch(request);
    const headers = new Headers((await origin).headers);
    headers.set("Content-Security-Policy", buildCSP(nonce));
    // Never cache nonce-bearing HTML at the CDN layer
    headers.set("Cache-Control", "private, no-store");
    const res = new HTMLRewriter()
      .on("script", { element: (el) => el.setAttribute("nonce", nonce) })
      .on("style",  { element: (el) => el.setAttribute("nonce", nonce) })
      .transform(origin);
    return new Response(res.body, { status: res.status, headers });
  },
};
```

## unsafe-inline vs hash-based CSP for static Pages exports

Static Pages exports have no server-side nonce injection. Two options:

**Option A — Hash-based (recommended).**
Compute SHA-256 hashes of every inline script at build time.

```bash
# Hash an inline script block for inclusion in script-src
echo -n 'console.log("init");' \
  | openssl dgst -sha256 -binary | openssl base64 -A
# paste as 'sha256-<hash>' in the _headers file
```

```
# _headers — Cloudflare Pages static header injection
/*
  Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-abc123...' 'sha256-def456...'; object-src 'none'
```

**Option B — Extract inline scripts to external files.**
Move all `<script>` blocks to `.js` files; `script-src 'self'` covers
them with no hashes. This is simpler and easier to maintain.

`'unsafe-inline'` negates XSS protection and must never appear in
`script-src` on a production deployment.

## Cloudflare challenge page CSP requirements

The challenge page injects scripts from `challenges.cloudflare.com`.
A strict CSP without this origin breaks the challenge page silently.

```
# Minimum additions when Cloudflare challenge is active:
script-src ... https://challenges.cloudflare.com;
frame-src  ... https://challenges.cloudflare.com;
```

Cloudflare evaluates the response CSP before the challenge page is
shown. Enable a temporary IUAM rule and verify the challenge renders
without CSP errors before shipping a new policy.

## report-uri and report-to for violation collection

```typescript
headers.set("Reporting-Endpoints", `csp-endpoint="/api/csp-report"`);

// POST /api/csp-report
async function handleCspReport(req: Request, env: Env) {
  if (req.method !== "POST") return new Response(null, { status: 405 });
  env.ANALYTICS.writeDataPoint({
    blobs: [await req.text()], doubles: [1], indexes: ["csp_violation"],
  });
  return new Response(null, { status: 204 });
}
```

Include both `report-to` (Reporting API, modern browsers) and
`report-uri` (legacy fallback for Safari) in the CSP header.

## Testing CSP without breaking the app

```bash
# 1. Deploy in report-only mode first — violations reported, not blocked
Content-Security-Policy-Report-Only: default-src 'self'; ...

# 2. Monitor violations for 48 hours; fix legitimate sources
# 3. Switch to enforcing header
Content-Security-Policy: default-src 'self'; ...

# Verify active policy
curl -sI https://example.com | grep -i content-security-policy

# Automated policy evaluation
# https://csp-evaluator.withgoogle.com/
```

`Report-Only` must never be the permanent production configuration —
it provides no actual XSS protection.

## Anti-patterns

- Using `'unsafe-inline'` in `script-src` — eliminates XSS protection.
- Setting CSP on some routes but not others — must be consistent.
- Omitting `frame-ancestors 'none'` — leaves clickjacking exposure.
- Caching nonce-bearing HTML at the CDN — a cached nonce can be
  exploited by anyone who observes the response.
- Shipping `Report-Only` permanently instead of enforcing.

## Gotchas

- **`'strict-dynamic'` overrides allowlists.** `'self'` and host
  sources in `script-src` are ignored when `'strict-dynamic'` is
  present in supporting browsers; keep them only as fallbacks.
- **`report-uri` is deprecated.** Include it alongside `report-to`
  for Safari and legacy browsers.
- **React hydration and nonces.** Pass the nonce from SSR into
  hydration via a `<meta>` tag or the `nonce` prop; do not regenerate
  it on the client.
- **Cloudflare challenge scripts change.** Never hash-pin challenge
  scripts; use `https://challenges.cloudflare.com` as a host source.

## Verification

- `curl -sI https://example.com | grep -i content-security-policy`
  returns a header with no `'unsafe-inline'` in `script-src`.
- DevTools console shows zero CSP violations on a full page load.
- `https://csp-evaluator.withgoogle.com/` rates the policy as no
  high severity findings.
- A synthetic CSP report POST to `/api/csp-report` appears in
  Analytics Engine within 60 seconds.
- IUAM challenge page renders and completes with the policy active.

## Related

- `security/content-security-policy-csp-modern-deployment.md`
- `security/content-security-policy-nonce.md`
- `security/xss-deep-dive.md`
- `security/x-frame-options-vs-csp.md`
- `cloudflare/workers-best-practices.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- https://content-security-policy.com/strict-dynamic/
- https://web.dev/articles/strict-csp
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://developers.cloudflare.com/turnstile/get-started/
- https://w3c.github.io/reporting/
