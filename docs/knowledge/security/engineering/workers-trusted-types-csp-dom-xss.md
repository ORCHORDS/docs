# Trusted Types CSP Enforcement via Workers to Prevent DOM XSS

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A React or vanilla JS application uses `innerHTML`, `document.write`, or `eval` with user-supplied data. Classic CSP blocks inline `<script>` tags but cannot prevent DOM-based XSS where JavaScript itself manipulates the DOM with untrusted strings. Trusted Types — a CSP Level 3 feature — forces all DOM sink assignments through typed policy objects, breaking the attack chain even when a reflected value reaches `element.innerHTML`. Workers inject the `Content-Security-Policy` and `Trusted-Types` headers on every response at the edge, before the browser receives any HTML.

## Context

Trusted Types is enforced via two CSP directives: `require-trusted-types-for 'script'` (blocks unsafe DOM assignments) and `trusted-types <policy-name>` (allowlists named policies). A Trusted Types policy is a `TrustedTypePolicy` object created via `trustedTypes.createPolicy()` that sanitizes input before returning a typed `TrustedHTML`, `TrustedScript`, or `TrustedURL`. Workers are the correct enforcement point for header injection because they sit in front of every origin response, including static assets served from Pages or R2.

---

## 1. Workers Middleware — Injecting Trusted Types Headers

```typescript
// src/trusted-types-headers.ts

export interface TrustedTypeConfig {
  policyNames: string[];         // Allowlisted policy names (e.g. ['sanitize-html', 'dompurify'])
  reportOnly: boolean;           // true = CSP-RO (observe without blocking), false = enforce
  reportUri?: string;            // Optional CSP violation reporting endpoint
}

export function buildTrustedTypesCSP(config: TrustedTypeConfig): string {
  const mode = config.reportOnly
    ? 'Content-Security-Policy-Report-Only'
    : 'Content-Security-Policy';

  const policyList = config.policyNames.join(' ');
  const directives: string[] = [
    `require-trusted-types-for 'script'`,
    `trusted-types ${policyList} 'allow-duplicates'`,
  ];

  if (config.reportUri) {
    directives.push(`report-uri ${config.reportUri}`);
  }

  return directives.join('; ');
}

export function injectTrustedTypesHeaders(
  response: Response,
  config: TrustedTypeConfig,
): Response {
  const headers = new Headers(response.headers);
  const cspValue = buildTrustedTypesCSP(config);
  const headerName = config.reportOnly
    ? 'Content-Security-Policy-Report-Only'
    : 'Content-Security-Policy';

  // Append to existing CSP if present (do not overwrite other directives)
  const existing = headers.get(headerName);
  headers.set(headerName, existing ? `${existing}; ${cspValue}` : cspValue);

  // Permissions-Policy to opt in to Trusted Types in cross-origin iframes
  headers.set('Permissions-Policy', 'trusted-types=*');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
```

---

## 2. Workers Fetch Handler — Apply Headers to HTML Responses Only

```typescript
// src/index.ts
import { injectTrustedTypesHeaders, TrustedTypeConfig } from './trusted-types-headers';

export interface Env {
  ORIGIN: Fetcher;
  CSP_REPORT_URI: string;
  TRUSTED_TYPES_ENFORCE: string;  // "true" | "false" — toggle enforce vs report-only
}

const HTML_CONTENT_TYPES = ['text/html', 'application/xhtml+xml'];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await env.ORIGIN.fetch(request);

    const contentType = response.headers.get('content-type') ?? '';
    const isHtml = HTML_CONTENT_TYPES.some(t => contentType.includes(t));
    if (!isHtml) return response; // Don't modify JSON/CSS/image responses

    const config: TrustedTypeConfig = {
      policyNames: ['sanitize-html', 'dompurify', 'lit-html'],
      reportOnly: env.TRUSTED_TYPES_ENFORCE !== 'true',
      reportUri: env.CSP_REPORT_URI,
    };

    return injectTrustedTypesHeaders(response, config);
  },
};
```

---

## 3. Client-Side Trusted Types Policy — Safe `innerHTML` Replacement

The client-side policy object pairs with the CSP header; without a matching policy name, assignments to DOM sinks throw `TypeError`.

```typescript
// src/client/trusted-types-policies.ts  (bundled into the frontend)

// Creates a named policy matching the name in the CSP 'trusted-types' directive
const sanitizeHtmlPolicy = trustedTypes.createPolicy('sanitize-html', {
  createHTML(dirty: string): string {
    // DOMPurify must be loaded before this policy is created
    // @ts-ignore — DOMPurify is loaded as a global
    return DOMPurify.sanitize(dirty, {
      ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br'],
      ALLOWED_ATTR: ['href', 'target', 'rel'],
      RETURN_TRUSTED_TYPE: false,  // DOMPurify output goes through our typed wrapper
    });
  },
  createScript(_dirty: string): string {
    throw new TypeError('createScript not allowed by sanitize-html policy');
  },
  createScriptURL(_dirty: string): string {
    throw new TypeError('createScriptURL not allowed by sanitize-html policy');
  },
});

// Usage — replaces: element.innerHTML = userInput (would throw with Trusted Types)
export function safeSetInnerHTML(element: Element, dirty: string): void {
  element.innerHTML = sanitizeHtmlPolicy.createHTML(dirty);
}
```

---

## 4. Handling Framework-Specific Sinks

React, Angular, and Lit each expose their own Trusted Types integration:

```typescript
// src/client/framework-policies.ts

// Angular requires a policy named 'angular' (or 'angular#bundler') in strict mode
if (typeof trustedTypes !== 'undefined') {
  // Angular's own security policy — allow Angular to manage its internal sinks
  // This policy name is hardcoded in Angular's TrustedTypes integration
  trustedTypes.createPolicy('angular', {
    createHTML: (s: string) => s,        // Angular escapes before calling createHTML
    createScript: (s: string) => s,
    createScriptURL: (s: string) => s,
  });

  // lit-html requires a policy for its template literals
  trustedTypes.createPolicy('lit-html', {
    createHTML: (s: string) => s,        // Lit's tagged template literals are structurally safe
  });
}
```

---

## 5. CSP Violation Reporting Worker — Collecting Trusted Types Violations

```typescript
// src/violation-collector.ts
export interface CSPViolationReport {
  'document-uri': string;
  'blocked-uri': string;
  'violated-directive': string;
  'effective-directive': string;
  'original-policy': string;
  'disposition': 'enforce' | 'report';
  'source-file'?: string;
  'line-number'?: number;
  'column-number'?: number;
  'script-sample'?: string;   // Trusted Types violations populate this
}

export async function handleCspReport(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') return new Response('', { status: 405 });

  let body: { 'csp-report': CSPViolationReport };
  try {
    body = await request.json();
  } catch {
    return new Response('', { status: 400 });
  }

  const report = body['csp-report'];
  const isTrustedTypesViolation = report['violated-directive']?.startsWith('require-trusted-types-for');

  // Log Trusted Types violations with higher priority — they indicate active sink abuse
  console.log(JSON.stringify({
    level: isTrustedTypesViolation ? 'CRITICAL' : 'WARN',
    type: 'csp-violation',
    directive: report['violated-directive'],
    blockedUri: report['blocked-uri'],
    sourceFile: report['source-file'],
    lineNumber: report['line-number'],
    scriptSample: report['script-sample'],  // excerpt of the string that was blocked
    disposition: report['disposition'],
  }));

  return new Response('', { status: 204 });
}

export interface Env { /* placeholder */ }
```

---

## Anti-patterns

- Allowlisting the `'none'` or wildcard `*` policy name — defeats the purpose; only name specific, reviewed policies.
- Setting `trusted-types` without `require-trusted-types-for 'script'` — browsers silently ignore the policy allowlist without the enforcement directive.
- Applying the Trusted Types CSP header to all response types — JSON and image responses do not have a DOM; the header wastes bytes and may confuse parsers.
- Writing a `createHTML` policy that returns the input unchanged (`s => s`) for user-generated content — this is a bypass, not a policy.
- Deploying enforce mode (`Content-Security-Policy`) before validating all policy violations in report-only mode — ensures production breakage.

## Gotchas

- Trusted Types is a living spec; browser support as of 2026 is Chromium-based only (Chrome, Edge, Arc). Firefox and Safari do not enforce the directive but also do not error on the header.
- `'allow-duplicates'` in the `trusted-types` directive allows multiple calls to `createPolicy` with the same name — required when third-party libraries and application code both create the same policy name (e.g., Angular creates `angular` internally).
- The `script-sample` field in CSP violation reports contains the first 40 characters of the blocked string — enough to triage the violation but insufficient to reconstruct the payload; store the full source file and line number.
- Workers using `HTMLRewriter` to inject a nonce into existing `<meta http-equiv="Content-Security-Policy">` tags will conflict with header-based injection — use one mechanism, not both.
- The `Permissions-Policy: trusted-types=*` header is needed only for cross-origin `<iframe>` contexts; it is harmless on top-level navigation.

## Verification

```bash
# Verify header is present on HTML responses
curl -sI https://app.example.com/ | grep -i 'content-security-policy'
# Expected: Content-Security-Policy: require-trusted-types-for 'script'; trusted-types sanitize-html dompurify lit-html 'allow-duplicates'

# Confirm header is absent on JSON API responses
curl -sI https://app.example.com/api/data | grep -i 'content-security-policy'
# Expected: (no output — header should not be present on API responses)

# In browser DevTools Console — verify policy creation succeeds
> trustedTypes.getPolicyNames()
# Expected: ["sanitize-html", "dompurify", "lit-html"]

# Attempt an unsafe assignment — should throw with Trusted Types enforced
> document.body.innerHTML = '<img src=x onerror=alert(1)>'
# Expected: Uncaught TypeError: This document requires 'TrustedHTML' assignment.
```

## Related

- `content-security-policy-workers-nonce.md` — Nonce-based CSP for inline scripts
- `csp-reporting-endpoint-workers.md` — CSP violation report collection endpoint
- `xss-htmlrewriter-sanitization-workers.md` — Workers HTMLRewriter for server-side XSS sanitization
- `xss-deep-dive.md` — DOM XSS attack taxonomy and sink classification

## Sources

- [Trusted Types — W3C Specification](https://w3c.github.io/trusted-types/dist/spec/)
- [Trusted Types — web.dev Guide](https://web.dev/articles/trusted-types)
- [Content-Security-Policy: trusted-types — MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/trusted-types)
- [Angular Trusted Types Integration](https://angular.dev/best-practices/security#trusted-types)
- [DOMPurify Trusted Types Support](https://github.com/cure53/DOMPurify#trusted-types)
