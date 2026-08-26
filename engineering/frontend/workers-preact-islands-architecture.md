# Preact Islands Architecture on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want a mostly-static site delivered fast from Workers, with a handful of
interactive widgets (search box, cart counter, video player) that hydrate
in-place. Full React/Next.js is overkill; you want sub-100 kB JS and
predictable hydration boundaries.

## Context

- **Preact 10** ships `preact-render-to-string` which runs in the Workers
  runtime without polyfills
- The "islands" pattern: server renders the full page as a static HTML string;
  only designated `<Island>` wrappers are re-hydrated on the client
- **KV** caches the static HTML shell (TTL 60 s) to keep CPU time in the free
  tier
- No framework magic — islands are explicit, co-located `.island.tsx` files

---

## 1 — Project structure

```
src/
  components/
    Header.tsx          # static, never shipped to client
    SearchBox.island.tsx  # interactive island
    CartCount.island.tsx  # interactive island
  worker/
    index.ts            # Worker entry
    render.ts           # server-side render helper
  client/
    hydrate.ts          # tiny client bootstrap
```

## 2 — Static components (server-only)

```typescript
// src/components/Header.tsx
import { h } from 'preact';

interface Props {
  title: string;
  cartCount: number;
}

export function Header({ title, cartCount }: Props) {
  return (
    <header>
      <a >{title}</a>
      {/* Island placeholder — hydrated on the client */}
      <island-root data-component="CartCount" data-props={JSON.stringify({ initial: cartCount })}>
        <span aria-label="cart">{cartCount} items</span>
      </island-root>
    </header>
  );
}
```

## 3 — Island component

```typescript
// src/components/CartCount.island.tsx
import { h } from 'preact';
import { useState } from 'preact/hooks';

interface Props {
  initial: number;
}

export default function CartCount({ initial }: Props) {
  const [count, setCount] = useState(initial);

  // In production, subscribe to a custom event from the cart store
  if (typeof window !== 'undefined') {
    window.addEventListener('cart:update', (e: Event) => {
      setCount((e as CustomEvent<number>).detail);
    });
  }

  return (
    <button
      aria-label={`Cart — ${count} items`}
      onClick={() => setCount(c => c + 1)}
    >
      🛒 {count}
    </button>
  );
}
```

## 4 — Worker: render and cache the HTML shell

```typescript
// src/worker/render.ts
import { h } from 'preact';
import { render } from 'preact-render-to-string';
import { Header } from '../components/Header.js';

export function renderPage(title: string, cartCount: number): string {
  const body = render(
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <title>{title}</title>
        <link rel="stylesheet"  />
      </head>
      <body>
        <Header title={title} cartCount={cartCount} />
        <main id="content">
          <island-root data-component="SearchBox" data-props="{}">
            <input placeholder="Search…" disabled />
          </island-root>
        </main>
        {/* Island bootstrap — tiny, ~2 kB gzip */}
        <script type="module" ></script>
      </body>
    </html>
  );
  return '<!doctype html>' + body;
}
```

```typescript
// src/worker/index.ts
import { renderPage } from './render.js';

export interface Env {
  STATIC_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Serve static assets from KV (set via wrangler kv:key put or Pages assets)
    if (url.pathname.startsWith('/assets/') || url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) {
      // Delegate to asset binding or a DO-based asset server in practice
      return new Response('Not found', { status: 404 });
    }

    const cacheKey = `html:${url.pathname}`;

    // Try KV cache first
    const cached = await env.STATIC_CACHE.get(cacheKey, { type: 'text' });
    if (cached) {
      return new Response(cached, {
        headers: { 'content-type': 'text/html;charset=utf-8', 'x-cache': 'HIT' },
      });
    }

    // Render fresh — in production, fetch cart count from a Durable Object or D1
    const html = renderPage('My Store', 0);

    // Cache for 60 seconds
    await env.STATIC_CACHE.put(cacheKey, html, { expirationTtl: 60 });

    return new Response(html, {
      headers: { 'content-type': 'text/html;charset=utf-8', 'x-cache': 'MISS' },
    });
  },
};
```

## 5 — Client hydration bootstrap

```typescript
// src/client/hydrate.ts  →  built to /public/hydrate.js

// Map of component names to dynamic imports
const registry: Record<string, () => Promise<{ default: unknown }>> = {
  CartCount: () => import('../components/CartCount.island.js'),
  SearchBox: () => import('../components/SearchBox.island.js'),
};

async function hydrateIslands(): Promise<void> {
  const roots = document.querySelectorAll<HTMLElement>('island-root[data-component]');

  await Promise.all(
    Array.from(roots).map(async (root) => {
      const name = root.dataset.component!;
      const props = JSON.parse(root.dataset.props ?? '{}');
      const mod = registry[name];
      if (!mod) {
        console.warn(`[islands] unknown component: ${name}`);
        return;
      }
      const { default: Component } = await mod();
      const { hydrate } = await import('preact');
      hydrate(h(Component as preact.ComponentType, props), root);
    })
  );
}

hydrateIslands().catch(console.error);
```

## Anti-patterns

- **Hydrating the entire `<body>`** — defeats the purpose; every component re-
  renders on load, eliminating the static-shell benefit.
- **Storing large HTML blobs in KV without a size guard** — KV values max at
  25 MB; add a `if (html.length > 20_000_000) skip` guard before `put`.
- **Sharing mutable state across islands via a global variable** — use
  `CustomEvent` / BroadcastChannel so islands stay decoupled.

## Gotchas

1. `preact-render-to-string` renders JSX via `h`, so your Worker esbuild config
   must set `--jsx-factory=h --jsx-import-source=preact`.
2. The `<island-root>` custom element is inert by default. Register it with
   `customElements.define('island-root', HTMLElement)` to avoid browser warnings.
3. KV TTL is eventually consistent across PoPs; a 60 s TTL can mean stale HTML
   up to ~2× TTL after a write in the worst case.
4. **No double data** — do not embed the full JSON state both in the server HTML
   and again in an inline `<script>`; use `data-props` on the island root only.

## Verification

```bash
# Build client bundle
npx esbuild src/client/hydrate.ts --bundle --format=esm \
  --jsx=transform --jsx-factory=h --jsx-import-source=preact \
  --outfile=public/hydrate.js

# Run worker locally
npx wrangler dev src/worker/index.ts --compatibility-date=2025-01-01

# Confirm island roots exist in static HTML
curl -s http://localhost:8787/ | grep 'data-component'
# Expected: <island-root data-component="CartCount" ...>

# Confirm KV caching works
curl -v http://localhost:8787/ 2>&1 | grep 'x-cache'
# First: x-cache: MISS  / Second: x-cache: HIT
```

## Related

- `documentation/categories/frontend/workers-lit-web-components-ssr-pages.md`
- `documentation/workers/workers-kv-caching-patterns.md`

## Sources

- https://preactjs.com/guide/v10/server-side-rendering/
- https://jasonformat.com/islands-architecture/
- https://developers.cloudflare.com/kv/
