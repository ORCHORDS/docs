# Islands Architecture on Cloudflare Pages with Partial Hydration

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You ship a mostly-static marketing or content site but a few interactive widgets (cart count, search modal, newsletter form) bloat your JS bundle and slow TTI. You want most of the page to render as plain HTML with zero JS, while individual interactive "islands" hydrate independently and lazily.

## Context

Islands architecture treats the page as a static HTML sea with discrete interactive islands. Each island carries its own hydration script; the rest of the page ships no JS at all. Cloudflare Pages serves static HTML from the CDN edge while Workers Functions handle dynamic island data. Frameworks that natively support islands include Astro, Fresh (Deno), and Qwik; React and Svelte require manual plumbing or a thin wrapper like Enhance or Îles.

Partial hydration goes further: even islands defer hydration until a viewport or idle trigger fires, cutting the main-thread work that drives INP regressions on mobile.

---

## Astro Islands on Cloudflare Pages

Astro compiles every component to plain HTML by default. Interactive islands use client directives.

```astro
---
// src/pages/index.astro
import CartCount from '../components/CartCount.tsx';
import SearchModal from '../components/SearchModal.tsx';
import StaticHero from '../components/StaticHero.astro';
---
<html>
  <body>
    <!-- zero JS – pure HTML -->
    <StaticHero />

    <!-- hydrates only when element enters viewport -->
    <CartCount client:visible />

    <!-- hydrates after browser is idle -->
    <SearchModal client:idle />
  </body>
</html>
```

The `client:visible` directive wraps the island in an `IntersectionObserver`; `client:idle` uses `requestIdleCallback`. Neither blocks the initial render.

---

## Manual React Islands with Web Components Shell

When you cannot switch frameworks, wrap React trees in a custom element that lazy-loads the bundle.

```typescript
// src/islands/define-island.ts
export function defineIsland(
  tagName: string,
  loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>,
) {
  class IslandElement extends HTMLElement {
    private observer: IntersectionObserver | null = null;

    connectedCallback() {
      this.observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) {
          this.observer?.disconnect();
          void this.hydrate();
        }
      });
      this.observer.observe(this);
    }

    disconnectedCallback() {
      this.observer?.disconnect();
    }

    private async hydrate() {
      const { createRoot } = await import('react-dom/client');
      const { default: Component } = await loader();
      const props = JSON.parse(this.dataset.props ?? '{}') as Record<string, unknown>;
      createRoot(this).render(<Component {...props} />);
    }
  }

  customElements.define(tagName, IslandElement);
}
```

```html
<!-- Rendered server-side by a Cloudflare Worker -->
<search-island data-props='{"placeholder":"Search…"}'></search-island>
<script type="module"  defer></script>
```

```typescript
// src/islands/search.ts – loaded only when island is visible
import { defineIsland } from './define-island';
defineIsland('search-island', () => import('../components/SearchModal'));
```

---

## Cloudflare Worker Rendering the Static Shell

A Worker pre-renders the HTML shell (or fetches it from Pages) and injects island placeholders using `HTMLRewriter`.

```typescript
// functions/api/page.ts  (Cloudflare Pages Function)
import { HTMLRewriter } from '@cloudflare/workers-types';

export const onRequest: PagesFunction = async (ctx) => {
  const upstream = await ctx.env.ASSETS.fetch(ctx.request);

  return new HTMLRewriter()
    .on('cart-count', {
      element(el) {
        // Inject server-side prop snapshot so island boots instantly
        el.setAttribute(
          'data-props',
          JSON.stringify({ count: 3 }), // hydrated from KV or D1
        );
      },
    })
    .transform(upstream);
};
```

---

## Lazy Island Hydration with `client:media`

Astro's `client:media` directive hydrates only when a CSS media query matches – useful for mobile-only widgets.

```astro
---
import MobileNav from '../components/MobileNav.tsx';
import DesktopNav from '../components/DesktopNav.astro';
---
<!-- Desktop gets a static nav – no JS -->
<DesktopNav />

<!-- Mobile nav hydrates only on narrow screens -->
<MobileNav client:media="(max-width: 768px)" />
```

For Cloudflare Pages deployments, combine with `astro.config.mjs` using the Cloudflare adapter:

```typescript
// astro.config.mjs
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'hybrid',          // static by default, opt-in SSR per route
  adapter: cloudflare({
    platformProxy: { enabled: true },
  }),
});
```

---

## Island Data Fetching via Workers KV

Islands that need fresh data fetch from a Workers endpoint rather than baking data into HTML at build time.

```typescript
// functions/api/cart.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  CART_KV: KVNamespace;
}

export const onRequestGet: PagesFunction<Env> = async ({ request, env }) => {
  const sessionId = new URL(request.url).searchParams.get('session') ?? '';
  const raw = await env.CART_KV.get(`cart:${sessionId}`, 'json');
  return Response.json(raw ?? { items: [], count: 0 });
};
```

```typescript
// src/components/CartCount.tsx
import { useEffect, useState } from 'react';

interface Cart { count: number }

export default function CartCount() {
  const [cart, setCart] = useState<Cart>({ count: 0 });

  useEffect(() => {
    const id = document.cookie.match(/sid=([^;]+)/)?.[1] ?? '';
    fetch(`/api/cart?session=${id}`)
      .then((r) => r.json() as Promise<Cart>)
      .then(setCart);
  }, []);

  return <span aria-label={`${cart.count} items in cart`}>{cart.count}</span>;
}
```

---

## Anti-patterns

- **Hydrating everything eagerly** – `client:load` on every component defeats islands; use it only for above-the-fold interactive UI critical to first interaction.
- **Sharing global state between islands** – islands are intentionally isolated; shared state should live in a cookie, URL param, or KV, not a JS module singleton.
- **Blocking island JS in `<head>`** – islands scripts must be `defer` or `type="module"`; synchronous scripts block the static content advantage.
- **Skipping `data-props` serialization** – without serialized props the island must re-fetch on hydration, causing a visible content flash.
- **Nesting islands** – child islands inside parent islands create duplicate hydration trees; flatten the component hierarchy.

---

## Gotchas

- Astro `client:visible` requires a polyfill for `IntersectionObserver` in Safari < 12.1 (effectively extinct, but worth noting for internal tools).
- `HTMLRewriter` runs synchronously per chunk; avoid awaiting async ops inside element handlers – fetch data before calling `.transform()`.
- Cloudflare Pages static assets served via `ctx.env.ASSETS` bypass Workers CPU limits; the rewriter itself counts against the 10 ms CPU budget per request on the free plan.
- Island bundles are separate JS files; ensure your build tool (Vite / Rollup) emits them as named chunks and does not tree-shake the `customElements.define` call.
- `client:idle` falls back to `setTimeout(fn, 200)` in browsers that lack `requestIdleCallback` (Safari pre-15.4).

---

## Verification

```bash
# Build and check JS chunk count
npx astro build --verbose 2>&1 | grep '.js'

# Confirm island scripts are deferred
curl -s https://your-site.pages.dev | grep 'island' | grep -v 'defer\|module'
# Should return nothing

# Measure JS transferred for a static page
npx lighthouse https://your-site.pages.dev --only-audits=total-byte-weight,unused-javascript
```

In Chrome DevTools Coverage tab, a well-implemented islands page shows > 80% unused JS removed from the initial load.

---

## Related

- `astro-cloudflare-adapter-ssr-hybrid.md`
- `web-components-cloudflare-workers-html-rewriter.md`
- `react-suspense-cloudflare-pages-ssr-edge.md`
- `browser-intersection-observer.md`
- `hono-cloudflare-workers-frontend-api.md`

---

## Sources

- https://docs.astro.build/en/concepts/islands/
- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://web.dev/articles/performance-budgets
