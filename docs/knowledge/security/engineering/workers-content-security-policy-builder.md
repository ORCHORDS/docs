# Dynamic Content Security Policy Generation in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker serves HTML pages and needs a strict Content Security Policy (CSP) that changes per request — injecting a unique nonce into inline scripts via HTMLRewriter, storing CSP violation reports in D1, enabling Report-Only mode during policy rollout, and applying different policies to different routes without duplicating configuration.

---

## Context

A static CSP header is easy to configure in `wrangler.toml`, but it cannot include per-request nonces, which are required for `strict-dynamic` to work with inline scripts. HTMLRewriter allows the Worker to rewrite HTML in a streaming fashion and inject the nonce attribute into `<script>` and `<style>` tags before the bytes reach the client. A separate `/csp-report` endpoint accepts violation reports from browsers (sent as JSON POSTs) and persists them to D1 for analysis.

---

## Solution

```typescript
// csp-builder.ts
// Dynamic CSP generation, nonce injection, and violation reporting.

export interface CspDirectives {
  defaultSrc?: string[];
  scriptSrc?: string[];
  styleSrc?: string[];
  imgSrc?: string[];
  connectSrc?: string[];
  fontSrc?: string[];
  objectSrc?: string[];
  mediaSrc?: string[];
  frameSrc?: string[];
  frameAncestors?: string[];
  formAction?: string[];
  baseUri?: string[];
  upgradeInsecureRequests?: boolean;
  reportUri?: string;
  reportTo?: string;
}

export interface RoutePolicy {
  pattern: RegExp;
  directives: Partial<CspDirectives>;
  reportOnly?: boolean;
}

// ── CSP directive builder ─────────────────────────────────────────────────────

export class CspBuilder {
  private directives: CspDirectives;

  constructor(base: CspDirectives = {}) {
    this.directives = {
      defaultSrc: ["'none'"],
      objectSrc: ["'none'"],
      baseUri: ["'none'"],
      frameAncestors: ["'none'"],
      upgradeInsecureRequests: true,
      ...base,
    };
  }

  withNonce(nonce: string): this {
    const nonceToken = `'nonce-${nonce}'`;
    this.directives.scriptSrc = [
      ...(this.directives.scriptSrc ?? []),
      nonceToken,
      "'strict-dynamic'",
    ];
    this.directives.styleSrc = [
      ...(this.directives.styleSrc ?? []),
      nonceToken,
    ];
    return this;
  }

  withReporting(reportUri: string, reportTo?: string): this {
    this.directives.reportUri = reportUri;
    if (reportTo) this.directives.reportTo = reportTo;
    return this;
  }

  merge(overrides: Partial<CspDirectives>): this {
    for (const [k, v] of Object.entries(overrides)) {
      const key = k as keyof CspDirectives;
      if (Array.isArray(v) && Array.isArray(this.directives[key])) {
        (this.directives[key] as string[]) = [
          ...(this.directives[key] as string[]),
          ...v,
        ];
      } else {
        (this.directives as Record<string, unknown>)[key] = v;
      }
    }
    return this;
  }

  build(): string {
    const parts: string[] = [];

    const directiveMap: Array<[keyof CspDirectives, string]> = [
      ['defaultSrc',             'default-src'],
      ['scriptSrc',              'script-src'],
      ['styleSrc',               'style-src'],
      ['imgSrc',                 'img-src'],
      ['connectSrc',             'connect-src'],
      ['fontSrc',                'font-src'],
      ['objectSrc',              'object-src'],
      ['mediaSrc',               'media-src'],
      ['frameSrc',               'frame-src'],
      ['frameAncestors',         'frame-ancestors'],
      ['formAction',             'form-action'],
      ['baseUri',                'base-uri'],
    ];

    for (const [key, directive] of directiveMap) {
      const values = this.directives[key] as string[] | undefined;
      if (values && values.length > 0) {
        parts.push(`${directive} ${values.join(' ')}`);
      }
    }

    if (this.directives.upgradeInsecureRequests) {
      parts.push('upgrade-insecure-requests');
    }
    if (this.directives.reportUri) {
      parts.push(`report-uri ${this.directives.reportUri}`);
    }
    if (this.directives.reportTo) {
      parts.push(`report-to ${this.directives.reportTo}`);
    }

    return parts.join('; ');
  }
}

// ── Nonce generation ──────────────────────────────────────────────────────────

export function generateNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes)).replace(/=+$/, '');
}

// ── HTMLRewriter nonce injector ───────────────────────────────────────────────

class NonceInjector implements HTMLRewriterElementContentHandlers {
  constructor(private nonce: string) {}

  element(element: Element): void {
    // Only inject nonce on inline scripts/styles (no src/href attribute).
    const hasSrc = element.getAttribute('src') !== null ||
                   element.getAttribute('href') !== null;
    if (!hasSrc) {
      element.setAttribute('nonce', this.nonce);
    }
  }
}

export function injectNonce(response: Response, nonce: string): Response {
  return new HTMLRewriter()
    .on('script', new NonceInjector(nonce))
    .on('style', new NonceInjector(nonce))
    .transform(response);
}

// ── Per-route CSP resolver ────────────────────────────────────────────────────

export function resolveRoutePolicy(
  pathname: string,
  routes: RoutePolicy[],
  base: CspDirectives
): { directives: CspDirectives; reportOnly: boolean } {
  let directives = { ...base };
  let reportOnly = false;

  for (const route of routes) {
    if (route.pattern.test(pathname)) {
      directives = { ...directives, ...route.directives };
      reportOnly = route.reportOnly ?? false;
      break;
    }
  }

  return { directives, reportOnly };
}

// ── CSP violation report endpoint ────────────────────────────────────────────

export async function handleCspReport(
  request: Request,
  db: D1Database
): Promise<Response> {
  if (request.method !== 'POST') {
    return new Response('Method Not Allowed', { status: 405 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  // Browsers send either `csp-report` (old) or the raw object (new).
  const report = (body['csp-report'] ?? body) as Record<string, string>;

  await db
    .prepare(
      `INSERT INTO csp_violations
         (document_uri, referrer, blocked_uri, violated_directive, original_policy, ts)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      report['document-uri'] ?? '',
      report['referrer'] ?? '',
      report['blocked-uri'] ?? '',
      report['violated-directive'] ?? '',
      report['original-policy'] ?? '',
      new Date().toISOString()
    )
    .run();

  return new Response(null, { status: 204 });
}

// ── D1 schema (run once via migration) ───────────────────────────────────────
// CREATE TABLE IF NOT EXISTS csp_violations (
//   id                INTEGER PRIMARY KEY AUTOINCREMENT,
//   document_uri      TEXT NOT NULL,
//   referrer          TEXT,
//   blocked_uri       TEXT,
//   violated_directive TEXT,
//   original_policy   TEXT,
//   ts                TEXT NOT NULL
// );

// ── Worker entry point ────────────────────────────────────────────────────────

interface Env {
  DB: D1Database;
}

const BASE_DIRECTIVES: CspDirectives = {
  defaultSrc: ["'none'"],
  imgSrc: ["'self'", 'data:'],
  connectSrc: ["'self'"],
  fontSrc: ["'self'"],
  objectSrc: ["'none'"],
  baseUri: ["'none'"],
  frameAncestors: ["'none'"],
  upgradeInsecureRequests: true,
};

const ROUTE_POLICIES: RoutePolicy[] = [
  {
    // API routes: no scripts at all.
    pattern: /^\/api\//,
    directives: { scriptSrc: [], styleSrc: [] },
  },
  {
    // Admin: allow same-origin images and tight script policy.
    pattern: /^\/admin/,
    directives: { imgSrc: ["'self'"] },
    reportOnly: false,
  },
  {
    // Everything else: report-only during rollout.
    pattern: /.*/,
    directives: {},
    reportOnly: true,
  },
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/csp-report') {
      return handleCspReport(request, env.DB);
    }

    const nonce = generateNonce();
    const { directives, reportOnly } = resolveRoutePolicy(
      url.pathname,
      ROUTE_POLICIES,
      BASE_DIRECTIVES
    );

    const csp = new CspBuilder(directives)
      .withNonce(nonce)
      .withReporting('/csp-report')
      .build();

    // Fetch the origin HTML (or construct it).
    const upstream = await fetch(request);
    const htmlWithNonces = injectNonce(upstream, nonce);

    const response = new Response(htmlWithNonces.body, htmlWithNonces);
    const headerName = reportOnly
      ? 'content-security-policy-report-only'
      : 'content-security-policy';
    response.headers.set(headerName, csp);

    return response;
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

- `CspBuilder` starts from a secure-by-default base (`default-src 'none'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`) and layers additional sources on top.
- `withNonce` appends both `'nonce-<value>'` and `'strict-dynamic'` to `script-src`. `'strict-dynamic'` allows scripts loaded by nonced scripts to execute, enabling module bundlers.
- `injectNonce` uses `HTMLRewriter` for streaming transformation — it does not buffer the entire HTML document, which is critical for large pages.
- Only inline tags (those without a `src` or `href` attribute) receive the nonce; external script tags are controlled by their URL allowlist.
- The CSP reporting endpoint accepts both the legacy `csp-report` wrapped format (Chrome) and the direct object format.
- `ROUTE_POLICIES` is evaluated in order; the first matching pattern wins.

---

## Anti-patterns

- Do not use `'unsafe-inline'` — it defeats the entire purpose of CSP nonces.
- Do not reuse nonces across requests — each request must generate a fresh nonce.
- Do not set `report-uri` and then ignore the reports; act on repeated violations.
- Do not use `*` in `default-src` — enumerate only the origins you actually need.
- Do not skip `frame-ancestors 'none'` unless you explicitly need your pages to be embeddable.

---

## Gotchas

- `HTMLRewriter` transforms happen lazily — the response body is not fully processed until it is consumed (e.g., returned from `fetch`). Do not call `response.text()` after `injectNonce`; it will double-consume the body.
- The `nonce` value must be base64-encoded; using raw bytes causes the CSP header to be unparseable by browsers.
- Some browsers (Firefox < 93) do not support `'strict-dynamic'` with `'nonce-*'` — add `'unsafe-inline'` as a fallback, which `'strict-dynamic'`-aware browsers will ignore.
- D1 writes in the violation handler are synchronous within the Worker; use `ctx.waitUntil` if the endpoint should return 204 before the write completes.
- Report-Only headers do not block anything; flip to `content-security-policy` only after reviewing violation reports and confirming zero false positives.

---

## Verification

```bash
# 1. Check the CSP header in the response.
curl -I https://your-worker.example.com/ | grep -i content-security-policy
# Expected: content-security-policy-report-only: default-src 'none'; ...; nonce-<random>

# 2. Simulate a CSP violation report.
curl -X POST https://your-worker.example.com/csp-report \
  -H 'content-type: application/csp-report' \
  -d '{"csp-report":{"document-uri":"https://example.com","blocked-uri":"inline","violated-directive":"script-src"}}'
# Expected: 204 No Content.

# 3. Query D1 for violations.
npx wrangler d1 execute <DB_NAME> --command 'SELECT * FROM csp_violations LIMIT 10;'
```

---

## Related

- `documentation/docs/policies/security/workers-secret-scanning-prevention.md`
- `documentation/docs/policies/security/workers-oauth2-pkce-flow.md`
- MDN CSP reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

---

## Sources

- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- W3C CSP3 specification: https://www.w3.org/TR/CSP3/
- Google CSP strict mode guide: https://csp.withgoogle.com/docs/strict-csp.html
