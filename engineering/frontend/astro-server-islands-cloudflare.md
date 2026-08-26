# Astro Server Islands on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
You want a statically-cached Cloudflare Pages site where specific, personalised UI sections (a user avatar, a cart count, a recommendation widget) are rendered fresh on every request without invalidating the full-page CDN cache.

## Context
Astro 5's Server Islands let you mark individual components with `server:defer` — Astro serves the outer static shell from CDN instantly, then each island is fetched as a separate, authenticated sub-request that runs through a Cloudflare Worker. Unlike ISR, the shell never needs to be revalidated; only the island endpoints carry user-specific data. The pattern composes with D1 for database reads and KV for session storage at the edge.

## Setup — Adapter and Project Config

```bash
npm create astro@latest my-site -- --template minimal
cd my-site
npx astro add cloudflare
npm install @astrojs/cloudflare
```

```ts
// astro.config.ts
import { defineConfig } from 'astro/config'
import cloudflare from '@astrojs/cloudflare'

export default defineConfig({
  output: 'static',          // outer shell is static
  adapter: cloudflare({
    platformProxy: { enabled: true },   // wrangler proxy for local dev
    imageService: 'cloudflare',
  }),
  // Server islands need a server endpoint; point it at the Worker
  experimental: {
    serverIslands: true,
  },
})
```

```toml
# wrangler.toml  (used by Pages Functions, not a standalone Worker)
name = "my-site"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = "dist"

[[d1_databases]]
binding = "DB"
database_name = "my-site-db"
database_id = "xxxx-xxxx-xxxx-xxxx"

[[kv_namespaces]]
binding = "SESSIONS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Static Shell Page

```astro
---
// src/pages/index.astro
// This page is pre-rendered to static HTML; no runtime cost on the CDN hit
import Layout from '../layouts/Layout.astro'
import UserAvatar from '../components/UserAvatar.astro'
import CartCount from '../components/CartCount.astro'
import HeroSection from '../components/HeroSection.astro'
---
<Layout title="My Store">
  <header>
    <!-- server:defer — each island is a separate sub-request to the Worker -->
    <UserAvatar server:defer>
      <!-- Fallback rendered while the island loads -->
      <span slot="fallback" class="avatar-skeleton" aria-hidden="true"></span>
    </UserAvatar>

    <CartCount server:defer>
      <span slot="fallback">🛒</span>
    </CartCount>
  </header>

  <!-- Static content — served from CDN, no Worker invocation -->
  <HeroSection />
</Layout>
```

## Server Island Components

```astro
---
// src/components/UserAvatar.astro
// This component only runs when fetched as an island sub-request
import type { Runtime } from '@astrojs/cloudflare'

type Env = { SESSIONS: KVNamespace }
const runtime = Astro.locals.runtime as Runtime<Env>

const sessionId = Astro.cookies.get('sid')?.value
let displayName = 'Guest'
let avatarUrl = '/default-avatar.svg'

if (sessionId) {
  const session = await runtime.env.SESSIONS.get<{ name: string; avatar: string }>(
    `session:${sessionId}`,
    { type: 'json' }
  )
  if (session) {
    displayName = session.name
    avatarUrl = session.avatar
  }
}
---
<div class="user-avatar">
  <img src={avatarUrl} alt="" width="32" height="32" />
  <span>{displayName}</span>
</div>
```

```astro
---
// src/components/CartCount.astro
import type { Runtime } from '@astrojs/cloudflare'

type Env = { DB: D1Database }
const runtime = Astro.locals.runtime as Runtime<Env>

const sessionId = Astro.cookies.get('sid')?.value ?? ''
let count = 0

if (sessionId) {
  const row = await runtime.env.DB
    .prepare('SELECT COUNT(*) as n FROM cart_items WHERE session_id = ?')
    .bind(sessionId)
    .first<{ n: number }>()
  count = row?.n ?? 0
}
---
<a  class="cart-link" aria-label={`Cart, ${count} items`}>
  🛒 {count > 0 && <span class="badge">{count}</span>}
</a>
```

## Island Caching Boundary — Edge Headers

```ts
// functions/_middleware.ts  (Cloudflare Pages Function)
// Cache the static shell aggressively; block caching on island sub-requests
import type { PagesFunction } from '@cloudflare/workers-types'

export const onRequest: PagesFunction = async ({ request, next }) => {
  const url = new URL(request.url)

  // Astro server islands are fetched via a `_server-islands` path segment
  if (url.pathname.includes('/_server-islands/')) {
    const res = await next()
    // Island responses carry user-specific data — must not be shared-cached
    const headers = new Headers(res.headers)
    headers.set('Cache-Control', 'private, no-store')
    headers.set('Vary', 'Cookie')
    return new Response(res.body, { status: res.status, headers })
  }

  const res = await next()

  // Static shell: cache for 1 hour at CDN, revalidate stale in background
  if (res.headers.get('Content-Type')?.includes('text/html')) {
    const headers = new Headers(res.headers)
    headers.set('Cache-Control', 'public, max-age=3600, stale-while-revalidate=86400')
    return new Response(res.body, { status: res.status, headers })
  }

  return res
}
```

## Anti-patterns
- Placing large database joins inside a server island that is called on every page load without result caching — each CDN miss spawns N island sub-requests; add KV caching with short TTLs
- Forgetting `slot="fallback"` on `server:defer` — without it the island slot renders blank while loading, causing layout shift
- Using server islands for content that is the same for all users (hero copy, navigation links) — static pre-rendering is faster and cheaper; reserve islands for personalised data
- Passing secrets through island component props — props are serialised into a signed URL query string; use KV or D1 lookups inside the island instead
- Nesting one server island inside another — Astro 5 does not support recursive island deferral; flatten the component tree

## Gotchas
- `server:defer` compiles to a `<astro-island>` custom element with a `data-component-url` pointing to the `/_server-islands/` endpoint; requests to that endpoint must reach the Worker, not the static CDN cache
- The `@astrojs/cloudflare` adapter wraps Pages Functions; you must deploy via `wrangler pages deploy`, not a plain static upload, for islands to work
- `Astro.locals.runtime` is only populated when the adapter is active; calling it from a static-only build throws at runtime
- Island sub-requests do not inherit the outer page's `<head>` — do not import global CSS inside an island component; it is not applied
- `platformProxy` in `astro.config.ts` enables local KV/D1 simulation via wrangler during `astro dev`; without it, `runtime.env.*` is undefined locally
- Signed island URLs expire after 60 seconds by default; long-lived pages loaded in a background tab may fail island fetches after returning

## Verification

```bash
# Local dev with wrangler proxy
npx astro dev

# Confirm island endpoint exists
curl -s http://localhost:4321/_server-islands/UserAvatar | grep 'user-avatar'

# Build and preview (Pages emulation)
npx astro build
npx wrangler pages dev dist --port 8788

# Check static shell cache headers
curl -I http://localhost:8788/ | grep -i cache-control

# Check island no-store header
curl -I "http://localhost:8788/_server-islands/CartCount?props=..." \
  | grep -i cache-control
```

## Related
- [astro-cloudflare-adapter-ssr-hybrid.md](astro-cloudflare-adapter-ssr-hybrid.md)
- [astro-content-collections-r2-integration.md](astro-content-collections-r2-integration.md)
- [islands-architecture-cloudflare-pages-partial-hydration.md](islands-architecture-cloudflare-pages-partial-hydration.md)
- [feature-flags-cloudflare-workers-kv-edge-config.md](feature-flags-cloudflare-workers-kv-edge-config.md)
- [cloudflare-pages-middleware-auth-gating.md](cloudflare-pages-middleware-auth-gating.md)

## Sources
- https://docs.astro.build/en/guides/server-islands/
- https://developers.cloudflare.com/pages/functions/
- https://docs.astro.build/en/guides/integrations-guide/cloudflare/
- https://developers.cloudflare.com/kv/
