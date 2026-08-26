# Temporal API Date Formatting on Cloudflare Pages

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need reliable, timezone-aware date arithmetic and formatting across your React app and Cloudflare Workers edge functions without pulling in heavy libraries like `date-fns` or `luxon`. The legacy `Date` object produces silent bugs when crossing DST boundaries or when serializing across the edge/client boundary.

## Context
The TC39 Temporal API landed in V8 and is available in the Cloudflare Workers runtime (which tracks V8 closely) and in modern browsers as of 2025. It provides immutable, timezone-aware date/time objects with explicit calendar and timezone handling. On Cloudflare Pages you must polyfill Temporal for any SSR build target that uses an older Node.js engine; the edge runtime itself does not need one. The `@js-temporal/polyfill` package serves as the official reference implementation when the native global is absent.

## Detecting and Importing Temporal

Use a lazy import strategy so the polyfill is never loaded in runtimes that already expose the native `Temporal` global.

```typescript
// lib/temporal.ts
let TemporalNS: typeof Temporal;

async function getTemporalNS(): Promise<typeof Temporal> {
  if (typeof Temporal !== "undefined") {
    return Temporal;
  }
  // Polyfill only on runtimes missing the native global (e.g. older Node builds)
  const { Temporal: poly } = await import("@js-temporal/polyfill");
  TemporalNS = poly as unknown as typeof Temporal;
  return TemporalNS;
}

// Synchronous version safe to call after an initial await getTemporalNS()
export function getTemporalSync(): typeof Temporal {
  if (typeof Temporal !== "undefined") return Temporal;
  if (TemporalNS) return TemporalNS;
  throw new Error("Call await getTemporalNS() before getTemporalSync()");
}
```

## Working with PlainDate, ZonedDateTime, and Instant

```typescript
// lib/dates.ts
import { getTemporalNS } from "./temporal";

export async function buildEventSummary(
  isoString: string,
  userTimeZone: string
): Promise<{
  display: string;
  relative: string;
  isoLocal: string;
}> {
  const T = await getTemporalNS();

  // Parse the ISO 8601 string coming from a D1 / KV stored value
  const instant = T.Instant.from(isoString);

  // Convert to the user's local timezone
  const zdt = instant.toZonedDateTimeISO(userTimeZone);

  // Human-readable display using Intl.DateTimeFormat under the hood
  const display = zdt.toLocaleString("en-US", {
    dateStyle: "long",
    timeStyle: "short",
  });

  // Relative time (how many days until/since)
  const now = T.Now.zonedDateTimeISO(userTimeZone);
  const diffDays = now.until(zdt, { largestUnit: "days" }).days;
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const relative = rtf.format(diffDays, "day");

  // ISO string in local wall-clock terms (no Z suffix)
  const isoLocal = zdt.toPlainDateTime().toString();

  return { display, relative, isoLocal };
}

export async function addBusinessDays(
  startISO: string,
  days: number,
  timeZone: string
): Promise<string> {
  const T = await getTemporalNS();
  let date = T.PlainDate.from(startISO);
  let added = 0;

  while (added < days) {
    date = date.add({ days: 1 });
    const dow = date.dayOfWeek; // 1=Monday … 7=Sunday
    if (dow <= 5) added++;
  }

  // Return as a ZonedDateTime at noon in the target timezone to avoid
  // DST midnight ambiguities
  const zdt = date
    .toZonedDateTime({ timeZone, plainTime: T.PlainTime.from("12:00") });
  return zdt.toInstant().toString();
}
```

## Edge Worker: Accepting and Returning Temporal-Formatted Dates

```typescript
// workers/date-service.ts
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const tz = url.searchParams.get("tz") ?? "UTC";
    const iso = url.searchParams.get("date") ?? "";

    if (!iso) {
      return new Response(JSON.stringify({ error: "date param required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    try {
      // Cloudflare Workers runtime has native Temporal
      const instant = Temporal.Instant.from(iso);
      const zdt = instant.toZonedDateTimeISO(tz);

      const body = JSON.stringify({
        epochMilliseconds: Number(instant.epochMilliseconds),
        isoLocal: zdt.toPlainDateTime().toString(),
        timeZone: zdt.timeZoneId,
        offset: zdt.offset,
        weekday: zdt.dayOfWeek, // 1=Mon
        weekOfYear: zdt.weekOfYear,
      });

      return new Response(body, {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=60",
        },
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: String(err) }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
```

## React Component: Timezone-Aware Date Display

```tsx
// components/EventDate.tsx
import { useEffect, useState } from "react";
import { getTemporalNS } from "@/lib/temporal";

interface EventDateProps {
  isoString: string;
  userTimeZone?: string;
}

export function EventDate({
  isoString,
  userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
}: EventDateProps) {
  const [formatted, setFormatted] = useState<string>(isoString);
  const [relative, setRelative] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const T = await getTemporalNS();
      const instant = T.Instant.from(isoString);
      const zdt = instant.toZonedDateTimeISO(userTimeZone);

      const display = zdt.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      });

      const now = T.Now.zonedDateTimeISO(userTimeZone);
      const diff = now.until(zdt, { largestUnit: "hours" });
      const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
      const rel =
        Math.abs(diff.hours) >= 24
          ? rtf.format(Math.round(diff.hours / 24), "day")
          : rtf.format(diff.hours, "hour");

      if (!cancelled) {
        setFormatted(display);
        setRelative(rel);
      }
    })();
    return () => { cancelled = true; };
  }, [isoString, userTimeZone]);

  return (
    <time dateTime={isoString} title={isoString}>
      <span>{formatted}</span>
      {relative && <span aria-label="relative time"> ({relative})</span>}
    </time>
  );
}
```

## Serializing Temporal Objects Across the Network

Temporal objects are not JSON-serializable by default. Use `.toString()` to produce ISO 8601 strings and `Temporal.Instant.from()` or `Temporal.ZonedDateTime.from()` to reconstruct them.

```typescript
// lib/temporal-serialization.ts
export function serializeZDT(zdt: Temporal.ZonedDateTime): string {
  // Produces "2026-08-23T14:30:00+05:30[Asia/Kolkata]"
  return zdt.toString();
}

export function deserializeZDT(s: string): Temporal.ZonedDateTime {
  return Temporal.ZonedDateTime.from(s);
}

// For plain dates stored in D1 (TEXT column)
export function serializePlainDate(d: Temporal.PlainDate): string {
  return d.toString(); // "2026-08-23"
}

export function deserializePlainDate(s: string): Temporal.PlainDate {
  return Temporal.PlainDate.from(s);
}
```

## Anti-patterns

- **Using `new Date(isoString)` for timezone math** — `Date` has no concept of a named timezone; arithmetic around DST transitions silently produces wrong results. Use `Temporal.ZonedDateTime` instead.
- **Storing `ZonedDateTime.toString()` in JSON columns** — The bracketed timezone annotation (`[America/New_York]`) is not valid ISO 8601 and some parsers reject it. Store the Instant (`instant.toString()`) and timezone ID separately.
- **Importing the full polyfill unconditionally** — The `@js-temporal/polyfill` bundle is ~60 KB gzipped. Gate the import behind a runtime check to avoid shipping it to browsers that already have native Temporal.
- **Comparing across calendars without explicit conversion** — `PlainDate.compare()` throws when the two dates use different calendar systems. Normalize to ISO calendar first: `date.withCalendar("iso8601")`.
- **Assuming `Temporal.Now.timeZoneId()` matches the user's preference** — On the server/edge it always returns `"UTC"`. Pass the user's timezone from the browser (`Intl.DateTimeFormat().resolvedOptions().timeZone`) via a header or query param.

## Gotchas

- **Cloudflare Workers runtime freeze** — `Temporal.Now.instant()` reflects the real clock even after `Date.now()` is mocked; use `Date.now()` polyfills in tests and avoid asserting exact `Temporal.Now` values.
- **`weekOfYear` is calendar-dependent** — ISO week numbering differs from `en-US` locale weeks. `Temporal.PlainDate.weekOfYear` uses the ISO calendar (weeks start Monday). Use `Intl.DateTimeFormat` with `{ week: "numeric" }` for locale-aware week numbers.
- **Duration arithmetic is not commutative with months** — `date.add({ months: 1 }).add({ days: -1 })` is not the same as `date.add({ months: 1, days: -1 })` at month boundaries. Be explicit about order.
- **Cloudflare Pages SSR (Node 18 target)** — Node 18 does not include native Temporal; the polyfill must be bundled. Set `"skipLibCheck": true` in tsconfig when mixing the polyfill types with native types.
- **`toLocaleString` output differs between V8 versions** — Pin locale and options explicitly; do not rely on default formatting to be stable across Workers and browser runtime versions.

## Verification

1. Deploy a Worker using the date-service handler above and call it with a `?date=2026-03-08T06:00:00Z&tz=America/New_York` to verify the pre-DST transition hour.
2. Confirm the `offset` field changes from `-05:00` to `-04:00` on `2026-03-08T07:00:00Z` in the same timezone.
3. In a browser DevTools console: `typeof Temporal` should return `"object"` in Chrome 121+; the polyfill path is exercised in older browsers.
4. Run `addBusinessDays("2026-08-21", 3, "America/Chicago")` and assert the result skips the weekend correctly.
5. Verify JSON serialization round-trips: `Temporal.Instant.from(zdt.toInstant().toString()).epochMilliseconds === zdt.toInstant().epochMilliseconds`.

## Related

- `import-maps-esm-cloudflare-pages.md` — loading the polyfill via an import map
- `dark-mode-edge-cookie-cloudflare-pages.md` — pattern for reading user preferences (timezone) from edge cookies
- `edge-middleware-i18n-routing-cloudflare-pages.md` — propagating user locale and timezone through middleware

## Sources

- https://tc39.es/proposal-temporal/docs/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://github.com/js-temporal/temporal-polyfill
