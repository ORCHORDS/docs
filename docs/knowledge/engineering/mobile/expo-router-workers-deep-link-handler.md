# Expo Router Workers Deep Link Handler

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case
example project / example.com shares wam permalinks (`https://example.com/wam/abc123`) on social platforms.
When a recipient taps the link on mobile the app should open to the correct in-app screen; on
desktop browsers it should render a server-side preview. Managing two separate routing layers —
Expo Router for native navigation and Cloudflare Worker for web preview and redirect logic — leads
to divergent routing tables that drift out of sync and broken deep links after route renames.

## Context
Expo Router's `app/` file-based routes can be mirrored by a Cloudflare Worker that inspects the
incoming request User-Agent to decide whether to redirect to the app via Universal Link or render
an HTML Open Graph preview for bots and desktop browsers. A single source-of-truth route map
TypeScript module is shared between the Worker and the Expo app (via a shared package or a
`constants/routes.ts` file copied at build time) so route renames propagate atomically.

## Architecture — Shared Route Map
The route map is a simple TypeScript object that maps route slugs to Expo Router path patterns.
It lives in `packages/routes/src/index.ts` and is consumed by both the Worker and the Expo app.

```typescript
// packages/routes/src/index.ts
export type RouteKey =
  | 'wam'
  | 'profile'
  | 'tag'
  | 'trending';

export const ROUTE_MAP: Record<RouteKey, { expoPath: string; webPath: string }> = {
  wam:      { expoPath: '/wam/[id]',      webPath: '/wam/:id' },
  profile:  { expoPath: '/profile/[anonId]', webPath: '/profile/:anonId' },
  tag:      { expoPath: '/tag/[slug]',    webPath: '/tag/:slug' },
  trending: { expoPath: '/trending',      webPath: '/trending' },
};

export function buildExpoDeepLink(key: RouteKey, params: Record<string, string>): string {
  let path = ROUTE_MAP[key].expoPath;
  for (const [k, v] of Object.entries(params)) {
    path = path.replace(`[${k}]`, encodeURIComponent(v));
  }
  return `example project:/${path}`;  // custom scheme for Android fallback
}

export function buildUniversalLink(key: RouteKey, params: Record<string, string>): string {
  let path = ROUTE_MAP[key].webPath;
  for (const [k, v] of Object.entries(params)) {
    path = path.replace(`:${k}`, encodeURIComponent(v));
  }
  return `https://example.com${path}`;
}
```

## Workers Side — Smart Deep Link Redirect
The Worker receives every `GET /wam/*`, `/profile/*`, `/tag/*`, and `/trending` request. It
detects the client type from `User-Agent` and either serves an OG-tag HTML preview or issues a
`302` to the Universal Link URL, letting iOS / Android handle the app hand-off.

```typescript
// worker/src/deep-link-handler.ts
import { Env } from './types';
import { ROUTE_MAP } from '../../packages/routes/src'; // bundled into Worker via wrangler alias

const BOT_UA_PATTERN =
  /Twitterbot|facebookexternalhit|LinkedInBot|Slackbot|TelegramBot|Googlebot|bingbot|curl/i;

const MOBILE_UA_PATTERN = /iPhone|iPad|Android/i;

export async function handleDeepLink(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const ua = request.headers.get('User-Agent') ?? '';

  const { routeKey, params } = resolveRoute(url.pathname);
  if (!routeKey) return new Response('Not Found', { status: 404 });

  const isBot = BOT_UA_PATTERN.test(ua);
  const isMobile = MOBILE_UA_PATTERN.test(ua);

  if (isBot) {
    return serveOgPreview(routeKey, params, env);
  }

  if (isMobile) {
    // Universal Links on iOS / App Links on Android are handled by the OS;
    // we serve the same HTML with a JS fallback to custom scheme if the app
    // is not installed.
    return serveSmartBanner(routeKey, params, url.pathname);
  }

  // Desktop browser — render a web preview or redirect to web app
  return Response.redirect(`https://web.example.com${url.pathname}${url.search}`, 302);
}

function resolveRoute(
  pathname: string,
): { routeKey: keyof typeof ROUTE_MAP | null; params: Record<string, string> } {
  const segments = pathname.split('/').filter(Boolean);

  if (segments[0] === 'wam' && segments[1]) return { routeKey: 'wam', params: { id: segments[1] } };
  if (segments[0] === 'profile' && segments[1]) return { routeKey: 'profile', params: { anonId: segments[1] } };
  if (segments[0] === 'tag' && segments[1]) return { routeKey: 'tag', params: { slug: segments[1] } };
  if (segments[0] === 'trending') return { routeKey: 'trending', params: {} };

  return { routeKey: null, params: {} };
}

async function serveOgPreview(
  routeKey: keyof typeof ROUTE_MAP,
  params: Record<string, string>,
  env: Env,
): Promise<Response> {
  // Fetch wam content from D1 for OG tags
  let title = 'example project';
  let description = 'Anonymous social — example.com';

  if (routeKey === 'wam' && params.id) {
    const row = await env.DB.prepare('SELECT content FROM wams WHERE id = ?1')
      .bind(params.id)
      .first<{ content: string }>();
    if (row) {
      title = row.content.slice(0, 60);
      description = row.content.slice(0, 160);
    }
  }

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${escHtml(title)}</title>
  <meta property="og:title" content="${escHtml(title)}">
  <meta property="og:description" content="${escHtml(description)}">
  <meta property="og:image" content="https://example.com/og-default.png">
  <meta name="twitter:card" content="summary">
</head>
<body><p>${escHtml(description)}</p></body>
</html>`;

  return new Response(html, { headers: { 'Content-Type': 'text/html;charset=UTF-8' } });
}

function serveSmartBanner(
  routeKey: keyof typeof ROUTE_MAP,
  params: Record<string, string>,
  pathname: string,
): Promise<Response> {
  const customSchemeUrl = buildCustomScheme(routeKey, params);
  const universalUrl = `https://example.com${pathname}`;

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Opening example project…</title>
  <meta name="apple-itunes-app" content="app-id=YOUR_APP_ID, app-argument=${universalUrl}">
</head>
<body>
<script>
  window.location.href = '${customSchemeUrl}';
  setTimeout(function () {
    window.location.href = 'https://example.com/download';
  }, 2500);
</script>
<p>Opening the example project app…</p>
</body>
</html>`;

  return Promise.resolve(new Response(html, { headers: { 'Content-Type': 'text/html;charset=UTF-8' } }));
}

function buildCustomScheme(routeKey: keyof typeof ROUTE_MAP, params: Record<string, string>): string {
  let path = ROUTE_MAP[routeKey].webPath;
  for (const [k, v] of Object.entries(params)) path = path.replace(`:${k}`, encodeURIComponent(v));
  return `example project:/${path}`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

## Expo Router Side — Universal Link and Custom Scheme Handling
Expo Router handles Universal Links via the `scheme` and `associatedDomains` fields in `app.json`.
The `app/wam/[id].tsx` route receives the `id` param automatically when iOS / Android opens the
app via either mechanism.

```typescript
// app/wam/[id].tsx
import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

type Wam = { id: string; content: string };

export default function WamScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [wam, setWam] = useState<Wam | null>(null);

  useEffect(() => {
    if (!id) return;
    fetch(`https://api.example.com/wam/${id}`)
      .then((r) => r.json() as Promise<Wam>)
      .then(setWam)
      .catch(console.error);
  }, [id]);

  if (!wam) return <View><Text>Loading…</Text></View>;
  return <View><Text>{wam.content}</Text></View>;
}
```

```json
// app.json (relevant excerpt)
{
  "expo": {
    "scheme": "example project",
    "ios": {
      "associatedDomains": ["applinks:example.com"]
    },
    "android": {
      "intentFilters": [
        {
          "action": "VIEW",
          "autoVerify": true,
          "data": [{ "scheme": "https", "host": "example.com" }],
          "category": ["BROWSABLE", "DEFAULT"]
        }
      ]
    }
  }
}
```

## Apple App Site Association and Android Asset Links
The Worker also serves the `/.well-known/apple-app-site-association` and
`/.well-known/assetlinks.json` files needed for OS-level deep link verification.

```typescript
// worker/src/well-known.ts
export function handleWellKnown(request: Request): Response {
  const url = new URL(request.url);

  if (url.pathname === '/.well-known/apple-app-site-association') {
    return Response.json({
      applinks: {
        apps: [],
        details: [{ appID: 'TEAMID.app.example project', paths: ['/wam/*', '/profile/*', '/tag/*', '/trending'] }],
      },
    });
  }

  if (url.pathname === '/.well-known/assetlinks.json') {
    return Response.json([{
      relation: ['delegate_permission/common.handle_all_urls'],
      target: { namespace: 'android_app', package_name: 'app.example project', sha256_cert_fingerprints: ['AA:BB:...'] },
    }]);
  }

  return new Response('Not Found', { status: 404 });
}
```

## Anti-patterns
- Hard-coding route strings in both the Worker and the Expo app separately — they will drift; use
  the shared `ROUTE_MAP` module.
- Redirecting mobile browsers directly to `example project://` without the smart banner fallback — if the
  app is not installed the custom scheme silently fails with no recovery path.
- Serving OG preview HTML for authenticated/private wams without checking visibility — bots should
  receive a generic preview or `noindex` for private content.
- Forgetting to serve `/.well-known/apple-app-site-association` from the Worker — iOS fetches it
  during first install; a 404 means Universal Links are disabled.

## Gotchas
- Android App Links verification (`autoVerify: true`) requires the `assetlinks.json` to be
  reachable over HTTPS within 20 seconds at install time; Cloudflare's edge latency is fine but
  the file must be returned with `Content-Type: application/json`.
- `expo-router` `useLocalSearchParams` returns `string | string[]`; always narrow to `string`
  before using as an API param.
- The `apple-itunes-app` meta tag smart banner requires a real App Store app-id — use it only
  after the app is published.
- Bot detection by `User-Agent` is imperfect; supplement with Cloudflare Bot Management or a
  `?_preview=1` query param for preview testing.

## Verification
1. `curl -A "Twitterbot/1.0" https://example.com/wam/test123` — expect OG HTML with correct title.
2. `curl -A "iPhone" https://example.com/wam/test123` — expect smart-banner HTML with `example project:/wam/test123` in JS.
3. On an iOS device with the app installed, tap a `https://example.com/wam/test123` link — app
   should open to the `WamScreen` with `id = "test123"`.
4. Verify `/.well-known/apple-app-site-association` returns valid JSON: `curl https://example.com/.well-known/apple-app-site-association | jq .`.

## Related
- `/documentation/docs/policies/mobile/expo-router-file-based-routing-deep-linking.md`
- `/documentation/docs/policies/mobile/deep-linking-universal-app-links.md`
- `/documentation/docs/policies/mobile/cloudflare-workers-deep-link-redirect.md`
- `/documentation/docs/policies/mobile/ios-universal-links.md`

## Sources
- https://docs.expo.dev/router/introduction/
- https://developers.cloudflare.com/workers/
- https://developer.android.com/training/app-links/verify-android-applinks
- https://developer.apple.com/documentation/bundleresources/applinks
