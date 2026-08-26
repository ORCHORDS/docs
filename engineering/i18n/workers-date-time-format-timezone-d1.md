# Date/Time Formatting with User Timezone Stored in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Worker API returns timestamps that must be formatted in the authenticated user's preferred timezone. Users can update their timezone preference through a settings endpoint, and the preference must survive across sessions without requiring a client-side conversion.

---

## Context
D1 is Cloudflare's SQLite-compatible database, accessible from Workers with zero-latency reads in most regions. Storing timezone as an IANA timezone string (e.g. `"America/Toronto"`) in a `users` table lets you use `Intl.DateTimeFormat` — which accepts any IANA identifier — to produce correctly offset and formatted date strings in the Worker. The preference is also embedded in the JWT claim (`tz`) so that the Worker can format dates without an extra D1 read on every request. When the JWT claim is absent (e.g. public endpoints), the Worker falls back to `cf.timezone` from the Cloudflare geolocation data.

---

## Setup / Config

```toml
# wrangler.toml
name = "datetime-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "app-db"
database_id = "YOUR_D1_DATABASE_ID"

[vars]
JWT_SECRET = "change-me-in-production"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_LOCALE = "en-US"
```

```bash
# Create D1 database
wrangler d1 create app-db

# Apply schema
wrangler d1 execute app-db --command "
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  locale TEXT NOT NULL DEFAULT 'en-US',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

INSERT OR IGNORE INTO users (id, email, timezone, locale)
VALUES
  ('user-1', 'alice@example.com', 'America/New_York', 'en-US'),
  ('user-2', 'bob@example.com', 'Europe/Paris', 'fr-FR'),
  ('user-3', 'carol@example.com', 'Asia/Tokyo', 'ja-JP');
"
```

---

## Implementation

```typescript
// src/index.ts
import { SignJWT, jwtVerify } from 'jose';

export interface Env {
  DB: D1Database;
  JWT_SECRET: string;
  DEFAULT_TIMEZONE: string;
  DEFAULT_LOCALE: string;
}

interface UserRow {
  id: string;
  email: string;
  timezone: string;
  locale: string;
}

interface JWTPayload {
  sub: string;
  email: string;
  tz: string;
  locale: string;
  iat: number;
  exp: number;
}

// IANA timezone validation — Intl throws for invalid names
function isValidTimezone(tz: string): boolean {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

/**
 * Format a UTC timestamp string for display in the user's timezone.
 */
function formatDateTime(
  isoString: string,
  locale: string,
  timeZone: string,
): string {
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return isoString; // invalid date passthrough
  return new Intl.DateTimeFormat(locale, {
    timeZone,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  }).format(date);
}

/**
 * Resolve timezone from: JWT claim -> D1 lookup -> cf.timezone -> default.
 */
async function resolveTimezone(
  request: Request,
  env: Env,
): Promise<{ timezone: string; locale: string; source: string }> {
  const cf = request.cf as { timezone?: string } | undefined;

  // 1. Try JWT
  const authHeader = request.headers.get('Authorization');
  if (authHeader?.startsWith('Bearer ')) {
    const token = authHeader.slice(7);
    try {
      const secret = new TextEncoder().encode(env.JWT_SECRET);
      const { payload } = await jwtVerify(token, secret);
      const claims = payload as unknown as JWTPayload;
      if (claims.tz && isValidTimezone(claims.tz)) {
        return { timezone: claims.tz, locale: claims.locale ?? env.DEFAULT_LOCALE, source: 'jwt' };
      }
    } catch { /* expired or invalid — fall through */ }
  }

  // 2. Try cf.timezone (geolocation)
  if (cf?.timezone && isValidTimezone(cf.timezone)) {
    return { timezone: cf.timezone, locale: env.DEFAULT_LOCALE, source: 'cf.timezone' };
  }

  // 3. Default
  return { timezone: env.DEFAULT_TIMEZONE, locale: env.DEFAULT_LOCALE, source: 'default' };
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // GET /format?ts=2026-08-24T12:00:00Z
    if (url.pathname === '/format') {
      const ts = url.searchParams.get('ts') ?? new Date().toISOString();
      const { timezone, locale, source } = await resolveTimezone(request, env);
      const formatted = formatDateTime(ts, locale, timezone);
      return Response.json({ ts, timezone, locale, source, formatted });
    }

    // PUT /path/to/timezone  {"timezone": "America/Los_Angeles"}
    const tzUpdateMatch = url.pathname.match(/^\/users\/([^/]+)\/timezone$/);
    if (tzUpdateMatch && request.method === 'PUT') {
      const userId = tzUpdateMatch[1];
      let body: { timezone?: string; locale?: string };
      try {
        body = await request.json();
      } catch {
        return Response.json({ error: 'Invalid JSON' }, { status: 400 });
      }

      const newTz = body.timezone;
      if (!newTz || !isValidTimezone(newTz)) {
        return Response.json({ error: 'Invalid IANA timezone' }, { status: 422 });
      }

      const newLocale = body.locale ?? env.DEFAULT_LOCALE;

      const result = await env.DB.prepare(
        `UPDATE users
         SET timezone = ?, locale = ?, updated_at = datetime('now')
         WHERE id = ?
         RETURNING id, email, timezone, locale`,
      )
        .bind(newTz, newLocale, userId)
        .first<UserRow>();

      if (!result) {
        return Response.json({ error: 'User not found' }, { status: 404 });
      }

      // Issue a fresh JWT with updated tz claim
      const secret = new TextEncoder().encode(env.JWT_SECRET);
      const token = await new SignJWT({
        sub: result.id,
        email: result.email,
        tz: result.timezone,
        locale: result.locale,
      })
        .setProtectedHeader({ alg: 'HS256' })
        .setIssuedAt()
        .setExpirationTime('7d')
        .sign(secret);

      return Response.json({ user: result, token });
    }

    // GET /users/:id
    const userMatch = url.pathname.match(/^\/users\/([^/]+)$/);
    if (userMatch && request.method === 'GET') {
      const user = await env.DB.prepare(
        'SELECT id, email, timezone, locale FROM users WHERE id = ?',
      )
        .bind(userMatch[1])
        .first<UserRow>();
      if (!user) return Response.json({ error: 'Not found' }, { status: 404 });
      return Response.json(user);
    }

    return Response.json({ error: 'Not found' }, { status: 404 });
  },
};
```

---

## Integration / Testing

```bash
# Start dev server with D1 local SQLite
npx wrangler dev

# Format a timestamp — no auth (uses cf.timezone or default)
curl 'http://localhost:8787/format?ts=2026-08-24T18:30:00Z'
# {"ts":"2026-08-24T18:30:00Z","timezone":"UTC","locale":"en-US","source":"default",
#  "formatted":"August 24, 2026 at 06:30:00 PM UTC"}

# Update user timezone
curl -X PUT 'http://localhost:8787/path/to/timezone' \
  -H 'Content-Type: application/json' \
  -d '{"timezone": "America/Los_Angeles", "locale": "en-US"}'
# Returns updated user + fresh JWT

# Use the JWT to format in user's timezone
TOKEN="<paste token from above>"
curl 'http://localhost:8787/format?ts=2026-08-24T18:30:00Z' \
  -H "Authorization: Bearer $TOKEN"
# {"timezone":"America/Los_Angeles","source":"jwt","formatted":"August 24, 2026 at 11:30:00 AM PDT"}

# Verify rejection of invalid timezone
curl -X PUT 'http://localhost:8787/path/to/timezone' \
  -H 'Content-Type: application/json' \
  -d '{"timezone": "Mars/Olympus"}'
# {"error":"Invalid IANA timezone"}

# Query D1 directly to confirm the update
wrangler d1 execute app-db --command \
  "SELECT id, timezone, updated_at FROM users WHERE id = 'user-1'"
```

---

## Anti-patterns
- **Storing timezone offset as `+05:30` instead of IANA name** — offsets do not handle DST transitions; always store IANA identifiers.
- **Formatting dates client-side only** — inconsistent formatting when the same timestamp is rendered server-side for SEO or email notifications.
- **Querying D1 for timezone on every API response** — embed `tz` in the JWT claim; only hit D1 when the preference is updated.
- **Skipping `RETURNING` clause on UPDATE** — a separate SELECT after UPDATE creates a race condition; use `RETURNING` for atomic read-after-write.

---

## Gotchas
- `Intl.DateTimeFormat` in Workers supports IANA timezones but requires the full CLDR dataset — only available on compatibility dates `2024-09-23` or later.
- D1's `datetime('now')` produces UTC timestamps without a `Z` suffix; always parse with `new Date(val + 'Z')` or store with the suffix explicitly.
- `jwtVerify` from `jose` works in Workers with no polyfills needed as of `jose` v5+.
- `cf.timezone` is `undefined` (not `null`) when not present; use optional chaining.

---

## Verification

```bash
# Check D1 table schema
wrangler d1 execute app-db --command ".schema users"

# Confirm all rows have valid IANA timezone
wrangler d1 execute app-db --command \
  "SELECT id, timezone FROM users"

# End-to-end: deploy to staging and verify formatted output
npx wrangler deploy --env staging
curl 'https://datetime-worker.your-subdomain.workers.dev/format?ts=2026-01-01T00:00:00Z'
```

---

## Related
- `workers-intl-message-format-kv-translations.md`
- `workers-currency-number-format-cf-country.md`
- `workers-multilingual-sitemap-xml-d1.md`

---

## Sources
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- MDN Intl.DateTimeFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- IANA Time Zone Database — https://www.iana.org/time-zones
- jose library — https://github.com/panva/jose
