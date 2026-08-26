# Flutter Workers Deep Link Universal Redirect

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Flutter app needs to handle deep links (`myapp://` custom scheme) and universal links / App Links (`https://` verified domain) from sources such as email campaigns, QR codes, and social shares. The link destination and any auth tokens embedded in the URL must be resolved server-side before the app receives them, supporting A/B redirect logic, expiring links, and tracking — all without a custom backend beyond a Cloudflare Worker.

## Context

Flutter uses `go_router` or `uni_links` for in-app navigation. The challenge is coordinating two platforms (iOS Universal Links, Android App Links) with a single Cloudflare Worker that: (1) serves the Apple App Site Association (AASA) and Digital Asset Links (DAL) files from the correct paths, (2) handles redirect logic (expiry, A/B test, geo), and (3) falls back to the App Store / Play Store for users without the app. KV stores the link metadata; Analytics Engine tracks click events.

---

## Worker: Serve AASA and Digital Asset Links

```typescript
// workers/deep-link.ts
interface Env {
  LINK_STORE: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
  APPLE_TEAM_ID: string;
  ANDROID_SHA256: string;
  APP_ID_SUFFIX: string;  // e.g. "com.example.myapp"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // iOS Universal Links verification file
    if (url.pathname === '/.well-known/apple-app-site-association') {
      return Response.json({
        applinks: {
          details: [
            {
              appIDs: [`${env.APPLE_TEAM_ID}.${env.APP_ID_SUFFIX}`],
              components: [
                { '/': '/l/*', comment: 'Short links' },
                { '/': '/invite/*', comment: 'Invite flows' },
              ],
            },
          ],
        },
      }, {
        headers: {
          'Content-Type': 'application/json',
          // Must not be cached too aggressively — Apple re-fetches periodically
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }

    // Android App Links verification file
    if (url.pathname === '/.well-known/assetlinks.json') {
      return Response.json([
        {
          relation: ['delegate_permission/common.handle_all_urls'],
          target: {
            namespace: 'android_app',
            package_name: env.APP_ID_SUFFIX,
            sha256_cert_fingerprints: [env.ANDROID_SHA256],
          },
        },
      ], {
        headers: { 'Cache-Control': 'public, max-age=3600' },
      });
    }

    // Short link resolution: /l/{code}
    const match = url.pathname.match(/^\/l\/([a-zA-Z0-9_-]+)$/);
    if (match) {
      return handleShortLink(match[1], request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handleShortLink(
  code: string,
  request: Request,
  env: Env
): Promise<Response> {
  const raw = await env.LINK_STORE.get(`link:${code}`, 'json') as LinkMeta | null;

  if (!raw) return new Response('Link not found', { status: 404 });

  const now = Date.now();
  if (raw.expiresAt && raw.expiresAt < now) {
    return new Response('Link expired', { status: 410 });
  }

  // Analytics: fire-and-forget
  env.ANALYTICS.writeDataPoint({
    blobs: [code, request.headers.get('User-Agent') ?? ''],
    doubles: [1],
    indexes: [code],
  });

  // Determine if request comes from a crawler / share preview
  const ua = request.headers.get('User-Agent') ?? '';
  const isCrawler = /facebookexternalhit|Twitterbot|LinkedInBot|WhatsApp/i.test(ua);
  if (isCrawler) {
    return new Response(buildOGPage(raw), {
      headers: { 'Content-Type': 'text/html' },
    });
  }

  // Build deep-link URI for the Flutter app
  const deepLink = `${raw.scheme}://${raw.path}?ref=${code}`;
  const fallback = raw.platform === 'ios' ? raw.appStoreUrl : raw.playStoreUrl;

  // Redirect: browser tries the custom scheme; JS falls back to store
  return new Response(buildRedirectPage(deepLink, fallback ?? raw.webFallback), {
    headers: { 'Content-Type': 'text/html' },
  });
}

interface LinkMeta {
  scheme: string;
  path: string;
  expiresAt?: number;
  platform?: 'ios' | 'android';
  appStoreUrl?: string;
  playStoreUrl?: string;
  webFallback: string;
  ogTitle?: string;
  ogDescription?: string;
  ogImage?: string;
}

function buildRedirectPage(deepLink: string, fallback: string): string {
  return `<!DOCTYPE html><html><head>
<meta http-equiv="refresh" content="2;url=${fallback}">
<script>
  window.location = ${JSON.stringify(deepLink)};
  setTimeout(() => { window.location = ${JSON.stringify(fallback)}; }, 1500);
</script></head><body></body></html>`;
}

function buildOGPage(meta: LinkMeta): string {
  return `<!DOCTYPE html><html><head>
<meta property="og:title" content="${meta.ogTitle ?? ''}">
<meta property="og:description" content="${meta.ogDescription ?? ''}">
<meta property="og:image" content="${meta.ogImage ?? ''}">
</head><body></body></html>`;
}
```

---

## Flutter: Handle Incoming Deep Links with go_router

```dart
// lib/router.dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:uni_links/uni_links.dart';

GoRouter buildRouter() {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
      GoRoute(
        path: '/invite/:code',
        builder: (context, state) => InviteScreen(
          code: state.pathParameters['code']!,
          ref: state.uri.queryParameters['ref'],
        ),
      ),
      GoRoute(
        path: '/share/:id',
        builder: (context, state) => ShareScreen(id: state.pathParameters['id']!),
      ),
    ],
  );
}
```

```dart
// lib/app.dart
import 'package:flutter/material.dart';
import 'package:uni_links/uni_links.dart';
import 'router.dart';

class App extends StatefulWidget {
  const App({super.key});
  @override
  State<App> createState() => _AppState();
}

class _AppState extends State<App> {
  late final GoRouter _router = buildRouter();

  @override
  void initState() {
    super.initState();
    _handleInitialLink();
    uriLinkStream.listen(_handleLink);
  }

  Future<void> _handleInitialLink() async {
    final uri = await getInitialUri();
    if (uri != null) _handleLink(uri);
  }

  void _handleLink(Uri? uri) {
    if (uri == null) return;
    // Convert custom scheme to router path
    // myapp://invite/ABC?ref=xyz  →  /invite/ABC?ref=xyz
    _router.go('/${uri.host}${uri.path}', extra: uri.queryParameters);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(routerConfig: _router);
  }
}
```

---

## Create Short Link via Worker API

```typescript
// POST /admin/links (authenticated endpoint, add auth middleware)
async function createLink(request: Request, env: Env): Promise<Response> {
  const body = await request.json<Omit<LinkMeta, 'scheme'> & { ttlSeconds?: number }>();
  const code = crypto.randomUUID().slice(0, 8);
  const meta: LinkMeta = {
    scheme: 'myapp',
    ...body,
    expiresAt: body.ttlSeconds ? Date.now() + body.ttlSeconds * 1000 : undefined,
  };
  await env.LINK_STORE.put(`link:${code}`, JSON.stringify(meta), {
    expirationTtl: body.ttlSeconds,
  });
  return Response.json({ code, url: `https://links.example.com/l/${code}` });
}
```

---

## Android Manifest Configuration

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<activity android:name=".MainActivity" android:launchMode="singleTask">
  <!-- Custom scheme -->
  <intent-filter>
    <action android:name="android.intent.action.VIEW"/>
    <category android:name="android.intent.category.DEFAULT"/>
    <category android:name="android.intent.category.BROWSABLE"/>
    <data android:scheme="myapp"/>
  </intent-filter>
  <!-- App Links (https) — requires assetlinks.json served by Worker -->
  <intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW"/>
    <category android:name="android.intent.category.DEFAULT"/>
    <category android:name="android.intent.category.BROWSABLE"/>
    <data android:scheme="https" android:host="links.example.com"
          android:pathPrefix="/l/"/>
  </intent-filter>
</activity>
```

---

## Anti-patterns

- **Serving AASA from a CDN with aggressive caching** — Apple's CDN pre-fetches AASA on first install; stale content means Universal Links stop working for all new installs until the cache expires.
- **Embedding auth tokens in the deep link path** — paths are logged by proxies and visible in analytics; use short-lived opaque codes resolved server-side in the Worker instead.
- **Skipping the crawler / OG preview branch** — WhatsApp and Slack unfurl the first URL they see; without an OG fallback page, shares show a blank preview.
- **Using a 301 permanent redirect from the Worker** — Cloudflare and browsers cache 301s; use 302 for all short-link redirects.

---

## Gotchas

- AASA must be served without a redirect at `/.well-known/apple-app-site-association`. Serving it at the root and redirecting breaks iOS verification.
- `uni_links` does not work in Flutter Web; guard with `kIsWeb` and use `window.location` parsing instead.
- Android App Links verification can take up to 20 seconds on first launch; always implement the custom-scheme fallback so links work during verification.
- Workers KV has eventual consistency — a newly created short link may not be readable for ~60 ms on edge nodes far from the write node. For zero-lag needs, use a Durable Object for link storage.

---

## Verification

```bash
# Verify AASA is valid JSON and well-formed
curl -s https://links.example.com/.well-known/apple-app-site-association | python3 -m json.tool

# Verify Android asset links
curl -s https://links.example.com/.well-known/assetlinks.json | python3 -m json.tool

# Test short link resolution
curl -L -A "Mozilla/5.0" https://links.example.com/l/abc123
```

---

## Related

- `cloudflare-workers-deep-link-redirect.md`
- `expo-router-workers-deep-link-handler.md`
- `ios-workers-universal-links-aasa.md`
- `android-app-links-dynamic-rules-verification.md`
- `mobile-deep-link-hijacking.md`

---

## Sources

- Apple Universal Links AASA format: https://developer.apple.com/documentation/xcode/supporting-associated-domains
- Android App Links: https://developer.android.com/training/app-links/verify-android-applinks
- uni_links Flutter package: https://pub.dev/packages/uni_links
- go_router: https://pub.dev/packages/go_router
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
