# API Versioning and Deprecation Security in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your anonymous social platform ships `/api/v1/posts` alongside a new `/api/v2/posts` that enforces stricter
authorization. Old clients keep calling v1. You need to sunset v1 safely without leaving an unguarded attack
surface open indefinitely, without breaking legitimate clients mid-deprecation, and without leaking
version-specific information attackers can exploit to target the weaker endpoint.

---

## Context

API versioning is not only a developer-experience concern — it is a security boundary. Each active version
multiplies your attack surface. Older versions often lack newer mitigations (schema validation, rate-limiting
tiers, audit-log enrichment). Anonymous platforms face an additional risk: unauthenticated callers may
deliberately pin to the oldest version to avoid tighter controls introduced in later iterations.

Cloudflare Workers provides deterministic routing, `Sunset` and `Deprecation` header support, D1 for tracking
client adoption, and KV for feature-flag-gated version enforcement — everything needed for a rigorous
deprecation pipeline.

---

## 1. Version Routing with Hard Isolation

Route versions at the Worker boundary, not inside shared handlers. Each version gets its own validation
and authorization middleware chain so a misconfiguration in v2 cannot accidentally affect v1's response
shape, and vice versa.

```typescript
// src/router.ts
import { handleV1 } from './v1/router';
import { handleV2 } from './v2/router';

export async function routeByVersion(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const url = new URL(request.url);
  const [, , version] = url.pathname.split('/'); // /api/v1/...

  switch (version) {
    case 'v1':
      return handleV1(request, env, ctx);
    case 'v2':
      return handleV2(request, env, ctx);
    default:
      return new Response(
        JSON.stringify({ error: 'unknown_version', supported: ['v2'] }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
  }
}
```

Never fall through to a default handler that serves a "latest" alias — an attacker who discovers the alias
can bypass version-specific controls.

---

## 2. Sunset and Deprecation Headers

RFC 8594 (`Sunset`) and the IETF draft (`Deprecation`) give clients machine-readable notice. Inject them
centrally so they cannot be omitted by individual handlers.

```typescript
// src/middleware/versioning.ts
const SUNSET_DATES: Record<string, Date> = {
  v1: new Date('2026-12-01T00:00:00Z'),
};

export function injectVersionHeaders(
  response: Response,
  version: string
): Response {
  const headers = new Headers(response.headers);

  const sunset = SUNSET_DATES[version];
  if (sunset) {
    headers.set('Sunset', sunset.toUTCString());
    headers.set(
      'Deprecation',
      `date="${sunset.toISOString()}"`
    );
    headers.set(
      'Link',
      '<https://api.example.com/api/v2>; rel="successor-version"'
    );
    headers.set('Warning', '299 - "This API version is deprecated"');
  }

  return new Response(response.body, {
    status: response.status,
    headers,
  });
}
```

---

## 3. Tracking Client Adoption in D1

Before hard-sunsetting a version, you must know who still calls it. Store per-client version usage in D1
with a coarse timestamp so you can alert stragglers without logging full request payloads.

```typescript
// src/middleware/version-telemetry.ts
export async function recordVersionUsage(
  env: Env,
  version: string,
  clientId: string // hashed API key or anonymous fingerprint
): Promise<void> {
  // Upsert: update last_seen, increment call_count
  await env.DB.prepare(
    `INSERT INTO api_version_usage (client_id, version, first_seen, last_seen, call_count)
     VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
     ON CONFLICT (client_id, version)
     DO UPDATE SET last_seen = CURRENT_TIMESTAMP,
                   call_count = call_count + 1`
  )
    .bind(clientId, version)
    .run();
}

// Schema (run once via migration):
// CREATE TABLE api_version_usage (
//   client_id  TEXT    NOT NULL,
//   version    TEXT    NOT NULL,
//   first_seen TEXT    NOT NULL,
//   last_seen  TEXT    NOT NULL,
//   call_count INTEGER NOT NULL DEFAULT 1,
//   PRIMARY KEY (client_id, version)
// );
```

---

## 4. Staged Enforcement via KV Feature Flags

Hard cutover breaks clients. Use KV to control the enforcement mode per version:
`sunset_mode: warn | block_new | block_all`.

```typescript
// src/middleware/sunset-enforcement.ts
type SunsetMode = 'warn' | 'block_new' | 'block_all';

interface SunsetConfig {
  mode: SunsetMode;
  cutoverEpoch: number; // unix ms — clients registered after this are "new"
}

export async function enforceSunset(
  request: Request,
  env: Env,
  version: string,
  clientRegisteredAt: number
): Promise<Response | null> {
  const raw = await env.VERSION_FLAGS.get(`sunset:${version}`, 'json');
  if (!raw) return null; // version not sunsetted

  const config = raw as SunsetConfig;

  if (config.mode === 'block_all') {
    return new Response(
      JSON.stringify({
        error: 'version_sunset',
        message: `${version} is no longer supported. Migrate to v2.`,
        migration_guide: 'https://docs.example.com/migration/v2',
      }),
      { status: 410, headers: { 'Content-Type': 'application/json' } }
    );
  }

  if (
    config.mode === 'block_new' &&
    clientRegisteredAt > config.cutoverEpoch
  ) {
    return new Response(
      JSON.stringify({ error: 'version_unavailable_for_new_clients' }),
      { status: 410 }
    );
  }

  return null; // warn mode: let request through, headers set upstream
}
```

---

## 5. Monitoring Deprecated Endpoint Abuse

Attackers sometimes deliberately target deprecated versions to exploit known-unfixed vulnerabilities or
bypass newer WAF rules. Emit security events via Analytics Engine when deprecated-version traffic spikes.

```typescript
// src/middleware/version-abuse-detector.ts
const DEPRECATED_VERSIONS = new Set(['v1']);

export function emitVersionAbuseEvent(
  env: Env,
  request: Request,
  version: string,
  clientId: string
): void {
  if (!DEPRECATED_VERSIONS.has(version)) return;

  env.ANALYTICS.writeDataPoint({
    blobs: [
      version,
      clientId,
      request.headers.get('cf-connecting-ip') ?? 'unknown',
      request.headers.get('user-agent') ?? '',
    ],
    doubles: [Date.now()],
    indexes: [`deprecated_version:${version}`],
  });
}
```

Set a Workers Analytics Engine alert: if `deprecated_version:v1` exceeds N events per minute from a single
IP range, trigger a WAF block rule via the Cloudflare API.

---

## 6. Preventing Version Downgrade Attacks

A version downgrade attack occurs when a client (or attacker posing as a client) requests `/api/v1/auth`
after your platform has patched a vulnerability in v2. Mitigate by requiring authenticated clients to
declare a minimum supported version in their API key metadata.

```typescript
// src/auth/version-check.ts
interface ApiKeyMeta {
  clientId: string;
  minVersion: number; // e.g. 2 = must use v2+
  issuedAt: number;
}

export async function assertVersionFloor(
  requestedVersion: string,
  keyMeta: ApiKeyMeta
): Promise<void> {
  const requested = parseInt(requestedVersion.replace('v', ''), 10);
  if (requested < keyMeta.minVersion) {
    throw new Response(
      JSON.stringify({
        error: 'version_downgrade_rejected',
        minimum_version: `v${keyMeta.minVersion}`,
      }),
      { status: 403 }
    );
  }
}
```

---

## Anti-patterns

- **Alias `/api/latest`** pointing to the newest version — attackers probe this to detect when mitigations
  change. Use explicit version strings only.
- **Shared authentication middleware across versions** — if v2 adds a claim validation step, v1 sharing
  the same middleware object may skip it due to short-circuit logic.
- **Deleting old version routes without a 410 response** — returning 404 for a sunsetted endpoint leaks
  nothing, but legitimate clients cannot distinguish "wrong path" from "sunset". Always return 410 Gone.
- **Logging version in plaintext alongside PII** — version telemetry tables should use hashed client IDs,
  not raw tokens or user identifiers.
- **Enforcing sunset only client-side** — the Worker must enforce; JS-level "upgrade" banners are cosmetic.

---

## Gotchas

- `Sunset` header value must be an HTTP date (`toUTCString()`), not ISO 8601. Some clients reject ISO 8601
  in this header.
- D1 upsert uses `ON CONFLICT DO UPDATE` which requires the conflicting columns to be in a `PRIMARY KEY`
  or `UNIQUE` constraint — add both `client_id` and `version` to the key.
- KV reads inside a middleware chain add ~1–5 ms of latency. Cache the sunset config in a module-level
  `Map` refreshed every 60 seconds via a scheduled Worker to keep hot paths fast.
- Analytics Engine blobs must be strings; coerce numeric fields with `.toString()` before writing.
- Workers do not natively propagate `version` context across service bindings — pass it explicitly in
  a request header or binding argument, otherwise inner Workers cannot emit correct telemetry.

---

## Verification

```bash
# 1. Confirm Sunset header on v1 response
curl -si https://api.example.com/api/v1/health | grep -i sunset

# 2. Confirm 410 after block_all is set in KV
wrangler kv key put --binding=VERSION_FLAGS sunset:v1 \
  '{"mode":"block_all","cutoverEpoch":0}'
curl -si https://api.example.com/api/v1/health | head -1
# expect: HTTP/2 410

# 3. Query adoption table
wrangler d1 execute example project-db \
  --command="SELECT version, COUNT(*) as clients, MAX(last_seen) as last_active
             FROM api_version_usage GROUP BY version ORDER BY version;"
```

---

## Related

- `api-schema-validation-openapi-zod-workers.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `workers-tail-workers-security-event-streaming.md`
- `workers-environment-variable-hygiene.md`
- `audit-log-security.md`

---

## Sources

- RFC 8594 — The Sunset HTTP Header Field (2019)
- IETF draft-ietf-httpapi-deprecation-header — Deprecation HTTP Header Field
- Cloudflare Analytics Engine documentation — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- OWASP API Security Top 10 2023 — API9:2023 Improper Inventory Management
