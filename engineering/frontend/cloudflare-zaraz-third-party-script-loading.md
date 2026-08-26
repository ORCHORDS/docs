# Cloudflare Zaraz for Third-Party Script Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Third-party scripts — analytics tags, pixels, chat widgets, A/B testing SDKs — are among
the top contributors to poor Total Blocking Time (TBT), high Interaction to Next Paint (INP),
and cumulative layout shift. A typical e-commerce page loading GA4, Meta Pixel, and a live
chat library often spends 400–800 ms in script evaluation on mid-range Android devices.
Cloudflare Zaraz moves tag execution server-side (to the edge) so the browser receives a
single lightweight `zaraz.js` stub and actual tag requests fire from Cloudflare's network
instead of from the visitor's device.

---

## Context

Zaraz is Cloudflare's server-side tag manager, available on all plans (Free tier included).
It runs as a Worker on Cloudflare's network and intercepts outbound calls that would
normally originate in the browser. For Cloudflare Pages projects, enabling Zaraz requires
only a zone-level toggle — no code changes to the SPA are needed beyond optionally calling
`window.zaraz.track()` and `window.zaraz.ecommerce()` for custom events.

Zaraz ships with managed integrations for Google Analytics 4, Google Ads, Meta Pixel,
Segment, TikTok Pixel, HubSpot, and dozens more. Each managed tool fires server-side by
default, but can be scoped to client-side if the vendor absolutely requires a browser cookie
from their own domain (rare).

---

## Enabling Zaraz on a Cloudflare Pages Zone

1. In the Cloudflare dashboard, navigate to **Zaraz** under the zone that serves your
   Pages project (the custom domain must be proxied — orange cloud).
2. Toggle **Zaraz** on. Cloudflare injects `<script >` into every
   HTML response via an HTML Rewriter at the edge.
3. Add a tool: **Tools → Add tool → Google Analytics 4**. Paste your Measurement ID.
   Zaraz auto-creates a "Page view" trigger mapped to the `pageview` event.

No `npm install` or bundle changes are required.

---

## Custom HTML Tools and the `zaraz.track()` API

For tags not in the managed catalogue, use a **Custom HTML** tool. Zaraz sandboxes the
HTML snippet inside a Web Worker so it cannot access `document` or `window` directly —
it can only call `zaraz.*` helpers and make outbound fetch requests.

Fire custom events from your React or SvelteKit app:

```typescript
// src/utils/analytics.ts
declare global {
  interface Window {
    zaraz?: {
      track: (eventName: string, properties?: Record<string, unknown>) => void;
      ecommerce: (eventName: string, properties?: Record<string, unknown>) => void;
      set: (key: string, value: string) => void;
    };
  }
}

export function track(
  event: string,
  properties?: Record<string, unknown>
): void {
  if (typeof window !== 'undefined' && window.zaraz) {
    window.zaraz.track(event, properties);
  }
  // SSR guard: zaraz.js is browser-only
}
```

Usage in a React component:

```typescript
// src/components/ProductCard.tsx
import { track } from '../utils/analytics';

export function ProductCard({ id, name, price }: Product) {
  const handleAddToCart = () => {
    addToCart(id);
    track('add_to_cart', { item_id: id, item_name: name, value: price });
  };

  return (
    <button onClick={handleAddToCart}>Add to cart</button>
  );
}
```

---

## E-Commerce Events via `zaraz.ecommerce()`

Zaraz maps a standard e-commerce schema to all connected tools simultaneously, avoiding
per-tool event mapping boilerplate:

```typescript
// Fire once; Zaraz fans out to GA4, Meta Pixel, TikTok Pixel simultaneously
window.zaraz.ecommerce('Order Completed', {
  checkout_id: order.id,
  revenue: order.total,
  currency: 'USD',
  products: order.items.map((item) => ({
    product_id: item.sku,
    name: item.name,
    price: item.price,
    quantity: item.qty,
  })),
});
```

---

## Consent API Integration (GDPR / CCPA)

Zaraz ships a built-in Consent API that blocks tool loading until the visitor grants
consent, removing the need for a separate CMP library:

```typescript
// Show consent modal, then update Zaraz consent state
async function acceptAll() {
  // Zaraz Consent API: set consent for all purposes
  await window.zaraz.consent.setAll(true);
  await window.zaraz.consent.sendQueuedEvents();
}

async function rejectAnalytics() {
  await window.zaraz.consent.set({ analytics: false, marketing: false });
}
```

Map Zaraz "purposes" (analytics, marketing, etc.) to tools in the dashboard
**Zaraz → Consent Management → Purposes**. Tools without a granted purpose are
never loaded, and queued `zaraz.track()` calls fire retroactively on grant.

---

## Configuring SPA History Navigation Events

Zaraz auto-detects `pushState`/`popstate` changes and fires a new `pageview` event
for each navigation when the **Single Page Application** option is enabled per-tool
in the dashboard. No manual re-triggering is needed for React Router, TanStack Router,
or SvelteKit page transitions.

For Pages projects using the Navigation API:

```typescript
// Only needed if you override Navigation API and suppress the default scroll
navigation.addEventListener('navigate', (e: NavigateEvent) => {
  if (!e.canIntercept) return;
  e.intercept({
    handler: async () => {
      await loadPage(e.destination.url);
      // Zaraz picks up the URL change automatically via MutationObserver
    },
  });
});
```

---

## Anti-patterns

- **Double-loading scripts**: If GA4 `gtag.js` is also included in `index.html` alongside
  Zaraz's GA4 managed tool, page views are counted twice. Remove all direct `<script>` tags
  for tools managed by Zaraz.
- **Calling `zaraz.track()` during SSR**: Zaraz is browser-only. Guard every call with
  `typeof window !== 'undefined'`.
- **Using Custom HTML for vendors with managed integrations**: Managed tools are optimised
  for server-side execution; custom HTML tools run with more restrictions and may miss
  events during fast navigations.
- **Expecting sub-millisecond latency on `zaraz.track()`**: The call is asynchronous and
  batched. Never block UI interactions waiting for it to resolve.

---

## Gotchas

- Zaraz requires the Pages domain to be **proxied** (orange cloud) through Cloudflare.
  Direct `*.pages.dev` subdomains are proxied automatically; custom domains must be
  configured with a CNAME + proxy toggle.
- Zaraz rewrites `<head>` HTML using HTMLRewriter. If your Pages project returns a
  `Content-Security-Policy` header with a strict `script-src`, you must add
  `'nonce-{zaraz-nonce}'` or whitelist `/cdn-cgi/zaraz/` — the dashboard shows the
  exact directive to append.
- Zaraz preview mode (the lightning-bolt icon in the dashboard) only activates when
  the `__zarazDebug=true` cookie is set. It does not affect production visitors.
- Tool load order is not guaranteed. Do not rely on one Zaraz tool's global variable
  being available inside another tool's code block.

---

## Verification

1. Open Chrome DevTools → Network, filter by `cdn-cgi/zaraz`. Confirm `zaraz.js` loads
   and subsequent pixel requests originate from `www.cloudflare.com` (not the visitor's
   browser directly).
2. Enable **Zaraz Preview** in the dashboard, then navigate your site. The debug panel
   shows each trigger evaluation and which tools fired.
3. Check GA4 DebugView (Admin → DebugView) to confirm server-side events arrive with
   correct parameters.
4. Run `window.zaraz.track('test_event')` in the console and verify it appears in
   DebugView within 5 seconds.

---

## Related

- `cloudflare-pages-headers-csp-mobile.md` — CSP configuration on Pages
- `beacon-api-analytics-cloudflare-workers.md` — alternative: self-hosted analytics
- `web-vitals-cloudflare-rum-integration.md` — Cloudflare RUM alongside Zaraz
- `dark-mode-edge-cookie-cloudflare-pages.md` — edge cookie patterns

---

## Sources

- Cloudflare Zaraz documentation: https://developers.cloudflare.com/zaraz/
- Zaraz Web API: https://developers.cloudflare.com/zaraz/web-api/
- Zaraz Consent API: https://developers.cloudflare.com/zaraz/consent-management/
- Zaraz E-commerce: https://developers.cloudflare.com/zaraz/advanced/ecommerce/
