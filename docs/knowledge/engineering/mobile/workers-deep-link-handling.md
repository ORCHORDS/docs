# Universal Links and App Links Handling via Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your iOS and Android apps need to intercept web URLs and open directly to in-app screens (product pages, user profiles, shared content). Universal Links (iOS) and App Links (Android) require serving verified JSON files from your domain. You also want to generate short deep links for marketing campaigns, handle deferred deep linking (user installs the app after tapping a link → lands on the original content), and route `link.example.com/abc123` to either the app or a web fallback based on the client's platform.

## Context

iOS Universal Links require `.well-known/apple-app-site-association` (AASA) served with `Content-Type: application/json` and no redirect from your HTTPS domain. Android App Links require `.well-known/assetlinks.json`. Both files are fetched by the OS — not the app — so a Cloudflare Worker on your domain can serve them directly without a separate origin.

Storing app association config in D1 means you can update bundle IDs or team IDs without a Worker redeployment. A KV cache layer prevents D1 queries on every app install. The Worker also handles short link creation, deferred deep link storage (KV with TTL), and platform detection via `User-Agent` to route clicks appropriately.

## Solution

```typescript
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
}

interface AppAssociation {
  id: string;
  platform: 'ios' | 'android';
  team_id: string | null;          // iOS: Apple Team ID (10-char alphanumeric)
  bundle_id: string;               // iOS bundle ID or Android package name
  fingerprints: string | null;     // Android: JSON array of SHA256 fingerprints
  paths: string;                   // JSON array of URL path patterns
  active: number;                  // SQLite boolean (0/1)
}

interface ShortLink {
  id: string;
  code: string;
  target_path: string;             // In-app navigation path, e.g. /product/456
  fallback_url: string;            // Web URL shown when app is not installed
  campaign: string | null;
  created_at: string;
  click_count: number;
}

// --- Apple App Site Association (AASA) ---

async function buildAASA(env: Env): Promise<unknown> {
  const cached = await env.KV.get('aasa:v1', 'json');
  if (cached) return cached;

  const { results } = await env.DB.prepare(
    "SELECT * FROM app_associations WHERE platform = 'ios' AND active = 1",
  ).all<AppAssociation>();

  const aasa = {
    applinks: {
      details: results.map((row) => ({
        appIDs: [`${row.team_id}.${row.bundle_id}`],
        components: (JSON.parse(row.paths) as string[]).map((p) => ({
          '/': p,
          comment: 'Handled by iOS app',
        })),
      })),
    },
    activitycontinuation: {
      apps: results.map((row) => `${row.team_id}.${row.bundle_id}`),
    },
    webcredentials: {
      apps: results.map((row) => `${row.team_id}.${row.bundle_id}`),
    },
  };

  // Cache 30 min. Apple's CDN caches AASA aggressively; 30 min is a safe floor.
  await env.KV.put('aasa:v1', JSON.stringify(aasa), { expirationTtl: 1800 });
  return aasa;
}

// --- Android Digital Asset Links ---

async function buildAssetLinks(env: Env): Promise<unknown[]> {
  const cached = await env.KV.get('assetlinks:v1', 'json');
  if (cached) return cached as unknown[];

  const { results } = await env.DB.prepare(
    "SELECT * FROM app_associations WHERE platform = 'android' AND active = 1",
  ).all<AppAssociation>();

  const links = results.map((row) => ({
    relation: ['delegate_permission/common.handle_all_urls'],
    target: {
      namespace: 'android_app',
      package_name: row.bundle_id,
      sha256_cert_fingerprints: JSON.parse(row.fingerprints ?? '[]') as string[],
    },
  }));

  await env.KV.put('assetlinks:v1', JSON.stringify(links), { expirationTtl: 1800 });
  return links;
}

// --- Platform detection ---

type Platform = 'ios' | 'android' | 'desktop';

function detectPlatform(request: Request): Platform {
  const ua = request.headers.get('User-Agent') ?? '';
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  return 'desktop';
}

// --- Deferred deep linking ---
// Stores the intended in-app destination before the app is installed.
// After install the app calls GET /deferred?key=… to retrieve and navigate.

async function storeDeferral(
  targetPath: string,
  code: string,
  env: Env,
): Promise<string> {
  const key = `deferred:${crypto.randomUUID()}`;
  await env.KV.put(
    key,
    JSON.stringify({ target_path: targetPath, code, ts: Date.now() }),
    { expirationTtl: 60 * 60 * 24 * 7 }, // 7 days
  );
  return key;
}

// --- Short link resolution ---

async function resolveShortLink(code: string, request: Request, env: Env): Promise<Response> {
  const link = await env.DB.prepare('SELECT * FROM short_links WHERE code = ?')
    .bind(code).first<ShortLink>();

  if (!link) return new Response('Link not found', { status: 404 });

  // Fire-and-forget click counter increment
  void env.DB.prepare('UPDATE short_links SET click_count = click_count + 1 WHERE code = ?')
    .bind(code).run();

  const deferralKey = await storeDeferral(link.target_path, code, env);
  const platform = detectPlatform(request);

  if (platform === 'ios') {
    // Redirect to the canonical HTTPS URL that iOS intercepts as a Universal Link.
    // If the app is installed, iOS opens it directly. If not, Safari loads the fallback_url.
    return new Response(null, {
      status: 302,
      headers: {
        Location: `${link.fallback_url}?_dlk=${deferralKey}`,
        'X-Deep-Link-Target': link.target_path,
        'X-Deep-Link-Deferral-Key': deferralKey,
      },
    });
  }

  if (platform === 'android') {
    // Android Intent URL with browser fallback
    const intent = [
      `intent:${link.target_path}`,
      '#Intent',
      'scheme=orchords',
      'package=com.orchords.app',
      `S.browser_fallback_url=${encodeURIComponent(link.fallback_url)}`,
      `S._dlk=${encodeURIComponent(deferralKey)}`,
      'end',
    ].join(';');

    return new Response(androidRedirectPage(intent, link.fallback_url, deferralKey), {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'X-Deep-Link-Deferral-Key': deferralKey,
      },
    });
  }

  // Desktop: redirect to web fallback
  return new Response(null, {
    status: 302,
    headers: { Location: link.fallback_url },
  });
}

function androidRedirectPage(intentUrl: string, fallbackUrl: string, deferralKey: string): string {
  const safeIntent = intentUrl.replace(/'/g, '\\x27');
  const safeFallback = fallbackUrl.replace(/'/g, '\\x27');
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Opening Orchords…</title>
<meta http-equiv="refresh" content="2;url=${fallbackUrl}">
</head>
<body>
<script>
(function() {
  var dlk = '${deferralKey}';
  try { localStorage.setItem('orchords_dlk', dlk); } catch(e) {}
  setTimeout(function() { window.location.href = '${safeFallback}'; }, 2000);
  window.location.href = '${safeIntent}';
})();
</script>
<p>Opening the Orchords app&hellip; <a >Continue in browser</a></p>
</body>
</html>`;
}

// --- Deferred deep link retrieval (called by app after first launch post-install) ---

async function getDeferredLink(key: string, env: Env): Promise<Response> {
  const raw = await env.KV.get(key, 'json') as Record<string, unknown> | null;
  if (!raw) return Response.json({ deferred: false });

  // One-time retrieval: delete to prevent replay
  await env.KV.delete(key);
  return Response.json({ deferred: true, ...raw });
}

// --- QR code (SVG, inline — swap body for wasm-qr in production) ---

function qrSVG(url: string): string {
  const escaped = url.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="210" viewBox="0 0 200 210">',
    '<rect width="200" height="200" rx="4" fill="#fff" stroke="#000" stroke-width="2"/>',
    '<text x="100" y="208" text-anchor="middle" font-family="sans-serif" font-size="9" fill="#555">',
    escaped.length > 50 ? escaped.slice(0, 47) + '…' : escaped,
    '</text>',
    '<text x="100" y="106" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#333">',
    'integrate wasm-qr',
    '</text>',
    '</svg>',
  ].join('');
}

// --- Main fetch handler ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/.well-known/apple-app-site-association') {
      const aasa = await buildAASA(env);
      return new Response(JSON.stringify(aasa), {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }

    if (url.pathname === '/.well-known/assetlinks.json') {
      const links = await buildAssetLinks(env);
      return new Response(JSON.stringify(links), {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }

    // Short link resolution
    const shortMatch = url.pathname.match(/^\/l\/([A-Za-z0-9_-]{4,12})$/);
    if (shortMatch) {
      return resolveShortLink(shortMatch[1], request, env);
    }

    // Create a short link
    if (request.method === 'POST' && url.pathname === '/l') {
      const { target_path, fallback_url, campaign } = await request.json<{
        target_path: string;
        fallback_url: string;
        campaign?: string;
      }>();
      const code = crypto.randomUUID().replace(/-/g, '').slice(0, 8);
      const id = crypto.randomUUID();
      await env.DB.prepare(
        'INSERT INTO short_links (id, code, target_path, fallback_url, campaign, created_at, click_count) VALUES (?, ?, ?, ?, ?, ?, 0)',
      ).bind(id, code, target_path, fallback_url, campaign ?? null, new Date().toISOString()).run();
      return Response.json({ code, url: `${url.origin}/l/${code}` }, { status: 201 });
    }

    // Deferred deep link retrieval (called by app on first post-install launch)
    if (request.method === 'GET' && url.pathname === '/deferred') {
      const key = url.searchParams.get('key');
      if (!key) return Response.json({ error: 'Missing key parameter' }, { status: 400 });
      return getDeferredLink(key, env);
    }

    // QR code generation
    if (request.method === 'GET' && url.pathname === '/qr') {
      const target = url.searchParams.get('url');
      if (!target) return Response.json({ error: 'Missing url parameter' }, { status: 400 });
      return new Response(qrSVG(target), { headers: { 'Content-Type': 'image/svg+xml' } });
    }

    // Invalidate AASA/assetlinks KV cache after D1 update
    if (request.method === 'POST' && url.pathname === '/admin/invalidate-app-association') {
      await Promise.all([
        env.KV.delete('aasa:v1'),
        env.KV.delete('assetlinks:v1'),
      ]);
      return Response.json({ invalidated: true });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**D1 schema:**

```sql
CREATE TABLE app_associations (
  id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  platform     TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  team_id      TEXT,
  bundle_id    TEXT NOT NULL,
  fingerprints TEXT,  -- JSON array, e.g. ["AA:BB:CC:..."] (Android only)
  paths        TEXT NOT NULL DEFAULT '["/"]',  -- JSON array of path patterns
  active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE short_links (
  id           TEXT PRIMARY KEY,
  code         TEXT NOT NULL UNIQUE,
  target_path  TEXT NOT NULL,
  fallback_url TEXT NOT NULL,
  campaign     TEXT,
  created_at   TEXT NOT NULL,
  click_count  INTEGER NOT NULL DEFAULT 0
);
```

**Apple CDN caching behavior:** Apple fetches the AASA file when a user installs the app and caches it per domain for up to 24 hours on the device. Changes to D1 config are reflected in KV within 30 minutes (KV TTL). Invalidate the KV cache immediately after updating D1 by calling `POST /admin/invalidate-app-association`.

**Android App Links vs custom scheme deep links:** App Links require verified domain ownership via `assetlinks.json` and only work on HTTPS. They open the app without a disambiguation dialog. Custom URI schemes (`orchords://`) work without verification but trigger a disambiguation dialog on first use and are less trustworthy (any app can register the same scheme).

**Deferred deep linking flow:** User clicks `link.example.com/l/abc123` → Worker stores `deferred:{uuid}` in KV with 7-day TTL → redirects to fallback URL with `?_dlk=<key>` → user installs app → app calls `GET /deferred?key=<key>` on first launch → Worker returns target path and deletes the KV entry (one-time use).

**QR code generation in production:** The inline SVG placeholder above demonstrates the response shape. Replace with a Wasm-compiled QR library (e.g., `qr-code-generator` compiled to Wasm) for real matrix generation. The Worker bundle size limit (1 MB compressed) is sufficient for a Wasm QR module (~50 KB).

## Anti-patterns

- Serving AASA with a redirect (`301`/`302`) — Apple's validation requires a direct 200 response from the origin with no redirect chain.
- Using `Content-Type: application/pkcs7-mime` for AASA — this was required only before iOS 9.3.1. Modern iOS requires plain `application/json`.
- JavaScript-only deep link redirect on iOS — Universal Links operate at OS level. A `window.location` change cannot trigger a Universal Link; it must be a real HTTPS URL click or a redirect response.
- Not calling `KV.delete('aasa:v1')` after updating `app_associations` in D1 — the old cached AASA will be served for up to 30 minutes.

## Gotchas

- Android `sha256_cert_fingerprints` are colon-separated uppercase hex strings (`AA:BB:CC:DD:…`). Extract from the release keystore with: `keytool -list -v -keystore release.jks | grep SHA256`.
- The AASA `components` array (iOS 13+) supersedes the older `paths` array. Include both for maximum compatibility: the Worker above uses `components`; add a `paths` key alongside it for iOS 12 and earlier.
- Deferred deep link keys in KV are single-use. Delete on retrieval to prevent replay. The 7-day TTL is a safety net for KV consistency failures.
- Short link codes that collide with existing routes (`/l`, `/qr`, `/deferred`, `.well-known`) must be prevented. Validate the generated code against a blocklist before inserting, or use a prefix (`/go/`) for short links.

## Verification

```bash
# Validate AASA JSON structure
curl -s https://your-domain.com/.well-known/apple-app-site-association | jq .applinks.details

# Validate assetlinks JSON
curl -s https://your-domain.com/.well-known/assetlinks.json | jq .[0].target

# Apple's official AASA validator
curl -s "https://app-site-association.cdn-apple.com/a/v1/your-domain.com" | jq .

# Create a short link
CODE=$(curl -s -X POST https://your-worker.workers.dev/l \
  -H "Content-Type: application/json" \
  -d '{"target_path":"/product/42","fallback_url":"https://example.com/product/42","campaign":"email-oct26"}' \
  | jq -r .code)
echo "Short link code: $CODE"

# Resolve on iOS UA (expect HTTPS redirect)
curl -sI -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" \
  "https://your-worker.workers.dev/l/$CODE" | grep -i location
```

## Related

- `workers-mobile-api-versioning.md` — versioned endpoints for deep link resolution
- `workers-push-notification-fcm-apns.md` — complementary mobile infrastructure

## Sources

- [Supporting associated domains — Apple Developer](https://developer.apple.com/documentation/xcode/supporting-associated-domains)
- [Verify Android App Links](https://developer.android.com/training/app-links/verify-android-applinks)
- [Digital Asset Links specification](https://developers.google.com/digital-asset-links/v1/getting-started)
- [Cloudflare KV — expiring keys](https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys)
