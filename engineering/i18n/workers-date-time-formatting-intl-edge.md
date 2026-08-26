# Edge-Side Date and Time Formatting with Intl.DateTimeFormat in Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your multilingual application displays dates in a single hardcoded format (e.g., `2026-08-24`) regardless of the visitor's locale or timezone. Users in Tokyo see UTC timestamps while users in New York see ISO strings — neither is user-friendly. You need edge-side formatting that reflects each user's local calendar conventions, timezone, and language without round-tripping to an origin server.

---

## Context

Cloudflare Workers expose the incoming request's inferred timezone via `request.cf.timezone` (e.g., `"America/New_York"`, `"Asia/Tokyo"`). The V8 isolate running your Worker ships with full ICU data, meaning `Intl.DateTimeFormat`, `Intl.RelativeTimeFormat`, and calendar system extensions (Buddhist, Hebrew, Islamic) are available at zero extra bundle cost. Combined with KV for user-preference persistence, you can deliver correctly localised dates from the edge with sub-millisecond formatting overhead.

Key constraints:
- `request.cf.timezone` is a best-effort geo-IP inference; users can override it.
- Workers run in the UTC timezone by default; `timeZone` must be passed explicitly to `Intl.DateTimeFormat`.
- Cloudflare's ICU build includes the full CLDR locale dataset — no polyfills needed.
- `Intl.DateTimeFormat` instances are cheap to construct but can be reused across calls within the same isolate lifetime.

---

## Solution

### 1. Basic locale-aware date formatting

```typescript
// src/date-formatter.ts

export interface DateFormatOptions {
  locale: string;       // BCP 47 tag, e.g. "en-US", "de-DE", "th-TH-u-ca-buddhist"
  timeZone: string;     // IANA tz, e.g. "America/Chicago"
  style?: "full" | "long" | "medium" | "short";
}

export function formatDate(date: Date, opts: DateFormatOptions): string {
  const fmt = new Intl.DateTimeFormat(opts.locale, {
    dateStyle: opts.style ?? "long",
    timeZone: opts.timeZone,
  });
  return fmt.format(date);
}

export function formatDateTime(date: Date, opts: DateFormatOptions): string {
  const fmt = new Intl.DateTimeFormat(opts.locale, {
    dateStyle: opts.style ?? "medium",
    timeStyle: "short",
    timeZone: opts.timeZone,
  });
  return fmt.format(date);
}

// Usage examples:
// formatDate(new Date(), { locale: "en-US", timeZone: "America/New_York" })
//   => "August 24, 2026"
// formatDate(new Date(), { locale: "de-DE", timeZone: "Europe/Berlin" })
//   => "24. August 2026"
// formatDate(new Date(), { locale: "th-TH-u-ca-buddhist", timeZone: "Asia/Bangkok" })
//   => "24 สิงหาคม 2569"  (Buddhist year 2569)
```

### 2. Timezone detection from cf object

```typescript
// src/timezone-resolver.ts

const FALLBACK_TIMEZONE = "UTC";

export function resolveTimezone(
  cfTimezone: string | undefined,
  userPref: string | null
): string {
  // User-stored preference wins over geo-inferred
  if (userPref && isValidIANATimezone(userPref)) {
    return userPref;
  }
  if (cfTimezone && isValidIANATimezone(cfTimezone)) {
    return cfTimezone;
  }
  return FALLBACK_TIMEZONE;
}

function isValidIANATimezone(tz: string): boolean {
  try {
    // Intl.DateTimeFormat throws RangeError on unknown tz
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

// In your Worker fetch handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as CfProperties | undefined;
    const cfTimezone = cf?.timezone as string | undefined;

    // Load user's saved timezone from KV (see section 5)
    const userId = getUserIdFromCookie(request);
    const userPref = userId
      ? await env.USER_PREFS_KV.get(`tz:${userId}`)
      : null;

    const timezone = resolveTimezone(cfTimezone, userPref);
    const locale = resolveLocale(request); // from Accept-Language

    const now = new Date();
    const formatted = formatDateTime(now, { locale, timeZone: timezone });

    return new Response(JSON.stringify({ formatted, timezone, locale }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

### 3. Relative time formatting

```typescript
// src/relative-time.ts

type RelativeUnit =
  | "seconds" | "minutes" | "hours"
  | "days" | "weeks" | "months" | "years";

interface RelativeSegment {
  value: number;
  unit: RelativeUnit;
}

function getRelativeSegment(diffMs: number): RelativeSegment {
  const abs = Math.abs(diffMs);
  if (abs < 60_000)       return { value: Math.round(diffMs / 1000),     unit: "seconds" };
  if (abs < 3_600_000)    return { value: Math.round(diffMs / 60_000),   unit: "minutes" };
  if (abs < 86_400_000)   return { value: Math.round(diffMs / 3_600_000),unit: "hours"   };
  if (abs < 604_800_000)  return { value: Math.round(diffMs / 86_400_000),unit: "days"   };
  if (abs < 2_592_000_000)return { value: Math.round(diffMs / 604_800_000),unit: "weeks" };
  if (abs < 31_536_000_000)return { value: Math.round(diffMs/2_592_000_000),unit:"months"};
  return                           { value: Math.round(diffMs/31_536_000_000),unit:"years"};
}

export function formatRelative(date: Date, locale: string, now = new Date()): string {
  const diffMs = date.getTime() - now.getTime();
  const { value, unit } = getRelativeSegment(diffMs);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  return rtf.format(value, unit);
}

// Examples:
// formatRelative(new Date(Date.now() - 45000), "en-US")  => "45 seconds ago"
// formatRelative(new Date(Date.now() - 45000), "fr-FR")  => "il y a 45 secondes"
// formatRelative(new Date(Date.now() + 86400000), "ja")  => "明日"  (auto: "tomorrow")
```

### 4. Calendar system support

```typescript
// src/calendar-formats.ts

export type CalendarSystem =
  | "gregory"    // Gregorian (default)
  | "buddhist"   // Thai Buddhist (BE = CE + 543)
  | "hebrew"     // Hebrew lunisolar
  | "islamic"    // Islamic (calculated)
  | "islamic-civil"  // Islamic civil calendar
  | "persian"    // Persian/Solar Hijri
  | "japanese"   // Japanese imperial eras
  | "chinese"    // Chinese lunisolar
  | "roc";       // Republic of China calendar

// Build a locale tag that includes the calendar extension
function localeWithCalendar(baseLocale: string, calendar: CalendarSystem): string {
  const url = new URL(`https://x/${baseLocale}`);
  // BCP 47 extension: -u-ca-<calendar>
  return `${baseLocale}-u-ca-${calendar}`;
}

export function formatWithCalendar(
  date: Date,
  locale: string,
  calendar: CalendarSystem,
  timeZone: string
): string {
  const tag = localeWithCalendar(locale, calendar);
  const fmt = new Intl.DateTimeFormat(tag, {
    dateStyle: "long",
    timeZone,
  });
  return fmt.format(date);
}

// Detect which calendar to use based on locale
export function inferCalendar(locale: string): CalendarSystem {
  const lang = locale.split("-")[0].toLowerCase();
  const region = (locale.split("-")[1] ?? "").toUpperCase();
  if (lang === "th") return "buddhist";
  if (lang === "he") return "hebrew";
  if (["ar", "ur"].includes(lang)) return "islamic-civil";
  if (lang === "fa") return "persian";
  if (lang === "ja") return "japanese";
  return "gregory";
}

// Usage:
// const d = new Date("2026-08-24");
// formatWithCalendar(d, "th-TH", "buddhist", "Asia/Bangkok")  => "24 สิงหาคม 2569"
// formatWithCalendar(d, "he-IL", "hebrew", "Asia/Jerusalem")  => "כ׳ אב 5786"
// formatWithCalendar(d, "fa-IR", "persian", "Asia/Tehran")    => "۲ شهریور ۱۴۰۵"
```

### 5. KV-cached user timezone preference

```typescript
// src/timezone-pref.ts

export interface Env {
  USER_PREFS_KV: KVNamespace;
}

export async function getUserTimezone(
  env: Env,
  userId: string
): Promise<string | null> {
  return env.USER_PREFS_KV.get(`tz:${userId}`);
}

export async function setUserTimezone(
  env: Env,
  userId: string,
  timezone: string
): Promise<void> {
  if (!isValidIANATimezone(timezone)) {
    throw new RangeError(`Invalid timezone: ${timezone}`);
  }
  // Cache for 90 days; user can update anytime
  await env.USER_PREFS_KV.put(`tz:${userId}`, timezone, {
    expirationTtl: 90 * 24 * 60 * 60,
  });
}

// PATCH /api/preferences/timezone
export async function handleTimezoneUpdate(
  request: Request,
  env: Env,
  userId: string
): Promise<Response> {
  const body = await request.json<{ timezone: string }>();
  try {
    await setUserTimezone(env, userId, body.timezone);
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
}
```

### 6. Complete Worker entry point

```typescript
// src/index.ts
import { resolveTimezone } from "./timezone-resolver";
import { resolveLocale } from "./locale-resolver";   // see accept-language-negotiation article
import { formatDate, formatDateTime } from "./date-formatter";
import { formatRelative } from "./relative-time";
import { inferCalendar, formatWithCalendar } from "./calendar-formats";
import { getUserTimezone } from "./timezone-pref";

export interface Env {
  USER_PREFS_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/api/format/date") {
      return new Response("Not Found", { status: 404 });
    }

    const cf = request.cf as { timezone?: string } | undefined;
    const userId = getCookieValue(request, "uid");
    const userTz = userId ? await getUserTimezone(env, userId) : null;
    const timezone = resolveTimezone(cf?.timezone, userTz);
    const locale = resolveLocale(request);
    const calendar = inferCalendar(locale);

    const targetParam = url.searchParams.get("date");
    const target = targetParam ? new Date(targetParam) : new Date();

    const payload = {
      iso: target.toISOString(),
      formatted: formatDate(target, { locale, timeZone: timezone }),
      formatted_with_time: formatDateTime(target, { locale, timeZone: timezone }),
      relative: formatRelative(target, locale),
      calendar_aware: formatWithCalendar(target, locale, calendar, timezone),
      meta: { locale, timezone, calendar },
    };

    return new Response(JSON.stringify(payload, null, 2), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

function getCookieValue(request: Request, name: string): string | null {
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`) );
  return match ? decodeURIComponent(match[1]) : null;
}
```

---

## Implementation Details

- **ICU data in Workers**: Cloudflare Workers include full ICU (International Components for Unicode) data, so all CLDR locales and calendar systems work without bundling a polyfill like `full-icu`.
- **BCP 47 unicode extensions**: Calendar and numbering system extensions use the `-u-` subtag: `th-TH-u-ca-buddhist-nu-thai` for Thai digits in the Buddhist calendar.
- **Intl.DateTimeFormat parts**: Use `.formatToParts()` when you need to style individual date components differently (e.g., bold the year, dim the separators).
- **US vs EU date order**: `en-US` with `dateStyle: "short"` yields `8/24/26`; `en-GB` yields `24/08/26`. Never hand-roll date order logic — always delegate to `Intl`.
- **Numeric time zones**: `request.cf.timezone` is always an IANA string; it is never a numeric offset like `+05:30`. Validate with the try/catch guard before use.

---

## Anti-patterns

- **Hardcoding `new Date().toLocaleDateString()` without a `timeZone` option.** Workers run in UTC; omitting `timeZone` silently formats in UTC, not the user's local time.
- **Building date strings with string concatenation.** `month + "/" + day + "/" + year` produces wrong order for non-US locales.
- **Calling `new Intl.DateTimeFormat()` on every field render in a loop.** Construct the formatter once outside the loop and call `.format()` repeatedly.
- **Relying solely on `cf.timezone` without a fallback.** Cloudflare's geo-IP can be wrong (VPNs, corporate proxies). Always accept user overrides.
- **Storing dates as locale-formatted strings in D1.** Store UTC ISO 8601 in the database; format only at response time in the Worker.

---

## Gotchas

- **Buddhist calendar year offset**: `th-TH-u-ca-buddhist` adds 543 to the CE year. Storing a formatted Buddhist year as the canonical date in a database causes import failures.
- **`Intl.RelativeTimeFormat` with `numeric: "auto"`** will collapse small deltas: `"yesterday"`, `"tomorrow"`, `"now"` instead of `"1 day ago"`. Some UIs prefer explicit numeric strings — use `numeric: "always"` in those cases.
- **Hebrew calendar months**: The Hebrew calendar has a leap month (Adar I/II), so month indices are not fixed year-to-year. Never compute Hebrew dates manually.
- **`timeZone: "UTC"` vs omitting `timeZone`**: Both produce UTC output in Workers, but omitting the option makes intent ambiguous. Always be explicit.
- **DST gaps**: When formatting a date that falls in a DST gap (e.g., 2:30 AM during spring-forward), `Intl.DateTimeFormat` silently adjusts to the next valid wall-clock time. This is spec-compliant but can surprise.

---

## Verification

```typescript
// tests/date-formatter.test.ts
import { describe, it, expect } from "vitest";
import { formatDate, formatDateTime } from "../src/date-formatter";
import { formatRelative } from "../src/relative-time";
import { formatWithCalendar } from "../src/calendar-formats";

const EPOCH = new Date("2026-08-24T12:00:00Z");

describe("formatDate", () => {
  it("formats en-US long", () => {
    expect(formatDate(EPOCH, { locale: "en-US", timeZone: "America/New_York" }))
      .toBe("August 24, 2026");
  });

  it("formats de-DE long", () => {
    expect(formatDate(EPOCH, { locale: "de-DE", timeZone: "Europe/Berlin" }))
      .toBe("24. August 2026");
  });

  it("formats ja-JP", () => {
    expect(formatDate(EPOCH, { locale: "ja-JP", timeZone: "Asia/Tokyo" }))
      .toMatch(/2026年8月24日/);
  });
});

describe("formatWithCalendar", () => {
  it("outputs Buddhist year for th-TH", () => {
    const result = formatWithCalendar(EPOCH, "th-TH", "buddhist", "Asia/Bangkok");
    expect(result).toContain("2569");  // 2026 + 543
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-08-24T12:00:00Z");

  it("returns 'yesterday' in en-US with auto numeric", () => {
    const yesterday = new Date(now.getTime() - 86_400_000);
    expect(formatRelative(yesterday, "en-US", now)).toBe("yesterday");
  });

  it("returns 'tomorrow' in fr-FR", () => {
    const tomorrow = new Date(now.getTime() + 86_400_000);
    expect(formatRelative(tomorrow, "fr-FR", now)).toBe("demain");
  });
});
```

```bash
# Deploy and smoke-test
npx wrangler deploy
curl "https://your-worker.workers.dev/api/format/date?date=2026-08-24T12:00:00Z" \
  -H "Accept-Language: th-TH" \
  -H "Cookie: uid=user123"
```

---

## Related

- `documentation/categories/i18n/accept-language-negotiation.md`
- `documentation/categories/i18n/workers-intl-edge-locale.md`
- `documentation/categories/i18n/workers-number-unit-formatting-intl.md`
- `documentation/categories/i18n/workers-translation-fallback-chain-kv.md`

---

## Sources

- MDN: [Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)
- MDN: [Intl.RelativeTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/RelativeTimeFormat)
- Cloudflare Docs: [Request object — cf properties](https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties)
- CLDR: [Calendar Systems](https://cldr.unicode.org/development/development-process/design-proposals/calendar-formats)
- Cloudflare Docs: [Workers KV](https://developers.cloudflare.com/kv/)
- Unicode CLDR: [BCP 47 Unicode Locale Extensions](https://unicode.org/reports/tr35/#u_Extension)
