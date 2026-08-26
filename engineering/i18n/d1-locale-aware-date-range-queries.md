# Locale-Aware Date Range Queries in D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers API returns booking records filtered by a user-supplied date range.
Users in different locales interpret date boundaries differently: a Japanese user
querying "fiscal year 2025" means April 1 2025 – March 31 2026; a US user querying
"Q3 2025" means July 1 – September 30; an ISO week query from a European user anchors
weeks on Monday. Parsing user input naively with `new Date()` applies the Workers
runtime's UTC clock and ignores locale calendar conventions, producing off-by-one-day
errors and wrong fiscal quarter boundaries.

## Context

Cloudflare Workers run in UTC. D1 stores datetimes as ISO 8601 TEXT strings (SQLite has
no native DATETIME type). The correct approach is to resolve locale-specific date
boundaries in the Worker using `Intl` and the Temporal API polyfill, then pass UTC-
normalised ISO strings to D1 for range queries.

Applicable stack: Workers, D1, optional KV (user timezone preferences), Temporal API
(`@js-temporal/polyfill`).

---

## 1. Storing and Retrieving User Timezone from KV

```typescript
// src/lib/user-tz.ts
import type { KVNamespace } from '@cloudflare/workers-types';

const DEFAULT_TZ = 'UTC';

export async function getUserTimezone(
  kv: KVNamespace,
  userId: string,
): Promise<string> {
  const tz = await kv.get(`user:${userId}:timezone`);
  return tz ?? DEFAULT_TZ;
}

export async function setUserTimezone(
  kv: KVNamespace,
  userId: string,
  tz: string,
): Promise<void> {
  // Validate before storing — Intl throws on unknown time zone IDs
  Intl.DateTimeFormat(undefined, { timeZone: tz }); // throws if invalid
  await kv.put(`user:${userId}:timezone`, tz, { expirationTtl: 86400 * 30 });
}
```

---

## 2. Parsing Locale-Aware Date Boundaries with Temporal

```typescript
// src/lib/date-range.ts
import { Temporal } from '@js-temporal/polyfill';

export interface DateRange {
  startUtc: string; // ISO 8601, UTC, e.g. "2025-04-01T00:00:00Z"
  endUtc: string;   // exclusive upper bound
}

/**
 * Returns [start, end) in UTC for a named ISO calendar month.
 * Works for any locale whose Intl calendar maps to ISO months.
 */
export function isoMonthRange(
  year: number,
  month: number, // 1-based
  timeZone: string,
): DateRange {
  const start = Temporal.PlainDateTime.from({ year, month, day: 1, hour: 0 });
  const end = start.add({ months: 1 });

  return {
    startUtc: start.toZonedDateTime(timeZone).toInstant().toString(),
    endUtc: end.toZonedDateTime(timeZone).toInstant().toString(),
  };
}

/**
 * Japanese fiscal year: April 1 – March 31 of the next year.
 */
export function japanFiscalYearRange(
  fiscalYear: number, // e.g. 2025 means FY2025 = Apr 2025 – Mar 2026
  timeZone = 'Asia/Tokyo',
): DateRange {
  return isoMonthRange(fiscalYear, 4, timeZone); // reuse: start = Apr 1
  // Override end to be March 31 of next year
}

export function japanFiscalYear(
  fiscalYear: number,
  timeZone = 'Asia/Tokyo',
): DateRange {
  const start = Temporal.PlainDateTime.from({
    year: fiscalYear,
    month: 4,
    day: 1,
    hour: 0,
  });
  const end = Temporal.PlainDateTime.from({
    year: fiscalYear + 1,
    month: 4,
    day: 1,
    hour: 0,
  });
  return {
    startUtc: start.toZonedDateTime(timeZone).toInstant().toString(),
    endUtc: end.toZonedDateTime(timeZone).toInstant().toString(),
  };
}

/**
 * ISO week range (Monday–Sunday).
 * weekNumber is 1-based per ISO 8601.
 */
export function isoWeekRange(
  isoYear: number,
  isoWeek: number,
  timeZone: string,
): DateRange {
  // Temporal has native ISO week support
  const monday = Temporal.PlainDate.from({
    calendar: 'iso8601',
    year: isoYear,
    month: 1,
    day: 1,
  });
  // First ISO week: the week containing the first Thursday of the year
  // Temporal.PlainDate.from with weekOfYear is not yet standard;
  // compute manually via day-of-year offset.
  const jan4 = Temporal.PlainDate.from({ year: isoYear, month: 1, day: 4 });
  const jan4DayOfWeek = jan4.dayOfWeek; // 1=Mon
  const week1Monday = jan4.subtract({ days: jan4DayOfWeek - 1 });
  const weekMonday = week1Monday.add({ weeks: isoWeek - 1 });
  const weekSunday = weekMonday.add({ days: 7 });

  return {
    startUtc: weekMonday
      .toPlainDateTime({ hour: 0 })
      .toZonedDateTime(timeZone)
      .toInstant()
      .toString(),
    endUtc: weekSunday
      .toPlainDateTime({ hour: 0 })
      .toZonedDateTime(timeZone)
      .toInstant()
      .toString(),
  };
}
```

---

## 3. US Fiscal Quarter Boundaries

```typescript
// src/lib/date-range.ts (continued)

const US_FISCAL_QUARTERS: Record<number, { month: number }> = {
  1: { month: 1 }, // Q1: Jan–Mar
  2: { month: 4 }, // Q2: Apr–Jun
  3: { month: 7 }, // Q3: Jul–Sep
  4: { month: 10 }, // Q4: Oct–Dec
};

export function usFiscalQuarterRange(
  year: number,
  quarter: 1 | 2 | 3 | 4,
  timeZone = 'America/New_York',
): DateRange {
  const { month } = US_FISCAL_QUARTERS[quarter];
  const start = Temporal.PlainDateTime.from({ year, month, day: 1, hour: 0 });
  const end = start.add({ months: 3 });
  return {
    startUtc: start.toZonedDateTime(timeZone).toInstant().toString(),
    endUtc: end.toZonedDateTime(timeZone).toInstant().toString(),
  };
}
```

---

## 4. D1 Query with UTC Bounds

```typescript
// src/lib/bookings-repo.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { DateRange } from './date-range';

interface Booking {
  id: number;
  user_id: string;
  start_at: string;
  end_at: string;
  title: string;
}

export async function getBookingsInRange(
  db: D1Database,
  userId: string,
  range: DateRange,
): Promise<Booking[]> {
  // Store start_at / end_at as TEXT ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)
  // SQLite TEXT comparison on ISO 8601 strings is lexicographically correct
  // because the format is zero-padded and UTC-normalised.
  const rows = await db
    .prepare(
      `SELECT id, user_id, start_at, end_at, title
       FROM bookings
       WHERE user_id = ?
         AND start_at >= ?
         AND start_at < ?
       ORDER BY start_at ASC
       LIMIT 200`,
    )
    .bind(userId, range.startUtc, range.endUtc)
    .all<Booking>();

  return rows.results;
}
```

D1 schema:

```sql
CREATE TABLE bookings (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id   TEXT NOT NULL,
  start_at  TEXT NOT NULL, -- ISO 8601 UTC: "2025-04-01T00:00:00Z"
  end_at    TEXT NOT NULL,
  title     TEXT NOT NULL
);

CREATE INDEX idx_bookings_user_start ON bookings (user_id, start_at);
```

---

## 5. Formatting Query Results Back into the User's Locale

```typescript
// src/lib/format-date.ts

export function formatDateForLocale(
  isoUtcString: string,
  locale: string,
  timeZone: string,
): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(isoUtcString));
}
```

---

## 6. Worker Handler Tying It Together

```typescript
// src/routes/bookings.ts
import type { Env } from '../types';
import { getUserTimezone } from '../lib/user-tz';
import { japanFiscalYear, usFiscalQuarterRange, isoWeekRange } from '../lib/date-range';
import { getBookingsInRange } from '../lib/bookings-repo';
import { formatDateForLocale } from '../lib/format-date';

export async function handleBookingsQuery(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const userId = url.searchParams.get('userId') ?? '';
  const locale = url.searchParams.get('locale') ?? 'en-US';
  const mode = url.searchParams.get('mode') ?? 'month';

  const timeZone = await getUserTimezone(env.KV, userId);

  let range;
  if (mode === 'jp-fiscal') {
    const year = Number(url.searchParams.get('year') ?? new Date().getFullYear());
    range = japanFiscalYear(year);
  } else if (mode === 'us-quarter') {
    const year = Number(url.searchParams.get('year'));
    const q = Number(url.searchParams.get('quarter')) as 1 | 2 | 3 | 4;
    range = usFiscalQuarterRange(year, q, timeZone);
  } else if (mode === 'iso-week') {
    const year = Number(url.searchParams.get('year'));
    const week = Number(url.searchParams.get('week'));
    range = isoWeekRange(year, week, timeZone);
  } else {
    return new Response('Unknown mode', { status: 400 });
  }

  const bookings = await getBookingsInRange(env.DB, userId, range);

  const formatted = bookings.map((b) => ({
    ...b,
    start_at_local: formatDateForLocale(b.start_at, locale, timeZone),
    end_at_local: formatDateForLocale(b.end_at, locale, timeZone),
  }));

  return Response.json({ bookings: formatted });
}
```

---

## Anti-patterns

- **Parsing user date input with `new Date('2025-04-01')` in UTC** — "2025-04-01" without
  a timezone offset is parsed as midnight UTC, not midnight in the user's timezone.
  Always resolve via `Temporal.PlainDate` + user timezone.
- **Storing datetimes as Unix timestamps (INTEGER)** — loses human readability in D1
  explorer and requires `datetime(ts, 'unixepoch')` wrappers in every query.
- **Using `BETWEEN` for date ranges** — `BETWEEN` is inclusive on both ends; use
  `>= start AND < end` for exclusive upper bounds (avoids duplicating bookings that
  land exactly on a boundary).
- **Hardcoding fiscal year start months** — fiscal calendars vary by country and even
  by company. Externalize fiscal year configuration per locale or organization.
- **Assuming ISO week 1 always starts January 1** — ISO week 1 is the week containing
  the first Thursday, which can start in late December of the previous year.

## Gotchas

- SQLite TEXT comparison for ISO 8601 is lexicographically correct **only** when all
  values are UTC-normalised (ending in `Z`) and zero-padded. Mixed offsets (`+09:00` vs
  `Z`) will sort incorrectly.
- `@js-temporal/polyfill` adds ~50 KB (minified + gzipped). Use Workers `compatibility_date`
  `2024-09-23` or later to check if native Temporal is available:
  `typeof Temporal !== 'undefined'` before importing the polyfill.
- Japanese fiscal year commonly refers to the starting calendar year (FY2025 = starting
  April 2025). Confirm the convention with the client before encoding it.
- D1 `LIMIT 200` on range scans is a safety valve. Always paginate large date ranges
  using `start_at > ?` cursor queries rather than `OFFSET`.
- Cloudflare Workers do not set a local timezone. `new Date().toLocaleString()` without
  a `timeZone` option returns UTC.

## Verification

```typescript
// test/date-range.test.ts
import { japanFiscalYear, isoWeekRange, usFiscalQuarterRange } from '../src/lib/date-range';

describe('japanFiscalYear', () => {
  it('starts April 1 JST in UTC', () => {
    const { startUtc } = japanFiscalYear(2025);
    // April 1 00:00 JST = March 31 15:00 UTC
    expect(startUtc).toBe('2025-03-31T15:00:00Z');
  });
});

describe('isoWeekRange', () => {
  it('ISO week 1 of 2025 starts Monday Dec 30 2024', () => {
    const { startUtc } = isoWeekRange(2025, 1, 'UTC');
    expect(startUtc).toMatch(/^2024-12-30/);
  });
});

describe('usFiscalQuarterRange', () => {
  it('Q3 starts July 1', () => {
    const { startUtc } = usFiscalQuarterRange(2025, 3, 'UTC');
    expect(startUtc).toMatch(/^2025-07-01/);
  });
});
```

## Related

- `d1-schema-locale-preferences-content-translations-2026.md`
- `date-time-timezone-workers-edge-formatting.md`
- `temporal-api-polyfill-workers-edge-deployment-2026.md`
- `timezone-iana-temporal-2026.md`

## Sources

- SQLite date/time functions: https://www.sqlite.org/lang_datefunc.html
- Temporal API (TC39): https://tc39.es/proposal-temporal/
- @js-temporal/polyfill: https://github.com/js-temporal/temporal-polyfill
- Cloudflare D1: https://developers.cloudflare.com/d1/
- ISO 8601 week date: https://www.iso.org/iso-8601-date-and-time-format.html
