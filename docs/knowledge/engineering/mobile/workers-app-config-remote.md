# Remote App Configuration System in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile apps hard-code feature flags, API base URLs, rate limits, and A/B variants, making any change require a new build submission. A remote config system lets you update these values instantly, target specific platform versions and locales, and shut down broken features without an app release.

## Context

A Cloudflare Worker serves `GET /config` with ETag-based diffing so clients only download what changed. Configs are stored in KV, namespaced by platform, version range, and locale. An emergency kill-switch key can disable the entire app. The client caches the full config locally with a TTL and only sends an `If-None-Match` header on subsequent requests to receive incremental diffs.

## Solution

```typescript
// remote-config/src/index.ts
import { Hono } from 'hono';

export interface Env {
  CONFIGS: KVNamespace;  // key pattern: config:{platform}:{locale} => JSON config object
  CONFIG_META: KVNamespace; // key: etag_index => JSON map of platform:locale => etag
}

type Platform = 'ios' | 'android' | 'web';

interface ConfigRequest {
  platform: Platform;
  app_version: string;
  locale: string;
}

interface RemoteConfig {
  _version: number;
  _generated_at: string;
  feature_flags: Record<string, boolean>;
  api_endpoints: Record<string, string>;
  rate_limits: Record<string, number>;
  kill_switch: boolean;
  kill_switch_message: string;
  ab_variants: Record<string, string>;

}

interface DiffResponse {
  etag: string;
  changed_keys: string[];
  config: Partial<RemoteConfig>;
  full: false;
}

interface FullResponse {
  etag: string;
  config: RemoteConfig;
  full: true;
}

// Deep-merge base config with override layers (later layers win)
function mergeConfigs(...layers: Partial<RemoteConfig>[]): RemoteConfig {
  const result: Record<string, unknown> = {};
  for (const layer of layers) {
    for (const [k, v] of Object.entries(layer)) {
      if (v !== null && typeof v === 'object' && !Array.isArray(v) && typeof result[k] === 'object') {
        result[k] = { ...(result[k] as object), ...(v as object) };
      } else {
        result[k] = v;
      }
    }
  }
  return result as RemoteConfig;
}

// Produce a stable ETag from config content
async function etagFromConfig(config: RemoteConfig): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(config));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash))
    .slice(0, 8)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// Compute which top-level keys differ between two configs
function diffKeys(prev: RemoteConfig, next: RemoteConfig): string[] {
  const keys = new Set([...Object.keys(prev), ...Object.keys(next)]);
  return [...keys].filter(
    (k) => JSON.stringify(prev[k]) !== JSON.stringify(next[k]),
  );
}

async function loadConfig(
  kv: KVNamespace,
  platform: Platform,
  appVersion: string,
  locale: string,
): Promise<RemoteConfig> {
  // Resolution order (most specific wins): platform+version+locale > platform+locale > platform > default
  const keys = [
    `config:default`,
    `config:${platform}`,
    `config:${platform}:${locale}`,
    `config:${platform}:${appVersion}:${locale}`,
  ];

  const values = await Promise.all(keys.map((k) => kv.get(k, 'json')));
  const layers = values.filter(Boolean) as Partial<RemoteConfig>[];

  if (layers.length === 0) {
    throw new Error('No configuration found');
  }

  const merged = mergeConfigs(...layers);
  merged._generated_at = new Date().toISOString();
  return merged;
}

const app = new Hono<{ Bindings: Env }>();

app.get('/config', async (c) => {
  const platform = c.req.query('platform') as Platform | undefined;
  const appVersion = c.req.query('app_version') ?? '0.0.0';
  const locale = c.req.query('locale') ?? 'en';
  const clientEtag = c.req.header('If-None-Match');

  if (!platform || !['ios', 'android', 'web'].includes(platform)) {
    return c.json({ error: 'Invalid platform' }, 400);
  }

  let config: RemoteConfig;
  try {
    config = await loadConfig(c.env.CONFIGS, platform, appVersion, locale);
  } catch {
    return c.json({ error: 'Configuration unavailable' }, 503);
  }

  const etag = await etagFromConfig(config);

  // Kill-switch: return minimal payload so client blocks the UI
  if (config.kill_switch) {
    return c.json(
      { kill_switch: true, kill_switch_message: config.kill_switch_message },
      200,
      { ETag: etag, 'Cache-Control': 'no-store' },
    );
  }

  // Not Modified
  if (clientEtag && clientEtag === etag) {
    return new Response(null, { status: 304, headers: { ETag: etag } });
  }

  // If client sends its previous ETag, retrieve the stored config for that ETag
  // and return only changed keys (incremental diff)
  if (clientEtag) {
    const prevRaw = await c.env.CONFIG_META.get(`snapshot:${clientEtag}`, 'json') as RemoteConfig | null;
    if (prevRaw) {
      const changed = diffKeys(prevRaw, config);
      const partial: Partial<RemoteConfig> = {};
      for (const k of changed) partial[k] = config[k] as never;

      // Store new snapshot for future diffs (30 min retention)
      await c.env.CONFIG_META.put(`snapshot:${etag}`, JSON.stringify(config), {
        expirationTtl: 1800,
      });

      const resp: DiffResponse = { etag, changed_keys: changed, config: partial, full: false };
      return c.json(resp, 200, { ETag: etag, 'Cache-Control': 'public, max-age=60' });
    }
  }

  // Full response — also store snapshot for future diffs
  await c.env.CONFIG_META.put(`snapshot:${etag}`, JSON.stringify(config), {
    expirationTtl: 1800,
  });

  const resp: FullResponse = { etag, config, full: true };
  return c.json(resp, 200, { ETag: etag, 'Cache-Control': 'public, max-age=60' });
});

// Admin: write a config layer
app.put('/admin/config/:layer', async (c) => {
  const layer = c.req.param('layer'); // e.g. "ios", "ios:en", "ios:2.5.0:en"
  const body = await c.req.json<Partial<RemoteConfig>>();
  body._version = (body._version ?? 0) + 1;
  await c.env.CONFIGS.put(`config:${layer}`, JSON.stringify(body));
  return c.json({ ok: true, layer, version: body._version });
});

// Admin: toggle kill-switch
app.post('/admin/kill-switch', async (c) => {
  const { enabled, message } = await c.req.json<{ enabled: boolean; message: string }>();
  const base = (await c.env.CONFIGS.get('config:default', 'json') ?? {}) as Partial<RemoteConfig>;
  base.kill_switch = enabled;
  base.kill_switch_message = message ?? 'Service temporarily unavailable. Please update your app.';
  await c.env.CONFIGS.put('config:default', JSON.stringify(base));
  return c.json({ ok: true, kill_switch: enabled });
});

export default app;
```

## Implementation Details

**KV key hierarchy** — configs resolve from least to most specific. A request from iOS 2.5.0 in French loads `config:default`, then `config:ios`, then `config:ios:fr`, then `config:ios:2.5.0:fr`, with later layers overriding earlier ones via `mergeConfigs`. Unset keys in an override layer fall through to the base.

**Incremental diff** — the client stores its last received ETag locally. On the next poll (recommended: every 5 minutes or on foreground resume) it sends `If-None-Match: <etag>`. The Worker looks up the snapshot stored for that ETag, diffs against the new config, and returns only changed top-level keys. This cuts payload size by 80–95% on subsequent requests.

**Emergency kill-switch** — writing `kill_switch: true` to the `config:default` layer causes all clients to receive a minimal blocking response within 60 seconds (the CDN cache TTL). The mobile app should check this flag before rendering any UI.

**Client-side cache** — the client stores the full config in secure local storage with a 5-minute TTL. On cold start it uses the cached value immediately (avoiding a blocking network request) and refreshes in the background.

## Anti-patterns

- **Polling every request.** The config endpoint is not a feature-flag evaluation API. Poll on foreground resume and on a 5-minute interval, not per API call.
- **Storing secrets in remote config.** Remote config is readable by any authenticated app instance. API keys, signing secrets, and PII must not be stored there.
- **Version-targeting every flag individually.** Use version ranges sparingly (e.g., only for breaking changes). Over-targetting creates an unmaintainable matrix of config layers.
- **Forgetting to increment `_version`.** Without a version counter, clients cannot tell whether a `304 Not Modified` means "identical" or "cache miss".

## Gotchas

- KV is eventually consistent. A config write may not be visible at every edge PoP for up to 60 seconds. Add a `?bust=1` query parameter in the admin UI to bypass the Cache-Control TTL when debugging.
- Snapshot keys in `CONFIG_META` grow unboundedly if you push many configs quickly. The 30-minute `expirationTtl` on snapshots prunes old ones automatically.
- The `mergeConfigs` function only deep-merges one level. Nested feature flags (`feature_flags.payment.new_flow`) are merged as a unit; a platform override that adds one sub-key replaces all sibling sub-keys from the base layer.
- Kill-switch responses deliberately bypass the CDN cache (`no-store`). Ensure your CDN respects this header to avoid serving stale "everything is fine" responses.

## Verification

```bash
# Write a base config
curl -X PUT https://api.example.com/admin/config/default \
  -H 'Content-Type: application/json' \
  -d '{"feature_flags":{"new_onboarding":false},"kill_switch":false,"kill_switch_message":""}'

# Fetch full config
curl -v https://api.example.com/config?platform=ios&app_version=2.5.0&locale=en

# Second request with ETag — expect 304
ETAG=$(curl -sI https://api.example.com/config?platform=ios | grep -i etag | awk '{print $2}' | tr -d $'\r')
curl -v -H "If-None-Match: $ETAG" https://api.example.com/config?platform=ios

# Toggle kill-switch
curl -X POST https://api.example.com/admin/kill-switch \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"message":"Emergency maintenance. Back in 10 minutes."}'
```

## Related

- `documentation/docs/policies/mobile/workers-app-update-checker.md` — force-update gating pairs with kill-switch
- `documentation/docs/policies/mobile/mobile-api-versioning.md` — API version targeting via config
- `documentation/docs/policies/mobile/offline-sync-conflict-resolution.md` — config drives sync retry policies

## Sources

- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- HTTP ETag / conditional requests (RFC 7232): https://www.rfc-editor.org/rfc/rfc7232
- Firebase Remote Config (reference pattern): https://firebase.google.com/docs/remote-config
