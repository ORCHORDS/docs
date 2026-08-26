# Flutter GoRouter Workers Deep Link Resolver

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Flutter app receives deep links (e.g., `https://app.example.com/share/abc123`) from marketing campaigns, email CTAs, and in-app sharing. The slug `abc123` is a short identifier that must be resolved to a full internal route (`/product/detail/42`) before navigation. Resolving on-device requires a network call; doing it inside GoRouter's `redirect` hook keeps the resolution logic in one place and prevents the app from navigating to a stale or invalid route.

## Context

`go_router` (Flutter's official routing package) supports a `redirect` callback that fires before any navigation. A Cloudflare Worker acts as the resolution backend: it stores short-link → full path mappings in KV, validates the link's expiry, and returns the resolved path (or an error slug for expired/invalid links). The Worker is also responsible for Universal Link / App Link AASA and `assetlinks.json` serving.

Resolution flow:

```
Incoming deep link URI
       ↓
GoRouter redirect callback
       ↓
Workers KV lookup (short slug → route path + metadata)
       ↓
Resolved: navigate to /product/detail/42
Not found: navigate to /link-expired
```

## Workers Short-Link Resolver

```typescript
// workers/links/index.ts
export interface Env {
  LINKS: KVNamespace; // key: slug, value: JSON { path, expiresAt, queryParams }
}

interface LinkRecord {
  path: string;
  expiresAt: number; // epoch seconds, 0 = never expires
  queryParams?: Record<string, string>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Serve AASA / assetlinks from Workers KV for App/Universal Link verification
    if (url.pathname === "/.well-known/apple-app-site-association") {
      const aasa = await env.LINKS.get("__aasa__");
      return new Response(aasa ?? "{}", {
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/.well-known/assetlinks.json") {
      const assetLinks = await env.LINKS.get("__assetlinks__");
      return new Response(assetLinks ?? "[]", {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Deep link resolution
    if (url.pathname.startsWith("/resolve/")) {
      const slug = url.pathname.slice("/resolve/".length);
      const raw = await env.LINKS.get(slug);
      if (!raw) {
        return Response.json({ error: "not_found" }, { status: 404 });
      }

      const record = JSON.parse(raw) as LinkRecord;
      if (record.expiresAt > 0 && record.expiresAt < Date.now() / 1000) {
        return Response.json({ error: "expired" }, { status: 410 });
      }

      return Response.json({
        path: record.path,
        queryParams: record.queryParams ?? {},
      });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## Seeding Links in KV

```typescript
// scripts/seedLinks.ts — run with `npx wrangler kv:key put`
// Example KV entry:
// key: "abc123"
// value: {"path":"/product/detail/42","expiresAt":0,"queryParams":{"ref":"email"}}

// Via Wrangler CLI:
// wrangler kv:key put --namespace-id=XXX "abc123" \
//   '{"path":"/product/detail/42","expiresAt":0,"queryParams":{"ref":"email"}}'
```

## Dart Link Resolver Service

```dart
// lib/services/link_resolver.dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class ResolvedLink {
  const ResolvedLink({required this.path, this.queryParams = const {}});
  final String path;
  final Map<String, String> queryParams;
}

class LinkResolver {
  static const _base = 'https://links.example.com';
  final http.Client _client;

  LinkResolver({http.Client? client}) : _client = client ?? http.Client();

  /// Returns resolved path or '/link-expired' / '/link-not-found' on error.
  Future<ResolvedLink> resolve(String slug) async {
    try {
      final res = await _client
          .get(Uri.parse('$_base/resolve/${Uri.encodeComponent(slug)}'))
          .timeout(const Duration(seconds: 5));

      if (res.statusCode == 200) {
        final body = jsonDecode(res.body) as Map<String, dynamic>;
        return ResolvedLink(
          path: body['path'] as String,
          queryParams: Map<String, String>.from(
            (body['queryParams'] as Map<String, dynamic>? ?? {}).map(
              (k, v) => MapEntry(k, v.toString()),
            ),
          ),
        );
      }
      if (res.statusCode == 410) return const ResolvedLink(path: '/link-expired');
    } catch (_) {
      // Network error — fall through to not-found
    }
    return const ResolvedLink(path: '/link-not-found');
  }
}
```

## GoRouter Configuration with Redirect

```dart
// lib/router/app_router.dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../services/link_resolver.dart';

final _resolver = LinkResolver();

GoRouter buildRouter() => GoRouter(
      initialLocation: '/home',
      redirect: (context, state) async {
        final uri = state.uri;

        // Only intercept /share/<slug> paths
        if (!uri.pathSegments.firstOrNull.equals('share')) return null;
        final slug = uri.pathSegments.elementAtOrNull(1);
        if (slug == null || slug.isEmpty) return '/link-not-found';

        final resolved = await _resolver.resolve(slug);

        // Append any query params from the resolution
        if (resolved.queryParams.isEmpty) return resolved.path;
        final resolvedUri = Uri.parse(resolved.path).replace(
          queryParameters: {
            ...Uri.parse(resolved.path).queryParameters,
            ...resolved.queryParams,
          },
        );
        return resolvedUri.toString();
      },
      routes: [
        GoRoute(path: '/home', builder: (_, __) => const HomeScreen()),
        GoRoute(
          path: '/product/detail/:id',
          builder: (_, state) => ProductDetailScreen(id: state.pathParameters['id']!),
        ),
        GoRoute(path: '/link-expired', builder: (_, __) => const LinkExpiredScreen()),
        GoRoute(path: '/link-not-found', builder: (_, __) => const LinkNotFoundScreen()),
        GoRoute(path: '/share/:slug', redirect: (_, __) async => null), // handled above
      ],
    );

extension on String? {
  bool equals(String other) => this == other;
}
```

## App Link / Universal Link Setup

```dart
// ios/Runner/Info.plist — add associated domains (handled by Xcode entitlements)
// android/app/src/main/AndroidManifest.xml
// <intent-filter android:autoVerify="true">
//   <action android:name="android.intent.action.VIEW"/>
//   <category android:name="android.intent.category.DEFAULT"/>
//   <category android:name="android.intent.category.BROWSABLE"/>
//   <data android:scheme="https" android:host="app.example.com" android:pathPrefix="/share"/>
// </intent-filter>

// main.dart — wire the incoming link to GoRouter
import 'package:app_links/app_links.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final appLinks = AppLinks();
  final router = buildRouter();

  appLinks.uriLinkStream.listen((uri) {
    router.go(uri.path + (uri.hasQuery ? '?${uri.query}' : ''));
  });

  runApp(MaterialApp.router(routerConfig: router));
}
```

## Anti-patterns

- **Resolving inside `onGenerateRoute` (Navigator 1.0)**: GoRouter's `redirect` fires declaratively before building the route tree; Navigator 1.0 `onGenerateRoute` requires manual async plumbing and breaks deep link queuing.
- **Caching resolved paths in-memory only**: if the user backgrounds the app mid-resolution, the cache is lost. Persist slug → path in `shared_preferences` or `flutter_secure_storage` for offline/re-open scenarios.
- **Exposing the KV write endpoint publicly**: seed links via `wrangler kv:key put` or a Worker secured by an admin secret, never a public unauthenticated endpoint.
- **Long-running redirect callbacks**: `redirect` blocks GoRouter navigation. Keep the timeout tight (≤ 5 s) and return a fallback path on network error.

## Gotchas

- GoRouter's `redirect` is async in go_router 13+; earlier versions are synchronous. Confirm your version before using `async`/`await` in `redirect`.
- Universal Link verification by iOS requires the AASA to be served with no redirect, `Content-Type: application/json`, and from the root domain (not a subdomain). Serving it from a Workers route at `https://app.example.com` (not `https://worker.example.com`) is mandatory.
- KV has eventual consistency (up to 60 s propagation). Newly seeded slugs may not resolve immediately at all edge PoPs. Consider using D1 for slugs that must be available instantly after creation.
- `app_links` (package) must be initialised before `runApp`; the first `uriLinkStream` event may fire before the widget tree is built if the app was cold-started from a deep link.

## Verification

```bash
# 1. Seed a test link
wrangler kv:key put --namespace-id=$LINKS_NS_ID "test99" \
  '{"path":"/product/detail/99","expiresAt":0,"queryParams":{}}'

# 2. Resolve via curl
curl https://links.example.com/resolve/test99
# {"path":"/product/detail/99","queryParams":{}}

# 3. Test Universal Link verification
curl -I https://app.example.com/.well-known/apple-app-site-association
# HTTP/2 200, Content-Type: application/json

# 4. Simulate deep link in Flutter (Android)
adb shell am start -W -a android.intent.action.VIEW \
  -d "https://app.example.com/share/test99" com.example.app
```

## Related

- `flutter-workers-deep-link-universal-redirect.md`
- `ios-workers-universal-links-aasa.md`
- `android-app-links-dynamic-rules-verification.md`
- `expo-router-workers-deep-link-handler.md`

## Sources

- https://pub.dev/packages/go_router
- https://developers.cloudflare.com/kv/
- https://pub.dev/packages/app_links
