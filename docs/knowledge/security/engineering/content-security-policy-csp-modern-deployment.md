# Content Security Policy (CSP) — Modern Nonce-Based Deployment Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your web application was hit by a stored XSS attack — an attacker
injected a `<script>` tag via a user profile field that executed in
every visitor's browser, exfiltrating session cookies. You had no CSP
header. After the incident, you add `script-src 'self'` but it breaks
your analytics, your CDN-hosted libraries, and all inline event
handlers. You add `'unsafe-inline'` to "fix" it, which completely
negates XSS protection. Six months later, a second XSS attack
succeeds because `'unsafe-inline'` allows any injected script to run.

## Context

Content Security Policy Level 3 is the current W3C standard for
mitigating XSS and data injection attacks by declaring which resources
a page is allowed to load. In 2026, the modern best practice (per
OWASP) has shifted decisively to nonce-based policies with
`strict-dynamic`, replacing the old allowlist-based approach that was
brittle and routinely bypassed via JSONP endpoints and open redirects.
The key CSP Level 3 additions are `strict-dynamic` (propagates trust
from a nonced script to scripts it dynamically loads), `report-sample`
(includes a snippet of violating code in reports), and the `worker-src`
directive.

## Recommended strict CSP

```
Content-Security-Policy:
  default-src 'none';
  script-src 'nonce-{RANDOM}' 'strict-dynamic';
  style-src 'self' 'nonce-{RANDOM}';
  img-src 'self' data:;
  font-src 'self';
  connect-src 'self';
  object-src 'none';
  base-uri 'none';
  form-action 'self';
  frame-ancestors 'none';
  report-to csp-endpoint;
  report-uri /csp-report;
```

## Server-side nonce generation

```javascript
// Node.js / Express
import crypto from 'crypto';

app.use((req, res, next) => {
  const nonce = crypto.randomBytes(16).toString('base64');
  res.locals.cspNonce = nonce;

  res.setHeader('Content-Security-Policy',
    `default-src 'none'; ` +
    `script-src 'nonce-${nonce}' 'strict-dynamic'; ` +
    `style-src 'self' 'nonce-${nonce}'; ` +
    `img-src 'self'; ` +
    `connect-src 'self'; ` +
    `object-src 'none'; ` +
    `base-uri 'none'; ` +
    `form-action 'self'; ` +
    `frame-ancestors 'none'; ` +
    `report-to csp-endpoint; ` +
    `report-uri /csp-report`
  );
  next();
});

// In templates (EJS example):
// <script nonce="<%= cspNonce %>">...</script>
```

## Reporting configuration

```
# Both report-to and report-uri for browser compatibility
# Chrome/Edge support report-to; Firefox still uses report-uri only

Reporting-Endpoints: csp-endpoint="https://collector.example.com/csp"

Report-To: {
  "group": "csp-endpoint",
  "max_age": 10886400,
  "endpoints": [
    {"url": "https://collector.example.com/csp"}
  ]
}

# Report-only mode for initial deployment
Content-Security-Policy-Report-Only:
  default-src 'none';
  script-src 'nonce-{RANDOM}' 'strict-dynamic';
  ...
  report-to csp-endpoint;
  report-uri /csp-report;
```

## strict-dynamic behavior

```
How strict-dynamic works:
  1. Browser trusts scripts with the correct nonce
  2. Trusted scripts can dynamically load other scripts
     (document.createElement('script'), import())
  3. Dynamically loaded scripts inherit trust automatically
  4. Parser-inserted scripts (inline <script> without nonce) are blocked

What strict-dynamic overrides:
  → 'self' is IGNORED in script-src
  → Domain allowlists are IGNORED in script-src
  → 'unsafe-inline' is IGNORED in script-src
  → Only nonce and hash sources are effective

This means:
  script-src 'nonce-abc' 'strict-dynamic' 'self' cdn.example.com
  is equivalent to:
  script-src 'nonce-abc' 'strict-dynamic'
```

## Deployment progression

```
Phase 1: Report-Only (2-4 weeks)
  Content-Security-Policy-Report-Only: [full policy]
  → Monitor reports for legitimate breakage
  → Fix violations (add nonces, move inline to files)
  → No user-facing impact

Phase 2: Enforce with monitoring (ongoing)
  Content-Security-Policy: [full policy]
  → Violations are blocked and reported
  → Monitor for new violations from deployments
  → Review reports weekly

Common violations to fix before enforcing:
  → Inline event handlers (onclick="...") → addEventListener
  → Inline <script> blocks → add nonce attribute
  → eval() usage → refactor to avoid eval
  → CDN scripts loaded by URL → load via nonced loader script
```

## Anti-patterns

- **Using unsafe-inline** — completely negates XSS protection from
  CSP. Developers add it to "fix" blocked inline scripts instead of
  migrating to nonces. Any injected script runs freely.
- **Static or cached nonces** — the nonce MUST regenerate on every
  request. A cached page or CDN-served HTML with a baked-in nonce
  is trivially bypassable. This is incompatible with full-page
  caching without edge-side nonce injection.
- **Deploying without report-only first** — enforcing CSP without
  a monitoring period breaks legitimate functionality in production.
  Always deploy as Report-Only, fix violations, then promote.
- **Ignoring object-src and base-uri** — omitting `object-src 'none'`
  leaves Flash/plugin injection vectors open. Omitting `base-uri
  'none'` allows `<base>` tag injection that redirects relative URLs
  to attacker-controlled domains.

## Gotchas

- **strict-dynamic overrides self** — teams that add `strict-dynamic`
  alongside `'self'` are surprised when same-origin parser-inserted
  scripts break. This is by design — `strict-dynamic` makes the
  browser ignore allowlists entirely.
- **Firefox report-to gap** — Firefox still does not support
  `report-to` for CSP as of 2026. Always send both `report-to` and
  `report-uri` headers for cross-browser coverage.
- **Nonce incompatibility with CDN caching** — nonces change per
  request, so HTML pages with nonces cannot be cached at the CDN
  edge. Solutions: edge-side nonce injection (Cloudflare Workers,
  Lambda@Edge) or hash-based CSP for static pages.
- **Third-party script loading** — third-party scripts that
  dynamically insert other scripts work with `strict-dynamic`, but
  third-party scripts loaded directly via `<script >`
  without a nonce are blocked. Load them via a nonced loader script.

## Verification

- CSP header is present on all responses (enforcing, not report-only).
- No `'unsafe-inline'` or `'unsafe-eval'` in script-src.
- Nonces are unique per request (not cached or static).
- `object-src 'none'` and `base-uri 'none'` are set.
- Report endpoint receives and processes violation reports.
- CSP does not break legitimate functionality (tested in report-only).

## Related

- `documentation/docs/policies/security/owasp-top-10-2025-mitigation.md`
- `documentation/docs/policies/security/xss-prevention-modern-frameworks.md`
- `documentation/docs/policies/security/supply-chain-security-slsa-sigstore.md`

## Source URLs (verified 2026-08-16)

- Content Security Policy Level 3 — W3C — https://www.w3.org/TR/CSP3/
- OWASP Content Security Policy Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html
- CSP strict-dynamic: When to Use It and How to Migrate Safely — https://cspify.io/blog/csp-strict-dynamic/
- Content Security Policy in Node.js: 12 Steps, 30 Min (2026) — https://shattered.io/content-security-policy-nodejs/
