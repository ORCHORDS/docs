# Date/Time Formatting with `Intl.DateTimeFormat` in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your SSR Worker renders timestamps — order dates, last-seen times, event countdowns — and sends them as pre-formatted HTML strings. Client-side hydration then re-renders those strings using the browser's local timezone, causing a mismatch that React (or any VDOM framework) flags as a hydration error. You also need relative time strings like "3 hours ago" without shipping `date-fns` or `moment.js`.

---

## Context

Cloudflare Workers run in UTC by default; `new Date()` returns the current UTC time and `Date.prototype.toLocaleDateString()` called without explicit options uses the runtime's default locale, which is not the user's locale. The correct approach is to store the user's IANA timezone string (e.g. `America/New_York`) in KV or D1, then pass it as the `timeZone` option to `Intl.DateTimeFormat`. Server-side formatting with the user's timezone eliminates hydration mismatch because both the server and client produce the same string. `Intl.RelativeTimeFormat` covers relative strings; it requires you to compute the numeric delta and choose the correct unit (seconds, minutes, hours, days) before calling `format()`.

---

## Section 1 — User timezone storage in KV

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "USER_PREFS"
id      = "YOUR_KV_NAMESPACE_ID"

[vars]
DEFAULT_LOCALE   = "en-US"
DEFAULT_TIMEZONE = "UTC"
```

```typescript
// KV key pattern: user_prefs:<userId>
// Value shape:
// {
//   "locale":   "de-DE",
//   "timezone": "Europe/Berlin"
// }

// Write example (during account settings update):
// await env.USER_PREFS.put(
//   `user_prefs:${userId}`,
//   JSON.stringify({ locale: 'de-DE', timezone: 'Europe/Berlin' }),
//   { expirationTtl: 86400 * 30 }
// );
```

---

## Section 2 — Formatter utilities

```typescript
// src/i18n/datetime.ts

export interface UserDatePrefs {
  locale: string;
  timezone: string;
}

/**
 * Format an absolute Date as a locale- and timezone-aware string.
 * Safe for SSR: the output is deterministic given the same inputs.
 */
export function formatDate(
  date: Date,
  prefs: UserDatePrefs,
  options: Intl.DateTimeFormatOptions = {}
): string {
  const defaults: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: prefs.timezone,
  };
  return new Intl.DateTimeFormat(prefs.locale, { ...defaults, ...options }).format(date);
}

/**
 * Format a Date as a full datetime string with time, timezone-aware.
 */
export function formatDateTime(
  date: Date,
  prefs: UserDatePrefs
): string {
  return new Intl.DateTimeFormat(prefs.locale, {
    year:   'numeric',
    month:  'short',
    day:    'numeric',
    hour:   '2-digit',
    minute: '2-digit',
    timeZone: prefs.timezone,
  }).format(date);
}

/**
 * Produce a relative-time string such as "3 hours ago" or "in 2 days".
 * `Intl.RelativeTimeFormat` requires a numeric delta + unit.
 */
export function formatRelative(
  date: Date,
  now: Date,
  locale: string
): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const diffMs = date.getTime() - now.getTime();
  const absDiffMs = Math.abs(diffMs);

  // Pick the most appropriate unit.
  if (absDiffMs < 60_000) {
    return rtf.format(Math.round(diffMs / 1_000), 'second');
  } else if (absDiffMs < 3_600_000) {
    return rtf.format(Math.round(diffMs / 60_000), 'minute');
  } else if (absDiffMs < 86_400_000) {
    return rtf.format(Math.round(diffMs / 3_600_000), 'hour');
  } else if (absDiffMs < 2_592_000_000) {
    return rtf.format(Math.round(diffMs / 86_400_000), 'day');
  } else if (absDiffMs < 31_536_000_000) {
    return rtf.format(Math.round(diffMs / 2_592_000_000), 'month');
  } else {
    return rtf.format(Math.round(diffMs / 31_536_000_000), 'year');
  }
}

/**
 * Load user preferences from KV. Falls back to defaults.
 */
export async function loadUserDatePrefs(
  kv: KVNamespace,
  userId: string,
  defaults: UserDatePrefs = { locale: 'en-US', timezone: 'UTC' }
): Promise<UserDatePrefs> {
  const raw = await kv.get<UserDatePrefs>(`user_prefs:${userId}`, { type: 'json' });
  return raw ?? defaults;
}
```

---

## Section 3 — SSR Worker handler

```typescript
// src/index.ts
import { formatDate, formatDateTime, formatRelative, loadUserDatePrefs } from './i18n/datetime';

export interface Env {
  USER_PREFS: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const userId = url.searchParams.get('user') ?? 'anonymous';
    const tsRaw  = url.searchParams.get('ts');  // ISO 8601 timestamp

    const prefs = await loadUserDatePrefs(env.USER_PREFS, userId);
    const date  = tsRaw ? new Date(tsRaw) : new Date();
    const now   = new Date();

    if (isNaN(date.getTime())) {
      return Response.json({ error: 'invalid timestamp' }, { status: 400 });
    }

    // All three formatted strings are deterministic on the server.
    const short    = formatDate(date, prefs);
    const full     = formatDateTime(date, prefs);
    const relative = formatRelative(date, now, prefs.locale);

    const html = `<!doctype html>
<html lang="${prefs.locale}">
<head><meta charset="utf-8"><title>Date demo</title></head>
<body>
  <!-- These strings are safe to hydrate: same output server and client when
       the client reads the same prefs and calls the same Intl APIs. -->
  <p data-ssr="date">${short}</p>
  <p data-ssr="datetime">${full}</p>
  <p data-ssr="relative">${relative}</p>
</body>
</html>`;

    return new Response(html, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  },
};

// Example:
// user=de_user (locale=de-DE, timezone=Europe/Berlin), ts=2026-03-15T14:00:00Z
// short    → "15. März 2026"
// full     → "15. März 2026, 15:00"  (UTC+1 Berlin offset applied)
// relative → "vor 5 Monaten"         (relative to 2026-08-24)
```

---

## Anti-patterns

- **Calling `date.toLocaleDateString()` without `timeZone` option** — In Workers the runtime timezone is UTC; the output ignores the user's location entirely.
- **Sending UTC ISO strings and formatting on the client only** — This defers formatting to JavaScript evaluation, creating a flash of wrong content and a hydration mismatch on first render.
- **Shipping `moment-timezone` or `date-fns-tz`** — These add hundreds of KB to the Worker bundle. `Intl.DateTimeFormat` with the IANA `timeZone` option covers all the same cases at zero bundle cost.
- **Caching formatted strings in KV** — A cached string for `"yesterday"` becomes stale immediately. Cache raw timestamps; format them fresh per request.

---

## Gotchas

- `Intl.DateTimeFormat` in Workers requires a **valid IANA timezone string** for the `timeZone` option (e.g. `America/New_York`). Abbreviations like `EST` are not universally accepted and may throw `RangeError: invalid time zone` on some compatibility dates.
- `Intl.RelativeTimeFormat` with `numeric: 'auto'` produces `"yesterday"` and `"tomorrow"` for ±1 day in English, but the equivalent locale-appropriate words in other languages — test all supported locales.
- Workers do not expose `process.env.TZ`; setting it has no effect. The only way to control timezone output is through the `timeZone` option of `Intl.DateTimeFormat`.
- `new Date()` inside a Worker gives the actual current wall-clock UTC time, NOT a mocked value. In tests, inject `now` as a parameter rather than calling `new Date()` inside the formatter.
- The `hour12` option defaults differ by locale: `en-US` defaults to 12-hour, `de-DE` to 24-hour. Pass `hour12: false` explicitly if your design always requires 24-hour format.

---

## Verification

```bash
# Seed KV with a test user
npx wrangler kv:key put --binding=USER_PREFS 'user_prefs:de_user' \
  '{"locale":"de-DE","timezone":"Europe/Berlin"}' --local

npx wrangler kv:key put --binding=USER_PREFS 'user_prefs:jp_user' \
  '{"locale":"ja-JP","timezone":"Asia/Tokyo"}' --local

# Run dev server
npx wrangler dev

# Test German locale
curl 'http://localhost:8787/?user=de_user&ts=2026-03-15T14:00:00Z'
# Expect: "15. März 2026", "15. März 2026, 15:00"

# Test Japanese locale
curl 'http://localhost:8787/?user=jp_user&ts=2026-03-15T14:00:00Z'
# Expect: "2026年3月15日", time in JST (UTC+9 = 23:00)

# Test relative time
curl 'http://localhost:8787/?user=de_user&ts=2026-08-24T10:00:00Z'
# Expect relative: "heute" or "vor N Stunden" depending on current time
```

---

## Related

- `locale-negotiation-accept-language-workers.md`
- `currency-formatting-intl-numberformat-workers.md`

---

## Sources

- MDN Intl.DateTimeFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- MDN Intl.RelativeTimeFormat — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat
- IANA Time Zone Database — https://www.iana.org/time-zones
- Cloudflare Workers runtime — https://developers.cloudflare.com/workers/runtime-apis/
