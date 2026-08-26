# Mobile Deep Link Handling: Universal Links (iOS) and App Links (Android) with Cloudflare Workers Redirect Logic

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

You need `https://example.com/orders/ORD-123` to open the native app on both iOS and Android when the app is installed, and to fall back gracefully to your website when it is not. Your existing deep-link setup uses a static file server to host `.well-known/apple-app-site-association` and `.well-known/assetlinks.json`, but the files are stale when you add a new app or team ID. You want the association files to be dynamic and the redirect fallback to be programmable — rewriting paths, A/B testing deep-link targets, and logging resolution outcomes — all without touching your origin server.

---

## Context

iOS Universal Links and Android App Links both require a JSON file hosted at a specific `.well-known/` path of your domain, served over HTTPS, with correct `Content-Type` and without a redirect on that path. A Cloudflare Worker is the ideal host:

- Zero-downtime updates (deploy a new Worker version, the JSON is live instantly).
- Programmable fallback: if the OS doesn't open the app, the Worker decides whether to redirect to the web app, the App Store, or a campaign landing page.
- Analytics: log every resolution request to Workers Analytics Engine or R2.
- No origin server involvement for these paths.

---

## 1. Serving the Association Files

```typescript
// workers/deep-link/src/index.ts
export interface Env {
  ASSOCIATION_CONFIG: KVNamespace;   // stores the JSON blobs, hot-reloadable
  ANALYTICS: AnalyticsEngineDataset; // optional — Workers Analytics Engine
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/.well-known/apple-app-site-association") {
      return serveAAAS(env);
    }

    if (url.pathname === "/.well-known/assetlinks.json") {
      return serveAssetLinks(env);
    }

    // Deep-link fallback router
    return handleDeepLinkFallback(request, env);
  },
};

async function serveAAAS(env: Env): Promise<Response> {
  const raw = await env.ASSOCIATION_CONFIG.get("apple-app-site-association");
  if (!raw) {
    return new Response("Not configured", { status: 503 });
  }

  return new Response(raw, {
    headers: {
      // Must be application/json — not application/pkcs7-mime for modern iOS
      "Content-Type": "application/json",
      // Must NOT redirect — iOS fetches this without following redirects
      "Cache-Control": "public, max-age=3600",
      // Required: no CDN redirect chains on this path
      "CF-Cache-Status": "BYPASS",
    },
  });
}

async function serveAssetLinks(env: Env): Promise<Response> {
  const raw = await env.ASSOCIATION_CONFIG.get("assetlinks.json");
  if (!raw) {
    return new Response("Not configured", { status: 503 });
  }

  return new Response(raw, {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
```

---

## 2. Association File Formats

Store these in KV via a deploy script or the Cloudflare dashboard.

### `apple-app-site-association`

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID1234.com.example.app", "TEAMID1234.com.example.app.beta"],
        "components": [
          { "/": "/orders/*", "comment": "Order detail pages" },
          { "/": "/profile/*" },
          { "/": "/invite/*", "?": { "code": "?*" }, "comment": "Invite links with query param" },
          { "/": "/reset-password", "comment": "Password reset" },
          {
            "/": "/*",
            "exclude": true,
            "comment": "Exclude everything else — fall through to web"
          }
        ]
      }
    ]
  },
  "webcredentials": {
    "apps": ["TEAMID1234.com.example.app"]
  }
}
```

### `assetlinks.json`

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.example.app",
      "sha256_cert_fingerprints": [
        "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"
      ]
    }
  }
]
```

Upload via the Wrangler CLI during your CI pipeline:

```bash
# In CI after updating team IDs or package names
wrangler kv:key put --binding ASSOCIATION_CONFIG \
  "apple-app-site-association" "$(cat aasa.json)"

wrangler kv:key put --binding ASSOCIATION_CONFIG \
  "assetlinks.json" "$(cat assetlinks.json)"
```

---

## 3. Programmable Fallback Router

When the OS cannot open the app (not installed, path excluded), the user lands on the Worker fallback handler. This replaces a static redirect:

```typescript
// workers/deep-link/src/fallback.ts
import type { Env } from "./index";

interface RouteRule {
  pattern: string;       // regex string
  iosStore: string;      // App Store URL
  androidStore: string;  // Play Store URL
  webFallback: string;   // relative URL on the web app
  campaign?: string;     // UTM campaign tag
}

const ROUTE_RULES: RouteRule[] = [
  {
    pattern: "^/orders/(.+)$",
    iosStore: "https://apps.apple.com/app/id123456789",
    androidStore: "https://play.google.com/store/apps/details?id=com.example.app",
    webFallback: "/orders/$1",
    campaign: "deeplink_order",
  },
  {
    pattern: "^/invite/(.+)$",
    iosStore: "https://apps.apple.com/app/id123456789",
    androidStore: "https://play.google.com/store/apps/details?id=com.example.app",
    webFallback: "/invite/$1",
    campaign: "deeplink_invite",
  },
];

export async function handleDeepLinkFallback(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const ua = request.headers.get("User-Agent") ?? "";

  const isIOS = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);

  for (const rule of ROUTE_RULES) {
    const match = url.pathname.match(new RegExp(rule.pattern));
    if (!match) continue;

    // Log the resolution event
    env.ANALYTICS?.writeDataPoint({
      blobs: [url.pathname, isIOS ? "ios" : isAndroid ? "android" : "web"],
      indexes: [rule.campaign ?? "unknown"],
    });

    // Build the web fallback URL with UTM params
    const webPath = url.pathname.replace(
      new RegExp(rule.pattern),
      rule.webFallback
    );
    const webUrl = new URL(webPath, "https://example.com");
    webUrl.searchParams.set("utm_source", "deeplink");
    webUrl.searchParams.set("utm_medium", "fallback");
    if (rule.campaign) webUrl.searchParams.set("utm_campaign", rule.campaign);

    if (isIOS) {
      // Attempt universal link via JS bridge, fall back to App Store
      return renderDeferredRedirect(
        request.url,
        rule.iosStore,
        webUrl.toString()
      );
    }
    if (isAndroid) {
      return renderDeferredRedirect(
        request.url,
        rule.androidStore,
        webUrl.toString()
      );
    }

    // Desktop / unknown — go straight to web
    return Response.redirect(webUrl.toString(), 302);
  }

  // No rule matched — send to home
  return Response.redirect("https://example.com", 302);
}

/**
 * Renders an HTML page that tries to open the native app first,
 * then falls back to the store URL after a timeout.
 */
function renderDeferredRedirect(
  deepLinkUrl: string,
  storeUrl: string,
  webFallback: string
): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Opening app…</title>
  <style>
    body { font-family: system-ui; text-align: center; padding: 3rem 1rem; }
    a { color: #0066cc; }
  </style>
</head>
<body>
  <p>Opening the app…</p>
  <p><small><a >Continue in browser instead</a></small></p>
  <script>
    (function () {
      var started = Date.now();
      // Try the deep link
      window.location.href = ${JSON.stringify(deepLinkUrl)};

      // If the app opens, the page is backgrounded — visibilitychange fires
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) return; // app opened, user came back
      });

      // After 2s, if still here, go to the store
      setTimeout(function () {
        if (Date.now() - started < 3000) {
          window.location.replace(${JSON.stringify(storeUrl)});
        }
      }, 2000);
    })();
  </script>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
```

---

## 4. Cloudflare Cache Rules for `.well-known/` Paths

Add a Cache Rule in the Cloudflare dashboard (or via Terraform) to bypass the CDN cache for association files so updates propagate immediately:

```terraform
resource "cloudflare_ruleset" "deep_link_cache" {
  zone_id = var.zone_id
  name    = "Deep link cache rules"
  kind    = "zone"
  phase   = "http_response_headers_transform"

  rules {
    action = "rewrite"
    action_parameters {
      headers {
        name      = "Cache-Control"
        operation = "set"
        value     = "no-store"
      }
    }
    expression  = "(http.request.uri.path eq \"/.well-known/apple-app-site-association\") or (http.request.uri.path eq \"/.well-known/assetlinks.json\")"
    description = "No cache on association files"
    enabled     = true
  }
}
```

---

## 5. React Native: Handling Incoming Deep Links

On the native side, register the URL handler in `App.tsx`:

```typescript
// App.tsx (React Native)
import { useEffect } from "react";
import { Linking } from "react-native";
import { useNavigation } from "@react-navigation/native";

export function useDeepLinkHandler() {
  const navigation = useNavigation();

  useEffect(() => {
    // Handle link that opened the app from cold start
    Linking.getInitialURL().then((url) => {
      if (url) handleUrl(url, navigation);
    });

    // Handle links while app is already running
    const sub = Linking.addEventListener("url", ({ url }) =>
      handleUrl(url, navigation)
    );
    return () => sub.remove();
  }, [navigation]);
}

function handleUrl(url: string, navigation: ReturnType<typeof useNavigation>) {
  const { pathname, searchParams } = new URL(url);

  if (pathname.startsWith("/orders/")) {
    const orderId = pathname.split("/")[2];
    // @ts-ignore navigation type
    navigation.navigate("OrderDetail", { orderId });
    return;
  }

  if (pathname.startsWith("/invite/")) {
    const code = searchParams.get("code");
    // @ts-ignore
    navigation.navigate("InviteAccept", { code });
    return;
  }
}
```

---

## Anti-Patterns

- **Redirecting the `.well-known/` paths.** iOS fetches the AASA file without following HTTP 3xx redirects. Serving a redirect from that path silently breaks Universal Links.
- **Serving the AASA file with the wrong MIME type.** The file must be `application/json`. `text/plain` works on some iOS versions but is not guaranteed.
- **Including a file extension** in the path (`apple-app-site-association.json`). The OS fetches the exact path `/.well-known/apple-app-site-association` with no extension.
- **Wildcard exclusions after wildcard inclusions in the wrong order.** AASA components are evaluated in order — put specific inclusions before the `"exclude": true` wildcard.
- **Using `window.location.href` for the deferred redirect on Android Chrome.** Chrome 120+ blocks deferred custom-scheme navigation if the user hasn't interacted with the page. Use an `<a>` element with a simulated click instead, or rely on the Intent URL scheme.

---

## Gotchas

- **iOS caches the AASA file for up to 24 hours.** Even with `Cache-Control: no-store`, a device that already fetched the file will not re-fetch it until the next OS-level check cycle. After updating the file, existing installs may take up to 24 hours to honour the new rules.
- **Android `.well-known/assetlinks.json` must be served without authentication.** A Worker that checks an `Authorization` header on this path will break App Links.
- **SHA-256 fingerprint in `assetlinks.json` changes per signing key.** Maintain separate entries for debug (Play Internal Sharing) and release keystore fingerprints.
- **Cloudflare Orange-Clouding.** If the domain is proxied through Cloudflare, the Worker is at the edge. If the domain is DNS-only, the Worker is not in the path. Ensure the relevant hostname is proxied (orange cloud enabled) in the DNS settings.
- **Rate limiting the fallback page.** A link-in-bio that goes viral can hit hundreds of thousands of hits per minute. Workers handle this natively, but ensure your Analytics Engine write rate does not exceed the 25 writes/second limit per isolate — batch analytics writes.

---

## Verification

```bash
# 1. Verify AASA is reachable and correct Content-Type
curl -v "https://example.com/.well-known/apple-app-site-association" 2>&1 | \
  grep -E "content-type|HTTP/"

# 2. Validate the JSON is parseable
curl -s "https://example.com/.well-known/apple-app-site-association" | jq .

# 3. Use Apple's validator
# https://branch.io/resources/aasa-validator/ or
# https://app-site-association.cdn-apple.com/a/v1/example.com

# 4. Android — test verification
adb shell pm verify-app-links --re-verify com.example.app
adb shell pm get-app-links com.example.app

# 5. Simulate a deep link on iOS Simulator
xcrun simctl openurl booted "https://example.com/orders/ORD-123"

# 6. Simulate a deep link on Android emulator
adb shell am start -a android.intent.action.VIEW \
  -d "https://example.com/orders/ORD-123" com.example.app
```

---

## Related

- `ios-universal-links.md`
- `android-deep-linking-intents.md`
- `android-app-links-dynamic-rules-verification.md`
- `mobile-deep-link-hijacking.md`
- `expo-router-file-based-routing-deep-linking.md`

---

## Sources

- Apple Universal Links — https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- Android App Links — https://developer.android.com/training/app-links/verify-android-applinks
- Cloudflare Workers routing — https://developers.cloudflare.com/workers/configuration/routing/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
