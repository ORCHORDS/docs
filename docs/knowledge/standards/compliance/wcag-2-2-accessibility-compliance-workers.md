# WCAG 2.2 Accessibility Compliance on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your platform serves EU users covered by the European Accessibility Act (EAA) and US users under Section 508 / ADA. You need server-side accessibility enforcement, automated audit logging, and dynamic ARIA injection without rewriting every front-end template.

## Context

WCAG 2.2 (October 2023) introduces nine new success criteria over WCAG 2.1: Focus Appearance (2.4.11/2.4.12), Dragging Alternatives (2.5.7), Target Size Minimum (2.5.8), Consistent Help (3.2.6), Redundant Entry (3.3.7), Accessible Authentication (3.3.8/3.3.9), and Focus Not Obscured (2.4.11/2.4.12). The EAA enforcement deadline is 28 June 2025 for new products and 28 June 2030 for legacy. Workers can validate responses, inject missing attributes, and record conformance evidence before bytes reach the browser.

---

## 1. Response Header Injection for Accessibility Metadata

```typescript
// src/accessibility-headers.ts
export function injectAccessibilityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  // Signal WCAG conformance level to assistive technology proxies
  headers.set('Content-Language', headers.get('Content-Language') ?? 'en');
  headers.set('X-Accessibility-Conformance', 'WCAG22-AA');
  headers.set('X-Accessibility-Audit-Date', new Date().toISOString().slice(0, 10));
  return new Response(response.body, { status: response.status, headers });
}
```

---

## 2. HTMLRewriter: Focus Appearance & Target Size Enforcement

WCAG 2.2 SC 2.5.8 requires interactive targets of at least 24×24 CSS pixels. Inject inline styles server-side to guarantee the floor.

```typescript
// src/target-size-rewriter.ts
export class TargetSizeHandler implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    const tag = el.tagName.toLowerCase();
    if (['a', 'button', 'input', 'select', 'textarea'].includes(tag)) {
      const existing = el.getAttribute('style') ?? '';
      if (!existing.includes('min-height') && !existing.includes('min-width')) {
        el.setAttribute(
          'style',
          `${existing}min-height:24px;min-width:24px;`.trimStart()
        );
      }
    }
  }
}

export function applyTargetSizeRewriter(response: Response): Response {
  return new HTMLRewriter()
    .on('a, button, input, select, textarea', new TargetSizeHandler())
    .transform(response);
}
```

---

## 3. Accessible Authentication (SC 3.3.8) — Disabling Cognitive Tests

SC 3.3.8 prohibits cognitive function tests (e.g., image CAPTCHA) as the *only* authentication step. Workers can gate requests to CAPTCHA-only endpoints and redirect to an alternative flow.

```typescript
// src/auth-flow-guard.ts
const CAPTCHA_ONLY_PATHS = ['/login/captcha-only'];

export async function authFlowGuard(request: Request): Promise<Response | null> {
  const url = new URL(request.url);
  if (CAPTCHA_ONLY_PATHS.includes(url.pathname)) {
    // Redirect to an accessible alternative (email link / passkey)
    return Response.redirect(
      `${url.origin}/login/accessible?from=${encodeURIComponent(url.pathname)}`,
      302
    );
  }
  return null;
}
```

---

## 4. Consistent Help Placement (SC 3.2.6) via HTMLRewriter

SC 3.2.6 requires help mechanisms (chat widget, support link) to appear in the same relative order across all pages.

```typescript
// src/consistent-help-rewriter.ts
const HELP_SNIPPET = `
<div id="wcag-help-anchor" role="complementary" aria-label="Help">
  <a  aria-label="Get help">Support</a>
</div>`;

class HelpInjector implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    // Inject before </body> if not already present
    el.prepend(HELP_SNIPPET, { html: true });
  }
}

export function injectConsistentHelp(response: Response): Response {
  return new HTMLRewriter()
    .on('body', new HelpInjector())
    .transform(response);
}
```

---

## 5. Audit Logging Conformance Evidence to D1

Automated conformance checks must be evidenced. Log per-page audit results to D1 for reporting.

```typescript
// src/audit-logger.ts
interface AuditRecord {
  url: string;
  conformance_level: 'A' | 'AA' | 'AAA' | 'fail';
  violations: string[];
  checked_at: string;
}

export async function logAuditRecord(db: D1Database, record: AuditRecord): Promise<void> {
  await db.prepare(
    `INSERT INTO wcag_audit_log (url, conformance_level, violations, checked_at)
     VALUES (?, ?, ?, ?)`
  ).bind(
    record.url,
    record.conformance_level,
    JSON.stringify(record.violations),
    record.checked_at
  ).run();
}

export async function fetchRecentViolations(
  db: D1Database,
  days = 7
): Promise<AuditRecord[]> {
  const since = new Date(Date.now() - days * 86400_000).toISOString();
  const { results } = await db.prepare(
    `SELECT * FROM wcag_audit_log WHERE checked_at >= ? ORDER BY checked_at DESC LIMIT 500`
  ).bind(since).all<AuditRecord>();
  return results;
}
```

---

## 6. Dragging Alternatives (SC 2.5.7) — Pointer Event Fallback Header

SC 2.5.7 requires every dragging operation to have a single-pointer alternative. Workers can add a `Vary` signal so CDN caches serve the right variant.

```typescript
// src/drag-alternative.ts
export function addDragAlternativeVary(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.append('Vary', 'Pointer-Capabilities');
  return new Response(response.body, { status: response.status, headers });
}
```

---

## Anti-patterns

- **Client-side-only a11y fixes** — HTMLRewriter runs on every request; a JS polyfill only fires if JS loads successfully.
- **Rewriting `aria-hidden` onto focusable elements** — sets `aria-hidden="true"` on elements that still receive focus, violating SC 1.3.1.
- **Logging PII in audit records** — store only URLs and violation codes, never user identifiers.
- **Blocking requests to non-conforming pages** — return HTTP 200 with a conformance note header; do not 403 non-conforming assets mid-session.

---

## Gotchas

- `HTMLRewriter` operates on streamed HTML; mutations are applied to the first occurrence of a selector per chunk — test with chunked responses.
- SC 2.4.11 (Focus Not Obscured) and SC 2.4.12 (Focus Not Obscured Enhanced) cannot be enforced by a CDN Worker — they require viewport-aware CSS; document them as client-side obligations.
- `new HTMLRewriter().on('a, button, …', handler)` — compound CSS selectors are not supported; chain `.on()` calls per selector instead.
- EAA covers *all* products/services offered to EU consumers regardless of where the company is based.

---

## Verification

```bash
# Check injected header
curl -I https://example.com/ | grep X-Accessibility

# Confirm target-size style attribute
curl -s https://example.com/ | grep -o 'min-height:[0-9]*px'

# D1 audit query
wrangler d1 execute DB --command \
  "SELECT conformance_level, COUNT(*) AS n FROM wcag_audit_log GROUP BY conformance_level"
```

---

## Related

- `accessibility-wcag-21-compliance.md`
- `european-accessibility-act-eaa-enforcement-2026.md`
- `cookie-consent-cloudflare-pages-workers.md`
- `gdpr-data-subject-rights-api.md`

---

## Sources

- WCAG 2.2 — https://www.w3.org/TR/WCAG22/
- European Accessibility Act Directive 2019/882 — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32019L0882
- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Section 508 Standards — https://www.access-board.gov/ict/
