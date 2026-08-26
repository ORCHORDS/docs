# Time Zone Detection and Conversion at the Edge with the Cloudflare cf Object

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You need to display dates and times in the user's local time zone without requiring JavaScript or a browser round-trip. Specific symptoms that bring teams here:

- Server-rendered HTML shows UTC timestamps; users see "3:00 AM" instead of "11:00 PM"
- A Next.js app on Cloudflare Pages cannot call `Intl.DateTimeFormat` with the correct time zone at SSR time because it doesn't know where the user is
- An email scheduling Worker must convert "9 AM user-local" to a UTC Unix timestamp before storing in D1
- A Cron Trigger Worker sends push notifications in the middle of the night for users in distant time zones

---

## Context

Cloudflare injects geolocation metadata into every Workers request via the `cf` object on `Request`. One of its properties is:

```typescript
request.cf.timezone // e.g. "America/New_York"
```

This is an IANA time zone identifier derived from the requester's IP address via MaxMind GeoIP. It is:

- **Available at no extra cost** in all Workers plans
- **Not always accurate** – VPNs, corporate proxies, and IPv6 addressing can shift the apparent location by 100–500 km
- **IANA-formatted** – directly usable with `Intl.DateTimeFormat` and the Temporal API
- **Absent on non-Cloudflare traffic** (e.g. `wrangler dev` local runs) – always code a fallback

The `cf` object also includes `cf.country`, `cf.region`, and `cf.city` which can supplement time zone inference.

---

## Reading cf.timezone Safely

```typescript
// src/utils/timezone.ts

const FALLBACK_TIMEZONE = 'UTC';

/**
 * Extract a valid IANA time zone from the Cloudflare cf object.
 * Returns the fallback if:
 *  - Running under wrangler dev (cf is absent or partial)
 *  - The cf.timezone value is not a recognized IANA identifier
 */
export function getTimezoneFromCf(request: Request): string {
  const cf = (request as Request & { cf?: CfProperties }).cf;
  const tz = cf?.timezone;

  if (!tz || typeof tz !== 'string') {
    return FALLBACK_TIMEZONE;
  }

  // Validate by attempting to construct an Intl.DateTimeFormat.
  // Invalid zone strings throw a RangeError.
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return tz;
  } catch {
    console.warn(`[i18n] Invalid timezone from cf: ${tz}`);
    return FALLBACK_TIMEZONE;
  }
}
```

### Type definition for CfProperties (Workers SDK)

```typescript
// Available from @cloudflare/workers-types
interface CfProperties {
  timezone?:   string;   // "America/Chicago"
  country?:    string;   // "US"
  region?:     string;   // "Texas"
  city?:       string;   // "Austin"
  latitude?:   string;   // "30.26715"
  longitude?:  string;   // "-97.74306"
  postalCode?: string;   // "78701"
  // ... other geo fields
}
```

---

## Formatting Dates at the Edge

Once you have the time zone, use `Intl.DateTimeFormat` to produce locale-aware formatted strings server-side:

```typescript
// src/utils/date-format.ts

export interface DateFormatOptions {
  locale:   string;  // BCP 47 locale, e.g. "fr-FR"
  timezone: string;  // IANA, e.g. "Europe/Paris"
}

/**
 * Format a UTC timestamp into a human-readable local date-time string.
 *
 * @param utcMs   - Unix timestamp in milliseconds (UTC)
 * @param options - locale and timezone
 */
export function formatLocalDateTime(utcMs: number, options: DateFormatOptions): string {
  return new Intl.DateTimeFormat(options.locale, {
    timeZone:     options.timezone,
    year:         'numeric',
    month:        'long',
    day:          'numeric',
    hour:         '2-digit',
    minute:       '2-digit',
    timeZoneName: 'short',
  }).format(new Date(utcMs));
}

/**
 * Format a relative time string, e.g. "3 hours ago" or "in 2 days".
 */
export function formatRelativeTime(
  utcMs: number,
  nowMs: number,
  locale: string
): string {
  const diffSeconds = (utcMs - nowMs) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

  const MINUTE = 60;
  const HOUR   = 3600;
  const DAY    = 86400;
  const WEEK   = 604800;

  const abs = Math.abs(diffSeconds);
  if (abs < MINUTE)  return rtf.format(Math.round(diffSeconds), 'second');
  if (abs < HOUR)    return rtf.format(Math.round(diffSeconds / MINUTE), 'minute');
  if (abs < DAY)     return rtf.format(Math.round(diffSeconds / HOUR), 'hour');
  if (abs < WEEK)    return rtf.format(Math.round(diffSeconds / DAY), 'day');
  return rtf.format(Math.round(diffSeconds / WEEK), 'week');
}
```

---

## Converting User-Local Time to UTC

When a user submits a form with a local date ("Schedule for 2026-09-01 09:00"), the Worker must convert to UTC before storing:

```typescript
// src/utils/local-to-utc.ts

/**
 * Convert a local date-time string ("2026-09-01T09:00") in a given IANA
 * time zone to a UTC Unix timestamp (ms).
 *
 * Strategy: use the Temporal API (Workers supports it as of 2025) for
 * unambiguous DST handling.  Falls back to a heuristic if Temporal is
 * unavailable.
 */
export function localToUtcMs(localDateTimeIso: string, timeZone: string): number {
  // Temporal.ZonedDateTime correctly handles DST gaps and folds.
  // "2026-03-08T02:30" in "America/New_York" is a DST gap – Temporal
  // advances it to 03:00 automatically (the "later" interpretation).
  const zdt = Temporal.PlainDateTime.from(localDateTimeIso)
    .toZonedDateTime(timeZone);

  return zdt.toInstant().epochMilliseconds;
}

/**
 * Convert a UTC ms timestamp back to a local ISO string for display.
 */
export function utcMsToLocalIso(utcMs: number, timeZone: string): string {
  const instant = Temporal.Instant.fromEpochMilliseconds(utcMs);
  return instant.toZonedDateTimeISO(timeZone).toString({
    smallestUnit: 'minute',
    offset:       'never',
  });
}
```

---

## Injecting Timezone into Server-Rendered HTML

Pass the detected time zone to the client via a `<meta>` tag or a data attribute so client-side hydration uses the same zone:

```typescript
// src/worker.ts

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const timezone = getTimezoneFromCf(request);
    const locale   = detectLocale(request);

    const upstream = await env.ASSETS.fetch(request);
    const html     = await upstream.text();

    // Inject into <head> so client-side JS can read it
    const patched  = html.replace(
      '<head>',
      `<head>\n<meta name="x-timezone" content="${timezone}">\n` +
      `<meta name="x-locale"   content="${locale}">`
    );

    return new Response(patched, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        // Pass tz in a response header for debugging / CDN awareness
        'X-Detected-Timezone': timezone,
      },
    });
  },
};
```

Client-side hydration:

```typescript
// Runs in the browser after SSR
const timezone = document.querySelector('meta[name="x-timezone"]')?.getAttribute('content')
  ?? Intl.DateTimeFormat().resolvedOptions().timeZone; // browser fallback
```

---

## Timezone Cookie: Trusting the Client Over IP

IP-based detection is imprecise. After the first page load, emit a JavaScript snippet that writes the browser's actual time zone to a cookie and reloads:

```html
<!-- Injected once if no __tz cookie exists -->
<script>
(function() {
  if (document.cookie.indexOf('__tz=') === -1) {
    var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    document.cookie = '__tz=' + encodeURIComponent(tz) +
      '; Max-Age=31536000; Path=/; SameSite=Lax; Secure';
    // Reload so the Worker picks up the accurate tz from the cookie
    location.reload();
  }
})();
</script>
```

In the Worker, prefer the cookie over the cf object:

```typescript
export function getEffectiveTimezone(request: Request): string {
  // 1. Client-set cookie (most accurate)
  const cookie = request.headers.get('Cookie') ?? '';
  const match  = cookie.match(/(?:^|;\s*)__tz=([^;]+)/);
  if (match) {
    const tz = decodeURIComponent(match[1]);
    try {
      Intl.DateTimeFormat(undefined, { timeZone: tz });
      return tz;
    } catch { /* ignore */ }
  }

  // 2. Cloudflare IP-based detection
  return getTimezoneFromCf(request);
}
```

---

## Working with DST-Sensitive Scheduling

```typescript
// src/scheduling/next-occurrence.ts

/**
 * Given a recurring rule "fire at HH:MM in user's timezone, on weekdays",
 * compute the next UTC ms after `afterUtcMs`.
 */
export function nextWeekdayOccurrence(
  hourLocal: number,
  minuteLocal: number,
  timeZone: string,
  afterUtcMs: number
): number {
  const afterInstant = Temporal.Instant.fromEpochMilliseconds(afterUtcMs);
  let zdt = afterInstant.toZonedDateTimeISO(timeZone);

  // Advance past the current candidate if it's already passed
  let candidate = zdt.with({ hour: hourLocal, minute: minuteLocal, second: 0 });
  if (Temporal.ZonedDateTime.compare(candidate, zdt) <= 0) {
    candidate = candidate.add({ days: 1 });
  }

  // Skip weekends (dayOfWeek: 6=Sat, 7=Sun in ISO weekday numbering)
  while (candidate.dayOfWeek >= 6) {
    candidate = candidate.add({ days: 1 });
  }

  return candidate.toInstant().epochMilliseconds;
}
```

---

## Time Zone in D1 Queries

D1 SQLite does not have a native TIMESTAMP WITH TIME ZONE type. Store all timestamps as INTEGER (Unix epoch seconds) in UTC and convert at the edge:

```typescript
// src/db/events.ts

export interface Event {
  id:         number;
  title:      string;
  starts_at:  number; // UTC epoch seconds stored in D1
}

export async function getUpcomingEventsLocal(
  db: D1Database,
  timezone: string,
  limit = 20
): Promise<Array<Event & { local_time: string }>> {
  const nowSeconds = Math.floor(Date.now() / 1000);

  const { results } = await db
    .prepare('SELECT id, title, starts_at FROM events WHERE starts_at > ? ORDER BY starts_at LIMIT ?')
    .bind(nowSeconds, limit)
    .all<Event>();

  // Convert each UTC timestamp to a local string at the edge
  return results.map((event) => ({
    ...event,
    local_time: formatLocalDateTime(event.starts_at * 1000, {
      locale:   'en',
      timezone,
    }),
  }));
}
```

---

## Anti-Patterns

- **Trusting `cf.timezone` unconditionally.** Users on VPNs, Tor, or corporate proxies will be assigned a wrong time zone. Always surface the cookie-based override mechanism.
- **Storing local times in D1.** Store UTC in D1, convert at the Worker layer. SQLite's date functions (`strftime`, `julianday`) do not support time zone conversion; any local-time storage becomes ambiguous during DST transitions.
- **Using `new Date()` arithmetic for DST.** `new Date('2026-11-01T01:30').getTime()` in a DST-observing zone is ambiguous (the clock goes back at 2:00 AM, making 1:30 occur twice). Use `Temporal.ZonedDateTime` for all local ↔ UTC conversion.
- **Sending `X-Detected-Timezone` as a CORS-unsafe header.** If your API is accessed cross-origin, add `X-Detected-Timezone` to `Access-Control-Expose-Headers`.
- **Reloading on every request** to sync the timezone cookie. Check for the cookie first; only reload if the cookie is absent.

---

## Gotchas

- **`cf.timezone` is absent in `wrangler dev`.** When running locally, `request.cf` is `undefined` (unless you enable `--cf` flag or provide a `cf.json`). Always guard with `cf?.timezone`.
- **Temporal is available in Workers but NOT in browsers before 2026.** Do not ship Temporal code to the client without a polyfill. On the Worker (V8 isolate) it is natively available.
- **IANA database version mismatch.** The V8 engine in Workers ships its own copy of the IANA tz database. When a country changes DST rules (e.g. Morocco in 2026), Workers may lag behind real-world changes by one release cycle. Track `v8::build::timezone_version` if your app is DST-sensitive.
- **`Intl.DateTimeFormat` resolves deprecated aliases.** `"US/Eastern"` becomes `"America/New_York"`. The `resolvedOptions().timeZone` property always returns the canonical name; use that for storage.
- **cf.timezone is a `string`, not typed in older Workers type packages.** Some `@cloudflare/workers-types` versions type `cf` as `IncomingRequestCfProperties` which lists `timezone` as `string | undefined`. Upgrade to `@cloudflare/workers-types@^4` for full typing.

---

## Verification

```bash
# Run locally with a mock cf object
cat > cf.json <<'EOF'
{ "timezone": "Asia/Tokyo", "country": "JP" }
EOF

wrangler dev --cf cf.json

curl http://localhost:8787/ -H 'Accept-Language: ja'
# Expect X-Detected-Timezone: Asia/Tokyo in response headers
```

Unit test:

```typescript
// test/timezone.test.ts
import { describe, it, expect } from 'vitest';
import { getTimezoneFromCf } from '../src/utils/timezone';

describe('getTimezoneFromCf', () => {
  it('returns the cf timezone when valid', () => {
    const req = new Request('https://example.com/', {
      cf: { timezone: 'Europe/Berlin' },
    } as RequestInit);
    expect(getTimezoneFromCf(req)).toBe('Europe/Berlin');
  });

  it('falls back to UTC when cf is absent', () => {
    const req = new Request('https://example.com/');
    expect(getTimezoneFromCf(req)).toBe('UTC');
  });

  it('falls back to UTC for an invalid timezone string', () => {
    const req = new Request('https://example.com/', {
      cf: { timezone: 'Mars/Olympus' },
    } as RequestInit);
    expect(getTimezoneFromCf(req)).toBe('UTC');
  });
});
```

---

## Related

- `timezone-iana-temporal-2026.md`
- `date-time-timezone-workers-edge-formatting.md`
- `dst-safe-scheduling-ui-2026.md`
- `locale-url-routing-workers-middleware.md`
- `cloudflare-workers-geolocation-locale-routing.md`

---

## Sources

- [Cloudflare Workers: Request.cf](https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties)
- [TC39 Temporal proposal](https://tc39.es/proposal-temporal/)
- [IANA Time Zone Database](https://www.iana.org/time-zones)
- [Intl.DateTimeFormat MDN](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
- [MaxMind GeoIP2 City](https://www.maxmind.com/en/geoip-demo)
