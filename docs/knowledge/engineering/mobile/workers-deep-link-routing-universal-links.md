# Universal Links / App Links Deep Link Routing via Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You ship both a native app and a web app. When a user taps a marketing email link or a QR code, you want iOS to open the native app directly (Universal Links) and Android to open the native app directly (App Links). If the app is not installed, fall back gracefully to the web URL. You also want click analytics and the ability to A/B test app-vs-web routing without a new app release.

## Context

Apple Universal Links require a JSON file served at `https://<domain>/.well-known/apple-app-site-association` (AASA) with specific headers (`Content-Type: application/json`, no redirect). Android App Links require `https://<domain>/.well-known/assetlinks.json`. Both files must be served from the apex domain or matching subdomain with TLS, within 200 ms, and without redirects. Cloudflare Workers sit at the edge, handle both files with zero cold-start latency, and can log every deep-link hit to D1 for analytics.

## Solution

```typescript
// worker.ts
import { Hono } from 'hono';

const app = new Hono<{ Bindings: Env }>();

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  APP_TEAM_ID: string;      // e.g. "ABCDE12345"
  APP_BUNDLE_IOS: string;   // e.g. "com.example.app"
  APP_PACKAGE_ANDROID: string; // e.g. "com.example.app"
  APP_SHA256_FINGERPRINT: string; // Android signing cert SHA-256
  AB_TEST_RATIO: string;    // "0.5" => 50% get app routing
}

// ── Apple AASA ──────────────────────────────────────────────────────────────
app.get('/.well-known/apple-app-site-association', async (c) => {
  const aasa = {
    applinks: {
      apps: [],
      details: [
        {
          appIDs: [`${c.env.APP_TEAM_ID}.${c.env.APP_BUNDLE_IOS}`],
          components: [
            { '/': '/app/*', comment: 'All /app/ paths' },
            { '/': '/share/*', comment: 'Share sheets' },
            { '/': '/invite/*', comment: 'Invite flows' },
          ],
        },
      ],
    },
    webcredentials: {
      apps: [`${c.env.APP_TEAM_ID}.${c.env.APP_BUNDLE_IOS}`],
    },
  };

  return c.json(aasa, 200, {
    'Content-Type': 'application/json',
    'Cache-Control': 'public, max-age=3600',
  });
});

// ── Android Asset Links ──────────────────────────────────────────────────────
app.get('/.well-known/assetlinks.json', async (c) => {
  const assetLinks = [
    {
      relation: ['delegate_permission/common.handle_all_urls'],
      target: {
        namespace: 'android_app',
        package_name: c.env.APP_PACKAGE_ANDROID,
        sha256_cert_fingerprints: [c.env.APP_SHA256_FINGERPRINT],
      },
    },
  ];

  return c.json(assetLinks, 200, {
    'Content-Type': 'application/json',
    'Cache-Control': 'public, max-age=3600',
  });
});

// ── Deep link entry point with analytics + A/B routing ──────────────────────
app.get('/link/:path{.*}', async (c) => {
  const path = c.req.param('path');
  const ua = c.req.header('User-Agent') ?? '';
  const ref = c.req.header('Referer') ?? '';
  const ip = c.req.header('CF-Connecting-IP') ?? '';
  const country = c.req.raw.cf?.country as string | undefined;

  const isIOS = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);

  // A/B test: percentage routed to app
  const ratio = parseFloat(c.env.AB_TEST_RATIO ?? '1.0');
  const useApp = Math.random() < ratio;

  // Record click in D1
  await c.env.DB.prepare(
    `INSERT INTO deep_link_clicks
       (path, ua, ref, ip, country, platform, routed_to, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))`
  )
    .bind(
      path,
      ua.slice(0, 512),
      ref.slice(0, 512),
      ip,
      country ?? '',
      isIOS ? 'ios' : isAndroid ? 'android' : 'web',
      useApp ? 'app' : 'web'
    )
    .run();

  // Web fallback or no-app routing
  if (!useApp || (!isIOS && !isAndroid)) {
    return c.redirect(`https://app.example.com/${path}`, 302);
  }

  // iOS: Universal Links handle the redirect transparently
  // but we can also serve an intermediate page with a custom scheme fallback
  if (isIOS) {
    const universalUrl = `https://example.com/app/${path}`;
    const fallbackUrl = `https://app.example.com/${path}`;
    return serveDeepLinkPage(c, universalUrl, fallbackUrl, 'ios', path);
  }

  // Android: intent:// scheme with fallback
  if (isAndroid) {
    const intentUrl =
      `intent://${path}#Intent;` +
      `scheme=exampleapp;` +
      `package=${c.env.APP_PACKAGE_ANDROID};` +
      `S.browser_fallback_url=https://app.example.com/${path};` +
      `end`;
    return serveDeepLinkPage(c, intentUrl, `https://app.example.com/${path}`, 'android', path);
  }

  return c.redirect(`https://app.example.com/${path}`, 302);
});

function serveDeepLinkPage(
  c: any,
  appUrl: string,
  fallbackUrl: string,
  platform: string,
  path: string
): Response {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Opening app...</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <script>
    (function () {
      var timeout;
      function fallback() { window.location.replace('${fallbackUrl}'); }
      window.addEventListener('blur', function () { clearTimeout(timeout); });
      timeout = setTimeout(fallback, 2500);
      window.location.replace('${appUrl}');
    })();
  </script>
</head>
<body style="font-family:sans-serif;text-align:center;padding:60px">
  <p>Opening in app&hellip;</p>
  <a >Open in browser instead</a>
</body>
</html>`;

  return new Response(html, {
    status: 200,
    headers: { 'Content-Type': 'text/html;charset=UTF-8' },
  });
}

export default app;
```

```sql
-- D1 migration: 001_deep_link_clicks.sql
CREATE TABLE IF NOT EXISTS deep_link_clicks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  path       TEXT    NOT NULL,
  ua         TEXT,
  ref        TEXT,
  ip         TEXT,
  country    TEXT,
  platform   TEXT    NOT NULL DEFAULT 'web',
  routed_to  TEXT    NOT NULL DEFAULT 'web',
  created_at TEXT    NOT NULL
);
CREATE INDEX idx_dlc_path       ON deep_link_clicks(path);
CREATE INDEX idx_dlc_created_at ON deep_link_clicks(created_at);
CREATE INDEX idx_dlc_platform   ON deep_link_clicks(platform);
```

## Implementation Details

- AASA and assetlinks.json are served directly from Workers memory — no KV or D1 read needed on the hot path. Update them via a code deploy.
- The intermediate HTML page with a 2500 ms timeout is the standard pattern for app-not-installed fallback. `window.blur` fires when the OS switches to the native app, clearing the timeout so the user is not redirected away from the app.
- D1 writes are fire-and-forget via `.run()` without `await` on the result; use `ctx.waitUntil()` for true fire-and-forget to avoid holding the response.
- A/B test ratio stored in `APP_TEST_RATIO` env var can be updated without a code deploy via `wrangler secret put`.
- For iOS, the redirect to `https://example.com/app/<path>` triggers Universal Links only when the AASA file lists that path component. Ensure AASA path globs are broad enough.

```typescript
// wrangler.toml binding snippet
// [vars]
// AB_TEST_RATIO = "0.8"
// APP_TEAM_ID   = "ABCDE12345"

// [[d1_databases]]
// binding = "DB"
// database_name = "example project-main"
// database_id   = "<uuid>"
```

## Anti-patterns

- **Redirecting AASA/assetlinks.json**: Apple and Google crawlers will reject any redirect (301/302) on the well-known paths. Serve them with 200 directly.
- **Serving AASA with wrong Content-Type**: Must be `application/json`. `application/octet-stream` causes iOS to ignore the file silently.
- **Using custom URL schemes as primary mechanism**: Custom schemes (`exampleapp://`) can be hijacked by other apps. Universal Links / App Links are the secure, verified alternative.
- **Blocking on D1 write**: Awaiting the D1 insert before responding adds ~10–40 ms of latency. Use `ctx.waitUntil(db.run(...))` instead.
- **Hardcoding SHA-256 in source**: The Android fingerprint should live in a secret or Workers env var, not committed to source.

## Gotchas

- iOS re-fetches AASA at most once every few hours per device after the app is installed. Changes to path components take time to propagate — do not rely on instant updates.
- `cf.country` is available on the `Request.cf` object in production Workers but is `undefined` in local `wrangler dev`. Guard with a fallback.
- The 2500 ms fallback timeout must be long enough for slow devices to open the app but short enough to feel responsive. 2000–3000 ms is the typical range.
- Android intent URLs must not be percent-encoded or they fail. Build them with string concatenation, not `URL` constructor.
- Universal Links are disabled if the user taps a link inside the same app's `WKWebView`. Only Safari and third-party browsers trigger them.

## Verification

```bash
# 1. Validate AASA JSON structure
curl -s https://example.com/.well-known/apple-app-site-association | jq .

# 2. Apple AASA validator (unofficial)
open https://branch.io/resources/aasa-validator/

# 3. Android assetlinks check
curl -s https://example.com/.well-known/assetlinks.json | jq .
# Google's official checker:
open https://developers.google.com/digital-asset-links/tools/generator

# 4. Check D1 analytics
npx wrangler d1 execute example project-main \
  --command "SELECT platform, routed_to, count(*) FROM deep_link_clicks GROUP BY 1,2"

# 5. Simulate iOS UA
curl -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" \
  https://example.com/link/share/abc123 -i
```

## Related

- `workers-app-version-gating-kv.md` — enforce minimum app version before deep linking
- `workers-geofencing-cf-geo-kv.md` — restrict deep link destinations by region
- `workers-mobile-api-rate-limiting-kv.md` — protect deep link analytics endpoint

## Sources

- https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- https://developer.android.com/training/app-links/verify-android-applinks
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/d1/
