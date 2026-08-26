# time-handling

**Issue:** Timezones, DST, ISO 8601, server time vs user time
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app shows "today" as the date. A user in Tokyo sees
"yesterday" because the server is in UTC. You store
"createdAt" as a Unix timestamp. The user wonders "when
exactly was this?" You want to show "2 hours ago" but the
timestamp is in the future.

## Root cause
**Time is hard.** Timezones, DST, and the difference
between "wall clock" and "elapsed time" cause bugs.

**Source:** IETF — Date and Time on the Internet:
https://datatracker.ietf.org/doc/html/rfc3339

> "Date and time formats cause confusion when not handled
> consistently."

## The "UTC everywhere" pattern

For storage, always use UTC:
```ts
const now = new Date();
const timestamp = now.toISOString();  // "2026-08-09T14:30:00.000Z"
```

For display, convert to the user's timezone:
```ts
const userTimezone = 'Asia/Tokyo';
const local = new Intl.DateTimeFormat(userTimezone, {
  dateStyle: 'long',
  timeStyle: 'short',
}).format(new Date(timestamp));
// "2026年8月9日 23:30"
```

## The "ISO 8601" format

For serialization, use ISO 8601:
- `2026-08-09T14:30:00.000Z` (UTC, milliseconds)
- `2026-08-09T14:30:00+09:00` (with timezone)
- `2026-08-09` (date only)
- `14:30:00` (time only)

```ts
// Server
const now = new Date();
const iso = now.toISOString();  // "2026-08-09T14:30:00.000Z"

// Client
const parsed = new Date(iso);  // Date object
```

The `Z` suffix means UTC. The `+09:00` is a timezone offset.

## The "Unix timestamp" format

For some uses (high-volume, time math), Unix timestamps:
```ts
const now = Date.now();  // 1723218600000 (ms since 1970)
const seconds = Math.floor(now / 1000);  // 1723218600
```

✅ **Pro:** No timezone issues
❌ **Con:** Not human-readable
❌ **Con:** Y2038 problem for 32-bit timestamps

For modern apps, ISO 8601 + millisecond precision is the
default.

## The "DST" gotcha

Daylight Saving Time changes the offset:
- New York: EST (UTC-5) in winter, EDT (UTC-4) in summer
- London: GMT (UTC+0) in winter, BST (UTC+1) in summer
- Tokyo: JST (UTC+9) all year (no DST)

For calculations, use a library:
```ts
import { DateTime } from 'luxon';

const dt = DateTime.now().setZone('America/New_York');
console.log(dt.toISO());  // With the correct offset
```

Don't try to handle DST manually; use a library.

## The "date math" pattern

For "2 days from now":
```ts
// ❌ Naive: doesn't account for DST
const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

// ✅ Correct: uses the calendar
const tomorrow = new Date(now);
tomorrow.setDate(tomorrow.getDate() + 1);
```

The naive version is wrong on DST transition days. The
calendar version is correct.

## The "elapsed time" pattern

For "2 hours ago":
```ts
function timeAgo(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const seconds = Math.floor((now - then) / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(timestamp).toLocaleDateString();
}
```

The "ago" is calculated from the server's current time
(usually UTC). For per-user "ago", the user may have a
different "now" than the server (timezone).

## The "server time vs user time" pattern

The server stores UTC. The client displays in the user's
timezone.

```ts
// Server
const createdAt = new Date().toISOString();
await db.insert({ ..., createdAt });

// Client
const createdAtLocal = new Date(createdAt).toLocaleString('en-US', { timeZone: userTimezone });
// "8/9/2026, 11:30:00 PM"
```

For "2 hours ago" on the client:
```ts
const now = new Date();
const created = new Date(createdAt);
const diff = (now - created) / 1000;  // seconds
const minutes = Math.floor(diff / 60);
const hours = Math.floor(minutes / 60);
const days = Math.floor(hours / 24);
```

## The "cron in the user's timezone" pattern

For "send this email at 9am in the user's timezone":
- The cron runs every hour
- The handler checks: is it 9am in the user's timezone?
- If yes, send

```ts
// Cron: every hour
async function sendDailyEmails(env: Env, ctx: ExecutionContext) {
  const users = await env.DB!.prepare(`
    SELECT id, email, timezone FROM users WHERE email_daily = 1
  `).all<User>();

  for (const user of users.results) {
    const localHour = new Date().toLocaleString('en-US', {
      hour: 'numeric',
      hour12: false,
      timeZone: user.timezone,
    });

    if (parseInt(localHour) === 9) {
      ctx.waitUntil(sendDailyEmail(user, env));
    }
  }
}
```

The cron is in UTC; the user sees the email at 9am their
time.

## The "date validation" pattern

For user input, validate the date:
```ts
import { z } from 'zod';

const DateSchema = z.string().refine((s) => !isNaN(Date.parse(s)), {
  message: 'Invalid date',
});
```

Reject dates that don't parse. Be lenient on format
("2026-08-09" vs "August 9, 2026" — use a parser).

## The "leap second" gotcha

Leap seconds are added occasionally. Most apps ignore them
(the time library handles it). For high-precision apps,
be aware.

## The "leap year" gotcha

Feb 29 exists every 4 years (except 100 years, except 400
years). The Date object handles it:
```ts
new Date(2024, 1, 29);  // Feb 29, 2024 (valid)
new Date(2025, 1, 29);  // Mar 1, 2025 (Feb doesn't have 29)
```

Don't do date math manually; use the Date object.

## The "library" choice

For most apps, **luxon** or **date-fns** is the right
choice. **moment.js** is in maintenance mode (don't use
for new code).

| Library | Size | Timezone | Mutability | Use |
|---|---|---|---|---|
| **Date** (built-in) | 0 | Limited | Mutable | Simple cases |
| **luxon** | 70k | ✅ | Immutable | Full-featured |
| **date-fns** | tree-shakeable | Limited | Immutable | Simple + modular |
| **dayjs** | 7k | Plugin | Immutable | Minimal |
| **Temporal** (proposal) | TBD | ✅ | Immutable | Future |

For most apps, **luxon** or **date-fns**.

## Verification
- **Test:** `test/time.test.ts > UTC conversion is correct` —
  passes
- **Test:** `test/time.test.ts > DST transition is handled
  correctly` — passes
- **Live:** Time displays are monitored
- **Audit:** Quarterly review of time handling

## Gotchas
- **The "Date is a footgun" anti-pattern.** The native
  Date has confusing APIs (getMonth is 0-indexed; getDate
  is 1-indexed; etc.). Use a library.
- **The "timezone is the user's responsibility" anti-
  pattern.** The user may have the wrong timezone. Have a
  "what's my timezone?" UI; let them correct.
- **The "no timezone in the timestamp" anti-pattern.**
  Always include the timezone in ISO 8601 (the `Z` for UTC
  or the offset).
- **The "Date math with milliseconds" anti-pattern.**
  `24 * 60 * 60 * 1000` is wrong on DST. Use a library.
- **The "date in the database" anti-pattern.** Store
  timestamps (ISO 8601), not "date" columns. Dates are
  ambiguous (whose date?).

## Related
- `i18n/date-and-number-formatting.md`
- `audit-log-as-product.md` (timestamps in audit log)
- `crontime-scheduling.md` (later)
- luxon: https://moment.github.io/luxon/
- date-fns: https://date-fns.org/
- RFC 3339: https://datatracker.ietf.org/doc/html/rfc3339
- IANA timezone DB: https://www.iana.org/time-zones
