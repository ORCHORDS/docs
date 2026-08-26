# Geofencing Feature Flags Using Cloudflare Geo Data + KV in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Certain features in your mobile app must be restricted by geography — gambling widgets blocked in jurisdictions that prohibit them, financial products only available in licensed markets, beta features rolled out region by region. You need sub-millisecond geo-aware feature toggling with no client-side changes, audit trail for compliance, and the ability to update geofence rules in seconds without a Worker redeploy.

## Context

Cloudflare automatically attaches `cf.country` (ISO 3166-1 alpha-2) and `cf.region` (ISO 3166-2 subdivision) to every request object, derived from Cloudflare's IP intelligence database. These values are available in Workers as `request.cf.country` and `request.cf.region` — no external IP lookup needed. Geofence rules (which features are allowed/blocked per region) are stored in KV as JSON, readable in ~1 ms from the edge cache. Audit records for compliance go to D1.

## Solution

```typescript
// geofence-worker.ts
import { Hono } from 'hono';

export interface Env {
  GEO_KV: KVNamespace;
  AUDIT_DB: D1Database;
}

// ── Data structures ───────────────────────────────────────────────────────────
interface GeofenceRule {
  mode: 'allowlist' | 'blocklist';
  // For allowlist: only these countries/regions can access the feature.
  // For blocklist: these countries/regions are denied.
  countries: string[];    // ISO 3166-1 alpha-2, e.g. ["US", "CA", "GB"]
  regions?: string[];     // ISO 3166-2, e.g. ["US-CA", "DE-BY"]; optional sub-country
  message?: string;       // Shown to blocked users
  complianceNote?: string; // Internal note for auditors
}

interface GeofenceConfig {
  // Map of featureId => rule
  features: Record<string, GeofenceRule>;
  updatedAt: string;
}

const GEO_CONFIG_KEY = 'geofence:config';
const CONFIG_TTL_MS = 30_000; // 30-second in-process cache

// In-process cache
let cachedGeoConfig: GeofenceConfig | null = null;
let geoCacheExpiry = 0;

async function getGeofenceConfig(env: Env): Promise<GeofenceConfig | null> {
  const now = Date.now();
  if (cachedGeoConfig && now < geoCacheExpiry) return cachedGeoConfig;

  const raw = await env.GEO_KV.get(GEO_CONFIG_KEY);
  if (!raw) return null;

  cachedGeoConfig = JSON.parse(raw) as GeofenceConfig;
  geoCacheExpiry = now + CONFIG_TTL_MS;
  return cachedGeoConfig;
}

// ── Core geo-check ────────────────────────────────────────────────────────────
function evaluateGeofence(
  rule: GeofenceRule,
  country: string,
  region: string
): { allowed: boolean; matchedOn: 'country' | 'region' | 'default' } {
  const inCountryList = rule.countries.includes(country);
  const inRegionList = rule.regions?.includes(region) ?? false;

  if (rule.mode === 'allowlist') {
    if (inRegionList) return { allowed: true,  matchedOn: 'region' };
    if (inCountryList) return { allowed: true,  matchedOn: 'country' };
    return { allowed: false, matchedOn: 'default' };
  } else {
    // blocklist
    if (inRegionList) return { allowed: false, matchedOn: 'region' };
    if (inCountryList) return { allowed: false, matchedOn: 'country' };
    return { allowed: true,  matchedOn: 'default' };
  }
}

// ── Audit log ─────────────────────────────────────────────────────────────────
async function writeAuditLog(
  featureId: string,
  country: string,
  region: string,
  allowed: boolean,
  matchedOn: string,
  path: string,
  env: Env
): Promise<void> {
  await env.AUDIT_DB.prepare(
    `INSERT INTO geofence_audit
       (feature_id, country, region, allowed, matched_on, path, created_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`
  ).bind(featureId, country, region, allowed ? 1 : 0, matchedOn, path).run();
}

const app = new Hono<{ Bindings: Env }>();

// ── Feature flag injection middleware ─────────────────────────────────────────
// Adds X-Feature-{ID}: enabled|disabled headers to responses
// so the mobile client can conditionally render features.
app.use('*', async (c, next) => {
  const cf = c.req.raw.cf as { country?: string; region?: string } | undefined;
  const country = cf?.country ?? 'XX';  // 'XX' = unknown
  const region  = cf?.region  ?? '';

  const config = await getGeofenceConfig(c.env);
  if (!config) {
    await next();
    return;
  }

  const auditWrites: Promise<void>[] = [];

  for (const [featureId, rule] of Object.entries(config.features)) {
    const { allowed, matchedOn } = evaluateGeofence(rule, country, region);
    // Inject feature state into response headers after next()
    // We do this after next() so the header is added without blocking origin.
    c.set(`feature:${featureId}`, allowed ? 'enabled' : 'disabled');

    // Audit only blocked requests to keep D1 write volume manageable
    if (!allowed) {
      auditWrites.push(
        writeAuditLog(featureId, country, region, false, matchedOn, c.req.path, c.env)
      );
    }
  }

  await next();

  // Attach feature flag headers to response
  for (const [featureId] of Object.entries(config.features)) {
    const value = c.get(`feature:${featureId}`) as string;
    if (value) c.res.headers.set(`X-Feature-${featureId}`, value);
  }

  // Fire-and-forget audit writes
  if (auditWrites.length > 0) {
    c.executionCtx.waitUntil(Promise.all(auditWrites));
  }
});

// ── Feature check API (for server-side rendering or native apps) ──────────────
app.get('/geo/features', async (c) => {
  const cf = c.req.raw.cf as { country?: string; region?: string } | undefined;
  const country = cf?.country ?? 'XX';
  const region  = cf?.region  ?? '';

  const config = await getGeofenceConfig(c.env);
  if (!config) return c.json({ features: {}, country, region });

  const features: Record<string, { enabled: boolean; reason: string }> = {};
  for (const [featureId, rule] of Object.entries(config.features)) {
    const { allowed, matchedOn } = evaluateGeofence(rule, country, region);
    features[featureId] = {
      enabled: allowed,
      reason: allowed
        ? `Allowed by ${rule.mode} rule (matched: ${matchedOn})`
        : rule.message ?? `Blocked by ${rule.mode} rule (matched: ${matchedOn})`,
    };
  }

  return c.json({ features, country, region, configUpdatedAt: config.updatedAt });
});

// ── Admin: update geofence config ─────────────────────────────────────────────
app.put('/admin/geofence-config', async (c) => {
  const adminKey = c.req.header('X-Admin-Key');
  const expectedKey = await c.env.GEO_KV.get('admin:key');
  if (!adminKey || adminKey !== expectedKey) return c.json({ error: 'Forbidden' }, 403);

  const body = await c.req.json<GeofenceConfig>();
  body.updatedAt = new Date().toISOString();

  await c.env.GEO_KV.put(GEO_CONFIG_KEY, JSON.stringify(body));
  cachedGeoConfig = null; // Bust local cache
  geoCacheExpiry  = 0;

  return c.json({ updated: true });
});

// ── Admin: audit log query ─────────────────────────────────────────────────────
app.get('/admin/geofence-audit', async (c) => {
  const adminKey = c.req.header('X-Admin-Key');
  const expectedKey = await c.env.GEO_KV.get('admin:key');
  if (!adminKey || adminKey !== expectedKey) return c.json({ error: 'Forbidden' }, 403);

  const feature = c.req.query('feature');
  const country = c.req.query('country');
  const since    = c.req.query('since') ?? '7 days';

  let query = `SELECT feature_id, country, region, allowed, matched_on, path, created_at
               FROM geofence_audit
               WHERE created_at > datetime('now', '-${since}')`;
  const binds: (string | number)[] = [];

  if (feature) { query += ' AND feature_id = ?'; binds.push(feature); }
  if (country) { query += ' AND country = ?'; binds.push(country); }
  query += ' ORDER BY created_at DESC LIMIT 200';

  const { results } = await c.env.AUDIT_DB.prepare(query).bind(...binds).all();
  return c.json({ logs: results });
});

export default app;
```

```sql
-- D1 migration: 001_geofence_audit.sql
CREATE TABLE IF NOT EXISTS geofence_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  feature_id  TEXT    NOT NULL,
  country     TEXT    NOT NULL,
  region      TEXT,
  allowed     INTEGER NOT NULL DEFAULT 1, -- 0=blocked, 1=allowed
  matched_on  TEXT    NOT NULL,
  path        TEXT,
  created_at  TEXT    NOT NULL
);
CREATE INDEX idx_ga_feature_id  ON geofence_audit(feature_id);
CREATE INDEX idx_ga_country     ON geofence_audit(country);
CREATE INDEX idx_ga_created_at  ON geofence_audit(created_at);
```

```jsonc
// Example KV config value for key "geofence:config"
{
  "features": {
    "gambling-widget": {
      "mode": "allowlist",
      "countries": ["GB", "MT", "GI"],
      "regions": [],
      "message": "This feature is not available in your region.",
      "complianceNote": "UK Gambling Commission licence only. UKGC ref: 123456"
    },
    "crypto-trading": {
      "mode": "blocklist",
      "countries": ["US", "CN", "KP", "IR"],
      "regions": ["US-NY"],
      "message": "Crypto trading is not available in your jurisdiction.",
      "complianceNote": "BitLicence not held for NY; OFAC sanctions for CN/KP/IR"
    },
    "beta-feature-x": {
      "mode": "allowlist",
      "countries": ["US", "CA"],
      "regions": ["US-CA", "US-WA", "US-NY"],
      "message": "Beta feature coming soon to your region."
    }
  },
  "updatedAt": "2026-08-24T10:00:00Z"
}
```

## Implementation Details

- **`cf.country` source**: Cloudflare derives country from MaxMind GeoIP2 + its own IP intelligence. It is available on `request.cf.country` in production Workers. In `wrangler dev`, the `cf` object is a minimal stub — `country` will be `undefined`.
- **`cf.region`**: The region is an ISO 3166-2 code (e.g., `US-CA` for California). It is not always populated, especially for mobile networks using carrier NAT. Guard with `?? ''`.
- **Header injection pattern**: Injecting `X-Feature-*` response headers lets a single Worker drive both native mobile apps (which read response headers) and server-side rendered pages without API calls.
- **Audit volume control**: Writing a D1 row for every request would overwhelm D1 at scale. The implementation above writes only on blocked events. For allowed-event audits, use a sampling rate (e.g., 1% of allowed hits) controlled by a KV config flag.
- **Allowlist vs. blocklist**: Use `allowlist` for features that are only permitted in specific licensed markets. Use `blocklist` for OFAC/sanctions-driven restrictions where the default is to allow and you explicitly block named jurisdictions.

## Anti-patterns

- **Client-side geo checks**: Never hide features only on the client. A motivated user can spoof geo or bypass the client check. The Worker enforces geo at the network edge, before any data reaches the client.
- **Using IP geolocation from a third-party API**: Calling an external geo API from the Worker adds latency, costs money, and has availability risk. `request.cf.country` is free, zero-latency, and always available.
- **Storing geofence rules in Worker source**: Country lists change frequently (new licences, regulatory orders). Always store rules in KV so they can be updated without a deploy.
- **Over-logging allowed events to D1**: D1 has a row write limit. Log only violations (blocked events) or use D1 for aggregate counters rather than per-request rows.

## Gotchas

- `cf.country` can be `'T1'` for Tor exit nodes or VPNs that Cloudflare detects. Treat `'T1'` as an unknown country in your allowlist/blocklist logic (most allowlists should deny it).
- `cf.region` is ISO 3166-2 format (`US-CA`), not the two-letter state code alone (`CA`). Ensure your config JSON uses the full code.
- Country-level blocks can be circumvented with VPNs. For strict compliance, combine geo-blocking with account-level jurisdiction verification at sign-up.
- The 30-second in-process cache means a config update takes up to 30 seconds to propagate within a given isolate. Lower the TTL for time-sensitive compliance changes, but accept more KV reads.
- KV values have a maximum size of 25 MB. A geofence config with hundreds of features and large country lists is well within this limit, but avoid embedding binary data in the config.

## Verification

```bash
# 1. Write the initial geofence config
npx wrangler kv key put --binding GEO_KV 'geofence:config' "$(cat geofence-config.json)"

# 2. Check feature flags for a simulated US request
curl -s https://api.example.com/geo/features \
  --resolve 'api.example.com:443:104.21.0.1' | jq .
# In production, cf.country is populated by Cloudflare automatically.

# 3. Test blocked country via curl with CF test header (staging only)
curl -s -H 'CF-IPCountry: KP' https://staging-api.example.com/geo/features | jq .
# Note: CF-IPCountry is only trusted in Workers when sent through Cloudflare;
# in wrangler dev, simulate by hardcoding country in the handler.

# 4. Query audit log for blocked events
curl -s -H 'X-Admin-Key: <key>' \
  'https://api.example.com/admin/geofence-audit?feature=gambling-widget' | jq .

# 5. D1 direct query for compliance report
npx wrangler d1 execute example project-main \
  --command "SELECT country, count(*) as blocks FROM geofence_audit WHERE feature_id='gambling-widget' AND allowed=0 GROUP BY 1 ORDER BY 2 DESC"
```

## Related

- `workers-app-version-gating-kv.md` — combine with version gating for region-specific rollouts
- `workers-mobile-api-rate-limiting-kv.md` — apply tighter rate limits to requests from high-risk regions
- `workers-deep-link-routing-universal-links.md` — redirect blocked users to region-specific landing pages

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/d1/
- https://en.wikipedia.org/wiki/ISO_3166-2
- https://home.treasury.gov/policy-issues/office-of-foreign-assets-control-sanctions-programs-and-information (OFAC)
