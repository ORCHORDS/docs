# Stripe Payment Element with Cloudflare Pages and CSP Configuration

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You deploy a Stripe Payment Element on Cloudflare Pages and see console errors like:

```
Refused to load script from 'https://js.stripe.com/v3/' because it violates the following
Content Security Policy directive: "script-src 'self'"
```

Or the Element renders but 3DS authentication iframes are blocked, resulting in silent payment failures. Cloudflare Pages applies headers via `_headers` files or Pages Functions middleware — neither is an Apache `.htaccess`. Getting CSP, COEP, and frame-ancestors right without breaking Stripe's multi-origin iframe architecture requires understanding exactly which origins Stripe loads at runtime.

---

## Context

Stripe Payment Element (based on Stripe.js) embeds two layers of iframes:

1. **Outer container** — `https://js.stripe.com` loads into your page via a `<script>` tag. It injects an `<iframe>` pointing to `js.stripe.com/v3/three-d-secure-2-...`.
2. **Inner 3DS iframe** — For authentication challenges, Stripe opens a nested iframe from the card issuer's ACS domain (`https://*.3ds2.com`, `https://3ds.mastercard.com`, etc.), which is outside Stripe's control.

You must allow both layers — plus the `connect.stripe.com` origin used for Stripe Connect embedded components — without opening up your CSP to `*`.

Cloudflare Pages also runs **Turnstile** (if you add bot protection to checkout) and **Cloudflare Insights** (if enabled), which each need their own CSP allowances.

---

## Cloudflare Pages `_headers` File

```
# public/_headers
# Applied to every response from Pages static hosting.
# Workers / Functions can override per-route (see below).

/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: payment=*

/checkout
  Content-Security-Policy: default-src 'self'; script-src 'self' https://js.stripe.com https://challenges.cloudflare.com; connect-src 'self' https://api.stripe.com https://errors.stripe.com https://r.stripe.com; frame-src https://js.stripe.com https://hooks.stripe.com https://challenges.cloudflare.com; img-src 'self' data: https://*.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; object-src 'none'; base-uri 'self'; form-action 'self'
  Cross-Origin-Embedder-Policy: unsafe-none
  Cross-Origin-Opener-Policy: same-origin-allow-popups
  X-Frame-Options: SAMEORIGIN
```

> **Note:** `_headers` does not support line continuation — each directive must be on one line. The CSP above is a single line per route.

---

## Breaking Down the CSP Directives

```
# Expanded for readability — NOT valid _headers syntax (use single-line in production)

Content-Security-Policy:
  default-src 'self';

  # Stripe.js main bundle + Stripe hosted elements JS
  script-src 'self'
    https://js.stripe.com
    https://challenges.cloudflare.com;   # Turnstile

  # Stripe API calls, error reporting, analytics
  connect-src 'self'
    https://api.stripe.com
    https://errors.stripe.com
    https://r.stripe.com
    https://m.stripe.com;

  # Payment Element iframe + 3DS challenge iframe
  frame-src
    https://js.stripe.com
    https://hooks.stripe.com
    https://challenges.cloudflare.com;

  # Payment method logos, card brand icons
  img-src 'self' data: https://*.stripe.com;

  # Stripe injects inline styles into its iframe — unsafe-inline is scoped to
  # the iframe's own document (different origin), so this applies only to YOUR page.
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;

  font-src 'self' https://fonts.gstatic.com;
  object-src 'none';
  base-uri 'self';
  form-action 'self';
```

---

## Pages Functions Middleware (Dynamic CSP)

For routes that require a nonce-based CSP (eliminating `unsafe-inline`), use a Pages Function:

```typescript
// functions/_middleware.ts
import type { PagesFunction } from '@cloudflare/workers-types';

const CHECKOUT_PATHS = ['/checkout', '/subscribe', '/upgrade'];

export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
  const response = await context.next();

  if (!CHECKOUT_PATHS.some(p => url.pathname.startsWith(p))) {
    return response;
  }

  const nonce = btoa(crypto.getRandomValues(new Uint8Array(16)).join(''));

  const csp = [
    `default-src 'self'`,
    `script-src 'self' 'nonce-${nonce}' https://js.stripe.com https://challenges.cloudflare.com`,
    `connect-src 'self' https://api.stripe.com https://errors.stripe.com https://r.stripe.com https://m.stripe.com`,
    `frame-src https://js.stripe.com https://hooks.stripe.com https://challenges.cloudflare.com`,
    `img-src 'self' data: https://*.stripe.com`,
    `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`,
    `font-src 'self' https://fonts.gstatic.com`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
  ].join('; ');

  const headers = new Headers(response.headers);
  headers.set('Content-Security-Policy', csp);
  headers.set('X-CSP-Nonce', nonce); // pass nonce to SSR renderer

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
};
```

**Using the nonce in your HTML template:**

```html
<!-- The nonce is injected server-side by your SSR framework -->
<!-- SvelteKit: app.html -->
<script nonce="%sveltekit.nonce%">
  // Stripe.js *itself* does not require a nonce — it's loaded via src="https://js.stripe.com"
  // The nonce here covers your own inline initialization script only.
</script>
<script nonce="%sveltekit.nonce%">
  window.__STRIPE_KEY__ = '%PUBLIC_STRIPE_KEY%';
</script>
```

---

## Payment Element Initialization

```typescript
// src/lib/stripe.ts
import { loadStripe, type Stripe, type StripeElements } from '@stripe/stripe-js';

let stripePromise: Promise<Stripe | null>;

export function getStripe(publishableKey: string): Promise<Stripe | null> {
  if (!stripePromise) {
    // Stripe.js loads from https://js.stripe.com/v3/ — must be allowed in script-src
    stripePromise = loadStripe(publishableKey);
  }
  return stripePromise;
}

export async function mountPaymentElement(
  clientSecret: string,
  mountPoint: string,
  options?: {
    appearance?: Record<string, unknown>;
    returnUrl: string;
  }
): Promise<{ stripe: Stripe; elements: StripeElements }> {
  const stripe = await getStripe(import.meta.env.PUBLIC_STRIPE_KEY);
  if (!stripe) throw new Error('Stripe.js failed to load');

  const elements = stripe.elements({
    clientSecret,
    appearance: options?.appearance ?? {
      theme: 'stripe',
      variables: { colorPrimary: '#0050b3' },
    },
    loader: 'auto',
  });

  const paymentElement = elements.create('payment', {
    layout: 'tabs',
    // wallets — hide if your CSP blocks the Apple Pay JS origin
    wallets: { applePay: 'auto', googlePay: 'auto' },
  });

  paymentElement.mount(mountPoint);

  return { stripe, elements };
}
```

---

## Apple Pay Domain Verification via Pages

Apple Pay requires a verification file at `/.well-known/apple-developer-merchantid-domain-association`.

```
# public/.well-known/apple-developer-merchantid-domain-association
# Download from Stripe Dashboard → Settings → Payment methods → Apple Pay
# Place file verbatim — no headers file needed for this path
```

Ensure the `_headers` file does NOT add CSP to `/.well-known/*`:

```
# public/_headers
/.well-known/*
  # No CSP — Apple verification fetch must not be blocked
  Cache-Control: public, max-age=86400
```

---

## Google Pay Configuration

Google Pay requires `https://pay.google.com` in `frame-src` and the Payment Request Button needs `https://pay.google.com` in `connect-src`:

```
# Updated frame-src and connect-src for Google Pay:

frame-src
  https://js.stripe.com
  https://hooks.stripe.com
  https://pay.google.com
  https://challenges.cloudflare.com;

connect-src
  'self'
  https://api.stripe.com
  https://errors.stripe.com
  https://r.stripe.com
  https://m.stripe.com
  https://pay.google.com;
```

---

## Stripe Connect Embedded Components

If your Pages site hosts Stripe Connect embedded components (account onboarding, payouts dashboard), add:

```
# Additional origins for Connect embedded components

script-src  ... https://connect-js.stripe.com;
frame-src   ... https://connect-js.stripe.com;
connect-src ... https://connect.stripe.com;
```

---

## CSP Violation Reporting

Route violations to a Cloudflare Worker that stores them in D1 for analysis:

```
# public/_headers
/checkout
  Content-Security-Policy-Report-Only: ...; report-to default
  Reporting-Endpoints: default="https://YOUR_WORKER.workers.dev/csp-report"
```

```typescript
// workers/csp-report.ts
export default {
  async fetch(request: Request, env: { DB: D1Database }): Promise<Response> {
    if (request.method !== 'POST') return new Response('', { status: 405 });

    const report = await request.json() as Record<string, unknown>;

    await env.DB.prepare(
      `INSERT INTO csp_violations (id, payload, created_at)
       VALUES (?, ?, datetime('now'))`
    ).bind(crypto.randomUUID(), JSON.stringify(report)).run();

    return new Response('', { status: 204 });
  },
};
```

---

## Anti-patterns

- **`script-src *` or `script-src 'unsafe-eval'`**: Stripe.js does not require `unsafe-eval`. If your bundler injects eval (e.g., webpack dev mode), it only affects local dev; production builds must not use it.

- **`frame-ancestors 'none'` on the checkout page**: Blocks Stripe's iframe injection entirely. Use `frame-ancestors 'self'` on checkout; keep `X-Frame-Options: DENY` on all other pages.

- **Setting COEP: `require-corp`**: Stripe's payment element iframes do not send `Cross-Origin-Resource-Policy` headers, so `require-corp` blocks them. Use `unsafe-none` on checkout routes.

- **Relying solely on `_headers` for dynamic nonces**: `_headers` is static — it cannot generate per-request nonces. Use Pages Functions middleware for nonce-based CSP.

- **Adding `https://*.stripe.com` to `script-src`**: Over-broad. Stripe only serves scripts from `js.stripe.com` and `connect-js.stripe.com`. Use exact origins.

- **Omitting `https://r.stripe.com` from `connect-src`**: This is Stripe's Radar telemetry endpoint. Blocking it degrades fraud signals without surfacing any visible error.

---

## Gotchas

1. **Cloudflare Pages `_headers` does not support comments on the same line as a directive** — only standalone lines starting with `#`.

2. **`_headers` file routes are longest-prefix matched** — a rule for `/checkout` also matches `/checkout/confirm`. Add specific overrides if confirm page needs different headers.

3. **Stripe.js loads additional sub-scripts at runtime** from `js.stripe.com` with unique filenames. You cannot enumerate them. `https://js.stripe.com` in `script-src` covers all of them via origin match (no trailing path needed).

4. **Safari blocks cross-site cookies inside iframes by default** (ITP). Stripe handles this with `SameSite=None; Secure` on its cookies — do not intercept or transform Stripe's cookie headers via a Worker.

5. **`report-uri` is deprecated** — use `report-to` + `Reporting-Endpoints` header as shown above.

6. **Turnstile widget loads from `https://challenges.cloudflare.com`** — this is separate from Cloudflare's CDN origin and must be explicitly allowed.

7. **`wrangler pages deploy` does NOT deploy `_headers` in preview deployments unless the file is in the build output directory** — confirm with `wrangler pages deployment list` and check response headers.

---

## Verification

```bash
# 1. Deploy to Pages preview
wrangler pages deploy dist --project-name my-app

# 2. Inspect headers on the checkout route
curl -si https://MY-APP.pages.dev/checkout | grep -i "content-security-policy"

# 3. Run CSP evaluator
# Open https://csp-evaluator.withgoogle.com and paste your CSP

# 4. Test in browser with Stripe test cards
# Open DevTools → Console — look for CSP violation warnings
# Stripe test card: 4242 4242 4242 4242, any future date, any CVC

# 5. Test 3DS challenge (triggers frame-src usage)
# Stripe test card requiring 3DS: 4000 0025 0000 3155

# 6. Check CSP violations table (if report-only mode was active)
wrangler d1 execute payments \
  --command "SELECT payload FROM csp_violations ORDER BY created_at DESC LIMIT 10"
```

---

## Related

- `stripe-payment-elements.md` — Payment Element API and customization options
- `stripe-3ds-authentication.md` — 3DS2 flow and challenge handling
- `pci-dss-saq-a-compliance.md` — SAQ-A scope implications of using Stripe.js iframes
- `pci-dss-v4-client-side-script-integrity.md` — PCI DSS 4.0 requirement 6.4.3 (SRI hashes)
- `stripe-apple-pay-setup.md` — Apple Pay domain verification
- `stripe-google-pay-setup.md` — Google Pay configuration

---

## Sources

- [Stripe — Content Security Policy](https://docs.stripe.com/security/guide#content-security-policy)
- [Stripe — Stripe.js reference](https://docs.stripe.com/js)
- [Cloudflare Pages — Headers configuration](https://developers.cloudflare.com/pages/configuration/headers/)
- [Cloudflare Pages — Functions middleware](https://developers.cloudflare.com/pages/functions/middleware/)
- [MDN — Content-Security-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy)
- [Google CSP Evaluator](https://csp-evaluator.withgoogle.com/)
- [PCI DSS v4.0 requirement 6.4.3](https://www.pcisecuritystandards.org/document_library/)
