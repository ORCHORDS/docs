# Trusted Types and CSP Nonce Generation at the Edge

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

DOM-based XSS attacks bypass server-side sanitization because they occur entirely in the browser. Trusted Types + a strict Content Security Policy block these attacks by requiring all dangerous DOM sinks (`innerHTML`, `eval`, `document.write`) to receive typed objects instead of plain strings.

## Context

Trusted Types (now Baseline 2024) let you define a `TrustedTypePolicy` and enforce that only values produced by that policy reach DOM sinks. Enforcement is controlled via the `require-trusted-types-for 'script'` CSP directive. Cloudflare Workers generate a cryptographically random nonce per request and inject it into the `Content-Security-Policy` header and the HTML `<script>` tags before the response reaches the client. This prevents inline script injection without `nonce-*` whitelisting.

## Generating a Nonce at the Edge

```typescript
// lib/csp.ts
export function generateNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function buildCSP(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline'",        // relax only what is necessary
    "img-src 'self' data: https://cdn.example.com",
    "font-src 'self' https://fonts.gstatic.com",
    "object-src 'none'",
    "base-uri 'self'",
    `require-trusted-types-for 'script'`,
    `trusted-types default dompurify`,
  ].join("; ");
}
```

## Injecting Nonce via HTMLRewriter

```typescript
// functions/_middleware.ts
import { generateNonce, buildCSP } from "../lib/csp";

export const onRequest: PagesFunction = async (context) => {
  const nonce = generateNonce();
  const csp = buildCSP(nonce);

  const response = await context.next();
  const ct = response.headers.get("content-type") ?? "";
  if (!ct.includes("text/html")) return response;

  const headers = new Headers(response.headers);
  headers.set("Content-Security-Policy", csp);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");

  const transformed = new HTMLRewriter()
    .on("script:not([src])", {
      element(el) {
        // Add nonce to every inline script
        el.setAttribute("nonce", nonce);
      },
    })
    .on("script[src]", {
      element(el) {
        el.setAttribute("nonce", nonce);
      },
    })
    .transform(new Response(response.body, { headers }));

  return transformed;
};
```

## Defining a Trusted Types Policy in the Browser

```typescript
// src/lib/trusted-types.ts
declare global {
  interface Window {
    trustedTypes: TrustedTypePolicyFactory;
  }
}

let policy: TrustedTypePolicy | null = null;

function getPolicy(): TrustedTypePolicy {
  if (policy) return policy;

  if (typeof window.trustedTypes?.createPolicy === "function") {
    policy = window.trustedTypes.createPolicy("default", {
      createHTML(input: string): string {
        // DOMPurify must be loaded via a nonce-whitelisted script tag
        // @ts-expect-error DOMPurify is loaded globally
        return DOMPurify.sanitize(input, { RETURN_TRUSTED_TYPE: true }) as unknown as string;
      },
      createScriptURL(input: string): string {
        const url = new URL(input, location.origin);
        if (url.origin !== location.origin) {
          throw new TypeError(`Untrusted script URL: ${input}`);
        }
        return input;
      },
    });
  }

  return policy!;
}

export function safeSetInnerHTML(el: Element, html: string): void {
  const p = getPolicy();
  if (p) {
    el.innerHTML = p.createHTML(html) as unknown as string;
  } else {
    // Trusted Types not supported — fall back to DOMPurify directly
    // @ts-expect-error DOMPurify global
    el.innerHTML = DOMPurify.sanitize(html);
  }
}
```

## React Integration: Escaping the Policy Boundary

React's JSX never calls `innerHTML` for user-controlled content, but `dangerouslySetInnerHTML` does.

```tsx
// src/components/RichContent.tsx
import { safeSetInnerHTML } from "@/lib/trusted-types";
import { useEffect, useRef } from "react";

interface RichContentProps {
  html: string;
}

export function RichContent({ html }: RichContentProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      safeSetInnerHTML(ref.current, html);
    }
  }, [html]);

  // Render empty div; content set imperatively to satisfy Trusted Types
  return <div ref={ref} />;
}
```

## Testing the Policy in Playwright

```typescript
// e2e/trusted-types.spec.ts
import { test, expect } from "@playwright/test";

test("CSP header contains require-trusted-types-for", async ({ page }) => {
  const response = await page.goto("/");
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("require-trusted-types-for 'script'");
  expect(csp).toMatch(/nonce-[A-Za-z0-9+/=]{24}/);
});

test("inline XSS via innerHTML is blocked", async ({ page }) => {
  await page.goto("/");
  const blocked = await page.evaluate(() => {
    try {
      document.body.innerHTML = "<img src=x onerror=alert(1)>";
      return false;
    } catch {
      return true;
    }
  });
  expect(blocked).toBe(true);
});
```

## Anti-patterns

- Hardcoding a static nonce in `_headers` — a static nonce provides zero protection; attackers can predict and reuse it
- Using `'unsafe-eval'` alongside Trusted Types — eval bypass defeats the entire policy
- Applying `nonce` only to inline scripts but not external `<script src>` tags — `strict-dynamic` still requires nonce on the outer script
- Calling `createPolicy` with a permissive `createHTML` that returns the raw input — equivalent to no policy at all

## Gotchas

- `strict-dynamic` renders `'self'` and allowlist entries ignored for scripts; load all external scripts via nonce or hash
- HTMLRewriter processes streamed bytes, so scripts added by client-side frameworks after hydration do not get the nonce — they must use the runtime policy
- The `default` policy name is special: Trusted Types calls it automatically for all sinks not routed to a named policy; do not register a permissive `default` in production
- Safari support for enforcement mode (`require-trusted-types-for`) landed in 2024; report-only mode (`Content-Security-Policy-Report-Only`) is available earlier for gradual rollout

## Verification

1. Check the `Content-Security-Policy` response header includes `require-trusted-types-for 'script'` and a unique nonce per request.
2. Open DevTools Console and run `document.body.innerHTML = 'test'` — should throw `TypeError: This document requires 'TrustedHTML'`.
3. Use `npx csp-evaluator` or https://csp-evaluator.withgoogle.com to audit the generated CSP.

## Related

- [cloudflare-pages-headers-csp-mobile.md](cloudflare-pages-headers-csp-mobile.md)
- [alpinejs-cloudflare-pages-csp.md](alpinejs-cloudflare-pages-csp.md)
- [sanitizer-api-safe-html-insertion.md](sanitizer-api-safe-html-insertion.md)
- [web-components-cloudflare-workers-html-rewriter.md](web-components-cloudflare-workers-html-rewriter.md)

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API
- https://web.dev/articles/trusted-types
- https://w3c.github.io/trusted-types/
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://content-security-policy.com/strict-dynamic/
