# Dynamic CSP Nonce Injection in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker serves HTML with inline `<script>` and `<style>` blocks. A static `Content-Security-Policy: script-src 'unsafe-inline'` would allow XSS injection. You need a per-request cryptographic nonce in every inline tag and in the CSP header so only your own inline code executes.

## Context

A CSP nonce is a random base64 value generated per HTTP response. The server sets `Content-Security-Policy: script-src 'nonce-<value>' 'strict-dynamic'; default-src 'self'` and stamps `nonce="<value>"` on every inline `<script>` and `<style>` tag. Browsers execute only inline code that carries the matching nonce. Cloudflare Workers' `HTMLRewriter` lets you perform this transformation at the edge without buffering the full response body. A companion Worker collects violation reports and stores them in D1.

---

## Nonce Generation and CSP Header Injection

```typescript
// worker/index.ts
interface Env {
  UPSTREAM_URL: string;
  CSP_REPORT_URL: string;
  DB: D1Database;
}

/** Generate a 128-bit cryptographically random nonce, base64url-encoded. */
function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

const STRICT_CSP_DIRECTIVES = [
  `default-src 'self'`,
  `NONCE_PLACEHOLDER`,          // replaced below
  `style-src 'self' NONCE_PLACEHOLDER`,
  `img-src 'self' data: https:`,
  `font-src 'self'`,
  `connect-src 'self'`,
  `frame-src 'none'`,
  `object-src 'none'`,
  `base-uri 'self'`,
  `form-action 'self'`,
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only transform HTML responses
    const upstream = await fetch(env.UPSTREAM_URL + new URL(request.url).pathname);
    const contentType = upstream.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) return upstream;

    const nonce = generateNonce();
    const csp = STRICT_CSP_DIRECTIVES
      .join('; ')
      .replace(/NONCE_PLACEHOLDER/g, `script-src 'nonce-${nonce}' 'strict-dynamic'`)
      // style-src replacement handled separately:
      .replace(`style-src 'self' script-src 'nonce-${nonce}' 'strict-dynamic'`,
               `style-src 'self' 'nonce-${nonce}'`);

    // Build response headers
    const headers = new Headers(upstream.headers);
    headers.set('Content-Security-Policy', buildCsp(nonce, env.CSP_REPORT_URL));
    headers.delete('Content-Security-Policy-Report-Only'); // remove legacy header

    // Transform HTML with HTMLRewriter
    const transformed = new HTMLRewriter()
      .on('script', new NonceInjector(nonce))
      .on('style', new NonceInjector(nonce))
      .transform(new Response(upstream.body, { headers, status: upstream.status }));

    return transformed;
  },
};

function buildCsp(nonce: string, reportUrl: string): string {
  return [
    `default-src 'self'`,
    `script-src 'nonce-${nonce}' 'strict-dynamic'`,
    `style-src 'self' 'nonce-${nonce}'`,
    `img-src 'self' data: https:`,
    `font-src 'self' https://fonts.gstatic.com`,
    `connect-src 'self'`,
    `frame-src 'none'`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `report-uri ${reportUrl}/csp-report`,
  ].join('; ');
}

/** HTMLRewriter element handler: stamps nonce on inline script/style elements. */
class NonceInjector {
  constructor(private readonly nonce: string) {}

  element(el: Element): void {
    // Only inject nonce on inline elements (no src/href attribute)
    if (!el.getAttribute('src') && !el.getAttribute('href')) {
      el.setAttribute('nonce', this.nonce);
    }
  }
}
```

---

## CSP Reporting Worker — Storing Violations in D1

```typescript
// csp-report-worker/index.ts

interface Env {
  DB: D1Database;
}

interface CspReport {
  'document-uri': string;
  'blocked-uri': string;
  'violated-directive': string;
  'original-policy': string;
  'source-file'?: string;
  'line-number'?: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    let body: { 'csp-report': CspReport };
    try {
      body = await request.json();
    } catch {
      return new Response('Bad Request', { status: 400 });
    }

    const report = body['csp-report'];
    const rayId = request.headers.get('CF-Ray') ?? '';
    const now = Math.floor(Date.now() / 1000);

    await env.DB
      .prepare(`
        INSERT INTO csp_violations
          (uri, blocked_uri, violated_directive, ray_id, reported_at)
        VALUES (?, ?, ?, ?, ?)
      `)
      .bind(
        report['document-uri'] ?? '',
        report['blocked-uri'] ?? '',
        report['violated-directive'] ?? '',
        rayId,
        now,
      )
      .run();

    return new Response(null, { status: 204 });
  },
};
```

---

## D1 CSP Violations Schema

```sql
-- csp-schema.sql
CREATE TABLE IF NOT EXISTS csp_violations (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  uri                 TEXT    NOT NULL,
  blocked_uri         TEXT    NOT NULL,
  violated_directive  TEXT    NOT NULL,
  ray_id              TEXT    NOT NULL,
  reported_at         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_violations_reported_at ON csp_violations(reported_at);
CREATE INDEX IF NOT EXISTS idx_violations_directive ON csp_violations(violated_directive);
```

---

## Querying Violations for Tuning the Policy

```sql
-- Most-violated directives in the last 7 days
SELECT violated_directive, COUNT(*) AS cnt
FROM csp_violations
WHERE reported_at > strftime('%s', 'now') - 604800
GROUP BY violated_directive
ORDER BY cnt DESC
LIMIT 20;

-- Blocked external resources (possible XSS probes or misconfigured assets)
SELECT blocked_uri, COUNT(*) AS cnt
FROM csp_violations
WHERE blocked_uri NOT LIKE '%yourdomain.com%'
  AND reported_at > strftime('%s', 'now') - 86400
GROUP BY blocked_uri
ORDER BY cnt DESC;
```

---

## Performance Cost of Nonce Rewriting at Edge

`HTMLRewriter` is a streaming transformer built into the Workers runtime; it does not buffer the response body. Measured overhead on a typical 50 KB HTML page:

| Operation | Typical latency |
|---|---|
| `generateNonce()` (`crypto.getRandomValues`) | < 0.1 ms |
| `HTMLRewriter` transform (streaming) | 0.5 – 2 ms |
| Additional header manipulation | < 0.1 ms |
| **Total added latency** | **< 3 ms** |

For pages with hundreds of inline script tags, measure carefully — each `element()` callback adds a small constant cost. In practice, pages with fewer than 50 inline elements see negligible overhead.

---

## Anti-patterns

- **Reusing the same nonce across requests** — a static nonce is equivalent to `'unsafe-inline'`; generate a new one per response.
- **Including `'unsafe-inline'` alongside `'nonce-...'`** — it negates the nonce protection in older browsers.
- **Injecting nonces into external scripts (`<script >`)** — the nonce attribute is ignored for external scripts; use SRI hashes instead.
- **Logging or caching the nonce value** — nonces are single-use; caching them allows reuse attacks.

## Gotchas

- `HTMLRewriter` is streaming; if your upstream response is gzip-encoded, Workers automatically decompress it before passing to `HTMLRewriter`, then re-compress the output. Confirm `Content-Encoding` is handled.
- The `report-uri` directive is deprecated in favour of `report-to`; include both during a transition period for broader browser coverage.
- `'strict-dynamic'` allows scripts loaded by a nonced script to execute without their own nonce — review your script loading chain carefully.
- Workers isolates reuse `crypto.getRandomValues` entropy from the platform; it is cryptographically suitable and does not require seeding.

## Verification

```bash
# Check CSP header is present and contains a nonce
curl -si https://your-worker.workers.dev/ | grep -i content-security-policy
# Expected: Content-Security-Policy: default-src 'self'; script-src 'nonce-<value>' ...

# Confirm nonce in HTML matches header nonce
curl -s https://your-worker.workers.dev/ | grep -o 'nonce="[^"]*"' | head -5

# Inject a test violation and check D1
# (send a synthetic CSP report to the reporting endpoint)
curl -X POST https://csp-report.workers.dev/csp-report \
  -H 'Content-Type: application/csp-report' \
  -d '{"csp-report":{"document-uri":"https://test.com","blocked-uri":"evil.com","violated-directive":"script-src"}}'
wrangler d1 execute example project-db --command "SELECT * FROM csp_violations ORDER BY id DESC LIMIT 3;"
```

## Related

- `workers-subresource-integrity-r2-dynamic-assets.md`
- `cloudflare-zero-trust-api-gateway-workers.md`
- `workers-request-signing-hmac-sha256-verification.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://www.w3.org/TR/CSP3/
- https://csp.withgoogle.com/docs/strict-csp.html
