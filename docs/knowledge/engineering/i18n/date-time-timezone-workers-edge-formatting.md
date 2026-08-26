# Date-Time and Timezone Formatting in Cloudflare Workers at the Edge

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Event timestamps on example project show the wrong time for users whose device timezone differs
from UTC. The `CF-Timezone` request header is available in the Worker but ignored,
causing the static-export shell to render a UTC timestamp that the client later
corrects — producing a flash of wrong content (FOWC). Mobile browsers on iOS report
a timezone via JavaScript that disagrees with the value in `CF-Timezone` when a VPN is
active or when the user has manually overridden their device timezone.

## Context

example project (example.com) serves event listings and booking confirmations. Timestamps are
stored as UTC instants in D1 and must be displayed in the visitor's local timezone.
Because the Next.js export is static, the Worker handles `/api/events` and injects
the formatted timestamp into JSON. The Temporal API is available in Workers under the
`nodejs_compat_v2` flag and resolves many `Date` ambiguity pitfalls. Mobile timezone
detection has specific pitfalls that differ from desktop.

---

## Temporal API Availability at the Edge

Cloudflare Workers gained `Temporal` (TC39 Stage 3 → Stage 4 path) in runtime version
2024.6.1+ when `nodejs_compat_v2` is enabled in `wrangler.toml`.

```toml
# wrangler.toml
compatibility_flags = ["nodejs_compat_v2"]
compatibility_date  = "2024-09-23"
```

| API                            | Workers (compat v2) | Browser (2026) |
|--------------------------------|---------------------|----------------|
| `Temporal.Instant`             | yes                 | yes            |
| `Temporal.ZonedDateTime`       | yes                 | yes            |
| `Temporal.PlainDate`           | yes                 | yes            |
| `Intl.DateTimeFormat`          | yes (always)        | yes            |
| `Date` (legacy)                | yes (always)        | yes            |

Prefer `Temporal.Instant` for storage/comparison and `Temporal.ZonedDateTime` for
display. Never call `new Date()` with a timezone string — it ignores the tz argument.

```typescript
import { Temporal } from "@js-temporal/polyfill"; // falls back if native absent

export function instantToZoned(
  isoUtc: string,
  tz: string
): Temporal.ZonedDateTime {
  return Temporal.Instant.from(isoUtc).toZonedDateTimeISO(tz);
}
```

---

## CF-Timezone Header: Reading and Validating

Cloudflare injects `CF-Timezone` (an IANA timezone identifier) based on the visitor's
IP geolocation. It is present on all requests routed through the Cloudflare proxy and
is more reliable than inferring timezone from `CF-IPCountry`.

```typescript
export function getTimezone(request: Request): string {
  const cfTz = request.headers.get("CF-Timezone");
  if (cfTz && isValidIANA(cfTz)) return cfTz;
  return "UTC"; // safe fallback
}

// Validate without importing a full tz database
function isValidIANA(tz: string): boolean {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}
```

| Scenario                        | CF-Timezone value      | Reliability |
|---------------------------------|------------------------|-------------|
| Home broadband, no VPN          | Accurate city-level    | High        |
| Corporate proxy / VPN exit      | Proxy's exit region    | Low         |
| Mobile carrier NAT              | Carrier's PoP region   | Medium      |
| Tor / anonymising proxy         | CF may omit header     | Very low    |

When `CF-Timezone` is absent or invalid, fall back to `UTC` and let the client
correct via JavaScript after hydration.

---

## Mobile Timezone Detection vs. Server-Side

Mobile devices report timezone through two mechanisms that can conflict:

1. **Device system timezone** — set in OS settings, read by `Intl.DateTimeFormat().resolvedOptions().timeZone` in the browser.
2. **Network-inferred timezone** — what Cloudflare sees via IP geolocation.

A traveller in Tokyo whose phone OS is still set to `America/New_York` will trigger:
- `CF-Timezone: Asia/Tokyo` (IP-based)
- `Intl.DateTimeFormat().resolvedOptions().timeZone` → `America/New_York` (device)

| Source                        | Reflects user intent? | Notes                          |
|-------------------------------|-----------------------|--------------------------------|
| Device OS timezone            | Best                  | User explicitly chose this     |
| Browser JS `resolvedOptions`  | Best                  | Mirrors device OS              |
| CF-Timezone (IP)              | Approximate           | Correct for local SIM roaming  |
| Accept-Language subtag region | Weak signal           | Language ≠ current location    |

Recommended strategy: always prefer the client-side JS value. Pass it as a header or
cookie on subsequent API requests so the Worker can use it.

```typescript
// Client: pages/_app.tsx
useEffect(() => {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  document.cookie = `tz=${encodeURIComponent(tz)}; path=/; SameSite=Lax`;
}, []);

// Worker: read from cookie on API requests
export function getUserTimezone(request: Request): string {
  const cookie = request.headers.get("Cookie") ?? "";
  const match = cookie.match(/\btz=([^;]+)/);
  if (match) {
    const decoded = decodeURIComponent(match[1]);
    if (isValidIANA(decoded)) return decoded;
  }
  return getTimezone(request); // fall back to CF-Timezone
}
```

---

## Formatting Timestamps for JSON API Responses

The Worker formats timestamps before returning them so the static Next.js shell can
embed them in HTML without client JS re-rendering.

```typescript
export function formatEventTime(
  utcIso: string,
  locale: string,
  tz: string
): { display: string; iso: string; tz: string } {
  const zdt = instantToZoned(utcIso, tz);
  const display = new Intl.DateTimeFormat(locale, {
    timeZone: tz,
    dateStyle: "long",
    timeStyle: "short",
  }).format(new Date(zdt.epochMilliseconds));
  return { display, iso: zdt.toInstant().toString(), tz };
}
```

Example outputs for the same UTC instant `2026-09-01T18:00:00Z`:

| locale  | tz                 | display                         |
|---------|--------------------|---------------------------------|
| en-US   | America/New_York   | September 1, 2026 at 2:00 PM   |
| de-DE   | Europe/Berlin      | 1. September 2026 um 20:00      |
| ar-SA   | Asia/Riyadh        | ١ سبتمبر ٢٠٢٦ في ٩:٠٠ م       |
| ja-JP   | Asia/Tokyo         | 2026年9月2日 3:00               |

---

## Anti-patterns

- Using `new Date(isoString).toLocaleString(locale, { timeZone: tz })` directly in the
  Worker — works, but `Date` has ambiguity bugs with offset-naive strings.
- Storing `CF-Timezone` as the canonical user preference without a cookie/JS override
  path — breaks for VPN users and travellers.
- Using `moment-timezone` in a Worker — the tz data bundle is ~500 KB and bloats the
  Worker script; use native `Intl` or Temporal instead.
- Emitting pre-formatted timestamps into static HTML and skipping client hydration
  entirely — correct timezone requires runtime JS for accuracy across timezones.
- Caching formatted timestamp strings in KV without the timezone in the cache key —
  users in different timezones get each other's formatted strings.

---

## Gotchas

- `CF-Timezone` is not present when the Worker is invoked via a service binding or
  `wrangler dev --local` — always code a fallback.
- Temporal is still stage-gated in Workers; a missing `compatibility_flags` entry
  causes `ReferenceError: Temporal is not defined`.
- DST transitions: `Temporal.ZonedDateTime` handles ambiguous wall-clock times
  (clocks spring forward/back) via `disambiguation` option; `Date` silently picks the
  wrong one.
- iOS Safari 17 on some regions reports the IANA id with a legacy alias
  (`Asia/Calcutta` instead of `Asia/Kolkata`) — normalise with
  `Temporal.TimeZone.from(tz).id` before using.
- KV TTL for formatted date strings must account for DST changes; cache for no more
  than 1 hour around DST transition windows.

---

## Verification

```bash
# Test CF-Timezone injection with wrangler
curl -H "CF-Timezone: Europe/Berlin" \
     -H "Accept-Language: de-DE" \
     http://localhost:8787/api/events/1
# Expected: display field in German, Berlin time

# Confirm Temporal is available
npx wrangler dev --compatibility-flags nodejs_compat_v2
# In console: typeof Temporal !== "undefined"
```

```typescript
// vitest unit test
import { formatEventTime } from "../src/datetime";

it("converts UTC to Berlin time in German", () => {
  const result = formatEventTime("2026-09-01T18:00:00Z", "de-DE", "Europe/Berlin");
  expect(result.display).toContain("20:00");
  expect(result.tz).toBe("Europe/Berlin");
});
```

---

## Related

- `datetime-formatting-temporal-api-intl.md`
- `timezone-iana-temporal-2026.md`
- `dst-safe-scheduling-ui-2026.md`
- `cloudflare-workers-geolocation-locale-routing.md`
- `intl-api-workers-edge-formatting.md`

---

## Sources

- TC39 Temporal Proposal: https://tc39.es/proposal-temporal/
- Cloudflare Workers — Available Headers: https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- MDN Intl.DateTimeFormat: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- IANA Time Zone Database: https://www.iana.org/time-zones
- Cloudflare CF-Timezone header docs: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
