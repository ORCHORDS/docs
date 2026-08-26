# React Suspense with Cloudflare Pages Functions — Streaming SSR at the Edge

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

The page renders a blank screen until all data is fetched (no progressive hydration),
or `renderToPipeableStream` throws `"TextEncoder is not defined"` in a Cloudflare Pages
Function because the Node.js API is unavailable. On mobile, TTFB exceeds 800 ms because
the entire HTML shell waits for the slowest data fetch.

## Context

example project (example.com) is a Next.js 14 app with `output: 'export'`, which means full static
HTML at build time. For routes that need dynamic personalised data (user feed, play count),
the pattern shifts to Cloudflare Pages Functions: edge workers that run React's
`renderToReadableStream` (Web Streams API — compatible with the Workers runtime) and
stream HTML chunks to the client. This coexists with Next.js static export: static routes
serve from `/out`, dynamic routes are handled by Pages Functions.

---

## Static Export vs Pages Functions — Decision Matrix

| Route Type | Approach | Runtime |
|---|---|---|
| Marketing pages, `/`, `/about` | `output: 'export'` static HTML | CDN edge (no compute) |
| `/feed` — personalised | Pages Function + `renderToReadableStream` | Workers runtime |
| `/track/[id]` — public | `output: 'export'` + ISR-equivalent via KV | CDN edge |
| `/api/**` — JSON | Pages Function (plain Worker) | Workers runtime |

---

## renderToReadableStream — Not renderToPipeableStream

Cloudflare Workers run on the V8-based Workerd runtime, not Node.js.
`renderToPipeableStream` is Node.js-only. Use `renderToReadableStream` instead:

```ts
// functions/feed/[[path]].tsx
import { renderToReadableStream } from 'react-dom/server';
import { createElement }          from 'react';
import type { PagesFunction }     from '@cloudflare/workers-types';
import { FeedPage }               from '../../src/pages/FeedPage';

interface Env { DB: D1Database; ASSETS: Fetcher; }

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env } = context;

  // Fetch critical data before streaming starts — keeps the shell cheap
  const userId = getUserIdFromCookie(request);

  // Bootstrap data streamed as an inline JSON tag (no extra round-trip)
  const bootstrapData = { userId };

  const stream = await renderToReadableStream(
    createElement(FeedPage, { userId }),
    {
      bootstrapScriptContent: `window.__BOOTSTRAP__=${JSON.stringify(bootstrapData)};`,
      // Signal errors in stream to Cloudflare
      onError(error) {
        console.error('[RSC stream error]', error);
      },
    },
  );

  // Wait for Suspense shells to resolve before flushing; improves SEO
  // for bots that don't execute JS (optional — omit for fastest TTFB)
  // await stream.allReady;

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      // Transfer-Encoding: chunked is set automatically for ReadableStream
      'Cache-Control': 'private, no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
};

function getUserIdFromCookie(req: Request): string | null {
  const cookie = req.headers.get('Cookie') ?? '';
  const match  = cookie.match(/example project_uid=([^;]+)/);
  return match?.[1] ?? null;
}
```

---

## Suspense Boundary Architecture

```
FeedPage
├── <Suspense fallback={<HeaderSkeleton />}>  ← resolves instantly (static)
│   └── <Header />
├── <Suspense fallback={<FeedSkeleton rows={5} />}>  ← waits for D1 query
│   └── <FeedList userId={userId} />
└── <Suspense fallback={<PlayerSkeleton />}>  ← waits for last-played track
    └── <Player userId={userId} />
```

```tsx
// src/pages/FeedPage.tsx
import { Suspense } from 'react';
import { FeedList }    from '../components/FeedList';
import { Player }      from '../components/Player';
import { Header }      from '../components/Header';
import { FeedSkeleton } from '../components/skeletons/FeedSkeleton';
import { PlayerSkeleton } from '../components/skeletons/PlayerSkeleton';
import { HeaderSkeleton } from '../components/skeletons/HeaderSkeleton';

interface Props { userId: string | null; }

export function FeedPage({ userId }: Props) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>example project Feed</title>
        <link rel="stylesheet"  />
      </head>
      <body>
        <Suspense fallback={<HeaderSkeleton />}>
          <Header />
        </Suspense>
        <main>
          <Suspense fallback={<FeedSkeleton rows={5} />}>
            <FeedList userId={userId} />
          </Suspense>
        </main>
        <footer>
          <Suspense fallback={<PlayerSkeleton />}>
            <Player userId={userId} />
          </Suspense>
        </footer>
      </body>
    </html>
  );
}
```

---

## Async Server Components — D1 Data Fetching

```tsx
// src/components/FeedList.tsx
// This is a Server Component — runs only on the edge, not in the browser
import { getRequestContext } from '@cloudflare/next-on-pages';

interface Track { id: string; title: string; artist: string; }

async function fetchFeedTracks(userId: string | null): Promise<Track[]> {
  // In a Pages Function, env is passed through React context or props
  // For Next.js + @cloudflare/next-on-pages, use getRequestContext()
  const { env } = getRequestContext();
  const result = await env.DB.prepare(
    `SELECT id, title, artist FROM tracks
     ORDER BY created_at DESC LIMIT 20`,
  ).all<Track>();
  return result.results;
}

export async function FeedList({ userId }: { userId: string | null }) {
  const tracks = await fetchFeedTracks(userId);

  return (
    <ul aria-label="Music feed">
      {tracks.map((t) => (
        <li key={t.id}>
          <strong>{t.title}</strong> — {t.artist}
        </li>
      ))}
    </ul>
  );
}
```

---

## TTFB Optimisation on Mobile

| Technique | TTFB impact | Notes |
|---|---|---|
| Stream shell before `allReady` | -200 to -600 ms | Browser paints header/skeleton immediately |
| Cloudflare Smart Placement | -50 to -150 ms | Routes Worker to PoP closest to D1 region |
| KV for quasi-static data | -100 to -300 ms | Avoid D1 round-trip for read-heavy data |
| `Cache-Control: private, s-maxage=0` | 0 | Ensures personalised pages bypass CDN cache |
| Compress Worker bundle | -20 ms cold start | Reduce parse time; avoid heavy node_modules |

### Enabling Smart Placement

```toml
# wrangler.toml (if using Wrangler for the Worker portion)
[placement]
mode = "smart"
```

Smart Placement routes each request to the Cloudflare PoP geographically closest to the
D1 primary database, reducing the Worker → D1 RTT from ~80 ms (cross-region) to ~5 ms.

---

## Fallback Boundary Error Handling

```tsx
// src/components/FeedErrorBoundary.tsx
'use client';
import { Component, type ReactNode } from 'react';

interface State { error: Error | null; }

export class FeedErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" aria-live="polite">
          <p>Could not load feed. <button onClick={() => this.setState({ error: null })}>Retry</button></p>
        </div>
      );
    }
    return this.props.children;
  }
}
```

Wrap each Suspense boundary with an ErrorBoundary to avoid the entire stream aborting
on a single component failure.

---

## Anti-patterns

- **`renderToPipeableStream` in a Pages Function** — Node.js API; throws in V8 Workers.
- **`await stream.allReady` always** — blocks streaming; only use for SEO-critical routes.
- **Fetching all data before starting the stream** — defeats the point of streaming SSR.
- **Returning a large `bootstrapScriptContent`** — it is inlined in every response;
  keep to minimal hydration signals.
- **Importing Node.js modules (`fs`, `path`, `crypto`) in Pages Functions** — Workers
  runtime does not have them; use the Web Crypto API (`crypto.subtle`) instead.

---

## Gotchas

- `@cloudflare/next-on-pages` is an adapter that wraps Next.js App Router for the Workers
  runtime. With `output: 'export'`, it is not used — you write the Pages Function manually.
- `renderToReadableStream` from `react-dom/server` requires React 18+. Verify the import
  resolves to the browser-agnostic export, not the Node.js one.
- The Workers runtime limits CPU time to 50 ms per request on the Free plan (30 s on
  Paid). Rendering a complex React tree with many Suspense nodes can exceed 50 ms.
- `bootstrapScriptContent` is injected as a raw `<script>` tag. Always sanitise any
  user-derived data before embedding it to prevent XSS.
- Streaming SSR requires the client to hydrate with `hydrateRoot`, not `createRoot`.
  Mismatches between server and client render tree cause React's `hydration failed` error.

---

## Verification

```bash
# 1. Confirm ReadableStream response (not buffered)
curl -N --no-buffer -s https://example.com/feed | head -c 500
# Should see <html><head>... before feed content arrives

# 2. Measure TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://example.com/feed

# 3. Check streaming headers
curl -I https://example.com/feed | grep -E "transfer-encoding|content-type|cache-control"
# Expected: transfer-encoding: chunked or no content-length

# 4. Validate Suspense boundaries render correctly
npx playwright test tests/feed.spec.ts --project=mobile-safari

# 5. Simulate slow D1 with artificial delay — verify skeleton renders first
# In the Pages Function, add await new Promise(r => setTimeout(r, 2000)) before DB query
# Open /feed — should see skeleton for 2 s, then feed appears without page reload
```

---

## Related

- `react-suspense-boundaries.md`
- `react-19-server-components-streaming-ssr.md`
- `react-server-components-patterns.md`
- `next-js-app-router-patterns.md`
- `nextjs-static-export-cloudflare-pages-routing.md`
- `html-web-vitals-lcp.md`

## Sources

- React renderToReadableStream — https://react.dev/reference/react-dom/server/renderToReadableStream
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
- Cloudflare Workers runtime APIs — https://developers.cloudflare.com/workers/runtime-apis/
- @cloudflare/next-on-pages — https://github.com/cloudflare/next-on-pages
- React Suspense SSR architecture — https://github.com/reactwg/react-18/discussions/37
- Cloudflare Smart Placement — https://developers.cloudflare.com/workers/configuration/smart-placement/
