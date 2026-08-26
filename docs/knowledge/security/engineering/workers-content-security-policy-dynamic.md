# Dynamic Content Security Policy Generation with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your application serves HTML with inline scripts or styles that require a Content Security Policy nonce. A static `Content-Security-Policy` header cannot include a fresh nonce per request. A Cloudflare Worker sits in front of the origin, generates a cryptographically random nonce for every request, rewrites the HTML to inject `nonce="..."` attributes, and sets the CSP header with the matching nonce value — all without touching origin code.

## Context

Content Security Policy (CSP) is a browser security mechanism that restricts which resources a page may load or execute. A nonce-based policy (`script-src 'nonce-{value}' 'strict-dynamic'`) is the most robust approach: only script elements carrying the correct nonce value are executed. Workers are uniquely positioned to add nonces because they process both the response headers and the response body via `HTMLRewriter` before the browser sees either.

## Solution

### Step 1 — Nonce Generation per Request

```typescript
// lib/csp.ts
export function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}
```

### Step 2 — Per-route CSP Policy Configuration

```typescript
// lib/policies.ts
export interface CspDirectives {
  defaultSrc?: string[];
  scriptSrc?: string[];
  styleSrc?: string[];
  imgSrc?: string[];
  connectSrc?: string[];
  fontSrc?: string[];
  objectSrc?: string[];
  frameSrc?: string[];
  reportUri?: string;
}

const BASE_POLICY: CspDirectives = {
  defaultSrc: ["'none'"],
  scriptSrc: ["'strict-dynamic'"],  // nonce added at runtime
  styleSrc: ["'self'"],
  imgSrc: ["'self'", 'data:'],
  connectSrc: ["'self'"],
  fontSrc: ["'self'"],
  objectSrc: ["'none'"],
  frameSrc: ["'none'"],
  reportUri: '/csp-report',
};

const ROUTE_OVERRIDES: Record<string, Partial<CspDirectives>> = {
  '/embed': { frameSrc: ['https://trusted-embed.example.com'] },
  '/maps':  { imgSrc: ["'self'", 'https://maps.googleapis.com'] },
};

export function getPolicyForPath(pathname: string): CspDirectives {
  const override = ROUTE_OVERRIDES[pathname] ?? {};
  return {
    ...BASE_POLICY,
    ...override,
    // Merge array directives rather than replace
    imgSrc: [...(BASE_POLICY.imgSrc ?? []), ...(override.imgSrc ?? [])],
    frameSrc: [...(BASE_POLICY.frameSrc ?? []), ...(override.frameSrc ?? [])],
  };
}

export function buildCspHeader(policy: CspDirectives, nonce: string): string {
  const directives: string[] = [];

  const addDirective = (name: string, values?: string[]) => {
    if (values && values.length > 0) {
      directives.push(`${name} ${values.join(' ')}`);
    }
  };

  // Inject nonce into script-src
  const scriptSrc = [...(policy.scriptSrc ?? []), `'nonce-${nonce}'`];

  addDirective('default-src', policy.defaultSrc);
  addDirective('script-src', scriptSrc);
  addDirective('style-src', policy.styleSrc);
  addDirective('img-src', policy.imgSrc);
  addDirective('connect-src', policy.connectSrc);
  addDirective('font-src', policy.fontSrc);
  addDirective('object-src', policy.objectSrc);
  addDirective('frame-src', policy.frameSrc);

  if (policy.reportUri) {
    directives.push(`report-uri ${policy.reportUri}`);
  }

  return directives.join('; ');
}
```

### Step 3 — HTMLRewriter Nonce Injector

```typescript
// lib/nonceInjector.ts
class NonceInjector implements HTMLRewriterElementContentHandlers {
  constructor(private nonce: string) {}

  element(element: Element): void {
    // Only inject nonce if the script/style does not already have one
    if (!element.getAttribute('nonce')) {
      element.setAttribute('nonce', this.nonce);
    }
    // Remove unsafe inline attributes
    element.removeAttribute('onclick');
    element.removeAttribute('onload');
  }
}

export function injectNonces(response: Response, nonce: string): Response {
  return new HTMLRewriter()
    .on('script', new NonceInjector(nonce))
    .on('style', new NonceInjector(nonce))
    .on('link[rel="stylesheet"]', new NonceInjector(nonce))
    .transform(response);
}
```

### Step 4 — CSP Violation Report Endpoint

```typescript
// handlers/cspReport.ts
export interface CspViolation {
  documentUri: string;
  violatedDirective: string;
  blockedUri: string;
  originalPolicy: string;
  timestamp: number;
  userAgent: string;
}

export async function handleCspReport(
  request: Request,
  db: D1Database
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let body: { 'csp-report'?: Partial<CspViolation> };
  try {
    body = await request.json();
  } catch {
    return new Response('Invalid JSON', { status: 400 });
  }

  const report = body['csp-report'];
  if (!report) return new Response('No report', { status: 400 });

  await db.prepare(
    `INSERT INTO csp_violations
       (document_uri, violated_directive, blocked_uri, original_policy, timestamp, user_agent)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(
    report.documentUri ?? '',
    report.violatedDirective ?? '',
    report.blockedUri ?? '',
    report.originalPolicy ?? '',
    Date.now(),
    request.headers.get('user-agent') ?? ''
  ).run();

  return new Response(null, { status: 204 });
}
```

### Step 5 — D1 Schema for Violation Logging

```sql
-- migrations/001_csp_violations.sql
CREATE TABLE IF NOT EXISTS csp_violations (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  document_uri     TEXT    NOT NULL,
  violated_directive TEXT  NOT NULL,
  blocked_uri      TEXT    NOT NULL,
  original_policy  TEXT    NOT NULL,
  timestamp        INTEGER NOT NULL,
  user_agent       TEXT    NOT NULL
);
CREATE INDEX idx_csp_violations_ts ON csp_violations (timestamp);
CREATE INDEX idx_csp_violations_directive ON csp_violations (violated_directive);
```

### Step 6 — Worker Integration

```typescript
// worker.ts
import { generateNonce } from './lib/csp';
import { getPolicyForPath, buildCspHeader } from './lib/policies';
import { injectNonces } from './lib/nonceInjector';
import { handleCspReport } from './handlers/cspReport';

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/csp-report') {
      return handleCspReport(request, env.DB);
    }

    // Fetch from origin
    const originResponse = await fetch(request);

    // Only process HTML responses
    const contentType = originResponse.headers.get('content-type') ?? '';
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    const nonce = generateNonce();
    const policy = getPolicyForPath(url.pathname);
    const cspHeader = buildCspHeader(policy, nonce);

    // Build new response headers
    const responseHeaders = new Headers(originResponse.headers);
    responseHeaders.set('Content-Security-Policy', cspHeader);
    // Remove any permissive CSP the origin may have set
    responseHeaders.delete('X-Content-Security-Policy');

    const newResponse = new Response(originResponse.body, {
      status: originResponse.status,
      headers: responseHeaders,
    });

    return injectNonces(newResponse, nonce);
  },
};
```

## Implementation Details

- **16-byte nonce**: 16 random bytes give 128 bits of entropy, sufficient for a per-request nonce. Base64-encoded length is 24 characters.
- **strict-dynamic**: When `strict-dynamic` is combined with a nonce, the browser trusts scripts that the nonced script dynamically inserts — useful for frameworks that lazy-load modules.
- **report-uri vs report-to**: `report-uri` is widely supported; `report-to` (Reporting API) is the modern successor but has limited browser coverage as of 2026. Implement both if broad coverage matters.
- **HTMLRewriter streaming**: `HTMLRewriter` processes the body as a stream — no buffering, no memory spike even for large HTML documents.
- **Inline event handlers**: The `NonceInjector` strips `onclick`/`onload` attributes; these cannot receive a nonce and should be moved to nonced script blocks.

## Anti-patterns

- Do not use `'unsafe-inline'` alongside a nonce — it defeats the purpose because CSP3 browsers ignore `'unsafe-inline'` when a nonce is present, but CSP2 browsers do not.
- Do not generate the nonce at deploy time (e.g., in a build step) — it must be unique per HTTP response.
- Do not set `'unsafe-eval'` unless absolutely required by a specific dependency; prefer building that dependency without eval.
- Do not log raw CSP violation reports to a public endpoint without authentication — they can be used to probe your policy.

## Gotchas

- Some CDN or edge caching layers will cache the HTML response and serve the same nonce to multiple users, breaking legitimate scripts. Ensure HTML responses have `Cache-Control: no-store` or are excluded from edge cache.
- `HTMLRewriter` operates on the response stream; if the origin sends `Content-Encoding: gzip`, Workers automatically decompresses it before `HTMLRewriter` sees it.
- The `report-uri` directive is deprecated in CSP Level 3 in favor of `report-to`, but dropping `report-uri` entirely will lose reports from older browsers.
- CSP violation reports are sent by the browser as `application/csp-report` (JSON), not `application/json` — ensure the `Content-Type` check in the report handler is lenient or accepts both.

## Verification

1. Fetch an HTML page and inspect the `Content-Security-Policy` response header — it should contain a `nonce-` value.
2. Make two requests to the same path — the nonce values must differ.
3. Add a `<script>` element without a nonce to the origin HTML — the browser should block it and send a CSP report.
4. Query D1: `SELECT * FROM csp_violations ORDER BY timestamp DESC LIMIT 10;` — violations should appear.
5. Load `/embed` and confirm the `frame-src` directive includes `https://trusted-embed.example.com`.

## Related

- `workers-subresource-integrity-r2.md` — SRI hashing for external scripts alongside CSP
- `workers-request-signing-hmac.md` — signing requests to the CSP report ingest endpoint

## Sources

- MDN CSP: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- W3C CSP Level 3: https://www.w3.org/TR/CSP3/
- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare D1: https://developers.cloudflare.com/d1/
