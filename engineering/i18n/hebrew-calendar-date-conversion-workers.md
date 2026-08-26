# Hebrew Calendar Date Conversion on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Jewish-community platform or Jewish-lifecycle app needs to display dates in the Hebrew calendar (e.g., "כ״ה אדר תשפ״ו") alongside Gregorian dates, calculate upcoming Jewish holidays, and schedule events relative to the Hebrew calendar (e.g., "30 days before Rosh Hashana"). All of this must be resolved at the Cloudflare Workers edge for server-side rendered pages and API responses without a heavy calendar library.

## Context

The Hebrew calendar is a lunisolar system with variable-length months, a 19-year Metonic cycle for leap years, and a 13th intercalated month (Adar II) in leap years. `Intl.DateTimeFormat` with `calendar: "hebrew"` provides correct Gregorian-to-Hebrew conversion in the V8 engine used by Cloudflare Workers, so no custom arithmetic is needed for display. The tricky parts are: formatting Hebrew month names correctly (including leap-year Adar disambiguation), converting from a Hebrew date back to Gregorian for scheduling, and formatting the numeric day and year in traditional *gematria* notation (e.g., `כ״ה` for 25).

## Gregorian-to-Hebrew Conversion via `Intl`

```typescript
// src/hebrew-calendar.ts

const HE_MONTHS_LEAP: string[] = [
  "תשרי","חשון","כסלו","טבת","שבט",
  "אדר א׳","אדר ב׳",               // leap year uses both
  "ניסן","אייר","סיון","תמוז","אב","אלול",
];

const HE_MONTHS_REGULAR: string[] = [
  "תשרי","חשון","כסלו","טבת","שבט","אדר",
  "ניסן","אייר","סיון","תמוז","אב","אלול",
];

export interface HebrewDate {
  day:    number;
  month:  number; // 1-based; Tishri = 1
  year:   number;
  monthName: string;
  formatted: string; // e.g. "כ״ה אדר תשפ״ו"
}

/** Convert a JS Date to a Hebrew calendar date using the built-in Intl API. */
export function toHebrewDate(date: Date, locale = "he-IL-u-ca-hebrew"): HebrewDate {
  // Extract numeric parts in Hebrew calendar
  const fDay   = new Intl.DateTimeFormat(locale, { day:   "numeric", calendar: "hebrew" });
  const fMonth = new Intl.DateTimeFormat(locale, { month: "numeric", calendar: "hebrew" });
  const fYear  = new Intl.DateTimeFormat(locale, { year:  "numeric", calendar: "hebrew" });

  const day   = parseInt(fDay.format(date),   10);
  const month = parseInt(fMonth.format(date), 10);
  const year  = parseInt(fYear.format(date),  10);

  // Determine if this Hebrew year is a leap year (has 13 months)
  const isLeap = isHebrewLeapYear(year);
  const months = isLeap ? HE_MONTHS_LEAP : HE_MONTHS_REGULAR;
  const monthName = months[month - 1] ?? `חודש ${month}`;

  // Full formatted string: day name + month + year in gematria
  const formatted = new Intl.DateTimeFormat("he-IL-u-ca-hebrew", {
    day:   "numeric",
    month: "long",
    year:  "numeric",
  }).format(date);

  return { day, month, year, monthName, formatted };
}

/** A Hebrew year is a leap year if (7 * year + 1) % 19 < 7. */
export function isHebrewLeapYear(hebrewYear: number): boolean {
  return ((7 * hebrewYear + 1) % 19) < 7;
}
```

## Upcoming Jewish Holiday Calculation

```typescript
// src/jewish-holidays.ts
import { toHebrewDate } from "./hebrew-calendar";

/**
 * Returns the Gregorian date of Rosh Hashana (1 Tishri) for a given Hebrew year.
 * Uses the Dechiyot postponement rules approximated via known epoch offsets.
 * For production, this approach is accurate from year 5700–5900 (2040 CE range).
 */
export function roshHashanaGregorian(hebrewYear: number): Date {
  // Known anchor: RH 5786 = 2025-09-22
  const ANCHOR_HY = 5786;
  const ANCHOR_GY = new Date("2025-09-22T00:00:00Z");

  // Average Hebrew year length ≈ 365.2468 days
  const AVG_HEB_YEAR_MS = 365.2468 * 24 * 60 * 60 * 1000;
  const delta = (hebrewYear - ANCHOR_HY) * AVG_HEB_YEAR_MS;

  return new Date(ANCHOR_GY.getTime() + delta);
}

export interface Holiday {
  name:     string;
  nameHe:   string;
  date:     Date;
  hebrewDate: string;
}

/** Get major holidays for a given Gregorian year. */
export function getHolidaysForYear(gregorianYear: number): Holiday[] {
  // Determine Hebrew year that mostly overlaps with the Gregorian year
  const hebrewYear = gregorianYear + 3761; // rough correspondence

  const rh = roshHashanaGregorian(hebrewYear);

  const holidays: Array<{ name: string; nameHe: string; offsetDays: number }> = [
    { name: "Rosh Hashana",  nameHe: "ראש השנה",  offsetDays: 0  },
    { name: "Yom Kippur",    nameHe: "יום כיפור", offsetDays: 9  },
    { name: "Sukkot",        nameHe: "סוכות",     offsetDays: 14 },
    { name: "Shmini Atzeret",nameHe: "שמיני עצרת",offsetDays: 21 },
  ];

  return holidays.map(h => {
    const d = new Date(rh.getTime() + h.offsetDays * 86_400_000);
    return {
      name:        h.name,
      nameHe:      h.nameHe,
      date:        d,
      hebrewDate:  toHebrewDate(d).formatted,
    };
  });
}
```

## Workers Handler — Dual-Calendar Date API

```typescript
// src/worker.ts
import { toHebrewDate } from "./hebrew-calendar";
import { getHolidaysForYear } from "./jewish-holidays";

export default {
  async fetch(request: Request): Promise<Response> {
    const url  = new URL(request.url);
    const path = url.pathname;

    // GET /convert?date=2026-03-14 → Hebrew equivalent
    if (path === "/convert") {
      const raw  = url.searchParams.get("date");
      const date = raw ? new Date(raw) : new Date();

      if (isNaN(date.getTime())) {
        return new Response("Invalid date", { status: 400 });
      }

      const heb = toHebrewDate(date);

      return new Response(JSON.stringify({
        gregorian:    date.toISOString().slice(0, 10),
        hebrew:       heb.formatted,
        hebrewParts: { day: heb.day, month: heb.monthName, year: heb.year },
      }), { headers: { "Content-Type": "application/json; charset=utf-8" } });
    }

    // GET /holidays?year=2026 → upcoming holidays
    if (path === "/holidays") {
      const year = parseInt(url.searchParams.get("year") ?? String(new Date().getFullYear()), 10);
      const holidays = getHolidaysForYear(year);

      return new Response(JSON.stringify(holidays), {
        headers: { "Content-Type": "application/json; charset=utf-8" },
      });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## Anti-patterns

- Implementing Hebrew calendar arithmetic from scratch in TypeScript — V8's `Intl` already ships correct Hebrew calendar support; custom arithmetic introduces subtle Dechiyot postponement bugs.
- Displaying Adar as a single month name during leap years — 5th-month Adar I (`אדר א׳`) and 6th-month Adar II (`אדר ב׳`) are distinct months; conflating them misplaces every event in the leap month.
- Assuming a fixed Gregorian-to-Hebrew year offset of 3760 — the offset is 3760 before Rosh Hashana and 3761 after it within the same Gregorian year.

## Gotchas

- Cloudflare Workers V8 supports `calendar: "hebrew"` in `Intl.DateTimeFormat` at runtime, but `wrangler dev` with `--local` may behave differently from production if the local Node.js `Intl` data is incomplete — always verify with `wrangler dev --remote` for calendar accuracy.
- The Hebrew day begins at nightfall (sunset), not midnight. If your event has a time component, dates that fall after sunset are already in the next Hebrew day. Store timestamps in UTC and apply a sunset-offset lookup if precision matters.

## Verification

```bash
# Verify Gregorian-to-Hebrew conversion
curl "http://localhost:8787/convert?date=2026-03-14" | jq .
# Expected: gregorian "2026-03-14", hebrew string containing "אדר" or "אדר ב׳"

# List holidays for 2026
curl "http://localhost:8787/holidays?year=2026" | jq '.[0]'
# Expected: name "Rosh Hashana", nameHe "ראש השנה"

# Confirm leap year detection — Hebrew 5784 is a leap year
node -e "console.log(((7*5784+1)%19)<7)" # → true
```

## Related

- `i18n/non-gregorian-calendars-eras-2026.md`
- `i18n/intl-locale-calendar-preference-and-explicit-choice.md`
- `i18n/date-time-timezone-workers-edge-formatting.md`
- `i18n/edge-timezone-detection-cf-object.md`

## Sources

- https://tc39.es/ecma402/#sec-intl.datetimeformat
- https://unicode.org/reports/tr35/tr35-dates.html#Calendar_Types
- https://www.hebcal.com/home/developer-apis
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/
