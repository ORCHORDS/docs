# Mobile App Version Gating and Forced Upgrade Enforcement via Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You have released a critical security patch or a breaking API change. Older app versions must be blocked (forced upgrade) or warned (soft upgrade). You need to enforce minimum version requirements per platform (iOS/Android) without a code deploy — the rules must be updateable from a dashboard or CLI in seconds. You also want to track which app versions are still active in the wild so you can plan deprecation windows.

## Context

Mobile apps send their version in a request header (e.g., `X-App-Version: 2.4.1`) and platform in `X-App-Platform: ios|android`. A Cloudflare Worker reads the minimum version config from KV on every request (KV reads are ~1 ms when the value is in edge cache). When the app version is below the forced minimum, the Worker returns HTTP 426 Upgrade Required before the request reaches your origin. When it is below the soft minimum, a warning header is injected. Version analytics are recorded in D1.

## Solution

```typescript
// version-gate-worker.ts
import { Hono } from 'hono';

export interface Env {
  CONFIG_KV: KVNamespace;
  DB: D1Database;
  ORIGIN_URL: string; // upstream to proxy to when version is allowed
}

interface PlatformVersionConfig {
  minForced: string;  // Below this => HTTP 426, block request
  minSoft: string;    // Below this => X-Upgrade-Suggested header, allow request
  storeUrl: string;   // Deep link to App Store / Play Store for upgrade
  message: string;    // Human-readable upgrade message
  deprecationWindowDays: number; // Days after which minSoft becomes minForced
  deprecationAnnounced: string;  // ISO date when window started
}

interface VersionConfig {
  ios: PlatformVersionConfig;
  android: PlatformVersionConfig;
  updatedAt: string;
}

const CONFIG_KEY = 'app:version_config';
const CONFIG_TTL_SECONDS = 60; // Re-read from KV at most once per minute per edge node

// ── Semver comparison ─────────────────────────────────────────────────────────
function parseSemver(v: string): [number, number, number] {
  const parts = v.replace(/^v/, '').split('.').map(Number);
  return [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0];
}

/**
 * Returns negative if a < b, 0 if equal, positive if a > b.
 */
function compareSemver(a: string, b: string): number {
  const [aMaj, aMin, aPat] = parseSemver(a);
  const [bMaj, bMin, bPat] = parseSemver(b);
  if (aMaj !== bMaj) return aMaj - bMaj;
  if (aMin !== bMin) return aMin - bMin;
  return aPat - bPat;
}

// ── Config loader with in-memory micro-cache ──────────────────────────────────
// A single Worker isolate caches the config for up to CONFIG_TTL_SECONDS.
// Different isolates (across edge nodes) each maintain their own cache.
let cachedConfig: VersionConfig | null = null;
let cacheExpiresAt = 0;

async function getVersionConfig(env: Env): Promise<VersionConfig | null> {
  const now = Date.now();
  if (cachedConfig && now < cacheExpiresAt) return cachedConfig;

  const raw = await env.CONFIG_KV.get(CONFIG_KEY);
  if (!raw) return null;

  cachedConfig = JSON.parse(raw) as VersionConfig;
  cacheExpiresAt = now + CONFIG_TTL_SECONDS * 1000;
  return cachedConfig;
}

// ── Analytics: record version hit ────────────────────────────────────────────
async function recordVersionHit(
  platform: string,
  version: string,
  status: 'allowed' | 'soft' | 'blocked',
  env: Env
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO app_version_hits (platform, version, status, created_at)
     VALUES (?, ?, ?, datetime('now'))`
  ).bind(platform, version, status).run();
}

// ── Deprecation window enforcement ───────────────────────────────────────────
function isDeprecationWindowExpired(cfg: PlatformVersionConfig): boolean {
  if (!cfg.deprecationAnnounced) return false;
  const announced = new Date(cfg.deprecationAnnounced).getTime();
  const windowMs = cfg.deprecationWindowDays * 86_400_000;
  return Date.now() > announced + windowMs;
}

const app = new Hono<{ Bindings: Env }>();

// ── Version gate middleware ───────────────────────────────────────────────────
app.use('*', async (c, next) => {
  const appVersion = c.req.header('X-App-Version');
  const appPlatform = (
    c.req.header('X-App-Platform') ?? 'unknown'
  ).toLowerCase() as 'ios' | 'android' | 'unknown';

  // Non-app clients (web, curl, health checks) pass through
  if (!appVersion || appPlatform === 'unknown') {
    await next();
    return;
  }

  const config = await getVersionConfig(c.env);
  if (!config) {
    // No config in KV — fail open (do not block requests)
    await next();
    return;
  }

  const platformCfg = appPlatform === 'ios' ? config.ios : config.android;

  // Check if deprecation window has expired — promote soft to forced
  const softBecameForced = isDeprecationWindowExpired(platformCfg);

  const belowForced = compareSemver(appVersion, platformCfg.minForced) < 0;
  const belowSoft = compareSemver(appVersion, platformCfg.minSoft) < 0;

  // Forced block condition
  if (belowForced || (softBecameForced && belowSoft)) {
    c.executionCtx.waitUntil(recordVersionHit(appPlatform, appVersion, 'blocked', c.env));

    return c.json(
      {
        error: 'Upgrade Required',
        code: 'APP_VERSION_TOO_OLD',
        message: platformCfg.message,
        minimumVersion: platformCfg.minForced,
        currentVersion: appVersion,
        storeUrl: platformCfg.storeUrl,
        platform: appPlatform,
      },
      426,
      {
        'Upgrade': 'app',
        'X-Min-App-Version': platformCfg.minForced,
        'X-Store-URL': platformCfg.storeUrl,
      }
    );
  }

  // Soft upgrade suggestion
  if (belowSoft) {
    c.executionCtx.waitUntil(recordVersionHit(appPlatform, appVersion, 'soft', c.env));
    await next();
    c.res.headers.set('X-Upgrade-Suggested', 'true');
    c.res.headers.set('X-Min-Recommended-Version', platformCfg.minSoft);
    c.res.headers.set('X-Store-URL', platformCfg.storeUrl);
    return;
  }

  // Version is fine
  c.executionCtx.waitUntil(recordVersionHit(appPlatform, appVersion, 'allowed', c.env));
  await next();
});

// ── Config management endpoint (admin only) ───────────────────────────────────
app.put('/admin/version-config', async (c) => {
  const adminKey = c.req.header('X-Admin-Key');
  const expectedKey = await c.env.CONFIG_KV.get('admin:key');
  if (!adminKey || adminKey !== expectedKey) {
    return c.json({ error: 'Forbidden' }, 403);
  }

  const body = await c.req.json<VersionConfig>();
  body.updatedAt = new Date().toISOString();

  await c.env.CONFIG_KV.put(CONFIG_KEY, JSON.stringify(body));
  // Invalidate local cache
  cachedConfig = null;
  cacheExpiresAt = 0;

  return c.json({ updated: true, config: body });
});

// ── Version analytics endpoint ────────────────────────────────────────────────
app.get('/admin/version-stats', async (c) => {
  const adminKey = c.req.header('X-Admin-Key');
  const expectedKey = await c.env.CONFIG_KV.get('admin:key');
  if (!adminKey || adminKey !== expectedKey) return c.json({ error: 'Forbidden' }, 403);

  const { results } = await c.env.DB.prepare(
    `SELECT platform, version, status, count(*) as hits
     FROM app_version_hits
     WHERE created_at > datetime('now', '-7 days')
     GROUP BY 1, 2, 3
     ORDER BY 4 DESC
     LIMIT 100`
  ).all();

  return c.json({ stats: results });
});

export default app;
```

```sql
-- D1 migration: 001_version_hits.sql
CREATE TABLE IF NOT EXISTS app_version_hits (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  platform   TEXT NOT NULL,
  version    TEXT NOT NULL,
  status     TEXT NOT NULL, -- 'allowed' | 'soft' | 'blocked'
  created_at TEXT NOT NULL
);
CREATE INDEX idx_avh_platform   ON app_version_hits(platform);
CREATE INDEX idx_avh_version    ON app_version_hits(version);
CREATE INDEX idx_avh_created_at ON app_version_hits(created_at);
```

```jsonc
// Example KV config value for key "app:version_config"
{
  "ios": {
    "minForced": "2.3.0",
    "minSoft": "2.4.0",
    "storeUrl": "https://apps.apple.com/app/id123456789",
    "message": "A critical update is required. Please update to continue.",
    "deprecationWindowDays": 30,
    "deprecationAnnounced": "2026-08-01T00:00:00Z"
  },
  "android": {
    "minForced": "2.3.0",
    "minSoft": "2.4.0",
    "storeUrl": "https://play.google.com/store/apps/details?id=com.example.app",
    "message": "A critical update is required. Please update to continue.",
    "deprecationWindowDays": 30,
    "deprecationAnnounced": "2026-08-01T00:00:00Z"
  },
  "updatedAt": "2026-08-24T10:00:00Z"
}
```

## Implementation Details

- **In-memory micro-cache**: The KV value is cached in the Worker isolate's memory for 60 seconds. This means a version config update propagates within 60 seconds to all active isolates on a given edge node, and within a few minutes globally as isolates cycle.
- **Fail open**: If KV has no config (first deploy, misconfiguration), requests pass through rather than block. This prevents an outage when the Worker is deployed before the config is written.
- **Deprecation window promotion**: When `deprecationWindowDays` have elapsed since `deprecationAnnounced`, the soft boundary is automatically promoted to forced — no KV update required. The timer is calculated in the Worker on every request.
- **HTTP 426**: The `426 Upgrade Required` status code is the correct RFC 7231 code for "the server refuses to perform the request using the current protocol" — repurposed here as "upgrade your app".
- **`X-Admin-Key` pattern**: For production, replace this with a proper auth system (Cloudflare Access, JWT). The pattern shown is illustrative.

## Anti-patterns

- **Hardcoding version numbers in Worker source**: Every version rule change would require a code deploy, killing the ability to react quickly to a zero-day. Always read from KV.
- **Using `>=` comparisons for forced blocks**: Use strict `<` so that the exact forced minimum itself is allowed. A user on exactly `2.3.0` when `minForced` is `2.3.0` should be let through.
- **Not logging `soft` hits**: The soft-upgrade stats tell you how many users are still on old versions, which informs when to promote soft to forced.
- **Blocking non-app traffic**: Health check probes and web browser requests do not send `X-App-Version`. Always allow requests without the version header to pass through.

## Gotchas

- The in-memory isolate cache means `cachedConfig` is per-isolate. If Cloudflare spawns new isolates during a traffic spike, the new isolates re-read from KV immediately. Expect N reads to KV at spike time where N = number of new isolates.
- `compareSemver` does not handle pre-release labels (`2.4.0-beta.1`). If your version scheme uses pre-release strings, strip the label before comparison or use a proper semver parser.
- D1 `waitUntil` writes accumulate quickly under high traffic. Aggregate counts into a time-series table with `INSERT OR REPLACE` keyed on `(platform, version, date(created_at))` to avoid unbounded row growth.
- KV `put` without `expirationTtl` means the config lives indefinitely — intentional here since it is admin-managed. The in-memory cache has its own TTL independent of KV.

## Verification

```bash
# 1. Write the initial config to KV
npx wrangler kv key put --binding CONFIG_KV 'app:version_config' '{
  "ios":{"minForced":"2.0.0","minSoft":"2.4.0",
         "storeUrl":"https://apps.apple.com","message":"Update required",
         "deprecationWindowDays":30,"deprecationAnnounced":"2026-07-01T00:00:00Z"},
  "android":{"minForced":"2.0.0","minSoft":"2.4.0",
             "storeUrl":"https://play.google.com","message":"Update required",
             "deprecationWindowDays":30,"deprecationAnnounced":"2026-07-01T00:00:00Z"},
  "updatedAt":"2026-08-24T00:00:00Z"
}'

# 2. Test forced block (old version)
curl -i -H 'X-App-Version: 1.5.0' -H 'X-App-Platform: ios' \
  https://api.example.com/api/data
# Expect: HTTP 426 with JSON body

# 3. Test soft warning
curl -i -H 'X-App-Version: 2.1.0' -H 'X-App-Platform: android' \
  https://api.example.com/api/data
# Expect: HTTP 200 with X-Upgrade-Suggested: true header

# 4. Test current version
curl -i -H 'X-App-Version: 2.5.0' -H 'X-App-Platform: ios' \
  https://api.example.com/api/data
# Expect: HTTP 200 with no upgrade headers

# 5. Check version analytics
npx wrangler d1 execute example project-main \
  --command "SELECT platform, version, status, count(*) FROM app_version_hits GROUP BY 1,2,3"
```

## Related

- `workers-mobile-api-rate-limiting-kv.md` — apply tighter rate limits to old blocked versions
- `workers-deep-link-routing-universal-links.md` — deep link to the app store upgrade page
- `workers-geofencing-cf-geo-kv.md` — combine version gating with region-based rollouts

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://www.rfc-editor.org/rfc/rfc7231#section-6.5.15 (HTTP 426)
- https://semver.org/
