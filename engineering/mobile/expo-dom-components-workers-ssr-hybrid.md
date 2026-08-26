# Expo DOM Components + Workers SSR Hybrid Rendering

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building an Expo app (SDK 52+) that needs certain screens — marketing landers,
rich-text article pages, complex interactive forms — to render with server-generated HTML for
SEO and fast initial paint, while still running natively on iOS and Android. React Native's
standard view tree cannot handle arbitrary HTML/CSS, and a full WebView swaps you out of the
native rendering pipeline entirely. Expo DOM components offer a middle path: a React component
tree where selected subtrees render in an embedded WKWebView / Chrome Custom Tab, but the
parent app stays native. Pairing DOM components with a Cloudflare Workers SSR endpoint means
the initial HTML is generated at the edge, delivered with sub-50 ms TTFB to the device, then
hydrated in the embedded WebView — no round-trip to an origin server required.

---

## Context

**Expo DOM components** (introduced in Expo SDK 52 / `expo-dom` package) let you annotate a
React component file with `'use dom'` at the top. Expo's Metro bundler then builds that
component into a separate web bundle that runs inside an embedded WKWebView on iOS or
WebView on Android. The native side communicates with it via a typed bridge. DOM component
trees can import web-only libraries (Tailwind, `react-query`, markdown renderers) that would
never work in a native React Native bundle.

**Workers SSR** extends this: instead of shipping a fully client-rendered DOM component, you
pre-render the initial HTML on a Cloudflare Worker and serve it as the WebView's `source.html`
string, then hydrate the React tree in the WebView. This eliminates the blank-flash typical of
client-only DOM components, improves Largest Contentful Paint inside the embedded view, and
lets you cache article/page HTML at the edge with `Cache-Control`.

---

## Project Setup

```bash
npx create-expo-app my-app --template blank-typescript
cd my-app
npx expo install expo-dom
```

Ensure `app.json` has the web output target enabled (required even for DOM component bundling):

```json
{
  "expo": {
    "web": { "bundler": "metro" },
    "plugins": ["expo-dom"]
  }
}
```

---

## Workers SSR Endpoint

```typescript
// workers/src/ssr.ts
// Renders an article page to HTML, caches at edge, serves to DOM component.
import { renderToString } from "react-dom/server";
import { createElement } from "react";

interface Env {
  ARTICLES: KVNamespace;
}

// Lightweight in-Worker SSR — for complex trees use a Durable Object or R2-cached fragments.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const slug = url.searchParams.get("slug");

    if (!slug) return new Response("Missing slug", { status: 400 });

    const cacheKey = new Request(`https://ssr-cache.internal/${slug}`);
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    const articleJson = await env.ARTICLES.get(slug, { type: "json" }) as Article | null;
    if (!articleJson) return new Response("Not Found", { status: 404 });

    const html = buildArticleHtml(articleJson);

    const response = new Response(html, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=300, stale-while-revalidate=3600",
        "X-SSR-At": new Date().toISOString(),
      },
    });

    // Cache in Cloudflare edge for 5 minutes
    await cache.put(cacheKey, response.clone());
    return response;
  },
};

interface Article {
  title: string;
  body: string; // Markdown or safe HTML
  author: string;
  publishedAt: string;
}

function buildArticleHtml(article: Article): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(article.title)}</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; line-height: 1.6; }
    h1 { font-size: 1.5rem; margin-bottom: 8px; }
    .meta { color: #666; font-size: 0.875rem; margin-bottom: 24px; }
    .body { max-width: 680px; }
  </style>
</head>
<body>
  <h1>${escapeHtml(article.title)}</h1>
  <div class="meta">${escapeHtml(article.author)} · ${escapeHtml(article.publishedAt)}</div>
  <div class="body" id="content">${article.body}</div>
  <script>
    // Hydration hook — the DOM component's JS bundle will call this after load.
    window.__INITIAL_DATA__ = ${JSON.stringify({ title: article.title, author: article.author })};
    window.dispatchEvent(new Event('ssr-ready'));
  </script>
</body>
</html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
```

---

## Expo DOM Component with SSR Source

```tsx
// components/ArticleView.tsx
'use dom'  // ← marks this file as a DOM component

import { useEffect, useState } from 'react';

interface Props {
  slug: string;
  ssrHtml: string;  // pre-fetched on native side, injected into WebView
  dom?: import('expo/dom').DOMProps;
}

export default function ArticleView({ slug, ssrHtml }: Props) {
  const [data, setData] = useState<{ title: string; author: string } | null>(null);

  useEffect(() => {
    // Listen for the SSR-injected initial data
    const onReady = () => {
      const w = window as Window & { __INITIAL_DATA__?: { title: string; author: string } };
      if (w.__INITIAL_DATA__) setData(w.__INITIAL_DATA__);
    };

    if ((window as Window & { __INITIAL_DATA__?: unknown }).__INITIAL_DATA__) {
      onReady();
    } else {
      window.addEventListener('ssr-ready', onReady);
      return () => window.removeEventListener('ssr-ready', onReady);
    }
  }, []);

  // The SSR HTML is already in the DOM from the injected source; React hydrates over it.
  return (
    <div id="article-root">
      {data && (
        <div style={{ fontFamily: 'system-ui', padding: 16 }}>
          <h1>{data.title}</h1>
          <p style={{ color: '#666', fontSize: 14 }}>{data.author}</p>
          {/* Body was server-rendered — leave #content div alone */}
        </div>
      )}
    </div>
  );
}
```

---

## Native Screen: Fetching SSR HTML and Injecting into DOM Component

```tsx
// screens/ArticleScreen.tsx  (native React Native file — no 'use dom')
import { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import ArticleView from '../components/ArticleView';

const WORKERS_SSR = 'https://api.example.com/ssr';

export default function ArticleScreen({ slug }: { slug: string }) {
  const [ssrHtml, setSsrHtml] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`${WORKERS_SSR}?slug=${encodeURIComponent(slug)}`);
        if (!resp.ok) throw new Error(`SSR ${resp.status}`);
        const html = await resp.text();
        if (!cancelled) setSsrHtml(html);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => { cancelled = true; };
  }, [slug]);

  if (error) return <View />;  // fallback to client-only render
  if (!ssrHtml) return <ActivityIndicator style={{ flex: 1 }} />;

  return (
    <View style={{ flex: 1 }}>
      {/* expo-dom automatically wraps this in a WebView; ssrHtml seeds the source */}
      <ArticleView
        slug={slug}
        ssrHtml={ssrHtml}
        dom={{ scrollEnabled: true, matchContents: true }}
      />
    </View>
  );
}
```

---

## Passing SSR HTML into the WebView

The `expo-dom` bridge does not expose a direct `source={{ html }}` prop like bare WebView.
Instead, inject via the `dom` prop's `injectedJavaScriptBeforeContentLoaded` escape hatch or
use the `useDOM` hook to call a bridge method:

```tsx
// In the native parent — call a bridge function exposed by the DOM component:
import { useDOM } from 'expo/dom';
import ArticleView from '../components/ArticleView';

const ref = useDOM(ArticleView);

useEffect(() => {
  if (ssrHtml && ref.current) {
    ref.current.loadSSRHtml(ssrHtml);  // bridge method defined in 'use dom' file
  }
}, [ssrHtml]);
```

Bridge definition inside the `'use dom'` file:
```tsx
'use dom'
import { defineDOMBridge } from 'expo/dom';

export const { loadSSRHtml } = defineDOMBridge({
  loadSSRHtml(html: string) {
    document.open();
    document.write(html);
    document.close();
  },
});
```

---

## Anti-patterns

- **Sending large `ssrHtml` strings (>500 KB) over the JS bridge.** The bridge serialises via
  JSON; large HTML strings cause measurable frame drops. Serve small, focused fragments and
  lazy-load supplemental content inside the WebView via `fetch`.
- **Using `'use dom'` for screens that need native gestures.** The WebView intercepts touch
  events. Anything requiring swipe-back, pull-to-refresh, or `react-native-gesture-handler`
  must stay in the native tree.
- **Shipping the full React DOM + SSR runtime inside the Workers function.** Workers CPU time
  is capped at 30 ms (free) / 50 ms (paid) per subrequest. Pre-render complex pages with
  Durable Objects or cache pre-rendered fragments in R2 rather than running `renderToString`
  on every request.
- **Forgetting `Cache-Control` on SSR responses.** Without it, every app cold start makes a
  live Workers invocation. Even a 60-second cache dramatically reduces p99 latency.

---

## Gotchas

- DOM components rebuild to a separate web bundle on `expo export`. The native app embeds this
  bundle — it is NOT loaded from the network at runtime. SSR HTML comes over the network but the
  React hydration JS is bundled.
- On Android, `WebView` does not support `document.write` in some hardened configurations.
  Prefer `innerHTML` assignment on a root element over `document.write`.
- `'use dom'` files cannot import from React Native packages that require native modules. Split
  your component tree at this boundary explicitly.
- WKWebView on iOS enforces a strict Content Security Policy for local resources. If your SSR
  HTML inlines scripts, ensure `unsafe-inline` is either allowed or switch to nonce-based CSP.

---

## Verification

```bash
# Confirm Workers SSR responds with HTML
curl -s "https://api.example.com/ssr?slug=my-article" | head -20

# Check edge cache hit
curl -I "https://api.example.com/ssr?slug=my-article" | grep -i cf-cache-status

# Build Expo and verify DOM bundle exists
npx expo export --platform ios
ls dist/_expo/static/js/dom/
```

---

## Related

- `expo-modules-api-router.md` — Expo Router file-based routing
- `expo-r2-ota-workers.md` — OTA update delivery via Workers
- `ios-wkwebview-cloudflare-cookies.md` — WKWebView cookie handling
- `android-webview-cloudflare-cache-control.md` — Android WebView cache headers

---

## Sources

- https://docs.expo.dev/guides/dom-components/
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://react.dev/reference/react-dom/server/renderToString
- https://docs.expo.dev/versions/latest/sdk/dom/
