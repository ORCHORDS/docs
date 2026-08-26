# Universal Link / Deep Link Routing via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your iOS and Android apps need Universal Links / App Links to open directly from web URLs, short deep links must redirect to the correct app-store listing when the app is not installed, and every click should be logged for attribution. A single Cloudflare Worker handles all of this at the edge without a dedicated server.

---

## Context
Apple requires `/.well-known/apple-app-site-association` (AASA) served over HTTPS with `Content-Type: application/json` from your domain. Android requires `/.well-known/assetlinks.json` at the same well-known path. Storing these files in KV means you can rotate app bundle IDs or fingerprints without redeploying the Worker. The Worker also reads the `User-Agent` header to decide whether to redirect to the App Store, Google Play, or a web fallback URL. D1 captures a lightweight click log for marketing analytics.

---

## Setup / Config

```toml
# wrangler.toml
name = "deep-link-router"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "APP_META"
id = "<your-kv-namespace-id>"

[[d1_databases]]
binding = "DB"
database_name = "deep-links"
database_id = "<your-d1-database-id>"
```

Seed KV (run once or via CI):

```bash
# Store AASA file
npx wrangler kv key put --namespace-id <id> \
  "well-known:apple-app-site-association" \
  '{"applinks":{"apps":[],"details":[{"appID":"TEAMID.com.orchords.app","paths":["*"]}]}}'

# Store Asset Links file
npx wrangler kv key put --namespace-id <id> \
  "well-known:assetlinks.json" \
  '[{"relation":["delegate_permission/common.handle_all_urls"],"target":{"namespace":"android_app","package_name":"com.orchords.app","sha256_cert_fingerprints":["AA:BB:CC..." ]}}]'

# Store a short deep link (TTL = 30 days)
npx wrangler kv key put --namespace-id <id> \
  "shortlink:abc123" \
  '{"destination":"orchords://product/42","webFallback":"https://example.com/product/42","appStore":"https://apps.apple.com/app/example-org/example-repo","playStore":"https://play.google.com/store/apps/details?id=com.orchords.app"}' \
  --ttl 2592000
```

Create D1 schema:

```bash
npx wrangler d1 execute deep-links --command \
  "CREATE TABLE IF NOT EXISTS link_clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL, ua TEXT, ip TEXT, platform TEXT, ts INTEGER NOT NULL);"
```

---

## Implementation — Worker

```typescript
// src/index.ts
export interface Env {
  APP_META: KVNamespace;
  DB: D1Database;
}

const WELL_KNOWN: Record<string, string> = {
  '/\.well-known/apple-app-site-association': 'well-known:apple-app-site-association',
  '/\.well-known/assetlinks\.json': 'well-known:assetlinks.json',
};

function detectPlatform(ua: string): 'ios' | 'android' | 'other' {
  if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
  if (/Android/i.test(ua)) return 'android';
  return 'other';
}

async function logClick(
  db: D1Database,
  slug: string,
  ua: string,
  ip: string,
  platform: string
): Promise<void> {
  await db
    .prepare(
      'INSERT INTO link_clicks (slug, ua, ip, platform, ts) VALUES (?, ?, ?, ?, ?)'
    )
    .bind(slug, ua, ip, platform, Date.now())
    .run();
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const ua = request.headers.get('User-Agent') ?? '';
    const ip = request.headers.get('CF-Connecting-IP') ?? '';

    // ── Serve well-known files ──────────────────────────────────────────
    for (const [pattern, kvKey] of Object.entries(WELL_KNOWN)) {
      if (new RegExp(pattern).test(url.pathname)) {
        const body = await env.APP_META.get(kvKey);
        if (!body) return new Response('Not configured', { status: 404 });
        return new Response(body, {
          headers: { 'Content-Type': 'application/json', 'Cache-Control': 'max-age=3600' },
        });
      }
    }

    // ── Short deep link resolution ──────────────────────────────────────
    const shortMatch = url.pathname.match(/^\/l\/([A-Za-z0-9_-]+)$/);
    if (shortMatch) {
      const slug = shortMatch[1];
      const raw = await env.APP_META.get(`shortlink:${slug}`);
      if (!raw) return new Response('Link not found or expired', { status: 404 });

      const link = JSON.parse(raw) as {
        destination: string;
        webFallback: string;
        appStore: string;
        playStore: string;
      };

      const platform = detectPlatform(ua);

      // Log asynchronously — don't block redirect
      ctx.waitUntil(logClick(env.DB, slug, ua, ip, platform));

      let target: string;
      if (platform === 'ios') {
        target = link.appStore;
      } else if (platform === 'android') {
        target = link.playStore;
      } else {
        target = link.webFallback;
      }

      return Response.redirect(target, 302);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Integration / Testing

```bash
# Verify AASA is served correctly (Apple CDN checks Content-Type)
curl -I https://example.com/.well-known/apple-app-site-association
# Expected: HTTP/2 200, content-type: application/json

# Verify Asset Links
curl -s https://example.com/.well-known/assetlinks.json | jq .

# Test iOS redirect
curl -L -A "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" \
  https://example.com/l/abc123
# Should redirect to App Store URL

# Test Android redirect
curl -L -A "Mozilla/5.0 (Linux; Android 14)" \
  https://example.com/l/abc123
# Should redirect to Play Store URL

# Query click log
npx wrangler d1 execute deep-links \
  --command "SELECT slug, platform, COUNT(*) as hits FROM link_clicks GROUP BY slug, platform;"
```

---

## Anti-patterns
- **Storing AASA as a static asset in `public/`** — Apple's CDN fetches at validation time; a KV-backed Worker lets you rotate without redeployment or CDN purge delays.
- **Using 301 for deep link redirects** — browsers cache 301 permanently; use 302 so destination can change (e.g., when a campaign ends).
- **Blocking the response on D1 write** — always use `ctx.waitUntil()` for analytics so latency stays under 20 ms.
- **Missing `Cache-Control` on AASA** — Apple caches the file aggressively; set `max-age=3600` and plan for stale reads for an hour after rotation.

---

## Gotchas
- Apple validates AASA from their own CDN servers — `curl` from your machine succeeding is not proof Apple can fetch it; check `swcd` logs on device.
- Android Asset Links require the exact SHA-256 fingerprint of the signing certificate; debug and release keystores differ.
- KV TTL is set at write time; updating the value does not reset TTL — delete and re-put to extend expiry.
- Workers are not invoked for requests handled by Cloudflare's cache; add `Cache-Control: no-store` on short link responses if you need guaranteed log capture.

---

## Verification

```bash
# aasa-validator (Apple open-source tool)
npx aasa-validator https://example.com

# Android Digital Asset Links validator
curl 'https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://example.com&relation=delegate_permission/common.handle_all_urls'
```

---

## Related
- `workers-mobile-api-versioning-accept-header.md`
- `workers-react-native-websocket-durable-objects.md`

---

## Sources
- Apple Universal Links documentation — https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
- Android App Links — https://developer.android.com/training/app-links/verify-android-applinks
- Cloudflare KV TTL — https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
