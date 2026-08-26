# API Versioning for Mobile Apps Using Accept Header in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Mobile apps cannot force users to upgrade immediately, so your API must support multiple versions simultaneously. Using `Accept: application/vnd.orchords.v2+json` header-based versioning keeps URLs stable, allows per-version handler modules in a single Worker, and lets you sunset old versions gracefully with standard HTTP deprecation headers.

---

## Context
Content negotiation via the `Accept` header is described in RFC 7231 and is the most REST-correct versioning strategy for mobile APIs: URLs remain unchanged across versions, clients opt into new behaviour explicitly, and intermediary caches key on `Vary: Accept`. A Cloudflare Worker parses the vendor MIME type, selects the appropriate handler module, and attaches `Deprecation` and `Sunset` response headers per RFC 8594 when a version is approaching end-of-life. Versions that have passed their sunset date return HTTP 410 Gone with a machine-readable body so mobile clients can prompt users to upgrade. D1 stores the schema in a backward-compatible way using nullable columns and default values rather than destructive migrations.

---

## Setup / Config

```toml
# wrangler.toml
name = "versioned-mobile-api"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "orchords-prod"
database_id = "<your-d1-database-id>"

[vars]
# ISO-8601 sunset dates — update as versions are retired
SUNSET_V1 = "2025-06-01T00:00:00Z"
SUNSET_V2 = "2027-01-01T00:00:00Z"
MIN_SUPPORTED_VERSION = "2"
```

D1 schema with additive migrations:

```bash
# v1 baseline
npx wrangler d1 execute orchords-prod --command "
  CREATE TABLE IF NOT EXISTS chords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frets TEXT NOT NULL,
    created_at INTEGER NOT NULL
  );
"

# v2 additive migration — new nullable column, no data loss
npx wrangler d1 execute orchords-prod --command "
  ALTER TABLE chords ADD COLUMN bpm INTEGER DEFAULT NULL;
  ALTER TABLE chords ADD COLUMN key_signature TEXT DEFAULT NULL;
"
```

---

## Implementation — Version Parser

```typescript
// src/version.ts
export type ApiVersion = 'v1' | 'v2' | 'v3';
const SUPPORTED: ApiVersion[] = ['v1', 'v2', 'v3'];

export interface ParsedAccept {
  version: ApiVersion | null;
  raw: string;
}

/**
 * Parses "application/vnd.orchords.v2+json" → { version: 'v2', raw: '...' }
 * Falls back to latest version when Accept is absent or uses plain 'application/json'.
 */
export function parseAcceptVersion(acceptHeader: string | null): ParsedAccept {
  if (!acceptHeader) return { version: 'v3', raw: '' };

  const match = acceptHeader.match(/application\/vnd\.orchords\.(v\d+)\+json/);
  if (!match) return { version: 'v3', raw: acceptHeader };

  const candidate = match[1] as ApiVersion;
  if (!SUPPORTED.includes(candidate)) return { version: null, raw: acceptHeader };
  return { version: candidate, raw: acceptHeader };
}
```

---

## Implementation — Versioned Handlers

```typescript
// src/handlers/v1.ts
import type { Env } from '../index';

export async function listChordsV1(env: Env): Promise<unknown[]> {
  const { results } = await env.DB.prepare(
    'SELECT id, name, frets FROM chords ORDER BY id DESC LIMIT 20'
  ).all();
  return results;
}
```

```typescript
// src/handlers/v2.ts
import type { Env } from '../index';

export async function listChordsV2(env: Env): Promise<unknown[]> {
  const { results } = await env.DB.prepare(
    'SELECT id, name, frets, bpm, key_signature, created_at FROM chords ORDER BY id DESC LIMIT 20'
  ).all();
  return results;
}
```

```typescript
// src/handlers/v3.ts
import type { Env } from '../index';

export async function listChordsV3(env: Env, url: URL): Promise<unknown> {
  const limit = Math.min(Number(url.searchParams.get('limit') ?? '20'), 100);
  const cursor = Number(url.searchParams.get('cursor') ?? '0');

  const { results } = await env.DB.prepare(
    'SELECT id, name, frets, bpm, key_signature, created_at FROM chords WHERE id > ? ORDER BY id ASC LIMIT ?'
  )
    .bind(cursor, limit)
    .all();

  const nextCursor = results.length === limit ? (results[results.length - 1] as { id: number }).id : null;
  return { data: results, nextCursor };
}
```

---

## Implementation — Router with Deprecation Headers

```typescript
// src/index.ts
import { parseAcceptVersion } from './version';
import { listChordsV1 } from './handlers/v1';
import { listChordsV2 } from './handlers/v2';
import { listChordsV3 } from './handlers/v3';

export interface Env {
  DB: D1Database;
  SUNSET_V1: string;
  SUNSET_V2: string;
  MIN_SUPPORTED_VERSION: string;
}

function addDeprecationHeaders(headers: Headers, sunsetDate: string, version: string): void {
  // RFC 8594 Sunset header
  headers.set('Sunset', new Date(sunsetDate).toUTCString());
  // Deprecation header (RFC draft)
  headers.set('Deprecation', 'true');
  headers.set(
    'Link',
    `<https://api.example.com/docs/migration/${version}>; rel="deprecation"`
  );
}

function versionNumber(v: string): number {
  return parseInt(v.replace('v', ''), 10);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const acceptHeader = request.headers.get('Accept');
    const { version } = parseAcceptVersion(acceptHeader);
    const minVersion = parseInt(env.MIN_SUPPORTED_VERSION, 10);

    // ── Unknown version ────────────────────────────────────────────────
    if (!version) {
      return new Response(
        JSON.stringify({ error: 'Unknown API version in Accept header' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const vNum = versionNumber(version);

    // ── Sunset / minimum version enforcement ───────────────────────────
    if (vNum < minVersion) {
      const sunsetHeader = version === 'v1' ? env.SUNSET_V1 : env.SUNSET_V2;
      return new Response(
        JSON.stringify({
          error: 'API version no longer supported',
          sunset: sunsetHeader,
          upgradeGuide: `https://api.example.com/docs/migration/${version}`,
        }),
        {
          status: 410, // HTTP 410 Gone
          headers: {
            'Content-Type': 'application/json',
            Sunset: new Date(sunsetHeader).toUTCString(),
          },
        }
      );
    }

    // ── Route to versioned handler ─────────────────────────────────────
    const responseHeaders = new Headers({
      'Content-Type': `application/vnd.orchords.${version}+json`,
      'Vary': 'Accept',
    });

    let data: unknown;

    if (url.pathname === '/chords' && request.method === 'GET') {
      if (version === 'v1') {
        data = await listChordsV1(env);
        // v1 is deprecated — add deprecation headers
        addDeprecationHeaders(responseHeaders, env.SUNSET_V1, 'v1');
      } else if (version === 'v2') {
        data = await listChordsV2(env);
        // v2 is supported but approaching sunset
        const sunsetDate = new Date(env.SUNSET_V2);
        const daysUntilSunset = (sunsetDate.getTime() - Date.now()) / 86_400_000;
        if (daysUntilSunset < 180) {
          addDeprecationHeaders(responseHeaders, env.SUNSET_V2, 'v2');
        }
      } else {
        data = await listChordsV3(env, url);
      }
    } else {
      return new Response(JSON.stringify({ error: 'Not found' }), {
        status: 404,
        headers: responseHeaders,
      });
    }

    return new Response(JSON.stringify(data), { status: 200, headers: responseHeaders });
  },
};
```

---

## Integration / Testing

```bash
# Request v3 (latest)
curl -H 'Accept: application/vnd.orchords.v3+json' \
  https://versioned-mobile-api.<subdomain>.workers.dev/chords
# Content-Type: application/vnd.orchords.v3+json

# Request v2 (deprecated within 180 days)
curl -I -H 'Accept: application/vnd.orchords.v2+json' \
  https://versioned-mobile-api.<subdomain>.workers.dev/chords
# Expect: Sunset, Deprecation, Link headers

# Request v1 (sunsetted — should 410)
curl -H 'Accept: application/vnd.orchords.v1+json' \
  https://versioned-mobile-api.<subdomain>.workers.dev/chords
# Expected: HTTP 410 Gone with upgradeGuide URL

# No Accept header → defaults to v3
curl https://versioned-mobile-api.<subdomain>.workers.dev/chords

# Verify Vary header is present (required for correct CDN caching per version)
curl -I -H 'Accept: application/vnd.orchords.v3+json' \
  https://versioned-mobile-api.<subdomain>.workers.dev/chords | grep -i vary
# Vary: Accept
```

---

## Anti-patterns
- **Versioning via URL path (`/v2/chords`)** — breaks bookmark and bookmark-sharing semantics; resources are the same thing across versions, only the representation changes.
- **Returning 200 for sunsetted versions** — 410 Gone is machine-readable; mobile apps can detect it and prompt for upgrade without hard-coding dates in the client.
- **Destructive D1 migrations (DROP COLUMN, rename)** — add columns as `DEFAULT NULL`; old app versions will ignore unknown fields, new versions can read them.
- **Forgetting `Vary: Accept`** — Cloudflare's cache will serve a v2 response to a v3 client if the cached key doesn't include the `Accept` header.

---

## Gotchas
- Safari on iOS aggressively sets `Accept: text/html,...` for WebView-initiated requests; ensure native app HTTP clients send the vendor MIME type explicitly, not the WebView default.
- `parseAcceptVersion` must handle quality values (`q=0.9`) in the Accept header if you want strict RFC compliance; the simplified version above ignores them.
- D1 `ALTER TABLE ADD COLUMN` with `DEFAULT NULL` is allowed; `ALTER TABLE ADD COLUMN NOT NULL` without a default is rejected by SQLite — always add `DEFAULT NULL` for non-breaking migrations.
- Worker env vars are strings; always `parseInt`/`parseFloat` before numeric comparison.

---

## Verification

```bash
# Unit test the version parser (Vitest)
npx vitest run src/version.test.ts

# Integration test with all versions
for v in v1 v2 v3; do
  echo "--- ${v} ---"
  curl -s -o /dev/null -w "%{http_code}" \
    -H "Accept: application/vnd.orchords.${v}+json" \
    https://versioned-mobile-api.<subdomain>.workers.dev/chords
  echo
done
# Expected: 410, 200, 200
```

---

## Related
- `workers-flutter-d1-rest-api.md`
- `workers-mobile-certificate-pinning-bypass-detect.md`
- `workers-react-native-websocket-durable-objects.md`

---

## Sources
- RFC 7231 Content Negotiation — https://datatracker.ietf.org/doc/html/rfc7231#section-5.3
- RFC 8594 Sunset HTTP Header — https://datatracker.ietf.org/doc/html/rfc8594
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers — https://developers.cloudflare.com/workers/
