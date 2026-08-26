# D1 Per-User Timezone Preferences and Locale-Aware Display in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application stores event timestamps in UTC in D1. Users in Tokyo, Berlin, and São Paulo all see `2026-08-23T14:00:00Z` instead of their local time. You need to: (1) store each user's preferred IANA timezone and locale in D1, (2) retrieve those preferences cheaply on every request via Workers, and (3) format timestamps server-side before returning JSON or HTML so the client never has to convert raw UTC.

## Context

Cloudflare Workers run in the edge datacenter closest to the user, but `Date` objects inside Workers always operate in UTC — there is no ambient local timezone. `Intl.DateTimeFormat` accepts a `timeZone` option that resolves any IANA tz identifier (e.g., `"Asia/Tokyo"`) against the V8-bundled IANA database. D1 is the natural store for per-user preferences because it supports SQL joins against user rows. A lightweight Workers middleware can hydrate `userLocale` and `userTimezone` into the request context on every authenticated call.

---

## D1 Schema

```sql
-- migrations/0001_user_preferences.sql
ALTER TABLE users ADD COLUMN locale TEXT NOT NULL DEFAULT 'en-US';
ALTER TABLE users ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC';
-- Keep an audit column so you can detect stale IANA names after a tzdata bump
ALTER TABLE users ADD COLUMN timezone_updated_at INTEGER;

-- Index for bulk timezone-aware reporting queries
CREATE INDEX idx_users_timezone ON users(timezone);
```

---

## Reading Preferences in Workers Middleware

```typescript
interface UserPrefs {
  locale: string;
  timezone: string;
}

// Cache prefs for the lifetime of the isolate (per-user, keyed by user_id)
const prefsCache = new Map<string, UserPrefs>();

export async function getUserPrefs(
  db: D1Database,
  userId: string
): Promise<UserPrefs> {
  if (prefsCache.has(userId)) return prefsCache.get(userId)!;

  const row = await db
    .prepare("SELECT locale, timezone FROM users WHERE id = ? LIMIT 1")
    .bind(userId)
    .first<UserPrefs>();

  const prefs: UserPrefs = row ?? { locale: "en-US", timezone: "UTC" };
  prefsCache.set(userId, prefs);
  return prefs;
}
```

---

## Locale-Aware Timestamp Formatting

```typescript
function formatTimestamp(
  isoUtc: string,
  locale: string,
  timezone: string
): string {
  // Validate the IANA name before using it — malformed names throw RangeError
  let tz = timezone;
  try {
    Intl.DateTimeFormat(locale, { timeZone: tz }).format(new Date());
  } catch {
    tz = "UTC"; // graceful fallback
  }

  return new Intl.DateTimeFormat(locale, {
    timeZone: tz,
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(isoUtc));
}

// Example output:
// formatTimestamp("2026-08-23T14:00:00Z", "ja-JP", "Asia/Tokyo")
// → "2026年8月23日 23:00 JST"

// formatTimestamp("2026-08-23T14:00:00Z", "de-DE", "Europe/Berlin")
// → "23. August 2026, 16:00 MESZ"
```

---

## Saving a Preference Update

```typescript
export async function updateTimezone(
  db: D1Database,
  userId: string,
  rawTz: string
): Promise<Response> {
  // Validate before persisting
  try {
    Intl.DateTimeFormat("en", { timeZone: rawTz });
  } catch {
    return Response.json({ error: "invalid_timezone" }, { status: 422 });
  }

  await db
    .prepare(
      "UPDATE users SET timezone = ?, timezone_updated_at = ? WHERE id = ?"
    )
    .bind(rawTz, Date.now(), userId)
    .run();

  prefsCache.delete(userId); // bust in-process cache
  return Response.json({ ok: true });
}
```

---

## Bulk UTC→Local Conversion for API Responses

When returning a list of events, format all timestamps server-side so the client receives ready-to-render strings:

```typescript
interface EventRow {
  id: string;
  title: string;
  starts_at: string; // stored as ISO 8601 UTC in D1
}

export async function listEvents(
  db: D1Database,
  userId: string,
  prefs: UserPrefs
): Promise<Response> {
  const { results } = await db
    .prepare("SELECT id, title, starts_at FROM events WHERE user_id = ? ORDER BY starts_at ASC LIMIT 50")
    .bind(userId)
    .all<EventRow>();

  const dtf = new Intl.DateTimeFormat(prefs.locale, {
    timeZone: prefs.timezone,
    dateStyle: "medium",
    timeStyle: "short",
  });

  const formatted = results.map((row) => ({
    ...row,
    starts_at_local: dtf.format(new Date(row.starts_at)),
  }));

  return Response.json(formatted);
}
```

---

## Anti-patterns

- **Storing timezone as a UTC offset** (`+09:00`): offsets do not model DST; always store the IANA tz name (`Asia/Tokyo`).
- **Formatting on the client in JavaScript after receiving UTC strings**: this couples the UI to timezone logic and breaks SSR HTML sent to users with JS disabled.
- **Using `toLocaleString()` on a `Date` without a locale argument**: it falls back to the runtime locale (UTC in Workers) producing wrong results.
- **Trusting user-supplied timezone strings without validation**: pass through `Intl.DateTimeFormat` to catch invalid names before writing to D1.

## Gotchas

- Workers' V8 IANA timezone database may lag IANA releases by several weeks. New zones or renamed aliases may throw `RangeError` on fully patched browsers but succeed in Workers (or vice-versa). Pin a test that enumerates `Intl.supportedValuesOf("timeZone")` in your CI pipeline.
- D1 TEXT columns store timezone names as-is; there is no IANA validation at the database layer. Validate in the application layer every time you write.
- The in-process `Map` cache is per-isolate and is evicted on cold starts. Do not rely on it for correctness — it is a latency optimisation only.
- `Intl.DateTimeFormat` with `timeZoneName: "short"` returns locale-specific abbreviations (`JST`, `MESZ`, `BRT`) that can be ambiguous. Prefer `timeZoneName: "longOffset"` (`GMT+09:00`) in machine-readable contexts.

## Verification

```bash
# Confirm D1 schema has timezone column
wrangler d1 execute <DB> --command "PRAGMA table_info(users);"

# Spot-check formatting
node -e "
  const dtf = new Intl.DateTimeFormat('ja-JP', { timeZone: 'Asia/Tokyo', dateStyle: 'full', timeStyle: 'long' });
  console.log(dtf.format(new Date('2026-08-23T14:00:00Z')));
"

# Integration test
npx vitest run tests/user-timezone-preferences.test.ts
```

## Related

- `d1-schema-locale-preferences-content-translations-2026.md`
- `date-time-timezone-workers-edge-formatting.md`
- `edge-timezone-detection-cf-object.md`
- `timezone-handling-intl.md`
- `temporal-api-polyfill-workers-edge-deployment-2026.md`

## Sources

- IANA Time Zone Database: https://www.iana.org/time-zones
- `Intl.DateTimeFormat` timeZone option: https://tc39.es/ecma402/#sec-intl.datetimeformat-intro
- Cloudflare D1 API: https://developers.cloudflare.com/d1/
- `Intl.supportedValuesOf`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/supportedValuesOf
