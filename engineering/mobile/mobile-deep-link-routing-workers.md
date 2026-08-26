# Universal Link / Deep Link Routing Worker for iOS and Android

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You need a single Cloudflare Worker to serve the iOS `apple-app-site-association` (AASA) and Android `assetlinks.json` files that enable universal/app links, and to perform smart routing: when a user opens a web URL on a mobile device that has the app installed the OS intercepts the request and opens the app directly; otherwise the Worker redirects to the App Store or Play Store. Routing rules (path patterns → app scheme deeplinks) are stored in KV for fast, codeless updates.

---

## Context
Apple and Google both require a JSON file hosted at a well-known path on your domain before they will intercept links and open your app. The AASA file must be served without redirects and with `Content-Type: application/json`. The Worker also handles the runtime redirect: it inspects the `User-Agent` header to distinguish iOS from Android, looks up the path in a KV routing table, constructs the app-scheme URL, and emits a redirect. If no rule matches, or the user is on desktop, it falls through to the web site. Because Workers run at the edge, the AASA/assetlinks files are served with sub-millisecond latency globally, eliminating the Apple CDN verification delays common with origin servers.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "deeplink-router"
main = "src/router.ts"
compatibility_date = "2024-09-23"

[[kv_namespaces]]
binding = "ROUTES"
id = "<YOUR_KV_NAMESPACE_ID>"

[vars]
IOS_APP_SCHEME   = "orchords"
ANDROID_PACKAGE  = "com.orchords.app"
APP_STORE_URL    = "https://apps.apple.com/app/example-org/example-repo"
PLAY_STORE_URL   = "https://play.google.com/store/apps/details?id=com.orchords.app"
WEB_FALLBACK_URL = "https://example.com"
```

```json
// KV key: "routes" — value: JSON array of routing rules
// Upload via: wrangler kv key put --namespace-id=<id> routes "$(cat routes.json)"
[
  { "pattern": "/songs/:id",   "appPath": "/songs/:id" },
  { "pattern": "/albums/:id",  "appPath": "/albums/:id" },
  { "pattern": "/artists/:id", "appPath": "/artists/:id" },
  { "pattern": "/invite/:code","appPath": "/invite/:code" }
]
```

```json
// apple-app-site-association (store as KV key "aasa" or serve inline)
{
  "applinks": {
    "details": [{
      "appIDs": ["TEAMID.com.orchords.app"],
      "components": [
        { "/": "/songs/*" },
        { "/": "/albums/*" },
        { "/": "/artists/*" },
        { "/": "/invite/*" }
      ]
    }]
  },
  "activitycontinuation": { "apps": ["TEAMID.com.orchords.app"] },
  "webcredentials":       { "apps": ["TEAMID.com.orchords.app"] }
}
```

---

## Section 2 — Worker implementation

```typescript
// src/router.ts
export interface Env {
  ROUTES: KVNamespace;
  IOS_APP_SCHEME: string;
  ANDROID_PACKAGE: string;
  APP_STORE_URL: string;
  PLAY_STORE_URL: string;
  WEB_FALLBACK_URL: string;
}

interface RouteRule {
  pattern: string; // e.g. "/songs/:id"
  appPath: string; // e.g. "/songs/:id" — same tokens used
}

// Minimal path-pattern matcher returning the filled appPath or null
function matchRoute(
  pathname: string,
  rules: RouteRule[]
): string | null {
  for (const rule of rules) {
    const patternParts = rule.pattern.split('/');
    const pathParts = pathname.split('/');
    if (patternParts.length !== pathParts.length) continue;

    const params: Record<string, string> = {};
    let match = true;
    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i].startsWith(':')) {
        params[patternParts[i].slice(1)] = pathParts[i];
      } else if (patternParts[i] !== pathParts[i]) {
        match = false;
        break;
      }
    }
    if (!match) continue;

    // Fill params into appPath
    let appPath = rule.appPath;
    for (const [k, v] of Object.entries(params)) {
      appPath = appPath.replace(`:${k}`, encodeURIComponent(v));
    }
    return appPath;
  }
  return null;
}

function detectPlatform(ua: string): 'ios' | 'android' | 'other' {
  if (/iPhone|iPad|iPod/.test(ua)) return 'ios';
  if (/Android/.test(ua)) return 'android';
  return 'other';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const { pathname } = url;

    // ── well-known files ─────────────────────────────────────────────────
    if (
      pathname === '/.well-known/apple-app-site-association' ||
      pathname === '/apple-app-site-association'
    ) {
      const aasa = await env.ROUTES.get('aasa', { cacheTtl: 3600 });
      if (!aasa) return new Response('not found', { status: 404 });
      return new Response(aasa, {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }

    if (pathname === '/.well-known/assetlinks.json') {
      const links = JSON.stringify([{
        relation: ['delegate_permission/common.handle_all_urls'],
        target: {
          namespace: 'android_app',
          package_name: env.ANDROID_PACKAGE,
          sha256_cert_fingerprints: [
            // Replace with your actual SHA-256 fingerprints
            'AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99'
          ],
        },
      }]);
      return new Response(links, {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }

    // ── smart redirect ───────────────────────────────────────────────────
    const rulesRaw = await env.ROUTES.get('routes', { cacheTtl: 60 });
    const rules: RouteRule[] = rulesRaw ? JSON.parse(rulesRaw) : [];
    const appPath = matchRoute(pathname, rules);

    if (!appPath) {
      // No rule — pass through to web
      return Response.redirect(`${env.WEB_FALLBACK_URL}${pathname}${url.search}`, 302);
    }

    const ua = request.headers.get('User-Agent') ?? '';
    const platform = detectPlatform(ua);

    if (platform === 'ios') {
      // Attempt to open the app; fall back to App Store after a timeout
      // The Worker cannot know if the app is installed — emit an interstitial
      // or just redirect to the custom scheme (works if app is installed,
      // otherwise iOS shows an error).
      // Better UX: serve an HTML page that tries the scheme, then falls back.
      const schemeUrl = `${env.IOS_APP_SCHEME}:/${appPath}${url.search}`;
      return new Response(
        deeplinkHtml(schemeUrl, env.APP_STORE_URL),
        { headers: { 'Content-Type': 'text/html;charset=UTF-8' } }
      );
    }

    if (platform === 'android') {
      const intentUrl =
        `intent:/${appPath}${url.search}#Intent;` +
        `scheme=${env.IOS_APP_SCHEME};` +
        `package=${env.ANDROID_PACKAGE};` +
        `S.browser_fallback_url=${encodeURIComponent(env.PLAY_STORE_URL)};end`;
      return Response.redirect(intentUrl, 302);
    }

    // Desktop — redirect to web
    return Response.redirect(`${env.WEB_FALLBACK_URL}${pathname}${url.search}`, 302);
  },
};

function deeplinkHtml(schemeUrl: string, fallback: string): string {
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Opening app...</title></head><body>
<script>
  window.location = ${JSON.stringify(schemeUrl)};
  setTimeout(function(){
    window.location = ${JSON.stringify(fallback)};
  }, 2500);
</script>
<p>Opening the Orchords app&hellip; <a >Download from App Store</a></p>
</body></html>`;
}
```

---

## Section 3 — Client-side (React Native / Expo)

```typescript
// app/_layout.tsx (Expo Router)
import { useEffect } from 'react';
import { Linking } from 'react-native';
import { useRouter } from 'expo-router';
import * as Linking2 from 'expo-linking';

export default function RootLayout() {
  const router = useRouter();

  useEffect(() => {
    // Handle cold-start deep link
    Linking2.getInitialURL().then((url) => {
      if (url) handleDeepLink(url, router);
    });

    // Handle foreground deep link
    const sub = Linking.addEventListener('url', ({ url }) => {
      handleDeepLink(url, router);
    });
    return () => sub.remove();
  }, []);

  return <Slot />;
}

function handleDeepLink(url: string, router: ReturnType<typeof useRouter>) {
  const parsed = Linking2.parse(url);
  if (!parsed.path) return;

  // Map path to Expo Router screen
  const [, resource, id] = parsed.path.split('/');
  const routes: Record<string, string> = {
    songs: '/(tabs)/songs/[id]',
    albums: '/(tabs)/albums/[id]',
    artists: '/(tabs)/artists/[id]',
    invite: '/invite/[code]',
  };
  const screen = routes[resource];
  if (screen) router.push({ pathname: screen as any, params: { id } });
}
```

---

## Anti-patterns
- **Serving the AASA file with an HTTP redirect** — Apple's CDN will refuse to follow redirects for AASA; the file must be served with a 200 directly from the canonical domain.
- **Caching the AASA file too aggressively on the client** — Apple re-validates the AASA file approximately every 7 days; frequent structural changes should be rolled out with a grace period.
- **Hardcoding SHA-256 fingerprints** — keep them in KV or a secret so you can rotate them without a Worker redeploy.
- **Redirecting directly to the custom scheme on iOS** — iOS will show an error alert if the app is not installed; always use the interstitial HTML page with a timed fallback.

---

## Gotchas
- Apple requires the AASA file to be served from the root domain or a subdomain listed in the entitlement; a Worker on a `*.workers.dev` subdomain will not work — attach a custom domain.
- The `sha256_cert_fingerprints` for Android must be the SHA-256 of the *signing* certificate (upload key for Play Store, debug key for development); they are different keys.
- Android intent URLs do not work in all browsers; Chrome supports them, but Safari on Android and some in-app WebViews do not.
- KV `cacheTtl` in the `get` call means the value is cached at the edge for up to that many seconds; after a routing rule update, changes propagate within the next 60 seconds.

---

## Verification
```bash
# Store AASA in KV
wrangler kv key put --namespace-id=<id> aasa "$(cat apple-app-site-association.json)"

# Store routes in KV
wrangler kv key put --namespace-id=<id> routes "$(cat routes.json)"

# Deploy
npx wrangler deploy

# Verify AASA is served correctly
curl -si https://example.com/.well-known/apple-app-site-association \
  | head -20

# Verify assetlinks
curl -s https://example.com/.well-known/assetlinks.json | jq .

# Test smart redirect (iOS UA)
curl -si https://example.com/songs/abc123 \
  -H 'User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'
```

---

## Related
- `react-native-expo-cloudflare-workers-api.md`
- `workers-ai-mobile-image-captioning.md`

---

## Sources
- Apple Universal Links — https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- Android App Links — https://developer.android.com/training/app-links/verify-android-applinks
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
