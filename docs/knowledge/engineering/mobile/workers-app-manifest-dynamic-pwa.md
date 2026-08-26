# Dynamic PWA Manifest Generation with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A multi-tenant SaaS needs each tenant to see its own branded PWA — custom `name`, `theme_color`, splash icon, and `start_url` — without maintaining one static `manifest.json` per tenant. The Worker generates the manifest on-the-fly from KV-stored tenant config, caches it at the edge, and tracks install-prompt events via Cloudflare Analytics Engine.

## Context

PWA install criteria require the `manifest.json` to be served with `Content-Type: application/manifest+json` and must be reachable within the same origin as the page. When a single Worker serves hundreds of tenants under subpaths or subdomains, a static manifest cannot satisfy per-tenant branding. Workers solve this by:

1. Reading tenant config from KV on manifest request.
2. Returning a generated JSON manifest with correct `Cache-Control` and ETag headers.
3. Persisting install-prompt analytics without a separate backend.
4. Scoping `start_url` to the authenticated user's home page so deep-link installs work.

## Solution

### 1. KV Config Schema

```typescript
// src/types.ts
export interface Env {
  TENANT_CONFIG: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;  // bound in wrangler.toml
}

export interface TenantConfig {
  tenantId: string;
  name: string;
  shortName: string;
  themeColor: string;   // hex e.g. "#3B82F6"
  backgroundColor: string;
  iconUrl512: string;   // absolute URL to a 512×512 PNG stored in R2/CDN
  iconUrl192: string;
  startUrlTemplate: string; // e.g. "/app/{userId}/home"
  scope: string;            // e.g. "/app/{userId}/"
  display: 'standalone' | 'minimal-ui' | 'fullscreen';
  categories: string[];
}
```

### 2. Wrangler Bindings

```toml
[[kv_namespaces]]
binding = "TENANT_CONFIG"
id      = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "pwa_events"
```

### 3. Tenant Config Loader with KV Cache

```typescript
// src/config.ts
import type { Env, TenantConfig } from './types';

const IN_MEMORY_CACHE = new Map<string, { config: TenantConfig; cachedAt: number }>();
const MEMORY_TTL_MS  = 60_000; // 1 min in-memory cache per isolate

export async function getTenantConfig(
  env: Env,
  tenantId: string,
): Promise<TenantConfig | null> {
  const cached = IN_MEMORY_CACHE.get(tenantId);
  if (cached && Date.now() - cached.cachedAt < MEMORY_TTL_MS) {
    return cached.config;
  }

  const raw = await env.TENANT_CONFIG.get(`tenant:${tenantId}`, { type: 'json' });
  if (!raw) return null;

  const config = raw as TenantConfig;
  IN_MEMORY_CACHE.set(tenantId, { config, cachedAt: Date.now() });
  return config;
}

export async function setTenantConfig(env: Env, config: TenantConfig): Promise<void> {
  await env.TENANT_CONFIG.put(`tenant:${config.tenantId}`, JSON.stringify(config));
  IN_MEMORY_CACHE.delete(config.tenantId); // invalidate isolate cache
}
```

### 4. Manifest Builder

```typescript
// src/manifest.ts
import type { TenantConfig } from './types';

export function buildManifest(config: TenantConfig, userId?: string): object {
  const startUrl = userId
    ? config.startUrlTemplate.replace('{userId}', userId)
    : config.startUrlTemplate.replace('/{userId}', '').replace('{userId}', '');

  const scope = userId
    ? config.scope.replace('{userId}', userId)
    : config.scope.replace('/{userId}', '/').replace('{userId}', '');

  return {
    name:             config.name,
    short_name:       config.shortName,
    description:      `${config.name} — Progressive Web App`,
    start_url:        startUrl,
    scope:            scope,
    display:          config.display,
    theme_color:      config.themeColor,
    background_color: config.backgroundColor,
    lang:             'en',
    dir:              'ltr',
    orientation:      'portrait-primary',
    categories:       config.categories,
    icons: [
      {
        src:     config.iconUrl192,
        sizes:   '192x192',
        type:    'image/png',
        purpose: 'any',
      },
      {
        src:     config.iconUrl512,
        sizes:   '512x512',
        type:    'image/png',
        purpose: 'any maskable',
      },
    ],
    screenshots: [],
    shortcuts:   [],
  };
}

export function etagForConfig(config: TenantConfig, userId?: string): string {
  const seed = JSON.stringify({ id: config.tenantId, uid: userId ?? '', tc: config.themeColor });
  // Workers have no crypto.createHash; use a lightweight djb2 hash
  let h = 5381;
  for (let i = 0; i < seed.length; i++) h = ((h << 5) + h) ^ seed.charCodeAt(i);
  return `"${(h >>> 0).toString(16)}"`;
}
```

### 5. Analytics Engine Tracking

```typescript
// src/analytics.ts
import type { Env } from './types';

export type PwaEventType = 'manifest_served' | 'install_prompt' | 'install_accepted' | 'install_dismissed';

export function trackPwaEvent(
  env: Env,
  event: PwaEventType,
  tenantId: string,
  userId?: string,
): void {
  // Analytics Engine writeDataPoint is fire-and-forget — no await needed
  env.ANALYTICS.writeDataPoint({
    blobs:   [event, tenantId, userId ?? 'anonymous'],
    doubles: [Date.now()],
    indexes: [tenantId],
  });
}
```

### 6. Worker Entry Point

```typescript
// src/index.ts
import type { Env } from './types';
import { getTenantConfig } from './config';
import { buildManifest, etagForConfig } from './manifest';
import { trackPwaEvent } from './analytics';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Route: GET /manifest.json?tenant=<id>[&userId=<id>]
    if (url.pathname === '/manifest.json' && request.method === 'GET') {
      return handleManifest(request, env, url);
    }

    // Route: POST /pwa-event  { event, tenantId, userId }
    if (url.pathname === '/pwa-event' && request.method === 'POST') {
      return handlePwaEvent(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};

async function handleManifest(request: Request, env: Env, url: URL): Promise<Response> {
  const tenantId = url.searchParams.get('tenant');
  const userId   = url.searchParams.get('userId') ?? undefined;

  if (!tenantId) return new Response('Missing tenant', { status: 400 });

  const config = await getTenantConfig(env, tenantId);
  if (!config) return new Response('Tenant not found', { status: 404 });

  const etag = etagForConfig(config, userId);

  // Conditional GET support
  if (request.headers.get('If-None-Match') === etag) {
    return new Response(null, { status: 304 });
  }

  const manifest = buildManifest(config, userId);

  trackPwaEvent(env, 'manifest_served', tenantId, userId);

  return new Response(JSON.stringify(manifest, null, 2), {
    headers: {
      'Content-Type':  'application/manifest+json',
      'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
      'ETag':          etag,
      'Vary':          'Accept-Encoding',
    },
  });
}

async function handlePwaEvent(request: Request, env: Env): Promise<Response> {
  const { event, tenantId, userId } = await request.json<{
    event: 'install_prompt' | 'install_accepted' | 'install_dismissed';
    tenantId: string;
    userId?: string;
  }>();

  if (!event || !tenantId) return new Response('Bad request', { status: 400 });

  trackPwaEvent(env, event, tenantId, userId);
  return Response.json({ ok: true });
}
```

### 7. Service Worker — Manifest Link and Install Prompt Tracking

```typescript
// public/app.ts (client-side)
const tenantId = document.documentElement.dataset.tenant;
const userId   = document.documentElement.dataset.userId;

// Inject dynamic manifest link
const link = document.createElement('link');
link.rel  = 'manifest';
link.href = `/manifest.json?tenant=${tenantId}&userId=${userId}`;
document.head.appendChild(link);

// Track install prompt
window.addEventListener('beforeinstallprompt', (e: Event) => {
  e.preventDefault();
  const promptEvent = e as BeforeInstallPromptEvent;

  fetch('/pwa-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event: 'install_prompt', tenantId, userId }),
  });

  // Show your own install button
  document.getElementById('install-btn')?.addEventListener('click', async () => {
    promptEvent.prompt();
    const { outcome } = await promptEvent.userChoice;
    fetch('/pwa-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event: outcome === 'accepted' ? 'install_accepted' : 'install_dismissed',
        tenantId,
        userId,
      }),
    });
  });
});

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}
```

## Implementation Details

- **Manifest link injection**: Avoid a static `<link rel="manifest">` in the HTML shell; inject it after hydration so `userId` is available. The browser will still pick it up for install eligibility.
- **KV read latency**: The in-memory `Map` cache caps KV reads to once per minute per isolate — critical because `manifest.json` is fetched on every page load.
- **Icon hosting**: Store icons in R2 and serve via a Worker or Cloudflare CDN. The icon URL in KV should be a fully qualified URL so the manifest validator can fetch it independently.
- **`start_url` and scope matching**: If `start_url` is `/app/user123/home` and `scope` is `/app/user123/`, all navigation within that scope keeps the user inside the installed PWA shell. A scope mismatch opens the browser.
- **ETag stability**: Derive the ETag from the config hash, not a timestamp, so CDN nodes can serve conditional `304` responses without invalidating on every Worker restart.
- **Analytics Engine dataset**: Data is available within minutes in Cloudflare's GraphQL analytics API; useful for cohort analysis of install funnel conversion.

## Anti-patterns

- **Do not** serve the manifest with `Cache-Control: no-store`. Chrome will not trigger the install prompt for manifests it cannot cache.
- **Do not** place tenant config in environment variables — they require a Worker redeploy for every config change. Use KV.
- **Do not** embed `userId` in the manifest's `name` — it gets shown in the OS home screen and app list, which would expose PII.
- **Do not** use relative `start_url` values without a leading `/`. Some browsers interpret them relative to the manifest URL rather than the origin.

## Gotchas

- Safari 16.4+ supports PWA install but ignores `shortcuts` and some manifest fields. Test on real iOS devices; the simulator differs.
- `maskable` icons must have at least 10% safe-zone padding. Use a tool like https://maskable.app to verify before storing in R2.
- Analytics Engine `writeDataPoint` is best-effort and may drop points under extreme load. Do not use it for billing-critical counters.
- The `Vary: Accept-Encoding` header is important if your CDN compresses JSON responses — without it, clients may receive corrupted payloads after a Brotli-compressed cached response is served to a client that requested identity encoding.

## Verification

1. `curl -s 'https://your-worker.example.com/manifest.json?tenant=acme&userId=u42' | jq .`
   Confirm `start_url`, `theme_color`, and `icons` reflect the KV config.
2. Open Chrome DevTools → Application → Manifest. Confirm no warnings.
3. Run Lighthouse PWA audit — score should reach 100 on manifest criteria.
4. Verify ETag caching: run the same `curl` twice with `-I`; second response should return `304`.
5. Query Analytics Engine: `SELECT blob1, count() FROM pwa_events GROUP BY blob1` to see event breakdown.

## Related

- `workers-web-push-vapid-notifications.md` — push subscription during PWA install
- `workers-device-fingerprint-session-kv.md` — session binding post-install
- Cloudflare Analytics Engine docs: https://developers.cloudflare.com/analytics/analytics-engine/
- Web App Manifest spec: https://www.w3.org/TR/appmanifest/

## Sources

- W3C Web Application Manifest (Level 1)
- Cloudflare Workers KV documentation
- Cloudflare Analytics Engine Workers Binding API
- MDN — `BeforeInstallPromptEvent`
