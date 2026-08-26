# Scheduled Maintenance Window Enforcement via Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to take the platform offline for a planned database migration, infrastructure change, or compliance audit window. Traffic must receive a well-formed 503 with a `Retry-After` header rather than timing out or hitting broken backends. Operations teams need an emergency bypass and an automated end-of-maintenance signal so the window does not accidentally outlast the work.

## Context

Cloudflare Workers sit in front of every request before it reaches an origin or another Worker. This makes the Worker layer the natural place to intercept traffic, inspect a maintenance flag, and short-circuit with a maintenance page. Using KV as the flag store means operations can toggle maintenance on or off from any machine without a re-deploy. The flag value also carries metadata: start time, expected duration, and a bypass token — so the 503 response can include an accurate `Retry-After` and emergency operators can access the live system.

## Solution

### KV flag schema

Store a single JSON value under the key `maintenance:config` in a dedicated KV namespace.

```typescript
// types/maintenance.ts
export interface MaintenanceConfig {
  /** Whether maintenance mode is currently active */
  active: boolean;
  /** ISO-8601 UTC start time */
  startedAt: string;
  /** Expected duration in seconds */
  durationSeconds: number;
  /** Plaintext reason shown to end users */
  reason: string;
  /** SHA-256 hex of the bypass secret; compare with crypto.subtle */
  bypassTokenHash: string;
  /** Contact address shown on maintenance page */
  contactEmail: string;
}
```

Set the flag before maintenance begins:

```bash
SECRET="$(openssl rand -hex 32)"
HASH="$(echo -n "$SECRET" | sha256sum | awk '{print $1}')"
echo "Bypass token (store securely): $SECRET"

wrangler kv:key put maintenance:config \
  "$(jq -n \
    --arg s "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg h "$HASH" \
    '{active:true, startedAt:$s, durationSeconds:3600, reason:"Scheduled DB migration", bypassTokenHash:$h, contactEmail:"ops@example.com"}')"
  --namespace-id "$KV_NAMESPACE_ID" --env production
```

### Middleware Worker

```typescript
// src/index.ts
import type { MaintenanceConfig } from '../types/maintenance';

export interface Env {
  MAINTENANCE: KVNamespace;
  ORIGIN: Fetcher;
}

const MAINTENANCE_KEY = 'maintenance:config';
const CACHE_TTL_MS = 10_000; // re-read KV at most every 10 s

let cachedConfig: MaintenanceConfig | null = null;
let cacheExpiry = 0;

async function getMaintenanceConfig(kv: KVNamespace): Promise<MaintenanceConfig | null> {
  const now = Date.now();
  if (cachedConfig !== null && now < cacheExpiry) return cachedConfig;
  const raw = await kv.get(MAINTENANCE_KEY, 'text');
  if (!raw) {
    cachedConfig = null;
    cacheExpiry = now + CACHE_TTL_MS;
    return null;
  }
  cachedConfig = JSON.parse(raw) as MaintenanceConfig;
  cacheExpiry = now + CACHE_TTL_MS;
  return cachedConfig;
}

async function verifyBypassToken(
  token: string,
  expectedHash: string
): Promise<boolean> {
  const enc = new TextEncoder();
  const digest = await crypto.subtle.digest('SHA-256', enc.encode(token));
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return hex === expectedHash;
}

function retryAfterSeconds(config: MaintenanceConfig): number {
  const endMs =
    new Date(config.startedAt).getTime() + config.durationSeconds * 1000;
  const remaining = Math.max(0, Math.ceil((endMs - Date.now()) / 1000));
  return remaining;
}

function maintenancePage(config: MaintenanceConfig, retryAfter: number): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Scheduled Maintenance</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 520px; margin: 10vh auto; padding: 2rem; text-align: center; color: #1a1a1a; }
    h1 { font-size: 1.75rem; margin-bottom: .5rem; }
    p  { color: #555; line-height: 1.6; }
    .eta { font-weight: 600; color: #0066cc; }
  </style>
</head>
<body>
  <h1>We will be right back</h1>
  <p>${config.reason}</p>
  <p>Estimated return: <span class="eta">${Math.ceil(retryAfter / 60)} minute(s)</span>.</p>
  <p>Questions? <a href="mailto:${config.contactEmail}">${config.contactEmail}</a></p>
</body>
</html>`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const config = await getMaintenanceConfig(env.MAINTENANCE);

    if (config?.active) {
      // Check for emergency bypass token in Authorization header
      const authHeader = request.headers.get('Authorization') ?? '';
      const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';
      const bypassed = token
        ? await verifyBypassToken(token, config.bypassTokenHash)
        : false;

      if (!bypassed) {
        const retryAfter = retryAfterSeconds(config);
        const html = maintenancePage(config, retryAfter);
        return new Response(html, {
          status: 503,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Retry-After': String(retryAfter),
            'Cache-Control': 'no-store',
            'X-Maintenance-Start': config.startedAt,
          },
        });
      }
    }

    return env.ORIGIN.fetch(request);
  },
};
```

### Automated maintenance end via Cron Trigger

```typescript
// src/scheduler.ts  (add to same Worker)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const config = await env.MAINTENANCE.get(MAINTENANCE_KEY, 'json') as MaintenanceConfig | null;
    if (!config?.active) return;

    const endMs = new Date(config.startedAt).getTime() + config.durationSeconds * 1000;
    if (Date.now() >= endMs) {
      const updated: MaintenanceConfig = { ...config, active: false };
      await env.MAINTENANCE.put(MAINTENANCE_KEY, JSON.stringify(updated));
      console.log('Maintenance window closed automatically.');
    }
  },
};
```

Add the trigger to `wrangler.toml`:

```toml
[[triggers.crons]]
cron = "* * * * *"
```

### Clearing maintenance manually

```bash
wrangler kv:key put maintenance:config \
  '{"active":false,"startedAt":"","durationSeconds":0,"reason":"","bypassTokenHash":"","contactEmail":"ops@example.com"}' \
  --namespace-id "$KV_NAMESPACE_ID" --env production
```

## Implementation Details

- The in-memory cache (`cachedConfig`, `cacheExpiry`) reduces KV reads to at most one per isolate per 10 s. Across all PoPs this means the maintenance flag propagates within ~10 s of a KV write — acceptable for a planned window.
- The bypass token is never stored in plaintext. Only the SHA-256 hash lives in KV. An attacker who reads the KV value cannot reconstruct the token.
- The `Retry-After` header is dynamic: it reflects the actual remaining duration rather than a static value, so crawlers and monitoring tools back off proportionally.
- The cron trigger fires once per minute. Combine it with a monitoring alert on the `maintenance:config` key to avoid human error leaving the flag on after work completes.

## Anti-patterns

- **Returning a 200 with a maintenance page body.** Uptime monitors and SEO crawlers will not understand the page is temporary and may cache the body or de-index the site.
- **Hard-coding the bypass token in the Worker.** Rotate the hash in KV without a re-deploy; never commit secrets to source control.
- **Setting a very long cache TTL for the KV read.** A 10-minute TTL means traffic flows to a broken origin for 10 minutes after you set the flag — keep it at 10–30 s.
- **Not serving a `Cache-Control: no-store` header on the 503.** CDN edge nodes may cache the 503 response and continue serving it after maintenance ends.

## Gotchas

- KV consistency is eventual across regions. After setting `active: true`, some PoPs may continue forwarding requests for up to ~60 s before all caches expire. For strict windows, set the flag 2 minutes before the actual maintenance start.
- The Cron Trigger runs in a separate isolate from the `fetch` handler; it does not share the in-memory cache. The scheduler always reads fresh from KV.
- `crypto.subtle.digest` is async. Do not block the warm-path check on bypass token verification for every request; only call it when an `Authorization` header is present.
- Workers free tier has a 1 000 KV reads/day limit per namespace. At one read per isolate per 10 s under sustained traffic, production namespaces should be on the paid tier.

## Verification

1. Set the flag with `active: true` and curl the Worker: confirm HTTP 503, `Retry-After` header present, and HTML body renders.
2. Add `Authorization: Bearer <bypass-token>` header: confirm HTTP 200 from origin.
3. Set `durationSeconds: 60`, wait 90 s, curl again: confirm the cron cleared the flag and the Worker returns 200.
4. Check `wrangler tail` for `Maintenance window closed automatically.` log line.

## Related

- `canary-deployment-kv-flag.md`
- `workers-feature-flag-deployment-kv.md`
- `workers-deployment-verification-smoke-tests.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
